"""M1 - Mininet topology with three disjoint s-d paths (Primary / Secondary / Backup).

    h1 - s1 - s2 - s5 - h2        (primary)
          |- s3 -|                 (secondary)
          |- s4 -|                 (backup)

Switches are Open vSwitch in standalone/remote-less mode; flows are installed by
ampd.emulation.flows (ovs-ofctl) so NO external SDN controller framework is needed.
"""
from mininet.link import TCLink
from mininet.net import Mininet
from mininet.node import OVSSwitch


def build_network(bw=10):
    net = Mininet(switch=OVSSwitch, link=TCLink, controller=None, autoSetMacs=True)
    h1, h2 = net.addHost("h1"), net.addHost("h2")
    sw = {n: net.addSwitch(n, protocols="OpenFlow13", failMode="secure") for n in ("s1", "s2", "s3", "s4", "s5")}
    net.addLink(h1, sw["s1"], bw=bw)
    net.addLink(h2, sw["s5"], bw=bw)
    for mid in ("s2", "s3", "s4"):
        net.addLink(sw["s1"], sw[mid], bw=bw)
        net.addLink(sw[mid], sw["s5"], bw=bw)
    return net


PATHS = {
    "primary": ["h1", "s1", "s2", "s5", "h2"],
    "secondary": ["h1", "s1", "s3", "s5", "h2"],
    "backup": ["h1", "s1", "s4", "s5", "h2"],
}

if __name__ == "__main__":
    n = build_network()
    n.start()
    n.pingAll()
    n.stop()
