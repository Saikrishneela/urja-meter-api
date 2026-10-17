import os

from dotenv import load_dotenv

from app.portal_client import PortalClient

load_dotenv()
client = PortalClient(
    "https://urja-ops.flockenergy.tech",
    os.environ["URJA_EMAIL"],
    os.environ["URJA_PASSWORD"],
)

print("meters:", len(client.meters()))
print("dts:", len(client.dts()))
print("geo:", client.geo("J100002"))
print("energy rows:", len(client.energy("J100002")))
print("page:", client.meter_page("J100004")["detail"]["Serial No"])

# Simulate an expired session: the next call should log in again by itself.
client._session.cookies.clear()
print("after expiry:", len(client.energy("J100002")), "rows")
