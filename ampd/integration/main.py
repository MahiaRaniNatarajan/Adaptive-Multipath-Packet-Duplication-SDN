"""M4 - Entry point. `python -m ampd.integration.main --sim` runs without Mininet."""
import argparse

from ampd.common.types import Path, PathMetrics
from ampd.integration.controller import AMPDController
from ampd.monitoring.monitor import SimMonitor


def run_sim():
    paths = [Path("primary", ["h1", "s1", "s2", "s5", "h2"]),
             Path("secondary", ["h1", "s1", "s3", "s5", "h2"]),
             Path("backup", ["h1", "s1", "s4", "s5", "h2"])]
    mon = SimMonitor({
        "primary": PathMetrics(0.02, 20, 3, 0.4),
        "secondary": PathMetrics(0.05, 35, 6, 0.3),
        "backup": PathMetrics(0.10, 60, 10, 0.2)})
    ctl = AMPDController(mon, paths)
    for cls in ("normal", "critical"):
        d = ctl.decide({"id": f"flow-{cls}", "class": cls})
        print(f"{cls:9s} -> k={d.k} R_total={d.r_total:.4f} paths={[p.path.id for p in d.paths]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", action="store_true", default=True)
    ap.parse_args()
    run_sim()
