"""M2 extra feature 2 - Smoothed, trend-aware reliability score.

EWMA smoothing stops one noisy measurement from flipping the path ranking.
A trend penalty lowers the score of a path whose reliability is falling, so the
controller reacts to degradation before the raw score collapses.
"""
from typing import Dict

from ampd.common.types import Path, PathMetrics, ScoredPath
from ampd.scoring.reliability import reliability_score


class SmoothedScorer:
    def __init__(self, alpha: float = 0.3, trend_gain: float = 0.5):
        self.alpha = alpha            # weight of the newest measurement (0..1)
        self.trend_gain = trend_gain  # how strongly a falling trend is penalised
        self.prev: Dict[str, float] = {}

    def score_path(self, path: Path, m: PathMetrics, w=None) -> ScoredPath:
        raw = reliability_score(m, w)
        old = self.prev.get(path.id, raw)
        smooth = self.alpha * raw + (1 - self.alpha) * old
        trend = smooth - old                      # < 0 means getting worse
        self.prev[path.id] = smooth
        score = smooth + self.trend_gain * min(trend, 0.0)
        return ScoredPath(path, m, max(0.0, min(1.0, score)))
