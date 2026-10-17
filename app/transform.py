import re
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
LEVELS = ["Zone", "Circle", "Division", "Subdivision", "Sub Station", "Feeder", "DT"]
OUTPUT_NAME = {"Sub Station": "Substation"}
LABEL = re.compile(r"^(.*) \(([^)]+)\)$")


def split_label(label):
    """'Vaishali DT 3 (DT-003)' -> ('Vaishali DT 3', 'DT-003'); damaged labels give code None."""
    match = LABEL.match(label or "")
    if match:
        return match.group(1), match.group(2)
    return (label or None), None


def has_gaps(raw):
    return any(split_label(raw.get(level))[1] is None for level in LEVELS)


def merge_chains(hierarchies):
    """Collect each level's (name, code) across meters; keep only unambiguous levels."""
    found = {}
    for raw in hierarchies:
        for level in LEVELS:
            name, code = split_label(raw.get(level))
            if code:
                found.setdefault(level, set()).add((name, code))
    return {
        level: next(iter(values)) for level, values in found.items() if len(values) == 1
    }


def build_hierarchy(raw, fallback=None):
    fallback = fallback or {}
    levels = []
    for key in LEVELS:
        name, code = split_label(raw.get(key))
        inferred = False
        if code is None and key in fallback:
            name, code = fallback[key]
            inferred = True
        levels.append(
            {
                "level": OUTPUT_NAME.get(key, key),
                "name": name,
                "code": code,
                "inferred": inferred,
            }
        )
    return levels


def parse_timestamp(text):
    return datetime.strptime(text, "%d/%m/%Y %H:%M").replace(tzinfo=IST)


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _delta(current, previous):
    if current is None or previous is None or current < previous:
        return None
    return round(current - previous, 3)


def build_series(meter_id, rows):
    """Portal registers are cumulative; add the usage in each interval."""
    readings = []
    prev_kwh = prev_kvah = None
    for row in rows:
        kwh = _number(row.get("kwh"))
        kvah = _number(row.get("kvah"))
        readings.append(
            {
                "timestamp": parse_timestamp(row["timestamp"]),
                "kwh_register": kwh,
                "kvah_register": kvah,
                "voltage_r": _number(row.get("voltR")),
                "kwh_interval": _delta(kwh, prev_kwh),
                "kvah_interval": _delta(kvah, prev_kvah),
            }
        )
        prev_kwh, prev_kvah = kwh, kvah
    interval = None
    if len(readings) >= 2:
        gap = readings[1]["timestamp"] - readings[0]["timestamp"]
        interval = int(gap.total_seconds() // 60)
    return {"meter_id": meter_id, "interval_minutes": interval, "readings": readings}
