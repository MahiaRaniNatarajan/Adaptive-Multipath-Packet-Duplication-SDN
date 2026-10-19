"""Full Mininet/OVS testbed run. Skipped unless root + Mininet + OVS are available.

    sudo AMPD_TESTBED=1 [AMPD_OVS_DATAPATH=user] pytest -q tests/test_m1_testbed.py
"""
import os
import shutil

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("AMPD_TESTBED") != "1" or os.geteuid() != 0 or not shutil.which("ovs-ofctl"),
    reason="set AMPD_TESTBED=1 and run as root on a box with Mininet + Open vSwitch")


def test_testbed_end_to_end(tmp_path):
    from ampd.emulation import topology as topo, traffic, verify
    net = topo.build_network()
    topo.start_network(net)
    try:
        results = verify.run(net, str(tmp_path))
    finally:
        traffic.stop_all_servers(net)
        net.stop()
    failed = [r for r in results if r[1] == verify.FAIL]
    assert not failed, failed
