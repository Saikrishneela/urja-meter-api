from app.decoder import resolve


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
