"""M1 - Impairment + traffic helpers (NetEm via tc, iPerf3)."""


def set_impairment(net, node_a, node_b, loss=0, delay_ms=0, jitter_ms=0):
    """Apply NetEm loss/delay/jitter on the link a<->b (both directions)."""
    link = net.linksBetween(net.get(node_a), net.get(node_b))[0]
    for intf in (link.intf1, link.intf2):
        intf.node.cmd(f"tc qdisc replace dev {intf.name} root netem loss {loss}% delay {delay_ms}ms {jitter_ms}ms")


def start_iperf_server(net, host="h2"):
    net.get(host).cmd("iperf3 -s -D")


def run_iperf_udp(net, src="h1", dst="h2", mbps=2, secs=10):
    return net.get(src).cmd(f"iperf3 -c {net.get(dst).IP()} -u -b {mbps}M -t {secs} -J")
