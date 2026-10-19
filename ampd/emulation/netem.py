"""M1 - Impairment scenarios: loss, delay, jitter, congestion, link failure (NetEm via tc).

Quick use
---------
    set_impairment(net, "s1", "s2", loss=5, delay_ms=20, jitter_ms=3)      # raw, one link
    with scenario(net, "loss", "primary", loss=10): ...                     # named, auto-cleared
    apply_profile(net, BASELINE_PROFILE)                                    # static per-path quality
    clear_all(net)                                                          # back to a clean testbed

Where impairments land: on the *ingress-switch <-> middle-switch* link of a path (topology.path_link),
in BOTH directions. So `loss=5` means ~5 % one-way loss, `delay_ms=20` means 20 ms one-way, which is
exactly what LiveMonitor reports for that path (one-way estimates).

NetEm is attached as a child of Mininet's HTB class (parent 5:1, handle 10:) so the link's bandwidth
cap survives; replacing the *root* qdisc would silently remove it.
"""
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from ampd.emulation import topology as topo
from ampd.emulation import traffic


class NetemError(RuntimeError):
    pass


class NetemUnsupported(NetemError):
    """The kernel has no sch_netem (common in minimal VMs/containers): `modprobe sch_netem`."""


# --------------------------------------------------------------------------- tc plumbing
def _tc(intf, cmd: str, ignore_errors: bool = False) -> str:
    out = intf.cmd(cmd).strip()
    if out and re.search(r"Error|RTNETLINK|Cannot|Unknown|unknown", out):
        if "qdisc kind is unknown" in out and "netem" in cmd:
            raise NetemUnsupported(out)
        if not ignore_errors:
            raise NetemError(f"`{cmd}` on {intf.name}: {out}")
    return out


def _parent(intf) -> str:
    """'parent 5:1' if Mininet's HTB bandwidth class is present (TCLink bw=...), else 'root'."""
    return "parent 5:1" if "htb 5:" in intf.cmd(f"tc qdisc show dev {intf.name}") else "root"


def netem_args(loss: float = 0, delay_ms: float = 0, jitter_ms: float = 0, limit: Optional[int] = None) -> str:
    """Build the `netem ...` argument string (pure; unit-tested)."""
    if not 0 <= loss <= 100:
        raise ValueError(f"loss must be a percentage 0..100, got {loss}")
    if delay_ms < 0 or jitter_ms < 0:
        raise ValueError("delay_ms and jitter_ms must be >= 0")
    parts = []
    if delay_ms or jitter_ms:
        parts.append(f"delay {delay_ms:g}ms" + (f" {jitter_ms:g}ms" if jitter_ms else ""))
    if loss:
        parts.append(f"loss {loss:g}%")
    if limit:
        parts.append(f"limit {int(limit)}")
    return " ".join(parts) or "delay 0ms"  # netem needs at least one parameter


def _link_intfs(net, a: str, b: str):
    links = net.linksBetween(net.get(a), net.get(b))
    if not links:
        raise ValueError(f"no link between {a} and {b}")
    return links[0].intf1, links[0].intf2


def set_impairment(net, node_a, node_b, loss=0, delay_ms=0, jitter_ms=0, limit=None):
    """Apply NetEm loss (%) / delay / jitter (ms) on the link a<->b (both directions)."""
    args = netem_args(loss, delay_ms, jitter_ms, limit)
    for intf in _link_intfs(net, node_a, node_b):
        _tc(intf, f"tc qdisc replace dev {intf.name} {_parent(intf)} handle 10: netem {args}")


def clear_impairment(net, node_a, node_b):
    """Remove NetEm from the link (the HTB bandwidth cap stays)."""
    for intf in _link_intfs(net, node_a, node_b):
        par = _parent(intf)
        tail = "handle 10:" if par != "root" else ""
        _tc(intf, f"tc qdisc del dev {intf.name} {par} {tail}", ignore_errors=True)


def netem_supported(net) -> bool:
    """True if the kernel can do NetEm (probes on h1's loopback; leaves nothing behind)."""
    h = net.get(topo.HOSTS[0])
    out = h.cmd("tc qdisc replace dev lo root netem delay 1ms; tc qdisc del dev lo root 2>/dev/null")
    return "unknown" not in out.lower() and "error" not in out.lower()


