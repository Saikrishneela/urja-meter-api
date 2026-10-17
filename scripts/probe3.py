import os
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


def span(rows):
    return (rows[0]["timestamp"], rows[-1]["timestamp"]) if rows else None


print("--- where does the data start? (cap or real start?)")
rows = c.energy("J100002", end="2026-06-03")
print("to=2026-06-03 ->", len(rows), span(rows))

print("--- reading interval for every meter")
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

print(Counter(profile.values()))
for kind in set(profile.values()):
    ids = sorted(i for i, p in profile.items() if p == kind)
    print(kind, len(ids), "first", ids[0], "last", ids[-1])
for field in ("phaseType", "installStatus"):
    print(field, Counter((m[field], profile[m["meterId"]]) for m in meters))

daily = next((i for i, p in profile.items() if p[1] == (1440,)), None)
if daily:
    rows = c.energy(daily, "2026-01-01", "2026-12-31")
    print("full range for daily meter", daily, len(rows), span(rows))

print("429 responses handled:", c.rate_limited, c.last_rate_limit_headers)
