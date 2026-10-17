import threading
import time
from collections import Counter

from app.models import (
    EnergySeries,
    Location,
    MeterDetail,
    MeterPage,
    MeterSummary,
    Transformer,
    TransformerDetail,
)
from app.portal_client import NotFoundError, PortalClient, PortalError
from app.transform import (
    LEVELS,
    build_hierarchy,
    build_series,
    has_gaps,
    merge_chains,
)

_MISSING = object()


class TTLCache:
    def __init__(self, ttl, maxsize=512):
        self._ttl = ttl
        self._maxsize = maxsize
        self._items = {}

    def get(self, key):
        entry = self._items.get(key)
        if entry is None:
            return _MISSING
        expires, value = entry
        if time.monotonic() > expires:
            del self._items[key]
            return _MISSING
        return value

    def set(self, key, value):
        if len(self._items) >= self._maxsize:
            self._items.pop(next(iter(self._items)))
        self._items[key] = (time.monotonic() + self._ttl, value)


def _to_summary(row):
    return MeterSummary(
        meter_id=row["meterId"],
        serial_no=row["serialNo"],
        make=row["make"],
        phase_type=row["phaseType"],
        install_status=row["installStatus"],
        dt_code=row["dtCode"],
    )


class MeterService:
    def __init__(self, client: PortalClient, ttl: float = 900):
        self._client = client
        self._cache = TTLCache(ttl)
        # One portal call at a time: the portal rate-limits, and the client is not thread-safe.
        self._lock = threading.RLock()

    def _cached(self, key, loader):
        hit = self._cache.get(key)
        if hit is not _MISSING:
            return hit
        with self._lock:
            hit = self._cache.get(key)
            if hit is not _MISSING:
                return hit
            value = loader()
            self._cache.set(key, value)
            return value

    def _index(self):
        def load():
            try:
                return {
                    m.meter_id: m
                    for m in (_to_summary(r) for r in self._client.meters())
                }
            except KeyError as exc:
                raise PortalError(f"unexpected meter list shape: {exc}") from exc

        return self._cached("meters", load)

    def _dts(self):
        return self._cached("dts", self._client.dts)

    def _summary(self, meter_id):
        try:
            return self._index()[meter_id]
        except KeyError:
            raise NotFoundError(f"meter {meter_id} not found") from None

    def _page(self, meter_id):
        return self._cached(
            ("page", meter_id), lambda: self._client.meter_page(meter_id)
        )

    def _dt_chain(self, dt_code):
        """Upper hierarchy of a DT, merged from its meters' pages."""

        def load():
            collected = []
            for m in self._index().values():
                if m.dt_code != dt_code:
                    continue
                try:
                    collected.append(self._page(m.meter_id)["hierarchy"])
                except NotFoundError:
                    continue
                if len(merge_chains(collected)) == len(LEVELS):
                    break
            return merge_chains(collected)

        return self._cached(("chain", dt_code), load)

    def _location(self, meter_id):
        try:
            geo = self._client.geo(meter_id)
        except NotFoundError:
            return None
        try:
            return Location(
                latitude=float(geo["latitude"]), longitude=float(geo["longitude"])
            )
        except (KeyError, TypeError, ValueError):
            return None

    def search(
        self,
        q=None,
        make=None,
        status=None,
        phase_type=None,
        dt_code=None,
        limit=50,
        offset=0,
    ):
        items = list(self._index().values())
        if q:
            needle = q.casefold()
            items = [
                m
                for m in items
                if needle in m.meter_id.casefold() or needle in m.serial_no.casefold()
            ]
        if make:
            items = [m for m in items if m.make.casefold() == make.casefold()]
        if status:
            items = [m for m in items if m.install_status == status]
        if phase_type:
            items = [m for m in items if m.phase_type == phase_type]
        if dt_code:
            items = [m for m in items if m.dt_code.casefold() == dt_code.casefold()]
        return MeterPage(
            items=items[offset : offset + limit],
            total=len(items),
            limit=limit,
            offset=offset,
        )

    def meter(self, meter_id):
        summary = self._summary(meter_id)

        def load():
            page = self._page(meter_id)
            raw = page["hierarchy"]
            fallback = self._dt_chain(summary.dt_code) if has_gaps(raw) else None
            return MeterDetail(
                **summary.model_dump(),
                installation_type=page["detail"].get("Installation Type"),
                hierarchy=build_hierarchy(raw, fallback),
                location=self._location(meter_id),
            )

        return self._cached(("detail", meter_id), load)

    def location(self, meter_id):
        self._summary(meter_id)
        return self._cached(("geo", meter_id), lambda: self._location(meter_id))

    def energy(self, meter_id, start=None, end=None):
        self._summary(meter_id)

        def load():
            rows = self._client.energy(meter_id, start, end)
            try:
                return EnergySeries(**build_series(meter_id, rows))
            except (KeyError, ValueError) as exc:
                raise PortalError(
                    f"unexpected energy data for {meter_id}: {exc}"
                ) from exc

        return self._cached(("energy", meter_id, start, end), load)

    def _to_transformer(self, raw, counts):
        return Transformer(
            code=raw["code"],
            name=raw["name"],
            feeder_code=raw["feederCode"],
            capacity_kva=raw["capacityKva"],
            meter_count=counts.get(raw["code"], 0),
        )

    def transformers(self):
        counts = Counter(m.dt_code for m in self._index().values())
        return [self._to_transformer(d, counts) for d in self._dts()]

    def transformer(self, code):
        counts = Counter(m.dt_code for m in self._index().values())
        for raw in self._dts():
            if raw["code"].casefold() == code.casefold():
                base = self._to_transformer(raw, counts)
                ids = [
                    m.meter_id for m in self._index().values() if m.dt_code == base.code
                ]
                return TransformerDetail(**base.model_dump(), meter_ids=ids)
        raise NotFoundError(f"transformer {code} not found")
