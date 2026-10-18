from ampd.common.types import Path, PathMetrics
from ampd.monitoring.monitor import SimMonitor


def test_sim_monitor_returns_profile():
    p = Path("a", ["h1", "s1", "h2"])
    m = SimMonitor({"a": PathMetrics(loss=0.1)})
    assert m.get_metrics(p).loss == 0.1
