import pytest

from ampd.common.types import Path, PathMetrics, ScoredPath
from ampd.duplication.adaptive import min_k, r_total
from ampd.duplication.cancellation import marginal_efficiency, overhead, should_cancel


def _sp(s):
    return ScoredPath(Path("x", ["a", "b"]), PathMetrics(), s)


def test_r_total_matches_paper_fig3():
    assert r_total([0.9, 0.9]) == pytest.approx(0.99)
    assert r_total([0.9] * 3) == pytest.approx(0.999)


def test_min_k_stops_early():
    k, _ = min_k([_sp(0.9999), _sp(0.9)], 0.999)
    assert k == 1


def test_min_k_needs_three():
    k, rt = min_k([_sp(0.9)] * 3, 0.999)
    assert k == 3 and rt >= 0.999 - 1e-9


def test_overhead_and_cancel():
    assert overhead(3, 1500) == 3000
    assert should_cancel(marginal_efficiency(0.999, 0.9991, 3), tau=1e-6)
