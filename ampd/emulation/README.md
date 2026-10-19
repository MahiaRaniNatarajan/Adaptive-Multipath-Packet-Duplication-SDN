# M1 testbed (Sandhiya) - run guide

```bash
sudo apt install mininet openvswitch-switch iperf3 tshark ethtool iputils-ping   # tshark = Wireshark CLI
sudo python -m ampd.emulation.topology            # build 3-path topology + pingAll (add --cli for Mininet CLI)
sudo python -m ampd.emulation.verify              # full checklist, PASS/FAIL per task; pcaps -> /tmp/ampd-pcaps
sudo AMPD_TESTBED=1 pytest -q tests/test_m1_testbed.py
```
No `openvswitch` kernel module (container / minimal VM)? add `--datapath user` (or `AMPD_OVS_DATAPATH=user`).
No NetEm (`tc qdisc add ... netem` fails)? `sudo modprobe sch_netem`; verify SKIPs those 4 checks until then.
If OVS is wedged after `mn -c`: `sudo /usr/share/openvswitch/scripts/ovs-ctl restart`.

| File | Task |
|---|---|
| `monitoring/live_monitor.py`, `monitoring/ovs_stats.py` | 1. LiveMonitor: per-path probes + utilization from `dump-ports` |
| `emulation/topology.py` | 2. 3-path topology, `start_network()` (static ARP + flows so pingAll works) |
| `emulation/netem.py` | 3. loss / delay / jitter / congestion / link_failure (`scenario(...)`, `apply_profile`) |
| `emulation/traffic.py`, `emulation/capture.py` | 4. iperf3 critical(5001) vs normal(5201); tshark capture + duplicate analysis |
| `emulation/flows.py` | 5. OVS ALL-group duplication; `OVSDataPlane.apply` plugs into `AMPDController(apply_fn=...)` |

Wiring for M4: `ctl = AMPDController(LiveMonitor(net), paths, apply_fn=OVSDataPlane(net).apply)`.

Gotchas: iperf3's own loss/packet counts are wrong under duplication (use `capture.analyze_delivery`);
iperf3's TCP control channel uses the primary path, so don't fail primary while measuring with iperf3.
