import os
import time
from collections import Counter
from datetime import datetime

from dotenv import load_dotenv

from app.portal_client import PortalClient

load_dotenv()
c = PortalClient(
    "https://urja-ops.flockenergy.tech",
    os.environ["URJA_EMAIL"],
    os.environ["URJA_PASSWORD"],
)
c.login()


def raw(path, **params):
    return c._session.get(c.base_url + path, params=params, timeout=15)


def span(rows):
    return (rows[0]["timestamp"], rows[-1]["timestamp"]) if rows else None


print("--- missing meter page, full body")
print(raw("/meters/J999999/__data.json", **{"x-sveltekit-invalidated": "001"}).text)

print("--- energy date range on J100002")
cases = [
    {"from": "2026-06-25", "to": "2026-06-27"},
    {"from": "2026-06-25"},
    {"to": "2026-06-27"},
    {"from": "2026-01-01", "to": "2026-06-30"},
    {"from": "2025-01-01", "to": "2026-12-31"},
    {"from": "25/06/2026", "to": "27/06/2026"},
    {"from": "2026-06-27", "to": "2026-06-25"},
    {"from": "not-a-date"},
]
for params in cases:
    r = raw("/portal/meters/J100002/energy", **params)
    try:
        rows = r.json()["data"]
        print(params, r.status_code, len(rows), span(rows))
    except (ValueError, KeyError):
        print(params, r.status_code, r.text[:150])

print("--- search matching")
for q in ("J1000", "j100005", "100005", "SE339", "se33962"):
    b = raw("/portal/meters/search", q=q, page=1).json()
    print(repr(q), "total", b["total"], [m["meterId"] for m in b["data"][:3]])

print("--- reading interval for every meter (about a minute)")
meters = c.meters()
profile = {}
for m in meters:
    rows = c.energy(m["meterId"])
    try:
        stamps = [datetime.strptime(r["timestamp"], "%d/%m/%Y %H:%M") for r in rows]
    except (ValueError, KeyError):
        profile[m["meterId"]] = (len(rows), ("unparseable",))
        continue
    steps = {int((b - a).total_seconds() // 60) for a, b in zip(stamps, stamps[1:])}
    profile[m["meterId"]] = (len(rows), tuple(sorted(steps)))
    time.sleep(0.1)

print(Counter(profile.values()))
for kind in set(profile.values()):
    ids = sorted(i for i, p in profile.items() if p == kind)
    print(kind, len(ids), "first", ids[0], "last", ids[-1])
for field in ("phaseType", "installStatus"):
    print(field, Counter((m[field], profile[m["meterId"]]) for m in meters))
