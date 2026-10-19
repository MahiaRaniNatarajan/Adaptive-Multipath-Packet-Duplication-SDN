from ampd.common.types import Path, PathMetrics
from ampd.monitoring.monitor import SimMonitor


def test_sim_monitor_returns_profile():
    p = Path("a", ["h1", "s1", "h2"])
    m = SimMonitor({"a": PathMetrics(loss=0.1)})
    assert m.get_metrics(p).loss == 0.1


# ---------------------------------------------------------------- M1 unit tests (no root / Mininet needed)
import struct
from collections import Counter

import pytest

from ampd import config
from ampd.emulation import capture, flows, netem, topology as topo
from ampd.monitoring.live_monitor import LiveMonitor, parse_ping
from ampd.monitoring.ovs_stats import PortCounters, parse_dump_ports, utilization

DUMP_NUMBERS = """OFPST_PORT reply (OF1.3) (xid=0x2): 3 ports
  port LOCAL: rx pkts=0, bytes=0, drop=0, errs=0, frame=0, over=0, crc=0
           tx pkts=0, bytes=0, drop=0, errs=0, coll=0
  port  2: rx pkts=3, bytes=294, drop=0, errs=0, frame=0, over=0, crc=0
           tx pkts=7, bytes=1000, drop=2, errs=0, coll=0
           duration=2.3s
"""


def test_parse_dump_ports_numbers_names_and_unknown():
    p = parse_dump_ports(DUMP_NUMBERS)
    assert p["2"] == PortCounters(3, 294, 7, 1000, 2) and "LOCAL" in p
    named = DUMP_NUMBERS.replace("port  2:", 'port  "s1-eth2":')
    assert parse_dump_ports(named)["s1-eth2"].tx_bytes == 1000
    assert parse_dump_ports(DUMP_NUMBERS.replace("bytes=1000", "bytes=?"))["2"].tx_bytes == 0


def test_utilization_math_clamp_and_counter_reset():
    a, b = PortCounters(tx_bytes=0), PortCounters(tx_bytes=625_000)  # 5 Mbit over 1 s
    assert utilization(a, b, 1.0, 10) == pytest.approx(0.5)
    assert utilization(a, PortCounters(tx_bytes=10**9), 1.0, 10) == 1.0
    assert utilization(b, a, 1.0, 10) == 0.0 and utilization(a, b, 0, 10) == 0.0


def test_parse_ping():
    out = "10 packets transmitted, 8 received, 20% packet loss, time 900ms\nrtt min/avg/max/mdev = 1.0/40.0/90.0/6.0 ms"
    assert parse_ping(out) == (10, 8, 40.0, 6.0)
    assert parse_ping("10 packets transmitted, 0 received, +10 errors, 100% packet loss, time 9ms") == (10, 0, 0.0, 0.0)
    with pytest.raises(ValueError):
        parse_ping("garbage")


class _Node:
    def __init__(self, name, replies=None):
        self.name, self.replies, self.cmds, self.ports = name, replies or [], [], {}

    def IP(self):
        return "10.0.0.2"

    def cmd(self, c):
        self.cmds.append(c)
        return self.replies.pop(0)


class _Net:
    def __init__(self, h1):
        self.nodes = {"h1": h1, "h2": _Node("h2")}
        for s in ("s1", "s2", "s3", "s4", "s5"):
            self.nodes[s] = _Node(s)
        self.switches = [self.nodes[s] for s in ("s1", "s2", "s3", "s4", "s5")]

    def get(self, n):
        return self.nodes[n]


def _monitor(replies, monkeypatch, counters=None):
    net = _Net(_Node("h1", replies))
    monkeypatch.setattr(topo, "port_no", lambda n, a, b: 1)
    return net, LiveMonitor(net, 10, dump_ports=lambda sw: counters.pop(0) if counters else {"1": PortCounters()})


PING_OK = "10 packets transmitted, 9 received, 10% packet loss\nrtt min/avg/max/mdev = 1/40.0/90/6.0 ms"


def test_live_monitor_one_way_conversion_and_pinned_probe(monkeypatch):
    net, mon = _monitor([PING_OK], monkeypatch)
    m = mon.get_metrics(Path("secondary", topo.PATHS["secondary"]))
    assert "-Q %d" % topo.PROBE_TOS["secondary"] in net.get("h1").cmds[0]   # probe is pinned to ITS path
    assert m.delay_ms == 20.0 and m.jitter_ms == 3.0 and m.availability == 1.0
    assert m.loss == pytest.approx(1 - (0.9 ** 0.5))                       # 10% RTT loss -> ~5.1% one-way


def test_live_monitor_utilization_from_counter_delta(monkeypatch):
    ticks = iter([0.0, 0.0, 1.0])                 # cache check, then before / after the probe
    net, _ = _monitor([PING_OK], monkeypatch)
    calls = []                                    # primary has 2 switch-switch links -> 3 switches dumped per sample
    def dump(sw):
        calls.append(sw)
        return {"1": PortCounters(tx_bytes=0 if len(calls) <= 3 else 625_000)}
    mon = LiveMonitor(net, 10, dump_ports=dump, clock=lambda: next(ticks, 1.0))
    assert mon.get_metrics(Path("p", topo.PATHS["primary"])).utilization == pytest.approx(0.5)


def test_live_monitor_dead_path_is_not_fast(monkeypatch):
    net, mon = _monitor(["10 packets transmitted, 0 received, +10 errors, 100% packet loss"], monkeypatch)
    m = mon.get_metrics(Path("backup", topo.PATHS["backup"]))
    assert (m.loss, m.availability, m.delay_ms, m.jitter_ms) == (1.0, 0.0, config.MAX_DELAY_MS, config.MAX_JITTER_MS)


