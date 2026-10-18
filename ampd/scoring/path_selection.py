"""M2 - Independent path selection (Eq. 2, Jaccard link overlap)."""
from itertools import islice
from typing import List

import networkx as nx

from ampd import config
from ampd.common.types import Path, ScoredPath


def independence(p: Path, q: Path) -> float:
    """I(P,Q) = 1 - |E_P ∩ E_Q| / |E_P ∪ E_Q|."""
    union = p.edges | q.edges
    return 1.0 if not union else 1 - len(p.edges & q.edges) / len(union)


def candidate_paths(g: nx.Graph, src: str, dst: str, limit: int = 8) -> List[Path]:
    gen = nx.shortest_simple_paths(g, src, dst)
    return [Path(f"p{i}", nodes) for i, nodes in enumerate(islice(gen, limit))]


def select_independent(ranked: List[ScoredPath], i_min: float = config.I_MIN) -> List[ScoredPath]:
    """Greedy: walk paths best-score-first, keep a path only if independent of all kept ones."""
    chosen: List[ScoredPath] = []
    for sp in sorted(ranked, key=lambda s: s.score, reverse=True):
        if all(independence(sp.path, c.path) >= i_min for c in chosen):
            chosen.append(sp)
    return chosen
