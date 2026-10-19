"""M2 - Path gating: drop paths that must never carry a duplicate.

1. Dead / near-dead paths. LiveMonitor reports a dead path as loss=1, delay/jitter at the ceilings,
   availability=0. Eq. 1 still gives such a path ~0.2 (its congestion term), so without a gate a dead
   path can be "selected" and a copy is sent into a black hole.
2. Delay skew. A duplicate that arrives long after the first copy adds overhead but no reliability,
   so paths much slower than the fastest usable path are dropped.
"""
from typing import List

from ampd.common.types import PathMetrics, ScoredPath


def is_usable(m: PathMetrics, max_loss: float = 0.5) -> bool:
    return m.availability > 0 and m.loss < max_loss


def filter_usable(scored: List[ScoredPath], max_loss: float = 0.5) -> List[ScoredPath]:
    return [s for s in scored if is_usable(s.metrics, max_loss)]


def skew_filter(scored: List[ScoredPath], max_ratio: float = 2.0, min_gap_ms: float = 20.0) -> List[ScoredPath]:
    """Keep a path if delay <= max(max_ratio * fastest, fastest + min_gap_ms).

    min_gap_ms stops tiny absolute differences (3 ms vs 7 ms) from counting as 'skewed'.
    """
    if not scored:
        return []
    fastest = min(s.metrics.delay_ms for s in scored)
    limit = max(max_ratio * fastest, fastest + min_gap_ms)
    return [s for s in scored if s.metrics.delay_ms <= limit]
