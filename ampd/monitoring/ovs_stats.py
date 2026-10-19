"""M1 - Parse `ovs-ofctl dump-ports` output and turn counter deltas into link utilization.

Pure functions only (no Mininet, no subprocess) so they are unit-testable anywhere.

`ovs-ofctl` prints port *names* when stdout is a terminal and port *numbers* when it is a
pipe (e.g. `port  "s1-eth2": rx pkts=...` vs `port  2: rx pkts=...`), so the parser accepts both and
returns them under whatever key OVS printed.  Callers should pass `--no-names` to get numbers
deterministically (see flows.dump_ports).
"""
import re
from dataclasses import dataclass
from typing import Dict, Optional

# "port  2:", 'port  "s1-eth2":', "port LOCAL:"
_PORT_LINE = re.compile(r'^\s*port\s+(?:"(?P<qname>[^"]+)"|(?P<tok>[^\s:]+))\s*:\s*rx\s+(?P<rx>.*)$')
_TX_LINE = re.compile(r"^\s*tx\s+(?P<tx>.*)$")


@dataclass(frozen=True)
class PortCounters:
    rx_pkts: int = 0
    rx_bytes: int = 0
    tx_pkts: int = 0
    tx_bytes: int = 0
    tx_drop: int = 0


def _field(blob: str, name: str) -> int:
    """Pull `name=<int>` out of 'pkts=3, bytes=294, drop=0, ...'. OVS prints '?' for unsupported counters."""
    m = re.search(rf"(?<![\w]){name}=(\d+|\?)", blob)
    return int(m.group(1)) if m and m.group(1) != "?" else 0


def parse_dump_ports(text: str) -> Dict[str, PortCounters]:
    """Return {port-key: PortCounters}. Key is the port number as a string ("2"), the interface name
    ("s1-eth2") or "LOCAL", exactly as OVS printed it."""
    out: Dict[str, PortCounters] = {}
    key: Optional[str] = None
    rx = ""
    for line in text.replace("\r", "").splitlines():
        m = _PORT_LINE.match(line)
        if m:
            key, rx = (m.group("qname") or m.group("tok")), m.group("rx")
            continue
        m = _TX_LINE.match(line)
        if m and key is not None:
            tx = m.group("tx")
            out[key] = PortCounters(_field(rx, "pkts"), _field(rx, "bytes"),
                                    _field(tx, "pkts"), _field(tx, "bytes"), _field(tx, "drop"))
            key = None
    return out


def utilization(prev: PortCounters, cur: PortCounters, dt_s: float, capacity_mbps: float) -> float:
    """Egress utilization in [0, 1]: transmitted bits over the interval / link capacity.

    A negative delta (counter reset, e.g. port bounced during a link-failure scenario) yields 0
    rather than a nonsense value.
    """
    if dt_s <= 0 or capacity_mbps <= 0:
        return 0.0
    delta = cur.tx_bytes - prev.tx_bytes
    if delta < 0:
        return 0.0
    return max(0.0, min(1.0, (delta * 8) / (dt_s * capacity_mbps * 1e6)))