def test_live_monitor_rejects_unknown_path_and_caches(monkeypatch):
    net, mon = _monitor([PING_OK], monkeypatch)
    with pytest.raises(ValueError):
        mon.get_metrics(Path("x", ["h1", "s1", "s9", "s5", "h2"]))
    mon.cache_ttl = 100
    p = Path("primary", topo.PATHS["primary"])
    assert mon.get_metrics(p) is mon.get_metrics(p) and len(net.get("h1").cmds) == 1


def test_resolve_path_id_by_nodes_even_if_id_differs():
    assert topo.resolve_path_id(Path("p2", topo.PATHS["backup"])) == "backup"


def test_netem_args():
    assert netem.netem_args(5, 20, 3) == "delay 20ms 3ms loss 5%"
    assert netem.netem_args(0.5) == "loss 0.5%" and netem.netem_args() == "delay 0ms"
    for bad in (dict(loss=101), dict(delay_ms=-1)):
        with pytest.raises(ValueError):
            netem.netem_args(**bad)


def test_netem_attaches_under_htb_not_root(monkeypatch):
    class I:
        def __init__(s, n): s.name, s.log = n, []
        def cmd(s, c):
            s.log.append(c); return "qdisc htb 5: root" if "show" in c else ""
    a, b = I("s1-eth2"), I("s2-eth1")
    link = type("L", (), {"intf1": a, "intf2": b})
    net = type("N", (), {"get": lambda s, n: n, "linksBetween": lambda s, x, y: [link]})()
    netem.set_impairment(net, "s1", "s2", loss=5, delay_ms=20)
    assert any("replace dev s1-eth2 parent 5:1 handle 10: netem delay 20ms loss 5%" in c for c in a.log)
    assert not any(" root handle" in c for c in a.log + b.log)   # would delete the bandwidth cap


def test_apply_duplication_commands(monkeypatch):
    calls = []
    def fake(*a, **k):
        calls.append(a)
        if a[0] == "mod-group" and len(calls) == 1:
            raise flows.OVSError("unknown group")
        return ""
    monkeypatch.setattr(flows, "ofctl", fake)
    flows.apply_duplication("s1", 1, [2, 3, 3], group_id=4, match="udp,tp_dst=5001", priority=200)
    assert calls[1] == ("add-group", "s1", "group_id=4,type=all,bucket=output:2,bucket=output:3")  # falls back, de-dupes
    assert calls[2] == ("add-flow", "s1", "priority=200,in_port=1,udp,tp_dst=5001,actions=group:4")
    with pytest.raises(ValueError):
        flows.apply_duplication("s1", 1, [])
    with pytest.raises(ValueError):
        flows.apply_duplication("s1", 2, [2, 3])


def _pcap(seqs):
    out = struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)
    for s in seqs:
        udp = struct.pack(">HHHH", 40000, 5001, 8 + 16, 0) + struct.pack(">IIII", 0, 0, s, 0)
        ip = struct.pack(">BBHHHBBH4s4s", 0x45, 0, 20 + len(udp), 1, 0, 64, 17, 0, bytes(4), bytes(4)) + udp
        fr = bytes(12) + b"\x08\x00" + ip
        out += struct.pack("<IIII", 0, 0, len(fr), len(fr)) + fr
    return out


def test_pcap_duplicate_analysis(tmp_path):
    tx, rx = tmp_path / "tx.pcap", tmp_path / "rx.pcap"
    tx.write_bytes(_pcap([0, 1, 2, 3]))
    rx.write_bytes(_pcap([0, 0, 0, 1, 1, 1, 2, 2, 2]))   # k=3 copies, packet 3 lost
    rep = capture.analyze_delivery(capture.read_seq_counts(str(tx)), capture.read_seq_counts(str(rx), 5001))
    assert rep.copies == {3: 3} and rep.delivered_ratio == 0.75 and rep.duplicates_confirmed
    assert rep.mean_copies == 3.0
    (tmp_path / "ng.pcap").write_bytes(b"\x0a\x0d\x0d\x0a" + bytes(40))
    with pytest.raises(ValueError):
        capture.read_udp_packets(str(tmp_path / "ng.pcap"))


def test_group_readback_selects_requested_group_even_if_ovs_dumps_all(monkeypatch):
    dump = (" group_id=1,type=all,bucket=actions=output:4,bucket=actions=output:3\n"
            " group_id=12,type=all,bucket=actions=output:9\n"
            " group_id=2,type=all,bucket=actions=output:3\n")
    stats = (" group_id=1,duration=1s,ref_count=1,packet_count=10,byte_count=900,bucket0:packet_count=10,byte_count=900,"
             "bucket1:packet_count=10,byte_count=900\n group_id=2,duration=1s,ref_count=1,packet_count=5,byte_count=1,"
             "bucket0:packet_count=5,byte_count=1\n")
    monkeypatch.setattr(flows, "ofctl", lambda cmd, *a, **k: dump if cmd == "dump-groups" else stats)
    assert flows.group_ports("s1", 1) == [4, 3] and flows.group_ports("s1", 2) == [3] and flows.group_ports("s1", 7) == []
    assert flows.group_stats("s1", 2) == {"packets": 5, "bytes": 1, "buckets": [5]}
    assert flows.group_stats("s1", 1)["buckets"] == [10, 10]
