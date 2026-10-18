"""M2 - Reliability score engine (Eq. 1)."""
from typing import Dict

from ampd import config
from ampd.common.types import Path, PathMetrics, ScoredPath


def normalize(m: PathMetrics):
    clamp = lambda x: max(0.0, min(1.0, x))
    return (clamp(m.loss), clamp(m.delay_ms / config.MAX_DELAY_MS),
            clamp(m.jitter_ms / config.MAX_JITTER_MS), clamp(m.utilization), clamp(m.availability))


def reliability_score(m: PathMetrics, w: Dict[str, float] = None) -> float:
    """R_i = w1(1-L)+w2(1-D)+w3(1-J)+w4(1-C)+w5*A, weights sum to 1."""
    w = w or config.DEFAULT_WEIGHTS
    assert abs(sum(w.values()) - 1) < 1e-6, "weights must sum to 1"
    L, D, J, C, A = normalize(m)
    return (w["loss"] * (1 - L) + w["delay"] * (1 - D) + w["jitter"] * (1 - J)
            + w["congestion"] * (1 - C) + w["availability"] * A)


def score_path(path: Path, m: PathMetrics, w=None) -> ScoredPath:
    return ScoredPath(path, m, reliability_score(m, w))
