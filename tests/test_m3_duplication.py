import pytest

from ampd.common.types import Path, PathMetrics, ScoredPath
from ampd.duplication.adaptive import min_k, min_k_with_budget, r_total
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

def test_min_k_when_target_is_unreachable():
    ranked = [_sp(0.8), _sp(0.8)]
    k, rt = min_k(ranked, target=0.999, max_k=2)
    assert k == 2
    assert rt == pytest.approx(0.96)
def test_marginal_efficiency_matches_eq5():
    eta = marginal_efficiency(0.9, 0.99, k=2, packet_size=1500)
    assert eta == pytest.approx(0.00006)


def test_marginal_efficiency_zero_gain():
    eta = marginal_efficiency(0.99, 0.99, k=3, packet_size=1500)
    assert eta == pytest.approx(0.0)


def test_should_cancel_below_tau():
    assert should_cancel(eta=1e-7, tau=1e-6)


def test_should_not_cancel_above_tau():
    assert not should_cancel(eta=2e-6, tau=1e-6)


def test_should_cancel_when_delivered():
    assert should_cancel(eta=2e-6, tau=1e-6, delivered=True)

def test_min_k_raises_error_when_no_paths_available():
    with pytest.raises(ValueError, match="No paths available"):
        min_k([], target=0.999)


def test_budget_allows_two_copies():
    k, rt = min_k_with_budget(
        [_sp(0.9), _sp(0.9), _sp(0.9)],
        target=0.999,
        extra_byte_budget=1500,
    )
    assert k == 2
    assert rt == pytest.approx(0.99)


def test_budget_allows_three_copies():
    k, rt = min_k_with_budget(
        [_sp(0.9), _sp(0.9), _sp(0.9)],
        target=0.999,
        extra_byte_budget=3000,
    )
    assert k == 3
    assert rt == pytest.approx(0.999)


def test_budget_reports_unreachable_target():
    k, rt = min_k_with_budget(
        [_sp(0.8), _sp(0.8), _sp(0.8)],
        target=0.999,
        extra_byte_budget=1500,
    )
    assert k == 2
    assert rt == pytest.approx(0.96)
