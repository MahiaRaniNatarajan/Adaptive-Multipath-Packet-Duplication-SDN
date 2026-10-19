"""M2 extra feature 1 - Correlation-aware (failure-weighted) path independence.

Plain Jaccard (Eq. 2) treats every shared link equally. Here each link carries a failure
probability, so sharing a flaky link makes two paths LESS independent than sharing a stable one.
With uniform weights this reduces exactly to Eq. 2.
"""
from typing import Dict, List, Tuple

from ampd import config
from ampd.common.types import Path, ScoredPath

Edge = Tuple[str, str]
DEFAULT_LINK_FAIL = 0.01


def _w(edges, link_fail: Dict[Edge, float]) -> float:
    return sum(link_fail.get(tuple(sorted(e)), DEFAULT_LINK_FAIL) for e in edges)


def weighted_independence(p: Path, q: Path, link_fail: Dict[Edge, float] = None) -> float:
    """I_w(P,Q) = 1 - W(E_P ∩ E_Q) / W(E_P ∪ E_Q), W = sum of link failure probabilities."""
    link_fail = link_fail or {}
    union = _w(p.edges | q.edges, link_fail)
    return 1.0 if union == 0 else 1 - _w(p.edges & q.edges, link_fail) / union


def select_independent_weighted(ranked: List[ScoredPath], link_fail: Dict[Edge, float] = None,
                                i_min: float = config.I_MIN) -> List[ScoredPath]:
    """Greedy best-score-first, keeping a path only if failure-weighted independent of all kept."""
    chosen: List[ScoredPath] = []
    for sp in sorted(ranked, key=lambda s: s.score, reverse=True):
        if all(weighted_independence(sp.path, c.path, link_fail) >= i_min for c in chosen):
            chosen.append(sp)
    return chosen
