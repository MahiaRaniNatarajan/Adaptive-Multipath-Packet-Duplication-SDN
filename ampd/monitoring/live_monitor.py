"""M1 - Live monitor: reads real telemetry from the Mininet/OVS emulation.

Loss/delay/jitter come from lightweight probes (ping/iperf3 UDP), utilization from
OVS port counters (ovs-ofctl dump-ports). Fill in TODOs once the topology is up.
"""
import re
import subprocess

from ampd.common.types import Path, PathMetrics
from ampd.monitoring.monitor import BaseMonitor


class LiveMonitor(BaseMonitor):
    def __init__(self, net, link_capacity_mbps: float = 10.0):
        self.net = net            # Mininet object from emulation.topology
        self.cap = link_capacity_mbps

    def _ping_stats(self, src: str, dst: str, count: int = 5):
        out = self.net.get(src).cmd(f"ping -c {count} -i 0.2 {self.net.get(dst).IP()}")
        loss = float(re.search(r"([\d.]+)% packet loss", out).group(1)) / 100
        m = re.search(r"= ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms", out)
        avg, mdev = (float(m.group(2)), float(m.group(4))) if m else (0.0, 0.0)
        return loss, avg, mdev

    def get_metrics(self, path: Path) -> PathMetrics:
        src, dst = path.nodes[0], path.nodes[-1]
        loss, delay, jitter = self._ping_stats(src, dst)
        util = 0.0  # TODO(M1): parse `ovs-ofctl dump-ports <sw>` tx_bytes delta / (cap * interval)
        return PathMetrics(loss, delay, jitter, util, availability=0.0 if loss >= 1 else 1.0)
