"""M1 - End-to-end testbed verification.  Run as root on a Linux box with Mininet + OVS + iperf3:

    sudo python -m ampd.emulation.verify [--datapath user] [--pcap-dir /tmp/ampd]

Prints PASS / FAIL / SKIP per check and exits non-zero on any FAIL.  SKIP is used only when the
kernel lacks NetEm (the loss/delay/jitter checks cannot run there).  Pcaps are kept for Wireshark.
"""
import argparse
import os
import subprocess
import sys
import time
from typing import Callable, List, Tuple

from ampd.common.types import DuplicationDecision, Path, PathMetrics, ScoredPath
from ampd.emulation import capture, flows, netem, topology as topo, traffic
from ampd.monitoring.live_monitor import LiveMonitor

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


def _paths() -> List[Path]:
    return [Path(pid, nodes) for pid, nodes in topo.PATHS.items()]


def _decision(cls: str, k: int) -> DuplicationDecision:
    sp = [ScoredPath(p, PathMetrics(), 0.9) for p in _paths()]
    return DuplicationDecision("verify", cls, k, sp[:k], 0.0)


def _tx(net, sw: str, peer: str) -> int:
    return flows.dump_ports(sw)[str(topo.port_no(net, sw, peer))].tx_pkts


def _blast(net, k: int, pcap_dir: str, secs: int = 3, mbps: float = 1, port=traffic.CRITICAL_PORT, tag="dup"):
    """Run a flow with captures at sender (h1) and receiver (h2); return (DeliveryReport, FlowResult)."""
    bpf = f"udp dst port {port}"
    tx, rx = f"{pcap_dir}/{tag}_k{k}_tx.pcap", f"{pcap_dir}/{tag}_k{k}_rx.pcap"
    with capture.Capture(net, "h1", "h1-eth0", tx, bpf), capture.Capture(net, "h2", "h2-eth0", rx, bpf):
        res = traffic.run_flow(net, port=port, mbps=mbps, secs=secs)
    return capture.analyze_delivery(capture.read_seq_counts(tx, port), capture.read_seq_counts(rx, port)), res


