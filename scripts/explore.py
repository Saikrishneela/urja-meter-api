import os
import requests
import time
from collections import Counter

BASE = "https://urja-ops.flockenergy.tech"


def login():
    session = requests.Session()
    response = session.post(
        BASE + "/login",
        data={  # login
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
            params={"q": "", "page": page},  # crawl function
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
