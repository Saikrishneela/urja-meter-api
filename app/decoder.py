def resolve(data, i):
    """Follow index i in SvelteKit's flat array and rebuild the real value."""
    if i < 0:
        return None
    value = data[i]
    if isinstance(value, dict):
        return {k: resolve(data, v) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(data, v) for v in value]
    return value


def parse_meter_page(payload):
    """Turn a meter page's __data.json into detail fields plus hierarchy."""
    data = payload["nodes"][-1]["data"]
    root = resolve(data, 0)
    detail = {p["parameterName"]: p["parameterValue"] for p in root["detail"]["data"]}
    return {
        "meterId": root["meterId"],
        "detail": detail,
        "hierarchy": root["hierarchy"],
    }
