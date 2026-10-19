"""M1 - Data-plane programming WITHOUT a controller framework.

Duplication is implemented with OpenFlow 1.3 via `ovs-ofctl`: an ALL-type group on the ingress switch
whose buckets output to each selected path's first hop. Changing k = rewriting the group (atomically,
with `mod-group`, so there is no window in which packets are dropped).

Public API
----------
apply_duplication(switch, in_port, out_ports, group_id=1, match="", priority=100)
cancel_duplicates(switch, in_port, keep_port, group_id=1, match="", priority=100)
install_baseline(net)                      static forwarding + per-path pinning (needed for pingAll)
OVSDataPlane(net).apply(decision)          adapter for M4: AMPDController(apply_fn=dp.apply)
group_ports / group_stats / dump_ports     read-back helpers used by verification

Flow priorities on the ingress switch (higher wins):
    400  ToS-pinned traffic (probes, cross-traffic)   -> exactly one path
    200  critical UDP (group 1)                       -> k copies
    150  normal   UDP (group 2)                       -> k copies (usually 1)
    100  replies from the middle switches             -> back to the host
     10  everything else (TCP control, ARP, ICMP)     -> primary path only
"""
import logging
import re
import subprocess
from typing import Dict, List, Optional, Sequence

from ampd.emulation import topology as topo
from ampd.monitoring.ovs_stats import PortCounters, parse_dump_ports

log = logging.getLogger(__name__)

OF_VERSION = "OpenFlow13"

# UDP destination ports treated as critical. Mirrors ampd/integration/classifier.py CRITICAL_PORTS;
# keep the two in sync (they are owned by different people, so this is a copy, not an import).
CRITICAL_UDP_PORTS = (5001, 5060, 8443)

CLASS_RULES = {
    "critical": {"group_id": 1, "priority": 200, "matches": [f"udp,tp_dst={p}" for p in CRITICAL_UDP_PORTS]},
    "normal": {"group_id": 2, "priority": 150, "matches": ["udp"]},
}


class OVSError(RuntimeError):
    pass


def ofctl(*args: str, input: Optional[str] = None, check: bool = True, timeout: float = 10) -> str:
    """Run `ovs-ofctl -O OpenFlow13 --no-names <args>` and return stdout.

    --no-names makes OVS print port *numbers* regardless of whether stdout is a terminal.
    """
    cmd = ["ovs-ofctl", "-O", OF_VERSION, "--no-names", *map(str, args)]
    r = subprocess.run(cmd, input=input, text=True, capture_output=True, timeout=timeout)
    if check and (r.returncode != 0 or "OFPT_ERROR" in r.stdout + r.stderr):
        raise OVSError(f"{' '.join(cmd)} failed (rc={r.returncode}): {(r.stderr or r.stdout).strip()}")
    return r.stdout


# --------------------------------------------------------------------------- groups & duplication
def _set_group(switch: str, group_id: int, out_ports: Sequence[int]) -> None:
    """Create or atomically modify an ALL group with one output bucket per port."""
    spec = f"group_id={group_id},type=all," + ",".join(f"bucket=output:{p}" for p in out_ports)
    try:
        ofctl("mod-group", switch, spec)
    except OVSError:  # group does not exist yet
        ofctl("add-group", switch, spec)


def _add_group_flow(switch: str, in_port: int, group_id: int, match: str, priority: int) -> None:
    parts = [f"priority={priority}", f"in_port={in_port}"] + ([match] if match else []) + [f"actions=group:{group_id}"]
    ofctl("add-flow", switch, ",".join(parts))  # same match+priority replaces the old flow


def _check_ports(in_port: int, out_ports: Sequence[int]) -> List[int]:
    ports = list(dict.fromkeys(out_ports))  # de-duplicate, keep order (best path first)
    if not ports:
        raise ValueError("out_ports is empty: need at least one path to send on")
    if in_port in ports:
        raise ValueError(f"in_port {in_port} cannot also be an output (OVS drops copies sent back to the ingress port)")
    return ports


def apply_duplication(switch: str, in_port: int, out_ports: List[int], group_id: int = 1,
                      match: str = "", priority: int = 100) -> None:
    """Replicate packets arriving on in_port to every port in out_ports (k copies).

    match: optional extra OpenFlow match (e.g. "udp,tp_dst=5001"); empty = every packet from in_port.
    """
    ports = _check_ports(in_port, out_ports)
    _set_group(switch, group_id, ports)
    _add_group_flow(switch, in_port, group_id, match, priority)


def cancel_duplicates(switch: str, in_port: int, keep_port: int, group_id: int = 1,
                      match: str = "", priority: int = 100) -> None:
    """Smart Duplicate Cancellation: collapse back to a single output."""
    apply_duplication(switch, in_port, [keep_port], group_id, match, priority)


# --------------------------------------------------------------------------- read-back helpers
def _group_line(text: str, group_id: int) -> str:
    """The single dump line for `group_id`. OVS (seen on 3.3.9) ignores a group_id filter on dump-groups /
    dump-group-stats and prints ALL groups, so we always dump everything and pick the line ourselves."""
    for line in text.splitlines():
        if re.match(rf"\s*group_id={group_id}\b(?!\d)", line):
            return line
    return ""


def group_ports(switch: str, group_id: int) -> List[int]:
    """Output ports of the group's buckets, in bucket order ([] if the group does not exist)."""
    line = _group_line(ofctl("dump-groups", switch, check=False), group_id)
    return [int(p) for p in re.findall(r"output:(\d+)", line)]


