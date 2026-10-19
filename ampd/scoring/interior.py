"""M2 - Interior-link independence.

Every path between the same two hosts shares its first and last hop (the host access links), and
no routing choice can avoid that. Counting those links in Eq. 2 caps independence below 1 for even
perfectly disjoint paths (0.667 on our 3-path testbed) and makes I_MIN hard to interpret.
Here only the links between the two end switches (the part of the path we can actually choose) are compared.
"""
from typing import Dict, FrozenSet, Tuple

from ampd.common.types import Path
from ampd.scoring.correlation import Edge, weighted_independence


def interior_edges(p: Path) -> FrozenSet[Edge]:
    """Edges of p without its first hop and last hop."""
    core = p.nodes[1:-1]
    return frozenset(tuple(sorted(e)) for e in zip(core, core[1:]))


def interior_independence(p: Path, q: Path, link_fail: Dict[Edge, float] = None) -> float:
    """Failure-weighted Jaccard independence over interior links only.

    Falls back to the full-path measure when a path has no interior link (single-switch path).
    """
    a, b = Path(p.id, p.nodes[1:-1]), Path(q.id, q.nodes[1:-1])
    if not interior_edges(p) and not interior_edges(q):
        return weighted_independence(p, q, link_fail)
    return weighted_independence(a, b, link_fail)
