from ampd.common.types import Path, PathMetrics
from ampd.integration.controller import AMPDController
from ampd.monitoring.monitor import SimMonitor

PATHS = [Path("p", ["h1", "s1", "s2", "s5", "h2"]),
         Path("q", ["h1", "s1", "s3", "s5", "h2"]),
         Path("r", ["h1", "s1", "s4", "s5", "h2"])]
# NOTE: all three share edge h1-s1 and s5-h2; I(P,Q)=0.5 so I_MIN must be <= 0.5 (see config).


def _ctl():
    mon = SimMonitor({"p": PathMetrics(0.02, 20, 3, 0.4), "q": PathMetrics(0.05, 35, 6, 0.3),
                      "r": PathMetrics(0.10, 60, 10, 0.2)})
    return AMPDController(mon, PATHS)


def test_critical_duplicates_more_than_normal():
    c = _ctl()
    assert c.decide({"id": "1", "class": "critical"}).k >= c.decide({"id": "2", "class": "normal"}).k


def test_k_at_least_one():
    assert _ctl().decide({"id": "1", "class": "normal"}).k >= 1
