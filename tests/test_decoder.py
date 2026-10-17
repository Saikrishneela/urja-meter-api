import json

import pytest

from app.decoder import parse_meter_page, resolve


def test_resolve_follows_indexes():
    data = [
        {"meterId": 1, "detail": 2},
        "J100000",
        {"data": 3},
        [4],
        {"parameterName": 5, "parameterValue": 1},
        "Meter ID",
    ]
    assert resolve(data, 0) == {
        "meterId": "J100000",
        "detail": {
            "data": [{"parameterName": "Meter ID", "parameterValue": "J100000"}]
        },
    }


def test_parse_shape_b_double_encoded_detail():
    inner = {
        "installed_meter": {
            "MeterId": "J100004",
            "SerialNo": "SE65293",
            "Make": "Genus",
            "PhaseType": "single",
            "InstallationStatus": "Faulty",
            "InstallationType": "CT Operated",
        }
    }
    data = [
        {"meterId": 1, "detail": 2, "hierarchy": 4},
        "J100004",
        {"classData": 3},
        json.dumps(inner),
        {"Meter ID": 1, "Zone": 5},
        "Jaipur Zone 2 (Z-02)",
    ]
    payload = {
        "nodes": [{"type": "skip"}, {"type": "skip"}, {"type": "data", "data": data}]
    }
    result = parse_meter_page(payload)
    assert result["detail"]["Serial No"] == "SE65293"
    assert result["detail"]["Installation Type"] == "CT Operated"
    assert result["hierarchy"]["Zone"] == "Jaipur Zone 2 (Z-02)"


def test_parse_unknown_detail_shape_fails_loudly():
    data = [{"meterId": 1, "detail": 2, "hierarchy": 3}, "J1", {"other": 1}, {}]
    payload = {"nodes": [{"type": "data", "data": data}]}
    with pytest.raises(ValueError):
        parse_meter_page(payload)
