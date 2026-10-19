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
    if not ranked:
        raise ValueError("No paths available")
    limit = min(len(ranked), max_k)
    for k in range(1, limit + 1):
        rt = r_total([p.score for p in ranked[:k]])
        if rt >= target:
            return k, rt
    return limit, r_total([p.score for p in ranked[:limit]])


def min_k_with_budget(
    ranked: List[ScoredPath],
    target: float,
    extra_byte_budget: int,
    max_k: int = config.MAX_K,
    packet_size: int = config.PACKET_SIZE,
) -> Tuple[int, float]:
    """Choose the smallest affordable k, prioritizing the reliability target.

    Extra overhead is (k - 1) * packet_size.
    If the target is unreachable within the budget, return the
    most reliable affordable option.
    """
    if not ranked:
        raise ValueError("No paths available")
    if extra_byte_budget < 0:
        raise ValueError("Budget cannot be negative")
    if packet_size <= 0:
        raise ValueError("Packet size must be positive")
    if max_k < 1:
        raise ValueError("max_k must be at least 1")

    limit = min(len(ranked), max_k)
    affordable_k = min(limit, 1 + extra_byte_budget // packet_size)

    for k in range(1, affordable_k + 1):
        rt = r_total([p.score for p in ranked[:k]])
        if rt >= target:
            return k, rt

    return affordable_k, r_total([p.score for p in ranked[:affordable_k]])