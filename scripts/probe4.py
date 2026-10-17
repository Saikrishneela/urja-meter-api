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


def show_headers(r):
    return {k: v for k, v in r.headers.items() if k.lower() != "set-cookie"}


print("--- is the limit still active after a fresh login?")
probe_path = "/portal/meters/J100098/energy"
r = raw(probe_path)
print(r.status_code, show_headers(r))
print(r.text[:200])

print("--- how long until it recovers? (polls every 10 s, up to 5 min)")
start = time.monotonic()
while r.status_code == 429 and time.monotonic() - start < 300:
    time.sleep(10)
    r = raw(probe_path)
    print(round(time.monotonic() - start), "s ->", r.status_code)

print("--- reading interval, every 8th meter")
meters = c.meters()
profile = {}
for m in meters[::8]:
    meter_id = m["meterId"]
    r = raw(f"/portal/meters/{meter_id}/energy")
    if r.status_code == 429:
        print("429 after", len(profile), "meters", show_headers(r))
        break
    rows = r.json()["data"]
    try:
        stamps = [datetime.strptime(x["timestamp"], "%d/%m/%Y %H:%M") for x in rows]
    except (ValueError, KeyError):
        profile[meter_id] = (len(rows), ("unparseable",))
        continue
    steps = {int((b - a).total_seconds() // 60) for a, b in zip(stamps, stamps[1:])}
    profile[meter_id] = (len(rows), tuple(sorted(steps)))
    time.sleep(0.25)

print("sampled:", len(profile))
print(Counter(profile.values()))
for kind in set(profile.values()):
    ids = sorted(i for i, p in profile.items() if p == kind)
    print(kind, len(ids), "first", ids[0], "last", ids[-1])
for field in ("phaseType", "installStatus"):
    print(
        field,
        Counter(
            (m[field], profile[m["meterId"]]) for m in meters if m["meterId"] in profile
        ),
    )
