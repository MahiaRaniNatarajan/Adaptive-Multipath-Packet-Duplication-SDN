"""M1 - Packet capture (Wireshark's tshark, or tcpdump) + duplicate analysis.

Capture writes classic .pcap files that open directly in Wireshark.  Analysis is done by a small
pure-Python pcap reader (no tshark parsing needed) that extracts iperf3's UDP sequence number
(payload bytes 8..12) so we can count how many copies of each packet arrived.

    with Capture(net, "h2", "h2-eth0", "/tmp/rx.pcap", "udp dst port 5001"):
        ...run traffic...
    report = analyze_delivery(read_seq_counts("/tmp/tx.pcap"), read_seq_counts("/tmp/rx.pcap"))
    report.copies            # {3: 170}  -> every packet arrived exactly 3 times  => k = 3 confirmed
    report.delivered_ratio   # unique packets delivered / unique packets sent     => feeds M4 finish()

Wireshark cross-check:  tshark -r /tmp/rx.pcap -T fields -e ip.id -e udp.dstport | sort | uniq -c
(identical ip.id repeated k times = k duplicate copies; or filter `udp.port==5001` in the GUI).
"""
import os
import shutil
import signal
import struct
import subprocess
import time
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional


# --------------------------------------------------------------------------- capture process
class Capture:
    def __init__(self, net, node: str, iface: str, pcap: str, bpf: str = "udp",
                 snaplen: int = 200, tool: Optional[str] = None):
        self.node, self.iface, self.pcap, self.bpf, self.snaplen = net.get(node), iface, pcap, bpf, snaplen
        self.tool = tool or ("tshark" if shutil.which("tshark") else "tcpdump")
        if not shutil.which(self.tool):
            raise RuntimeError(f"{self.tool} not found; install wireshark-common/tshark or tcpdump")
        self.proc = None

    def _cmd(self) -> List[str]:
        if self.tool == "tshark":
            return ["tshark", "-q", "-i", self.iface, "-f", self.bpf, "-s", str(self.snaplen), "-F", "pcap", "-w", self.pcap]
        return ["tcpdump", "-n", "-U", "-i", self.iface, "-s", str(self.snaplen), "-w", self.pcap, self.bpf]

    def start(self) -> "Capture":
        if os.path.exists(self.pcap):
            os.remove(self.pcap)
        self.proc = self.node.popen(self._cmd(), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        for _ in range(50):  # file appears once the capture is live
            if os.path.exists(self.pcap):
                break
            if self.proc.poll() is not None:
                raise RuntimeError(f"{self.tool} exited early: {self.proc.stderr.read().decode(errors='replace')[-300:]}")
            time.sleep(0.1)
        time.sleep(0.3)
        return self

    def stop(self) -> str:
        if self.proc and self.proc.poll() is None:
            time.sleep(0.3)  # let in-flight packets reach the buffer
            self.proc.send_signal(signal.SIGINT)
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        return self.pcap

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()


# --------------------------------------------------------------------------- pcap reading
@dataclass
class UdpPacket:
    ts: float
    sport: int
    dport: int
    ip_id: int
    payload: bytes

    @property
    def seq(self) -> Optional[int]:
        """iperf3 UDP packet counter (32-bit, after 4 B sec + 4 B usec)."""
        return struct.unpack(">I", self.payload[8:12])[0] if len(self.payload) >= 12 else None


def read_udp_packets(path: str) -> List[UdpPacket]:
    data = open(path, "rb").read()
    if len(data) < 24:
        return []
    magic = data[:4]
    if magic == b"\x0a\x0d\x0d\x0a":
        raise ValueError(f"{path} is pcapng; capture with `-F pcap` (Capture does this for you)")
    if magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1"):
        en = "<"
    elif magic in (b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d"):
        en = ">"
    else:
        raise ValueError(f"{path}: not a pcap file")
    tdiv = 1e9 if magic in (b"\x4d\x3c\xb2\xa1", b"\xa1\xb2\x3c\x4d") else 1e6
    link = struct.unpack(en + "I", data[20:24])[0] & 0x0FFFFFFF
    out, off = [], 24
    while off + 16 <= len(data):
        sec, frac, caplen, _ = struct.unpack(en + "IIII", data[off:off + 16])
        frame, off = data[off + 16:off + 16 + caplen], off + 16 + caplen
        if link == 1:      # Ethernet (+ optional 802.1Q tag)
            if len(frame) < 14:
                continue
            et, ip = struct.unpack(">H", frame[12:14])[0], 14
            if et == 0x8100 and len(frame) >= 18:
                et, ip = struct.unpack(">H", frame[16:18])[0], 18
            if et != 0x0800:
                continue
            ip_off = ip
        elif link == 113:  # Linux cooked
            ip_off = 16
        elif link == 101:  # raw IP
            ip_off = 0
        else:
            raise ValueError(f"unsupported pcap link type {link}")
        p = frame[ip_off:]
        if len(p) < 28 or p[0] >> 4 != 4 or p[9] != 17:
            continue
        ihl = (p[0] & 0x0F) * 4
        if len(p) < ihl + 8 or (struct.unpack(">H", p[6:8])[0] & 0x1FFF):  # skip non-first fragments
            continue
        sport, dport, ulen = struct.unpack(">HHH", p[ihl:ihl + 6])
        out.append(UdpPacket(sec + frac / tdiv, sport, dport, struct.unpack(">H", p[4:6])[0],
                             p[ihl + 8:ihl + ulen]))
    return out


def read_seq_counts(path: str, dport: Optional[int] = None) -> Counter:
    """Counter {iperf3 sequence number: copies seen} for UDP packets (optionally to one port)."""
    return Counter(p.seq for p in read_udp_packets(path)
                   if p.seq is not None and (dport is None or p.dport == dport))


# --------------------------------------------------------------------------- analysis
@dataclass
class DeliveryReport:
    sent: int                 # unique packets seen at the sender
    delivered: int            # of those, how many arrived at least once
    arrivals: int             # total packets (all copies) seen at the receiver
    copies: Dict[int, int]    # histogram: copies-per-packet -> number of packets

    @property
    def delivered_ratio(self) -> float:
        return self.delivered / self.sent if self.sent else 0.0

    @property
    def mean_copies(self) -> float:
        return self.arrivals / self.delivered if self.delivered else 0.0

    @property
    def duplicates_confirmed(self) -> bool:
        return any(c > 1 for c in self.copies)


def analyze_delivery(sent: Counter, received: Counter) -> DeliveryReport:
    """Compare sender-side and receiver-side sequence counters."""
    got = {s: n for s, n in received.items() if s in sent}
    return DeliveryReport(sent=len(sent), delivered=len(got), arrivals=sum(got.values()),
                          copies=dict(sorted(Counter(got.values()).items())))
