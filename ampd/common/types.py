"""Shared data contracts. ALL members import from here. Change only via PR reviewed by everyone."""
from dataclasses import dataclass, field
from typing import FrozenSet, List, Tuple

Edge = Tuple[str, str]


@dataclass
class PathMetrics:
    """Raw per-path measurements (produced by monitoring, M1)."""
    loss: float = 0.0          # 0..1
    delay_ms: float = 0.0
    jitter_ms: float = 0.0
    utilization: float = 0.0   # 0..1 link/queue congestion
    availability: float = 1.0  # 0..1


@dataclass
class Path:
    id: str
    nodes: List[str]

    @property
    def edges(self) -> FrozenSet[Edge]:
        return frozenset(tuple(sorted(e)) for e in zip(self.nodes, self.nodes[1:]))


@dataclass
class ScoredPath:
    path: Path
    metrics: PathMetrics
    score: float  # Reliability score R_i (Eq. 1)


@dataclass
class DuplicationDecision:
    flow_id: str
    traffic_class: str
    k: int
    paths: List[ScoredPath] = field(default_factory=list)
    r_total: float = 0.0


@dataclass
class FlowOutcome:
    """Feedback record sent after transmission (M4 -> weight tuner)."""
    flow_id: str
    traffic_class: str
    k: int
    target: float
    delivered_ratio: float
    overhead_bytes: int
