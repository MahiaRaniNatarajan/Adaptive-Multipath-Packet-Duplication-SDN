import pytest

from ampd import config
from ampd.common.types import Path, PathMetrics, ScoredPath
from ampd.monitoring.monitor import SimMonitor
from ampd.scoring.gating import filter_usable, is_usable, skew_filter
from ampd.scoring.interior import interior_independence
from ampd.scoring.path_selection import independence
from ampd.scoring.pipeline import PathSelector, calibrate
from ampd.scoring.presets import CLASS_WEIGHTS, weights_for
from ampd.scoring.reliability import reliability_score

# the real 3-path testbed
PRI = Path("primary", ["h1", "s1", "s2", "s5", "h2"])
SEC = Path("secondary", ["h1", "s1", "s3", "s5", "h2"])
BAK = Path("backup", ["h1", "s1", "s4", "s5", "h2"])
PATHS = [PRI, SEC, BAK]

GOOD = PathMetrics(0.02, 20, 3, 0.4)
OK = PathMetrics(0.05, 30, 5, 0.3)
WEAK = PathMetrics(0.10, 40, 8, 0.2)
# what LiveMonitor returns for a path with no replies
DEAD = PathMetrics(1.0, config.MAX_DELAY_MS, config.MAX_JITTER_MS, 0.0, 0.0)


def _sel(profiles, cls="normal", selector=None):
    sel = selector or PathSelector()
    mon = SimMonitor(dict(profiles))
    return sel.select(PATHS, mon.get_metrics, cls), sel


# ---- the bug this fixes -------------------------------------------------------
def test_eq1_alone_rates_a_dead_path_above_zero():
    assert reliability_score(DEAD) == pytest.approx(0.2)


def test_dead_path_is_never_selected():
    chosen, _ = _sel({"primary": DEAD, "secondary": OK, "backup": WEAK})
    assert [s.path.id for s in chosen] == ["secondary", "backup"]


def test_all_dead_gives_empty_selection():
    chosen, _ = _sel({"primary": DEAD, "secondary": DEAD, "backup": DEAD})
    assert chosen == []


# ---- gating -------------------------------------------------------------------
def test_is_usable_thresholds():
    assert is_usable(OK)
    assert not is_usable(DEAD)
    assert not is_usable(PathMetrics(loss=0.6))
    assert not is_usable(PathMetrics(loss=0.0, availability=0.0))


def test_skew_filter_drops_late_path_but_keeps_small_gaps():
    m = PathMetrics
    sp = lambda pid, d: ScoredPath(Path(pid, ["a", "b"]), m(0, d, 0, 0), 0.9)
    kept = skew_filter([sp("f", 10), sp("close", 25), sp("late", 80)])
    assert [s.path.id for s in kept] == ["f", "close"]        # 25 <= max(20, 30); 80 > 30
    assert len(skew_filter([sp("a", 3), sp("b", 7)])) == 2    # 4 ms gap is not "skew"
    assert skew_filter([]) == []


def test_filter_usable():
    s = [ScoredPath(PRI, DEAD, 0.2), ScoredPath(SEC, OK, 0.9)]
    assert [x.path.id for x in filter_usable(s)] == ["secondary"]


# ---- interior independence ----------------------------------------------------
def test_interior_ignores_shared_host_links():
    assert independence(PRI, SEC) == pytest.approx(2 / 3)     # capped by unavoidable shared links
    assert interior_independence(PRI, SEC) == 1.0
    assert interior_independence(PRI, PRI) == 0.0


def test_interior_detects_a_real_shared_core_link():
    a = Path("a", ["h1", "s1", "s2", "s3", "s5", "h2"])
    b = Path("b", ["h1", "s1", "s2", "s4", "s5", "h2"])        # shares s1-s2
    assert interior_independence(a, b) < 1.0
    assert interior_independence(a, b, {("s1", "s2"): 0.5}) < interior_independence(a, b)


# ---- presets ------------------------------------------------------------------
def test_presets_sum_to_one_and_critical_prefers_loss():
    for w in CLASS_WEIGHTS.values():
        assert sum(w.values()) == pytest.approx(1.0)
    assert weights_for("critical")["loss"] > weights_for("normal")["loss"]
    assert weights_for("unknown") == config.DEFAULT_WEIGHTS


def test_lossy_path_ranks_lower_for_critical_than_normal():
    lossy = PathMetrics(loss=0.30, delay_ms=10, jitter_ms=1, utilization=0.1)
    slow = PathMetrics(loss=0.0, delay_ms=60, jitter_ms=12, utilization=0.5)
    wc, wn = weights_for("critical"), weights_for("normal")
    assert reliability_score(lossy, wc) < reliability_score(slow, wc)
    assert reliability_score(lossy, wn) > reliability_score(slow, wn)


# ---- hysteresis ---------------------------------------------------------------
def test_hysteresis_keeps_incumbent_on_tiny_difference():
    two = [PRI, SEC]
    sel = PathSelector(i_min=0.5, alpha=1.0, trend_gain=0.0, margin=0.05)
    mon = SimMonitor({"primary": PathMetrics(0.02, 20, 3, 0.4), "secondary": PathMetrics(0.02, 20, 3, 0.4)})
    first = sel.select(two, mon.get_metrics)
    mon.set_profile("secondary", PathMetrics(0.019, 20, 3, 0.4))   # marginally better
    second = sel.select(two, mon.get_metrics)
    assert [s.path.id for s in second] == [s.path.id for s in first]


def test_hysteresis_switches_on_clear_improvement():
    sel = PathSelector(i_min=0.5, alpha=1.0, trend_gain=0.0, margin=0.05)
    mon = SimMonitor({"primary": OK, "secondary": WEAK, "backup": WEAK})
    first, _ = _sel({"primary": OK, "secondary": WEAK, "backup": WEAK}, selector=sel)
    assert first[0].path.id == "primary"
    mon.set_profile("primary", WEAK)
    mon.set_profile("secondary", PathMetrics(0.0, 10, 1, 0.1))     # far better
    second = sel.select(PATHS, mon.get_metrics)
    assert second[0].path.id == "secondary"


# ---- calibration & contract ---------------------------------------------------
def test_calibrate_gives_delivery_probability():
    chosen, _ = _sel({"primary": GOOD, "secondary": OK, "backup": WEAK})
    cal = calibrate(chosen)
    assert cal[0].score == pytest.approx(1 - chosen[0].metrics.loss)
    assert [c.path.id for c in cal] == [s.path.id for s in chosen]
    assert chosen[0].score != cal[0].score                         # originals untouched


def test_output_is_best_first_scoredpaths():
    chosen, _ = _sel({"primary": WEAK, "secondary": PathMetrics(0.0, 10, 1, 0.1), "backup": OK})
    assert all(isinstance(s, ScoredPath) for s in chosen)
    assert chosen[0].path.id == "secondary"
