import os
from datetime import datetime
from functools import lru_cache
from typing import Annotated, Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from app.models import (
    EnergySeries,
    Location,
    MeterDetail,
    MeterPage,
    TransformerDetail,
    Transformer,
)
from app.portal_client import AuthError, NotFoundError, PortalClient, PortalError
from app.service import MeterService

load_dotenv()

DESCRIPTION = """
A clean JSON API over the legacy *Urja Meter Ops* portal.

* Timestamps are ISO 8601 with an **assumed** +05:30 offset (the portal gives none).
* Energy `*_register` fields are the meter's cumulative readings; `*_interval` is the
  usage since the previous reading (null for the first reading of a response).
* Hierarchy levels the portal left blank or damaged are filled from the same
  transformer's other meters and marked `inferred: true`.
* Errors: 404 unknown meter, 422 bad input, 503 portal down or rate limiting
  (see the `Retry-After` header), 502 portal rejected our credentials.
"""

app = FastAPI(title="Urja Meter API", version="1.0.0", description=DESCRIPTION)


@lru_cache
def get_service() -> MeterService:
    client = PortalClient(
        os.environ.get("URJA_BASE_URL", "https://urja-ops.flockenergy.tech"),
        os.environ["URJA_EMAIL"],
        os.environ["URJA_PASSWORD"],
    )
    return MeterService(client)


ServiceDep = Annotated[MeterService, Depends(get_service)]


@app.exception_handler(NotFoundError)
async def handle_not_found(request, exc):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(AuthError)
async def handle_auth(request, exc):
    return JSONResponse(
        status_code=502,
        content={"detail": "The upstream portal rejected our credentials."},
    )


@app.exception_handler(PortalError)
async def handle_portal(request, exc):
    return JSONResponse(
        status_code=503,
        headers={"Retry-After": "30"},
        content={
            "detail": f"The upstream portal is unavailable or rate limiting: {exc}"
        },
    )


def _day(value, name):
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(422, f"'{name}' must be a date like 2026-06-25") from None


@app.get("/health", summary="Liveness check (does not call the portal)")
def health():
    return {"status": "ok"}


@app.get("/meters", response_model=MeterPage, summary="List and filter meters")
def list_meters(
    service: ServiceDep,
    q: Annotated[
        str | None, Query(description="Substring of meter ID or serial number")
    ] = None,
    make: str | None = None,
    status: Literal["Installed", "Faulty", "Decommissioned"] | None = None,
    phase_type: Literal["single", "three"] | None = None,
    dt_code: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return service.search(q, make, status, phase_type, dt_code, limit, offset)


@app.get(
    "/meters/{meter_id}",
    response_model=MeterDetail,
    summary="One meter with hierarchy and location",
)
def get_meter(meter_id: str, service: ServiceDep):
    return service.meter(meter_id)


@app.get(
    "/meters/{meter_id}/location", response_model=Location, summary="Meter coordinates"
)
def get_location(meter_id: str, service: ServiceDep):
    location = service.location(meter_id)
    if location is None:
        raise NotFoundError(f"no usable location for {meter_id}")
    return location


@app.get(
    "/meters/{meter_id}/energy",
    response_model=EnergySeries,
    summary="Energy readings with per-interval usage",
    description=(
        "Without parameters the portal returns the last 7 days. Its data runs from "
        "2026-06-01 to 2026-06-30. Dates are inclusive whole days (YYYY-MM-DD). "
        "Some meters report every 30 minutes, others once a day; see `interval_minutes`."
    ),
)
def get_energy(
    meter_id: str,
    service: ServiceDep,
    start: Annotated[str | None, Query(alias="from", description="YYYY-MM-DD")] = None,
    end: Annotated[str | None, Query(alias="to", description="YYYY-MM-DD")] = None,
):
    start_day, end_day = _day(start, "from"), _day(end, "to")
    if start_day and end_day and start_day > end_day:
        raise HTTPException(422, "'from' must not be after 'to'")
    return service.energy(
        meter_id,
        start_day.isoformat() if start_day else None,
        end_day.isoformat() if end_day else None,
    )


@app.get(
    "/transformers",
    response_model=list[Transformer],
    summary="List distribution transformers",
)
def list_transformers(service: ServiceDep):
    return service.transformers()


@app.get(
    "/transformers/{code}",
    response_model=TransformerDetail,
    summary="One transformer and its meters",
)
def get_transformer(code: str, service: ServiceDep):
    return service.transformer(code)
