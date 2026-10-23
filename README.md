# AMPD – Adaptive Multipath Packet Duplication using SDN

AMPD scores network paths using packet loss, delay, jitter, congestion, and availability; selects sufficiently independent paths; chooses the minimum duplication factor `k` needed to meet a reliability target; and evaluates the efficiency of redundant-copy cancellation.

**No Ryu or external controller framework is required.** The controller is plain Python. The optional emulated data plane uses Mininet + Open vSwitch (OVS) programmed with OpenFlow 1.3 rules through `ovs-ofctl`.

## Project layout

```text
ampd/
  common/types.py        Shared dataclasses
  config.py              Weights, targets, and thresholds (M4)
  monitoring/             Simulated and live telemetry (M1)
  emulation/              Mininet topology, NetEm, iPerf3, OVS flows (M1)
  scoring/                Reliability, independence, and path selection (M2)
  duplication/            Minimum-k selection, efficiency, cancellation (M3)
  integration/            Classifier, feedback, controller, entry point (M4)
experiments/              Analytical figures and baseline comparisons
tests/                    Unit tests and optional testbed tests
docs/TEAM_SPLIT.md        Team ownership and workflow
```

## Run the project (simulation — no Mininet required)

Run these commands from the **project root directory** (the folder containing `README.md`).

### 1. Check Python

Python 3.10+ is recommended.

```bash
python --version
```

On some Linux systems, use `python3` and `python3 -m` instead of `python`.

### 2. Create and activate a virtual environment (recommended)

**Linux / Ubuntu / WSL:**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

If creating the environment fails because `venv` is missing on Ubuntu/WSL:

```bash
sudo apt update
sudo apt install python3-venv python3-pip
```

**Windows PowerShell:**

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

### 3. Install Python dependencies

```bash
python -m pip install -r requirements.txt
```

### 4. Run the AMPD simulation

```bash
python -m ampd.integration.main --sim
```

This runs the controller against simulated path metrics and prints decisions for normal and critical traffic, including the chosen `k`, total reliability, and selected paths. It does **not** require Mininet or root privileges.

### 5. Generate analytical figures

```bash
python experiments/run_analytical.py
```

The figures are written to:

```text
results/fig3_reliability.png
results/fig4_overhead_efficiency.png
```

### 6. Run the test suite

```bash
pytest -q
```

The normal test suite should run without launching the Mininet testbed. The live testbed test is opt-in and is enabled with `AMPD_TESTBED=1` (see below).

### 7. Compare baseline strategies (optional)

```bash
python experiments/compare_strategies.py
```

Check the script's output for the comparison results.

## Run the Mininet + Open vSwitch testbed (Linux / Ubuntu / WSL)

The testbed requires Linux networking features and system packages. Run these commands in a Linux terminal, not ordinary Windows PowerShell. Use `sudo` for the Mininet commands.

### 1. Install system dependencies

```bash
sudo apt update
sudo apt install mininet openvswitch-switch iperf3 tshark ethtool iputils-ping
```

Start or restart OVS if necessary:

```bash
sudo service openvswitch-switch start
sudo ovs-vsctl show
```

### 2. Start the three-path topology

```bash
sudo python3 -m ampd.emulation.topology
```

This builds the topology, installs baseline forwarding flows, runs `pingAll`, and then stops the network. To open the Mininet CLI after the ping test:

```bash
sudo python3 -m ampd.emulation.topology --cli
```

If your environment does not have the OVS kernel module, try the userspace datapath:

```bash
sudo env AMPD_OVS_DATAPATH=user python3 -m ampd.emulation.topology --datapath user
```

### 3. Run testbed verification

```bash
sudo python3 -m ampd.emulation.verify
```

To run the optional live testbed test, from the project root:

```bash
sudo env AMPD_TESTBED=1 python3 -m pytest -q tests/test_m1_testbed.py
```

The testbed test requires the system packages above and may need root privileges to create network namespaces and configure OVS.

### 4. Clean up Mininet after a failed run

```bash
sudo mn -c
```

If OVS appears stuck, restart it:

```bash
sudo /usr/share/openvswitch/scripts/ovs-ctl restart
```

For additional testbed notes, see [`ampd/emulation/README.md`](ampd/emulation/README.md).

## Troubleshooting

- **`ModuleNotFoundError: No module named 'ampd'`** — run the command from the project root, with the virtual environment activated.
- **`pytest: command not found`** — activate the virtual environment and run `python -m pip install -r requirements.txt`; then use `python -m pytest -q`.
- **Missing `matplotlib` or `networkx`** — install dependencies with `python -m pip install -r requirements.txt`.
- **Mininet/OVS errors on Windows** — run the testbed in a Linux VM or WSL environment with the required privileges; the simulation mode works on Windows.
- **`NetEm` commands fail** — try `sudo modprobe sch_netem`. NetEm requires kernel support.

## Team ownership

See [`docs/TEAM_SPLIT.md`](docs/TEAM_SPLIT.md) for module ownership and collaboration workflow.
