import pytest

from app import portal_client
from app.portal_client import NotFoundError, PortalClient, PortalError


class FakeResponse:
    def __init__(self, status, payload=None, headers=None):
        self.status_code = status
        self._payload = payload or {}
        self.headers = headers or {}

    def json(self):
        return self._payload


def make_client(responses):
    client = PortalClient("http://portal", "e", "p", min_interval=0)
    client._logged_in = True
    queue = list(responses)
    client._session.get = lambda *args, **kwargs: queue.pop(0)
    return client


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(portal_client.time, "sleep", lambda s: None)


def test_retries_after_429_then_succeeds():
    client = make_client(
        [
            FakeResponse(429, headers={"Retry-After": "1"}),
            FakeResponse(200, {"data": [1]}),
        ]
    )
    assert client.geo("J1") == [1]
    assert client.rate_limited == 1
    assert client.last_rate_limit_headers == {"Retry-After": "1"}


def test_gives_up_after_repeated_429():
    client = make_client([FakeResponse(429)] * 5)
    with pytest.raises(PortalError):
        client.geo("J1")


def test_404_raises_not_found():
    client = make_client([FakeResponse(404)])
    with pytest.raises(NotFoundError):
        client.geo("J999999")
