"""M3 - Adaptive duplication (Eqs. 3-4)."""
from math import prod
from typing import List, Tuple

from ampd import config
from ampd.common.types import ScoredPath


def r_total(scores: List[float]) -> float:
    """R_total(k) = 1 - prod(1 - R_i)."""
    return 1 - prod(1 - r for r in scores)


def min_k(ranked: List[ScoredPath], target: float, max_k: int = config.MAX_K) -> Tuple[int, float]:
    """k* = min{k : R_total(k) >= R_target}; ranked is best-first. Caps at available paths / max_k."""
    limit = min(len(ranked), max_k)
    for k in range(1, limit + 1):
        rt = r_total([p.score for p in ranked[:k]])
        if rt >= target:
            return k, rt
    return limit, r_total([p.score for p in ranked[:limit]])