def run(net, pcap_dir: str) -> List[Tuple[str, str, str]]:
    results: List[Tuple[str, str, str]] = []
    dp, mon = flows.OVSDataPlane(net), LiveMonitor(net, link_capacity_mbps=10)
    paths = _paths()
    has_netem = netem.netem_supported(net)

    def check(name: str, fn: Callable[[], Tuple[bool, str]], skip: str = ""):
        if skip:
            results.append((name, SKIP, skip)); return
        try:
            ok, detail = fn()
        except Exception as e:  # a crash is a failure, not a reason to stop verifying
            ok, detail = False, f"{type(e).__name__}: {e}"
        results.append((name, PASS if ok else FAIL, detail))

    # ---- Task 2: topology
    check("topology: 5 switches, 2 hosts, 8 links",
          lambda: (len(net.switches) == 5 and len(net.hosts) == 2 and len(net.links) == 8,
                   f"{len(net.switches)} sw, {len(net.hosts)} hosts, {len(net.links)} links"))
    check("pingAll (h1<->h2) 0% loss", lambda: ((lambda l: (l == 0, f"{l:.0f}% dropped"))(net.pingAll(timeout=2))))

    def pinning():
        bad = []
        for pid, nodes in topo.PATHS.items():
            mid = nodes[2]
            before = {m: _tx(net, topo.PATHS[q][2], "s5") for q, m in ((q, topo.PATHS[q][2]) for q in topo.PATHS)}
            net.get("h1").cmd(f"ping -n -c 5 -i 0.1 -W 1 -Q {topo.PROBE_TOS[pid]} {net.get('h2').IP()}")
            after = {m: _tx(net, m, "s5") for m in before}
            moved = {m for m in before if after[m] - before[m] >= 5}
            if moved != {mid}:
                bad.append(f"{pid}: counters moved on {sorted(moved)}")
        return (not bad, "; ".join(bad) or "each probe crossed only its own middle switch")
    check("path pinning: ToS probe uses exactly its own path", pinning)

    # ---- Task 1: monitoring
    def metrics_clean():
        ms = {p.id: mon.get_metrics(p) for p in paths}
        ok = all(m.availability == 1 and m.loss < 0.05 and m.delay_ms < 20 and m.utilization < 0.2 for m in ms.values())
        return ok, ", ".join(f"{k}: d={m.delay_ms:.2f}ms u={m.utilization:.2f}" for k, m in ms.items())
    check("LiveMonitor: idle metrics sane for all 3 paths", metrics_clean)

    def util_counters():
        ct = traffic.CrossTraffic(net, "primary", 5.0)
        try:
            time.sleep(1.5)
            mon.reset()
            up, us = mon.get_metrics(paths[0]).utilization, mon.get_metrics(paths[1]).utilization
        finally:
            ct.stop()
        return (0.35 <= up <= 0.65 and us < 0.1), f"primary={up:.2f} (offered 0.50), secondary={us:.2f} (expected ~0)"
    check("utilization from OVS port counters (5 Mbit/s on 10 Mbit link ~ 0.5)", util_counters)

    # ---- Task 5 + Task 4: group-table duplication confirmed by counters AND capture
    for k in (1, 2, 3):
        def dup(k=k):
            ports = dp.apply(_decision("critical", k))
            rep, res = _blast(net, k, pcap_dir)
            gs = flows.group_stats("s1", flows.CLASS_RULES["critical"]["group_id"])
            buckets = gs.get("buckets", [])
            ok = (len(ports) == k and len(buckets) == k and rep.sent > 50 and rep.delivered_ratio > 0.99
                  and rep.copies == {k: rep.delivered} and len(set(buckets)) == 1)
            return ok, (f"group ports={ports} bucket pkts={buckets}; sent={rep.sent} delivered={rep.delivered_ratio:.3f} "
                        f"copies={rep.copies}; receiver saw {res.received_mbps:.2f} Mbit/s for 1 offered")
        check(f"duplication k={k}: group buckets + capture show exactly {k} cop{'y' if k == 1 else 'ies'}", dup)

    def classes():
        dp.apply(_decision("critical", 3)); dp.apply(_decision("normal", 1))
        rep, _ = _blast(net, 3, pcap_dir, port=traffic.NORMAL_PORT, tag="normal")
        return rep.copies == {1: rep.delivered} and rep.sent > 50, f"normal flow copies={rep.copies} while critical k=3"
    check("class separation: normal traffic NOT duplicated while critical is", classes)

    def cancel():
        dp.apply(_decision("critical", 3)); dp.cancel(_decision("critical", 3))
        rep, _ = _blast(net, 1, pcap_dir, tag="cancel")
        return rep.copies == {1: rep.delivered} and rep.sent > 50, f"after cancel copies={rep.copies}"
    check("Smart Duplicate Cancellation collapses k=3 back to 1 copy", cancel)

    # ---- Task 3: scenarios
    def failure():
        mon.reset()
        with netem.scenario(net, "link_failure", "primary"):
            m = mon.get_metrics(paths[0]); other = mon.get_metrics(paths[1])
        mon.reset(); back = mon.get_metrics(paths[0])
        ok = m.availability == 0 and m.loss == 1 and other.availability == 1 and back.availability == 1
        return ok, f"down: avail={m.availability} loss={m.loss}; secondary avail={other.availability}; restored avail={back.availability}"
    check("link failure: path goes unavailable, others unaffected, recovers", failure)

    def survive():
        # NB: iperf3's TCP control channel rides the default (primary) path, so we fail the *secondary*
        # path here; failing primary would sever the measurement tool itself, not the data copies.
        dp.apply(_decision("critical", 2))  # primary + secondary
        with netem.scenario(net, "link_failure", "secondary"):
            rep, _ = _blast(net, 2, pcap_dir, tag="failover")
        return (rep.delivered_ratio > 0.99 and rep.copies == {1: rep.delivered},
                f"k=2, secondary down: delivered={rep.delivered_ratio:.3f}, copies={rep.copies} (one copy lost, none of the packets)")
    check("duplication masks a link failure (k=2, one path down => still ~100% delivered)", survive)

    def congestion():
        mon.reset()
        with netem.scenario(net, "congestion", "primary", mbps=9.5):
            time.sleep(1.5); mon.reset()
            m = mon.get_metrics(paths[0])
        return m.utilization > 0.7, f"primary utilization={m.utilization:.2f} under 9.5 Mbit/s cross-traffic"
    check("congestion scenario raises utilization >0.7", congestion)

    skip = "" if has_netem else "kernel has no sch_netem (try: sudo modprobe sch_netem)"

    def loss():
        with netem.scenario(net, "loss", "primary", loss=10):
            mon.reset(); m = mon.get_metrics(paths[0])
            m = [mon.get_metrics(paths[0]) for _ in range(3)][-1]
        return 0.03 <= m.loss <= 0.2, f"configured 10% one-way, measured {m.loss*100:.1f}%"
    check("NetEm loss 10% reflected in get_metrics", loss, skip)

    def delay():
        with netem.scenario(net, "delay", "primary", delay_ms=80):
            mon.reset(); m = mon.get_metrics(paths[0])
        return 70 <= m.delay_ms <= 100, f"configured 80 ms one-way, measured {m.delay_ms:.1f} ms"
    check("NetEm delay 80ms reflected in get_metrics", delay, skip)

    def jitter():
        with netem.scenario(net, "jitter", "primary", delay_ms=30, jitter_ms=20):
            mon.reset(); m = mon.get_metrics(paths[0])
        return m.jitter_ms > 3, f"configured 30ms+-20ms, measured jitter {m.jitter_ms:.1f} ms"
    check("NetEm jitter reflected in get_metrics", jitter, skip)

    def bw_kept():
        with netem.scenario(net, "delay", "primary", delay_ms=5):
            out = net.get("s1").cmd("tc qdisc show dev s1-eth2")
        return "htb" in out and "netem" in out, "htb root + netem child present"
    check("NetEm keeps the HTB bandwidth cap (not replaced)", bw_kept, skip)

    netem.clear_all(net); dp.reset()
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--datapath", choices=["kernel", "user"], default=None)
    ap.add_argument("--pcap-dir", default="/tmp/ampd-pcaps")
    args = ap.parse_args()
    if os.geteuid() != 0:
        sys.exit("run as root (Mininet/OVS/tc need it)")
    os.makedirs(args.pcap_dir, exist_ok=True)
    from mininet.log import setLogLevel
    setLogLevel("error")
    net = topo.build_network(datapath=args.datapath)
    topo.start_network(net)
    try:
        results = run(net, args.pcap_dir)
    finally:
        traffic.stop_all_servers(net)
        net.stop()
    w = max(len(n) for n, _, _ in results)
    for n, s, d in results:
        print(f"[{s}] {n:<{w}}  {d}")
    fails = sum(s == FAIL for _, s, _ in results)
    print(f"\n{sum(s == PASS for _, s, _ in results)} passed, {fails} failed, {sum(s == SKIP for _, s, _ in results)} skipped"
          f"  (pcaps in {args.pcap_dir} - open in Wireshark)")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
