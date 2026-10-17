import json


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


def _read_detail(detail):
    """Normalise the two detail shapes the portal returns into one dict."""
    if "data" in detail:
        return {p["parameterName"]: p["parameterValue"] for p in detail["data"]}
    if "classData" in detail:
        inner = json.loads(detail["classData"])["installed_meter"]
        return {
            "Meter ID": inner["MeterId"],
            "Serial No": inner["SerialNo"],
            "Make": inner["Make"],
            "Phase Type": inner["PhaseType"],
            "Installation Status": inner["InstallationStatus"],
            "Installation Type": inner["InstallationType"],
        }
    raise ValueError(f"unknown detail shape: {sorted(detail)}")


def parse_meter_page(payload):
    """Turn a meter page's __data.json into detail fields plus hierarchy."""
    data = payload["nodes"][-1]["data"]
    root = resolve(data, 0)
    return {
        "meterId": root["meterId"],
        "detail": _read_detail(root["detail"]),
        "hierarchy": root["hierarchy"],
    }
