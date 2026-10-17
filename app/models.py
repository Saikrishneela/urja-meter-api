from datetime import datetime

from pydantic import BaseModel


class MeterSummary(BaseModel):
    meter_id: str
    serial_no: str
    make: str
    phase_type: str
    install_status: str
    dt_code: str


class MeterPage(BaseModel):
    items: list[MeterSummary]
    total: int
    limit: int
    offset: int


class HierarchyLevel(BaseModel):
    level: str
    name: str | None = None
    code: str | None = None
    inferred: bool = False


class Location(BaseModel):
    latitude: float
    longitude: float


class MeterDetail(MeterSummary):
    installation_type: str | None = None
    hierarchy: list[HierarchyLevel]
    location: Location | None = None


class Reading(BaseModel):
    timestamp: datetime
    kwh_register: float | None
    kvah_register: float | None
    voltage_r: float | None
    kwh_interval: float | None
    kvah_interval: float | None


class EnergySeries(BaseModel):
    meter_id: str
    interval_minutes: int | None
    timezone: str = "UTC+05:30 (assumed, the portal gives none)"
    readings: list[Reading]


class Transformer(BaseModel):
    code: str
    name: str
    feeder_code: str
    capacity_kva: int
    meter_count: int


class TransformerDetail(Transformer):
    meter_ids: list[str]
