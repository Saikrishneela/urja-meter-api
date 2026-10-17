import time

import requests

from app.decoder import PageError, parse_meter_page


class PortalError(Exception):
    """The portal could not be reached or returned something unusable."""


class AuthError(PortalError):
    """Login failed, or the session could not be renewed."""


class NotFoundError(PortalError):
    """The portal has no such meter."""


def _retry_delay(response, attempt):
    """Seconds to wait before retrying: the portal's Retry-After if it sends one."""
    try:
        return min(float(response.headers.get("Retry-After")), 30.0)
    except (TypeError, ValueError):
        return 1.0 * 2**attempt


class PortalClient:
    def __init__(
        self, base_url, email, password, timeout=15, retries=5, min_interval=0.25
    ):
        self.base_url = base_url.rstrip("/")
        self._email = email
        self._password = password
        self.timeout = timeout
        self.retries = retries
        self.min_interval = min_interval
        self._last_request = 0.0
        self._session = requests.Session()
        self._logged_in = False
        self.rate_limited = 0
        self.last_rate_limit_headers = {}

    def login(self):
        self._session.cookies.clear()
        r = self._session.post(
            self.base_url + "/login",
            data={"email": self._email, "password": self._password},
            headers={"Origin": self.base_url},
            timeout=self.timeout,
        )
        has_cookie = any("session_token" in c.name for c in self._session.cookies)
        if r.status_code != 200 or not has_cookie:
            raise AuthError(f"login failed: HTTP {r.status_code}")
        self._logged_in = True

    def _throttle(self):
        wait = self._last_request + self.min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def _get(self, path, **params):
        if not self._logged_in:
            self.login()
        relogged = False
        last_error = None
        for attempt in range(self.retries):
            self._throttle()
            try:
                r = self._session.get(
                    self.base_url + path, params=params, timeout=self.timeout
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_error = exc
                time.sleep(0.5 * 2**attempt)
                continue
            if r.status_code == 401:
                if relogged:
                    raise AuthError("still unauthorized after logging in again")
                self.login()
                relogged = True
                continue
            if r.status_code == 404:
                raise NotFoundError(f"not found: {path}")
            if r.status_code == 429:
                self.rate_limited += 1
                self.last_rate_limit_headers = {
                    k: v
                    for k, v in r.headers.items()
                    if k.lower().startswith(("retry-after", "x-ratelimit"))
                }
                last_error = PortalError(f"rate limited on {path}")
                time.sleep(_retry_delay(r, attempt))
                continue
            if r.status_code >= 500:
                last_error = PortalError(f"HTTP {r.status_code} from {path}")
                time.sleep(0.5 * 2**attempt)
                continue
            if r.status_code >= 400:
                raise PortalError(f"HTTP {r.status_code} from {path}")
            return r
        raise PortalError(f"giving up on {path}: {last_error}")

    def _paginate(self, path, **params):
        rows, page = [], 1
        while True:
            body = self._get(path, page=page, **params).json()
            if not body["data"]:
                break
            rows.extend(body["data"])
            if len(rows) >= body["total"]:
                break
            page += 1
        return rows

    def meters(self):
        return self._paginate("/portal/meters/search", q="")

    def dts(self):
        return self._paginate("/portal/dts")

    def energy(self, meter_id, start=None, end=None):
        params = {}
        if start:
            params["from"] = start
        if end:
            params["to"] = end
        return self._get(f"/portal/meters/{meter_id}/energy", **params).json()["data"]

    def geo(self, meter_id):
        return self._get(f"/portal/meters/{meter_id}/geo").json()["data"]

    def meter_page(self, meter_id):
        r = self._get(
            f"/meters/{meter_id}/__data.json",
            **{"x-sveltekit-invalidated": "001"},
        )
        try:
            return parse_meter_page(r.json())
        except PageError as exc:
            raise NotFoundError(f"no page data for {meter_id}: {exc}") from exc
