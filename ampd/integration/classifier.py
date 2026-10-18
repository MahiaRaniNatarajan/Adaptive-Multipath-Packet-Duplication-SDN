"""M4 - Traffic classifier (critical vs normal)."""
CRITICAL_PORTS = {5060, 5001, 8443}  # example: telemedicine / industrial / banking


def classify(flow: dict) -> str:
    if flow.get("class"):
        return flow["class"]
    return "critical" if flow.get("dst_port") in CRITICAL_PORTS else "normal"
