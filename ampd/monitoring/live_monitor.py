"""M1 - Live monitor: reads real telemetry from the Mininet/OVS emulation.

get_metrics(path) -> PathMetrics   (signature frozen: M2/M3/M4 depend on it)

How each field is measured
--------------------------
The probe is a burst of ICMP echoes from path.nodes[0] to path.nodes[-1], *pinned onto that path* by
an IP ToS mark (see topology.PROBE_TOS / flows.install_baseline), so every path gets its own numbers.
Without pinning all three paths would see the same default-route (primary) measurement.

loss          one-way loss, from probe results pooled over the last `window` bursts (so ~1-2 % losses are
              resolvable, not just multiples of 1/probe_count). Round-trip loss L_rtt is converted to
              one-way with 1 - sqrt(1 - L_rtt) (both directions are impaired alike). 1.0 when the path is dead.
delay_ms      mean RTT / 2   (one-way estimate; matches the NetEm per-direction delay setting)
jitter_ms     RTT mdev / 2   (one-way estimate)
utilization   max over the path's switch-to-switch links and both directions of
              (tx bytes delta from `ovs-ofctl dump-ports` x 8) / (dt x link_capacity), sampled just
              before and just after the probe burst, clamped to [0, 1]. Host access links are
              excluded: they are shared by all paths and would make every path look equally loaded.
availability  1.0 if any probe was answered, else 0.0 (latest burst only, so recovery is immediate).

A dead path (no replies) gets delay/jitter at the normalisation ceilings (config.MAX_*), not 0, so it
cannot look "fast".
"""
import re
import time
from collections import deque
from math import sqrt
from typing import Callable, Deque, Dict, List, Optional, Tuple

from ampd import config
from ampd.common.types import Path, PathMetrics
from ampd.emulation import flows
from ampd.emulation import topology as topo
from ampd.monitoring.monitor import BaseMonitor
from ampd.monitoring.ovs_stats import PortCounters, parse_dump_ports, utilization

_STATS = re.compile(r"(\d+) packets transmitted, (\d+) (?:packets )?received")
_RTT = re.compile(r"= ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms")


def parse_ping(out: str) -> Tuple[int, int, float, float]:
    """-> (sent, received, rtt_avg_ms, rtt_mdev_ms). Raises ValueError if ping printed no summary."""
    m = _STATS.search(out)
    if not m:
        raise ValueError(f"unparseable ping output: {out[-200:]!r}")
    sent, recv = int(m.group(1)), int(m.group(2))
    r = _RTT.search(out)
    avg, mdev = (float(r.group(2)), float(r.group(4))) if r else (0.0, 0.0)
    return sent, recv, avg, mdev


class LiveMonitor(BaseMonitor):
    def __init__(self, net, link_capacity_mbps: float = 10.0, *, probe_count: int = 10,
                 probe_interval_s: float = 0.1, window: int = 3, cache_ttl_s: float = 0.0,
                 dump_ports: Optional[Callable[[str], Dict[str, PortCounters]]] = None,
                 clock: Callable[[], float] = time.monotonic):
        self.net = net                    # Mininet object from emulation.topology
        self.cap = link_capacity_mbps     # capacity of the switch-to-switch path links, Mbit/s
        self.probe_count, self.probe_interval = probe_count, probe_interval_s
        self.window = window              # bursts pooled for the loss estimate
        self.cache_ttl = cache_ttl_s      # reuse a path's last result if younger than this (0 = always probe)
        self._dump_ports = dump_ports or flows.dump_ports
        self._clock = clock
        self._hist: Dict[str, Deque[Tuple[int, int]]] = {}
        self._cache: Dict[str, Tuple[float, PathMetrics]] = {}

    # ------------------------------------------------------------------ probing
    def _ping_stats(self, src: str, dst: str, tos: Optional[int] = None):
        """One probe burst; returns (sent, received, rtt_avg_ms, rtt_mdev_ms)."""
        q = f"-Q {tos} " if tos is not None else ""
        out = self.net.get(src).cmd(
            f"ping -n -c {self.probe_count} -i {self.probe_interval} -W 1 {q}{self.net.get(dst).IP()}")
        return parse_ping(out)

    # ------------------------------------------------------------------ utilization
    def _links(self, path: Path) -> List[Tuple[str, str]]:
        """Switch-to-switch hops of the path (host access links excluded)."""
        sw = {s.name for s in self.net.switches}
        return [(a, b) for a, b in zip(path.nodes, path.nodes[1:]) if a in sw and b in sw]

    def _sample(self, links: List[Tuple[str, str]]) -> Dict[Tuple[str, str], PortCounters]:
        """tx counters for both directions of every link: {(switch, peer): counters of switch's port toward peer}."""
        want: Dict[str, List[Tuple[str, str]]] = {}
        for a, b in links:
            want.setdefault(a, []).append((a, b))
            want.setdefault(b, []).append((b, a))
        out = {}
        for sw, pairs in want.items():
            ports = self._dump_ports(sw)
            for key in pairs:
                pno = str(topo.port_no(self.net, *key))
                if pno in ports:
                    out[key] = ports[pno]
        return out

    def _utilization(self, before, after, dt: float) -> float:
        rates = [utilization(before[k], after[k], dt, self.cap) for k in before if k in after]
        return max(rates, default=0.0)

    # ------------------------------------------------------------------ BaseMonitor
    def reset(self) -> None:
        """Forget loss history/cache (e.g. right after changing a scenario, to avoid smoothing lag)."""
        self._hist.clear()
        self._cache.clear()

    def get_metrics(self, path: Path) -> PathMetrics:
        pid = topo.resolve_path_id(path)  # raises ValueError for a path the testbed doesn't have
        now = self._clock()
        hit = self._cache.get(pid)
        if hit and now - hit[0] < self.cache_ttl:
            return hit[1]

        src, dst = path.nodes[0], path.nodes[-1]
        links = self._links(path)
        before, t0 = self._sample(links), self._clock()
        sent, recv, avg, mdev = self._ping_stats(src, dst, topo.PROBE_TOS[pid])
        after, t1 = self._sample(links), self._clock()
        util = self._utilization(before, after, t1 - t0)

        hist = self._hist.setdefault(pid, deque(maxlen=self.window))
        hist.append((sent, recv))

        if recv == 0:  # dead path
            m = PathMetrics(1.0, config.MAX_DELAY_MS, config.MAX_JITTER_MS, util, availability=0.0)
        else:
            tot_sent = sum(s for s, _ in hist)
            l_rtt = 1.0 - sum(r for _, r in hist) / tot_sent if tot_sent else 0.0
            loss = 1.0 - sqrt(max(0.0, 1.0 - l_rtt))
            m = PathMetrics(loss, avg / 2.0, mdev / 2.0, util, availability=1.0)
        self._cache[pid] = (self._clock(), m)
        return m