def group_stats(switch: str, group_id: int) -> Dict:
    """{'packets': N, 'bytes': N, 'buckets': [pkts_bucket0, ...]}: per-bucket counters prove duplication."""
    line = _group_line(ofctl("dump-group-stats", switch, check=False), group_id)
    m = re.search(r"packet_count=(\d+),byte_count=(\d+)", line)
    if not m:
        return {}
    return {"packets": int(m.group(1)), "bytes": int(m.group(2)),
            "buckets": [int(x) for x in re.findall(r"bucket\d+:packet_count=(\d+)", line)]}


def dump_ports(switch: str) -> Dict[str, PortCounters]:
    """Port counters keyed by port number (as a string)."""
    return parse_dump_ports(ofctl("dump-ports", switch))


# --------------------------------------------------------------------------- baseline forwarding
def _reset_switch(switch: str) -> None:
    ofctl("del-flows", switch)
    ofctl("del-groups", switch)


def _install(switch: str, rules: List[str]) -> None:
    ofctl("add-flows", switch, "-", input="\n".join(rules) + "\n")


def install_baseline(net) -> None:
    """Install static forwarding so the 3-path diamond works with no controller.

    * everything defaults to the primary path (so pingAll / TCP control work);
    * ToS-pinned traffic (topology.PROBE_TOS) is forced onto one specific path in both directions
      (the echo reply keeps the request's ToS, so it returns on the same path);
    * replies from any middle switch go back to the host; middle switches just bridge their two ports.
    Duplication of data traffic is layered on top by apply_duplication / OVSDataPlane.
    Idempotent: wipes existing flows and groups on all five switches first.
    """
    h_src, h_dst = topo.HOSTS
    ing, egr = topo.INGRESS, topo.EGRESS
    mids = {pid: nodes[2] for pid, nodes in topo.PATHS.items()}
    primary_mid = mids["primary"]
    pn = lambda a, b: topo.port_no(net, a, b)

    for sw, host in ((ing, h_src), (egr, h_dst)):
        _reset_switch(sw)
        rules = []
        for pid, mid in mids.items():
            rules.append(f"priority=400,ip,in_port={pn(sw, host)},nw_tos={topo.PROBE_TOS[pid]},actions=output:{pn(sw, mid)}")
            rules.append(f"priority=100,in_port={pn(sw, mid)},actions=output:{pn(sw, host)}")
        rules.append(f"priority=10,in_port={pn(sw, host)},actions=output:{pn(sw, primary_mid)}")
        _install(sw, rules)

    for mid in mids.values():
        _reset_switch(mid)
        _install(mid, [f"priority=100,in_port={pn(mid, ing)},actions=output:{pn(mid, egr)}",
                       f"priority=100,in_port={pn(mid, egr)},actions=output:{pn(mid, ing)}"])


# --------------------------------------------------------------------------- adapter for M4
class OVSDataPlane:
    """Turns a DuplicationDecision (M4) into OVS group-table state.

        dp = OVSDataPlane(net)
        ctl = AMPDController(monitor, paths, apply_fn=dp.apply)

    decision.paths[:decision.k] are the chosen paths (best first); each path's first hop out of the
    ingress switch becomes one ALL-group bucket. Traffic class decides which traffic is duplicated:
    'critical' -> UDP to CRITICAL_UDP_PORTS (group 1), 'normal' -> any other UDP (group 2).
    """

    def __init__(self, net, ingress: str = topo.INGRESS, host: str = topo.HOSTS[0]):
        self.net, self.ingress, self.host = net, ingress, host
        self.state: Dict[str, List[int]] = {}  # traffic class -> ports currently duplicated to

    def first_hop_port(self, path) -> int:
        nodes = list(path.nodes)
        if len(nodes) < 3 or nodes[1] != self.ingress:
            raise ValueError(f"path {path.id} {nodes} does not leave via ingress switch {self.ingress}")
        return topo.port_no(self.net, self.ingress, nodes[2])

    def apply(self, decision) -> List[int]:
        rule = CLASS_RULES.get(decision.traffic_class)
        if rule is None:
            log.warning("no data-plane rule for traffic class %r; ignoring", decision.traffic_class)
            return []
        chosen = decision.paths[:decision.k]
        if not chosen:
            log.warning("decision for %s has no paths; leaving data plane unchanged", decision.flow_id)
            return self.state.get(decision.traffic_class, [])
        in_port = topo.port_no(self.net, self.ingress, self.host)
        ports = _check_ports(in_port, [self.first_hop_port(sp.path) for sp in chosen])
        _set_group(self.ingress, rule["group_id"], ports)
        for match in rule["matches"]:
            _add_group_flow(self.ingress, in_port, rule["group_id"], match, rule["priority"])
        self.state[decision.traffic_class] = ports
        log.info("flow %s (%s): k=%d -> ports %s", decision.flow_id, decision.traffic_class, len(ports), ports)
        return ports

    def cancel(self, decision) -> List[int]:
        """Smart Duplicate Cancellation: keep only the best path for this decision's class."""
        return self.apply(_Single(decision))

    def reset(self) -> None:
        install_baseline(self.net)
        self.state.clear()


class _Single:
    """View of a decision truncated to its best path (k=1)."""

    def __init__(self, d):
        self.flow_id, self.traffic_class, self.paths, self.k = d.flow_id, d.traffic_class, d.paths[:1], 1
