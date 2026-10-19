import pytest

from ampd.common.types import Path, PathMetrics, ScoredPath
from ampd.scoring.correlation import select_independent_weighted, weighted_independence
from ampd.scoring.path_selection import independence, select_independent
from ampd.scoring.reliability import reliability_score
from ampd.scoring.smoothing import SmoothedScorer

A = Path("A", ["s", "x", "m", "d"])
B = Path("B", ["s", "x", "n", "d"])   # shares link s-x with A
C = Path("C", ["s", "y", "m", "d"])   # shares link m-d with A


def test_uniform_weights_reduce_to_jaccard():
    assert weighted_independence(A, B) == pytest.approx(independence(A, B))


def test_flaky_shared_link_lowers_independence():
    flaky = {("s", "x"): 0.5}
    assert weighted_independence(A, B, flaky) < 0.2          # share the flaky link
    assert weighted_independence(A, C, flaky) > 0.9          # share only a stable link


def test_weighted_selection_rejects_flaky_overlap():
    m = PathMetrics()
    ranked = [ScoredPath(A, m, .9), ScoredPath(B, m, .85), ScoredPath(C, m, .8)]
    assert [s.path.id for s in select_independent(ranked, 0.5)] == ["A", "B", "C"]
    chosen = select_independent_weighted(ranked, {("s", "x"): 0.5}, 0.5)
    assert [s.path.id for s in chosen] == ["A", "C"]


def test_stable_metrics_give_raw_score():
    sc, m = SmoothedScorer(), PathMetrics(0.05, 30, 5, 0.3)
    for _ in range(5):
        r = sc.score_path(A, m)
    assert r.score == pytest.approx(reliability_score(m))


def test_spike_is_damped():
    sc = SmoothedScorer(alpha=0.3, trend_gain=0.0)
    sc.score_path(A, PathMetrics())
    bad = PathMetrics(loss=0.8, delay_ms=150, jitter_ms=40, utilization=0.9)
    assert sc.score_path(A, bad).score > reliability_score(bad)


def test_falling_trend_is_penalised():
    plain, trend = SmoothedScorer(trend_gain=0.0), SmoothedScorer(trend_gain=0.5)
    seq = [PathMetrics(), PathMetrics(0.1), PathMetrics(0.2)]
    for m in seq:
        p, t = plain.score_path(A, m), trend.score_path(A, m)
    assert t.score < p.score
