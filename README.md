# AMPD – Adaptive Multipath Packet Duplication using SDN

SDN-based adaptive multipath duplication: score paths (loss, delay, jitter, congestion, availability),
select independent paths, duplicate with the minimum k meeting a reliability target, cancel redundant copies.

**No Ryu / external controller framework.** The controller is plain Python; the data plane is
Mininet + Open vSwitch programmed through OpenFlow 1.3 group tables via `ovs-ofctl`.

## Layout
```
ampd/
  common/types.py        shared dataclasses (all)
  config.py              weights, targets, thresholds (M4 – Nanthini)
  monitoring/            M1  telemetry (SimMonitor, LiveMonitor)
  emulation/             M1  Mininet topology, NetEm, iPerf3, OVS flows
  scoring/               M2  Eq.1 reliability score, Eq.2 independence, path selection
  duplication/           M3  Eq.3-4 min-k, Eq.5 efficiency & cancellation
  integration/           M4  classifier, feedback, controller, main
experiments/             M4  analytical figures / baselines
tests/                   one test file per module
docs/TEAM_SPLIT.md       who owns what
```

## Quick start
```bash
pip install -r requirements.txt
python -m ampd.integration.main --sim       # runs without Mininet
python experiments/run_analytical.py        # Figs. 3-4 -> results/
pytest -q
```
Testbed (Linux, root): `sudo apt install mininet openvswitch-switch iperf3` then `sudo python -m ampd.emulation.topology`.

See [docs/TEAM_SPLIT.md](docs/TEAM_SPLIT.md) for ownership and workflow.
