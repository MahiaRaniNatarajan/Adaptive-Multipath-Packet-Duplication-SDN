import pytest

from ampd.common.types import Path, PathMetrics, ScoredPath
from ampd.scoring.path_selection import independence, select_independent
from ampd.scoring.reliability import reliability_score


def test_perfect_path_scores_one():
    assert reliability_score(PathMetrics()) == pytest.approx(1.0)


def test_loss_lowers_score():
    assert reliability_score(PathMetrics(loss=0.5)) < reliability_score(PathMetrics(loss=0.1))


def test_independence_disjoint_and_identical():
    a = Path("a", ["s", "x", "d"]); b = Path("b", ["s", "y", "d"])
    assert independence(a, b) == 1.0 and independence(a, a) == 0.0


def test_select_drops_overlapping():
    a = Path("a", ["s", "x", "d"]); a2 = Path("a2", ["s", "x", "d"]); b = Path("b", ["s", "y", "d"])
    m = PathMetrics()
    sel = select_independent([ScoredPath(a, m, .9), ScoredPath(a2, m, .8), ScoredPath(b, m, .7)])
    assert [s.path.id for s in sel] == ["a", "b"]
