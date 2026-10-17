from app.transform import build_hierarchy, build_series, merge_chains, split_label

RAW = {
    "Zone": "Jaipur Zone 3 (Z-03)",
    "Circle": "Circle 3 (C-03)",
    "Division": "Division 3 (D-03)",
    "Subdivision": "Subdivision 3 (SD-03)",
    "Sub Station": "Substation 3 (SS-03)",
    "Feeder": "Feeder 3 (F-003)",
    "DT": "Vaishali DT 3 (DT-003)",
}


def test_split_label_handles_damaged_labels():
    assert split_label("Vaishali DT 3 (DT-003)") == ("Vaishali DT 3", "DT-003")
    assert split_label("Circle 6") == ("Circle 6", None)
    assert split_label("") == (None, None)
    assert split_label(None) == (None, None)


def test_hierarchy_gap_is_filled_and_marked_inferred():
    broken = {**RAW, "Circle": "Circle 3"}
    levels = build_hierarchy(broken, merge_chains([RAW]))
    circle = next(level for level in levels if level["level"] == "Circle")
    assert circle == {
        "level": "Circle",
        "name": "Circle 3",
        "code": "C-03",
        "inferred": True,
    }
    assert not any(
        level["inferred"] for level in build_hierarchy(RAW, merge_chains([RAW]))
    )


def test_conflicting_levels_are_not_filled():
    other = {**RAW, "Circle": "Circle 9 (C-09)"}
    merged = merge_chains([RAW, other])
    assert "Circle" not in merged
    assert "Zone" in merged


def test_series_intervals_and_timezone():
    rows = [
        {
            "timestamp": "24/06/2026 00:00",
            "kwh": "100.00",
            "kvah": "110.0",
            "voltR": "230",
        },
        {
            "timestamp": "24/06/2026 00:30",
            "kwh": "100.41",
            "kvah": "110.5",
            "voltR": "231",
        },
    ]
    series = build_series("J1", rows)
    assert series["interval_minutes"] == 30
    assert series["readings"][0]["kwh_interval"] is None
    assert series["readings"][1]["kwh_interval"] == 0.41
    assert series["readings"][0]["timestamp"].isoformat() == "2026-06-24T00:00:00+05:30"


def test_daily_meter_interval():
    rows = [
        {"timestamp": "23/06/2026 00:00", "kwh": "10", "kvah": "11", "voltR": "230"},
        {"timestamp": "24/06/2026 00:00", "kwh": "17", "kvah": "18", "voltR": "230"},
    ]
    assert build_series("J1", rows)["interval_minutes"] == 1440


def test_register_going_backwards_gives_no_interval():
    rows = [
        {"timestamp": "24/06/2026 00:00", "kwh": "100", "kvah": "110", "voltR": "230"},
        {"timestamp": "24/06/2026 00:30", "kwh": "50", "kvah": "120", "voltR": "230"},
    ]
    readings = build_series("J1", rows)["readings"]
    assert readings[1]["kwh_interval"] is None
    assert readings[1]["kvah_interval"] == 10.0
