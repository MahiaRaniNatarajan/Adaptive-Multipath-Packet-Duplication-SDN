"""M2 - PathSelector: one call that does the whole scoring-and-selection stage.

  metrics -> class weights -> smoothed trend-aware score -> gate dead paths -> delay-skew filter
          -> hysteresis bonus for incumbent paths -> greedy selection by interior, failure-weighted
             independence

Returns List[ScoredPath] best-first, the same type select_independent() returns, so M3/M4 code that
consumes it does not change. Dead paths are never returned.

M4 integration (two lines in AMPDController.decide):
    self.selector = PathSelector(link_fail=...)                      # in __init__
    independent = self.selector.select(self.paths, self.monitor.get_metrics, cls)
"""
from dataclasses import replace
from typing import Callable, Dict, List

from ampd import config
from ampd.common.types import Path, PathMetrics, ScoredPath
from ampd.scoring.gating import is_usable, skew_filter
from ampd.scoring.interior import interior_independence
from ampd.scoring.presets import weights_for
from ampd.scoring.smoothing import SmoothedScorer


def calibrate(selected: List[ScoredPath]) -> List[ScoredPath]:
    """Copies of `selected` whose score is the measured delivery probability availability*(1-loss).

    Eq. 3 (R_total = 1 - prod(1 - R_i)) is only a probability if each R_i is one. Eq. 1 is a quality
    index (a 30% loss path still scores ~0.82), so feed THESE to min_k if the team wants R_total to
    mean "probability at least one copy arrives".
    """
    return [replace(s, score=s.metrics.availability * (1.0 - s.metrics.loss)) for s in selected]


class PathSelector:
    def __init__(self, link_fail: Dict = None, i_min: float = config.I_MIN, alpha: float = 0.3,
                 trend_gain: float = 0.5, margin: float = 0.05, max_loss: float = 0.5,
                 skew_ratio: float = 2.0):
        self.link_fail, self.i_min, self.margin = link_fail, i_min, margin
        self.max_loss, self.skew_ratio = max_loss, skew_ratio
        self.alpha, self.trend_gain = alpha, trend_gain
        self._scorers: Dict[str, SmoothedScorer] = {}   # one per traffic class (weights differ)
        self._held: Dict[str, List[str]] = {}           # previous selection, best-first, per traffic class

    def select(self, paths: List[Path], metrics_fn: Callable[[Path], PathMetrics],
               traffic_class: str = "normal") -> List[ScoredPath]:
        w = weights_for(traffic_class)
        scorer = self._scorers.setdefault(traffic_class, SmoothedScorer(self.alpha, self.trend_gain))
        held = self._held.get(traffic_class, [])

        scored: List[ScoredPath] = []
        for p in paths:
            m = metrics_fn(p)
            if not is_usable(m, self.max_loss):
                scorer.prev.pop(p.id, None)        # restart smoothing when the path recovers
                continue
            scored.append(scorer.score_path(p, m, w))

        scored = skew_filter(scored, self.skew_ratio)
        # Incumbent bonus is rank-weighted: the previous best path gets the full margin, the next a
        # little less, and so on, so both membership and ORDER resist tiny score changes.
        n = len(held)
        bonus = {pid: self.margin * (n - i) / n for i, pid in enumerate(held)}
        bonus = {s.path.id: bonus.get(s.path.id, 0.0) for s in scored}
        order = sorted(scored, key=lambda s: s.score + bonus[s.path.id], reverse=True)

        chosen: List[ScoredPath] = []
        for sp in order:
            if all(interior_independence(sp.path, c.path, self.link_fail) >= self.i_min for c in chosen):
                chosen.append(sp)

        self._held[traffic_class] = [s.path.id for s in chosen]
        return chosen
