"""M1 - Data-plane programming WITHOUT a controller framework.

Duplication is implemented with OpenFlow 1.3 via `ovs-ofctl`: an ALL-type group on the
ingress switch whose buckets output to each selected path's first hop. Changing k = rewriting
the group. Called by M4's controller through `apply_duplication()`.
"""
import subprocess
from typing import List


def _run(*args):
    subprocess.run(args, check=True)


def apply_duplication(switch: str, in_port: int, out_ports: List[int], group_id: int = 1) -> None:
    """Replicate packets arriving on in_port to every port in out_ports (k copies)."""
    buckets = ",".join(f"bucket=output:{p}" for p in out_ports)
    _run("ovs-ofctl", "-O", "OpenFlow13", "del-groups", switch, f"group_id={group_id}")
    _run("ovs-ofctl", "-O", "OpenFlow13", "add-group", switch, f"group_id={group_id},type=all,{buckets}")
    _run("ovs-ofctl", "-O", "OpenFlow13", "add-flow", switch, f"priority=100,in_port={in_port},actions=group:{group_id}")


def cancel_duplicates(switch: str, in_port: int, keep_port: int, group_id: int = 1) -> None:
    """Smart Duplicate Cancellation: collapse back to a single output."""
    apply_duplication(switch, in_port, [keep_port], group_id)
