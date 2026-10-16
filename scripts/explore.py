import os
import requests

BASE = "https://urja-ops.flockenergy.tech"


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


if __name__ == "__main__":
    s = login()
    r = s.get(BASE + "/portal/meters/search?q=&page=1")
    print("Search Status:", r.status_code)
    body = r.json()
    print("total:", body["total"])
    print("page:", body["page"])
    print("rows:", len(body["data"]))

    anon = requests.Session()
    r2 = anon.get(BASE + "/portal/meters/search?q=&page=1")
    print("No-login status:", r2.status_code)
    print("No-login body:", r2.text[:200])
