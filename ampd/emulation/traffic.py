"""M1 - iPerf3 traffic generation: critical vs normal flows, plus path-pinned cross-traffic.

Critical flows use UDP port 5001 (in flows.CRITICAL_UDP_PORTS -> duplicated); normal flows use
5201 (iperf3's default -> duplicated only if the controller decides so).  Packets are 1500 B on the
wire (config.PACKET_SIZE): 1472 B UDP payload + 8 UDP + 20 IP.

CAVEAT - iperf3's own loss/packet counters are NOT meaningful when packets are duplicated: the
receiver treats extra copies as out-of-order packets and *subtracts* them from the loss count
(we measured 204 'received' packets and 0 loss for 170 packets sent over k=3). Use
ampd.emulation.capture.analyze_delivery() for the real delivered ratio.
"""
import json
import subprocess
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from ampd.emulation import topology as topo

CRITICAL_PORT = 5001
NORMAL_PORT = 5201
CROSS_PORT_BASE = 5300
UDP_PAYLOAD = 1472


class TrafficError(RuntimeError):
    pass


# --------------------------------------------------------------------------- servers
def _pidfile(port: int) -> str:
    return f"/tmp/ampd-iperf3-{port}.pid"


def start_iperf_server(net, host: str = "h2", port: int = NORMAL_PORT) -> None:
    h = net.get(host)
    if h.cmd(f"ss -H -ltn 'sport = :{port}'").strip():
        return  # already listening
    h.cmd(f"iperf3 -s -p {port} -D -I {_pidfile(port)}")
    for _ in range(30):  # -D forks before it binds; wait until the port is really open
        if h.cmd(f"ss -H -ltn 'sport = :{port}'").strip():
            return
        time.sleep(0.1)
    raise TrafficError(f"iperf3 server on {host}:{port} did not start")


def stop_iperf_server(net, host: str = "h2", port: int = NORMAL_PORT) -> None:
    net.get(host).cmd(f"kill $(cat {_pidfile(port)} 2>/dev/null) 2>/dev/null; rm -f {_pidfile(port)}")


# --------------------------------------------------------------------------- measured flows
@dataclass
class FlowResult:
    name: str
    port: int
    sent_packets: int            # packets the iperf3 client sent
    received_mbps: float         # wire rate at the receiver: ~k x offered rate when k copies arrive
    jitter_ms: float
    reported_lost: int           # iperf3's figure - UNRELIABLE under duplication (see module docstring)
    raw: dict = field(default_factory=dict, repr=False)


def parse_iperf_json(out: str, name: str = "", port: int = 0) -> FlowResult:
    start = out.find("{")
    try:
        j = json.loads(out[start:]) if start >= 0 else {}
    except json.JSONDecodeError as e:
        raise TrafficError(f"unparseable iperf3 output: {out[-300:]!r}") from e
    if j.get("error") or "end" not in j or not j["end"]:
        raise TrafficError(f"iperf3 failed: {j.get('error', out[-300:])}")
    end = j["end"]
    sent = end.get("sum_sent") or end.get("sum") or {}
    recv = end.get("sum_received") or end.get("sum") or {}
    return FlowResult(name, port, int(sent.get("packets", 0)), float(recv.get("bits_per_second", 0)) / 1e6,
                      float(recv.get("jitter_ms", 0)), int(recv.get("lost_packets", 0)), j)


class RunningFlow:
    def __init__(self, proc, name: str, port: int):
        self.proc, self.name, self.port = proc, name, port

    def wait(self, timeout: float = 60) -> FlowResult:
        out, err = self.proc.communicate(timeout=timeout)
        return parse_iperf_json(out.decode(errors="replace") if isinstance(out, bytes) else out, self.name, self.port)


def start_flow(net, src: str = "h1", dst: str = "h2", port: int = NORMAL_PORT, mbps: float = 2,
               secs: float = 10, name: Optional[str] = None, tos: Optional[int] = None,
               length: int = UDP_PAYLOAD) -> RunningFlow:
    """Start an iperf3 UDP client (non-blocking). Starts the matching server on dst if needed."""
    start_iperf_server(net, dst, port)
    args = ["iperf3", "-c", net.get(dst).IP(), "-p", str(port), "-u", "-b", f"{mbps}M", "-t", str(secs),
            "-l", str(length), "-J"]
    if tos is not None:
        args += ["-S", str(tos)]
    proc = net.get(src).popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return RunningFlow(proc, name or f"{src}->{dst}:{port}", port)


def run_flow(net, **kw) -> FlowResult:
    return start_flow(net, **kw).wait(timeout=kw.get("secs", 10) + 30)


def start_critical(net, mbps: float = 2, secs: float = 10, **kw) -> RunningFlow:
    return start_flow(net, port=CRITICAL_PORT, mbps=mbps, secs=secs, name="critical", **kw)


def start_normal(net, mbps: float = 2, secs: float = 10, **kw) -> RunningFlow:
    return start_flow(net, port=NORMAL_PORT, mbps=mbps, secs=secs, name="normal", **kw)


# --------------------------------------------------------------------------- cross traffic (congestion)
class CrossTraffic:
    """Background UDP load pinned (via ToS) onto ONE path; runs until stop()."""

    def __init__(self, net, path_id: str, mbps: float, src: str = "h1", dst: str = "h2"):
        self.net, self.dst = net, dst
        self.path_id, self.mbps = path_id, mbps
        self.port = CROSS_PORT_BASE + list(topo.PATHS).index(path_id)
        start_iperf_server(net, dst, self.port)
        self.proc = net.get(src).popen(
            ["iperf3", "-c", net.get(dst).IP(), "-p", str(self.port), "-u", "-b", f"{mbps}M", "-t", "0",
             "-l", str(UDP_PAYLOAD), "-S", str(topo.PROBE_TOS[path_id])],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        stop_iperf_server(self.net, self.dst, self.port)


def stop_all_servers(net, host: str = "h2") -> None:
    for port in (CRITICAL_PORT, NORMAL_PORT, *(CROSS_PORT_BASE + i for i in range(len(topo.PATHS)))):
        stop_iperf_server(net, host, port)
