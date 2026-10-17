import json
import os
import re
import time
from collections import Counter
from pathlib import Path

import requests
from dotenv import load_dotenv

from app.decoder import parse_meter_page

load_dotenv()

BASE = "https://urja-ops.flockenergy.tech"
CACHE = Path("data/hierarchies.json")
LEVELS = ["Zone", "Circle", "Division", "Subdivision", "Sub Station", "Feeder", "DT"]
LABEL = re.compile(r"^(.*) \(([^)]+)\)$")


def login():
    session = requests.Session()
    response = session.post(
        BASE + "/login",
        data={
            "email": os.environ["URJA_EMAIL"],
            "password": os.environ["URJA_PASSWORD"],
        },
        headers={"Origin": BASE},
    )
    print("Status:", response.status_code)
    print("Body:", response.text)
    return session


def fetch_all_meters(session):
    meters = []
    page = 1
    while True:
        r = session.get(
            BASE + "/portal/meters/search",
            params={"q": "", "page": page},
        )
        r.raise_for_status()
        body = r.json()
        rows = body["data"]
        if not rows:
            break
        meters.extend(rows)
        if len(meters) >= body["total"]:
            break
        page += 1
        time.sleep(0.2)
    return meters


def check_meters(meters):
    ids = [m["meterId"] for m in meters]
    print("rows:", len(ids))
    print("distinct ids:", len(set(ids)))

    dts = {m.get("dtCode") for m in meters}
    print("distinct dtCodes:", len(dts))
    expected_dts = {f"DT-{n:03d}" for n in range(1, 41)}
    print("dtCodes outside DT-001..040:", sorted(map(str, dts - expected_dts)))

    expected_ids = {f"J{100000 + n}" for n in range(403)}
    print("missing ids:", sorted(expected_ids - set(ids)))
    print("unexpected ids:", sorted(set(ids) - expected_ids))


def profile_meters(meters):
    for field in ("make", "phaseType", "installStatus"):
        print(field, dict(Counter(m.get(field) for m in meters)))

    blanks = [m["meterId"] for m in meters if any(v in (None, "") for v in m.values())]
    print("meters with empty fields:", blanks)

    per_dt = Counter(m["dtCode"] for m in meters)
    print("meters per DT, min/max:", min(per_dt.values()), max(per_dt.values()))
    print("busiest DTs:", per_dt.most_common(3))


def fetch_all_dts(session):
    dts = []
    page = 1
    while True:
        r = session.get(BASE + "/portal/dts", params={"page": page})
        r.raise_for_status()
        body = r.json()
        if not body["data"]:
            break
        dts.extend(body["data"])
        if len(dts) >= body["total"]:
            break
        page += 1
        time.sleep(0.2)
    return dts


def fetch_all_hierarchies(session, meters):
    results = {}
    failures = {}
    for m in meters:
        meter_id = m["meterId"]
        r = session.get(
            BASE + f"/meters/{meter_id}/__data.json",
            params={"x-sveltekit-invalidated": "001"},
        )
        r.raise_for_status()
        try:
            results[meter_id] = parse_meter_page(r.json())
        except (KeyError, TypeError, IndexError, ValueError) as exc:
            failures[meter_id] = {"error": repr(exc), "raw": r.text[:1500]}
        time.sleep(0.2)

    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(results, indent=2))
    Path("data/failures.json").write_text(json.dumps(failures, indent=2))

    print("parsed:", len(results), "failed:", len(failures))
    print("failed meters:", sorted(failures))
    for meter_id in sorted(failures)[:2]:
        print("---", meter_id, failures[meter_id]["error"])
        print(failures[meter_id]["raw"])
    return results


def split_label(label):
    """'Vaishali DT 3 (DT-003)' -> ('Vaishali DT 3', 'DT-003')"""
    match = LABEL.match(label or "")
    return (match.group(1), match.group(2)) if match else (label, None)


def check_hierarchies(meters, dts, pages):
    dt_feeder = {d["code"]: d["feederCode"] for d in dts}
    chains = {}
    problems = Counter()

    for m in meters:
        page = pages[m["meterId"]]
        codes = []
        for level in LEVELS:
            label = page["hierarchy"].get(level)
            _, code = split_label(label)
            if code is None:
                problems[f"missing or unparseable {level}"] += 1
                print("  ", m["meterId"], level, repr(label))
            codes.append(code)

        if codes[-1] != m["dtCode"]:
            problems["DT differs from list"] += 1
            print("  ", m["meterId"], "list says", m["dtCode"], "page says", codes[-1])
        if codes[-2] != dt_feeder.get(m["dtCode"]):
            problems["feeder differs from /portal/dts"] += 1

        chains.setdefault(m["dtCode"], set()).add(tuple(codes[:-1]))

        d = page["detail"]
        from_page = (
            d.get("Serial No"),
            d.get("Make"),
            d.get("Phase Type"),
            d.get("Installation Status"),
        )
        from_list = (m["serialNo"], m["make"], m["phaseType"], m["installStatus"])
        if from_page != from_list:
            problems["detail differs from list"] += 1

    print("problems:", dict(problems))
    for dt, found in chains.items():
        if len(found) > 1:
            print("DT with more than one upper chain:", dt, found)
    print(
        "installation types:",
        dict(Counter(p["detail"].get("Installation Type") for p in pages.values())),
    )


def build_dt_chains(meters, pages):
    """For each DT and level, collect the codes seen across its meters."""
    seen = {}
    for m in meters:
        hierarchy = pages[m["meterId"]]["hierarchy"]
        for level in LEVELS:
            _, code = split_label(hierarchy.get(level))
            if code:
                seen.setdefault(m["dtCode"], {}).setdefault(level, set()).add(code)
    return seen


def report_chains(meters, seen):
    conflicts = [
        (dt, level, codes)
        for dt, levels in seen.items()
        for level, codes in levels.items()
        if len(codes) > 1
    ]
    print("conflicting levels:", conflicts)

    all_dts = {m["dtCode"] for m in meters}
    never_seen = [
        (dt, level)
        for dt in sorted(all_dts)
        for level in LEVELS
        if level not in seen.get(dt, {})
    ]
    print("levels never seen for a DT:", never_seen)


if __name__ == "__main__":
    s = login()
    meters = fetch_all_meters(s)
    check_meters(meters)
    profile_meters(meters)

    dts = fetch_all_dts(s)
    print("DTs fetched:", len(dts), "distinct codes:", len({d["code"] for d in dts}))
    print("feeders:", len({d["feederCode"] for d in dts}))
    print("capacities:", dict(Counter(d["capacityKva"] for d in dts)))

    past_end = s.get(BASE + "/portal/meters/search", params={"q": "", "page": 22})
    print("meters page 22:", past_end.status_code, past_end.text[:150])
    past_end = s.get(BASE + "/portal/dts", params={"page": 3})
    print("dts page 3:", past_end.status_code, past_end.text[:150])

    anon = requests.Session()
    r2 = anon.get(BASE + "/portal/meters/search", params={"q": "", "page": 1})
    print("No-login status:", r2.status_code)
    print("No-login body:", r2.text[:200])

    if CACHE.exists():
        pages = json.loads(CACHE.read_text())
    else:
        pages = fetch_all_hierarchies(s, meters)

    good_meters = [m for m in meters if m["meterId"] in pages]
    print("checking", len(good_meters), "of", len(meters), "meters")
    check_hierarchies(good_meters, dts, pages)
    seen = build_dt_chains(good_meters, pages)
    report_chains(good_meters, seen)