# --------------------------------------------------------------------------- scenarios
@dataclass
class ActiveScenario:
    name: str
    path: str
    params: dict
    _undo: Callable[[], None] = field(repr=False, default=lambda: None)

    def stop(self) -> None:
        self._undo()


def _loss(net, path, loss=10.0):
    a, b = topo.path_link(path)
    set_impairment(net, a, b, loss=loss)
    return lambda: clear_impairment(net, a, b)


def _delay(net, path, delay_ms=80.0):
    a, b = topo.path_link(path)
    set_impairment(net, a, b, delay_ms=delay_ms)
    return lambda: clear_impairment(net, a, b)


def _jitter(net, path, delay_ms=30.0, jitter_ms=20.0):
    a, b = topo.path_link(path)
    set_impairment(net, a, b, delay_ms=delay_ms, jitter_ms=jitter_ms)
    return lambda: clear_impairment(net, a, b)


def _congestion(net, path, mbps=None, capacity_mbps=10.0):
    """Real congestion: saturating UDP cross-traffic pinned onto this path (default 90 % of capacity).
    Shows up in OVS port counters (utilization) and as queueing delay/loss in probes."""
    ct = traffic.CrossTraffic(net, path, mbps if mbps is not None else 0.9 * capacity_mbps)
    return ct.stop


def _link_failure(net, path):
    a, b = topo.path_link(path)
    net.configLinkStatus(a, b, "down")
    return lambda: net.configLinkStatus(a, b, "up")


SCENARIOS: Dict[str, Callable] = {
    "loss": _loss, "delay": _delay, "jitter": _jitter, "congestion": _congestion, "link_failure": _link_failure,
}
NEEDS_NETEM = {"loss", "delay", "jitter"}


def apply_scenario(net, name: str, path: str = "primary", **params) -> ActiveScenario:
    if name not in SCENARIOS:
        raise ValueError(f"unknown scenario {name!r}; choose from {sorted(SCENARIOS)}")
    if path not in topo.PATHS:
        raise ValueError(f"unknown path {path!r}; choose from {sorted(topo.PATHS)}")
    undo = SCENARIOS[name](net, path, **params)
    return ActiveScenario(name, path, params, undo)


@contextmanager
def scenario(net, name: str, path: str = "primary", **params):
    """with scenario(net, 'link_failure', 'primary'): ...   (restored on exit, even on error)"""
    active = apply_scenario(net, name, path, **params)
    try:
        yield active
    finally:
        active.stop()


# Static per-path quality; mirrors the SimMonitor profile in ampd/integration/main.py so sim and
# testbed runs are comparable. Values are one-way (see module docstring).
BASELINE_PROFILE: Dict[str, dict] = {
    "primary": dict(loss=2, delay_ms=20, jitter_ms=3),
    "secondary": dict(loss=5, delay_ms=35, jitter_ms=6),
    "backup": dict(loss=10, delay_ms=60, jitter_ms=10),
}


def apply_profile(net, profile: Dict[str, dict]) -> None:
    for pid, kw in profile.items():
        a, b = topo.path_link(pid)
        set_impairment(net, a, b, **kw)


def clear_all(net) -> None:
    """Remove every impairment: NetEm on all path links, failed links back up, cross-traffic stopped."""
    for pid in topo.PATHS:
        a, b = topo.path_link(pid)
        net.configLinkStatus(a, b, "up")
        try:
            clear_impairment(net, a, b)
        except NetemError:
            pass
    for i in range(len(topo.PATHS)):
        traffic.stop_iperf_server(net, topo.HOSTS[1], traffic.CROSS_PORT_BASE + i)
    net.get(topo.HOSTS[0]).cmd("pkill -f 'iperf3 -c .* -t 0' 2>/dev/null")


# --------------------------------------------------------------------------- backwards-compatible helpers
def start_iperf_server(net, host="h2"):
    traffic.start_iperf_server(net, host)


def run_iperf_udp(net, src="h1", dst="h2", mbps=2, secs=10):
    """Raw iperf3 JSON text (original behaviour). Prefer ampd.emulation.traffic for parsed results."""
    traffic.start_iperf_server(net, dst)
    return net.get(src).cmd(f"iperf3 -c {net.get(dst).IP()} -u -b {mbps}M -t {secs} -J")
