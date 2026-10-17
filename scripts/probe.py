import os
from datetime import datetime

from dotenv import load_dotenv

from app.portal_client import PortalClient

load_dotenv()
BASE = "https://urja-ops.flockenergy.tech"
c = PortalClient(BASE, os.environ["URJA_EMAIL"], os.environ["URJA_PASSWORD"])
c.login()


def raw(path, **params):
    return c._session.get(c.base_url + path, params=params, timeout=15)


print("--- unknown meter")
for path in (
    "/portal/meters/J999999/energy",
    "/portal/meters/J999999/geo",
    "/meters/J999999/__data.json",
):
    r = raw(path)
    print(path, r.status_code, r.text[:150])

print("--- search q")
for q in ("Genus", "genus", "J100005", "DT-021", "SE33962", "L&T", "zzz"):
    b = raw("/portal/meters/search", q=q, page=1).json()
    print(repr(q), "total", b["total"], [m["meterId"] for m in b["data"][:3]])

print("--- pageSize")
b = raw("/portal/meters/search", q="", page=1, pageSize=100).json()
print("pageSize=100 ->", len(b["data"]), "rows, pageSize field", b["pageSize"])

print("--- energy params (does anything change the 337 rows?)")
for params in ({"days": 3}, {"from": "2026-06-25", "to": "2026-06-27"}, {"page": 2}):
    r = raw("/portal/meters/J100002/energy", **params)
    print(params, r.status_code, len(r.json().get("data", [])))


def check_energy(meter_id):
    rows = c.energy(meter_id)
    if not rows:
        print(meter_id, "no rows")
        return
    try:
        ts = [datetime.strptime(r["timestamp"], "%d/%m/%Y %H:%M") for r in rows]
        kwh = [float(r["kwh"]) for r in rows]
    except (ValueError, KeyError) as exc:
        print(meter_id, "unparseable row:", repr(exc))
        return
    gaps = sum(1 for a, b in zip(ts, ts[1:]) if (b - a).total_seconds() != 1800)
    drops = sum(1 for a, b in zip(kwh, kwh[1:]) if b < a)
    print(
        meter_id,
        "rows",
        len(rows),
        rows[0]["timestamp"],
        "->",
        rows[-1]["timestamp"],
        "gaps",
        gaps,
        "kwh drops",
        drops,
        "keys",
        sorted(rows[0]),
    )


print("--- energy health (J100000 decommissioned, J100004 faulty, J100005 three-phase)")
for meter_id in ("J100000", "J100001", "J100004", "J100005", "J100200", "J100402"):
    check_energy(meter_id)

print("--- geo sample (every 10th meter)")
bad = []
for m in c.meters()[::10]:
    r = raw(f"/portal/meters/{m['meterId']}/geo")
    try:
        g = r.json()["data"]
        float(g["latitude"]), float(g["longitude"])
    except (ValueError, KeyError, TypeError):
        bad.append((m["meterId"], r.status_code, r.text[:100]))
print("odd geo responses:", bad)
