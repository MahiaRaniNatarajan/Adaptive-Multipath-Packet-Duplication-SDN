"""M1 - Mininet topology with three disjoint s-d paths (Primary / Secondary / Backup).

    h1 - s1 -+- s2 -+- s5 - h2        (primary)
             +- s3 -+                  (secondary)
             +- s4 -+                  (backup)

Switches are Open vSwitch with NO controller (failMode=secure); all flows are installed by
ampd.emulation.flows (ovs-ofctl), so no external SDN controller framework is needed.

Constants and helpers here do not import Mininet, so the monitor / tests can use them on any machine.
Only build_network() needs Mininet (imported lazily).

Capacity model: the three s1->mid->s5 links are the *path* links (`bw` Mbit/s each, the bottleneck).
Host access links get `access_bw` (default 100) so that k duplicate copies leaving s5 towards h2 are
not throttled by the access link.
"""
import os
from typing import Dict, List

HOSTS = ("h1", "h2")
INGRESS, EGRESS = "s1", "s5"

PATHS: Dict[str, List[str]] = {
    "primary": ["h1", "s1", "s2", "s5", "h2"],
    "secondary": ["h1", "s1", "s3", "s5", "h2"],
    "backup": ["h1", "s1", "s4", "s5", "h2"],
}

# Path pinning: traffic from h1/h2 carrying this IP ToS byte is forced onto that path (priority-400
# OVS flows). Used for per-path probes and for cross-traffic. Values are multiples of 4 (ECN bits clear)
# so they can be matched with OVS `nw_tos`.
PROBE_TOS: Dict[str, int] = {"primary": 0x20, "secondary": 0x40, "backup": 0x60}


def resolve_path_id(path) -> str:
    """Map an ampd Path (by node list, falling back to id) onto one of this testbed's path names."""
    nodes = list(path.nodes)
    for pid, ref in PATHS.items():
        if nodes == ref:
            return pid
    if path.id in PATHS:
        return path.id
    raise ValueError(f"Path {path.id!r} {nodes} is not one of the testbed paths {list(PATHS)}")


def build_network(bw: float = 10, access_bw: float = 100, datapath: str = None, disable_offload: bool = None):
    """Create (but do not start) the Mininet network.

    datapath: 'kernel' (default, needs the openvswitch kernel module) or 'user' (OVS userspace
              datapath; works in containers/VMs without the module). Env override: AMPD_OVS_DATAPATH.
    disable_offload: turn off tx/rx checksum offload on links. The OVS userspace datapath forwards
              offloaded (partial-checksum) packets that the receiving kernel then drops, which breaks
              TCP/UDP (ICMP still works). Defaults to True when datapath == 'user'.
    """
    from mininet.link import TCLink
    from mininet.net import Mininet
    from mininet.node import OVSSwitch

    datapath = datapath or os.environ.get("AMPD_OVS_DATAPATH", "kernel")
    if disable_offload is None:
        disable_offload = datapath == "user"
    off = {"txo": False, "rxo": False} if disable_offload else {}

    net = Mininet(switch=OVSSwitch, link=TCLink, controller=None, autoSetMacs=True)
    h1, h2 = net.addHost("h1"), net.addHost("h2")
    sw = {n: net.addSwitch(n, protocols="OpenFlow13", failMode="secure", datapath=datapath)
          for n in ("s1", "s2", "s3", "s4", "s5")}
    net.addLink(h1, sw["s1"], bw=access_bw, **off)
    net.addLink(h2, sw["s5"], bw=access_bw, **off)
    for mid in ("s2", "s3", "s4"):
        net.addLink(sw["s1"], sw[mid], bw=bw, **off)
        net.addLink(sw[mid], sw["s5"], bw=bw, **off)
    return net


def intf_between(net, a: str, b: str):
    """The interface of node `a` that faces node `b` (e.g. s1 -> s2 gives s1-eth2)."""
    na, nb = net.get(a), net.get(b)
    links = net.linksBetween(na, nb)
    if not links:
        raise ValueError(f"no link between {a} and {b}")
    link = links[0]
    return link.intf1 if link.intf1.node == na else link.intf2


def port_no(net, a: str, b: str) -> int:
    """OpenFlow port number on switch/host `a` of the link towards `b`."""
    return net.get(a).ports[intf_between(net, a, b)]


def path_link(path_id: str):
    """The impairable link of a path: ingress switch <-> that path's middle switch (e.g. s1,s2)."""
    nodes = PATHS[path_id]
    return nodes[1], nodes[2]


def start_network(net) -> None:
    """Start Mininet, then make it usable: static ARP + baseline forwarding flows (primary path)."""
    from ampd.emulation import flows  # local import: flows imports this module's constants

    net.start()
    net.staticArp()
    flows.install_baseline(net)


if __name__ == "__main__":
    import argparse

    from mininet.cli import CLI
    from mininet.log import setLogLevel

    ap = argparse.ArgumentParser(description="Build the 3-path AMPD testbed and run pingAll.")
    ap.add_argument("--bw", type=float, default=10, help="path-link capacity, Mbit/s")
    ap.add_argument("--datapath", choices=["kernel", "user"], default=None)
    ap.add_argument("--cli", action="store_true", help="drop into the Mininet CLI afterwards")
    args = ap.parse_args()

    setLogLevel("info")
    n = build_network(bw=args.bw, datapath=args.datapath)
    start_network(n)
    try:
        loss = n.pingAll()
        if args.cli:
            CLI(n)
    finally:
        n.stop()
    raise SystemExit(0 if loss == 0 else 1)
