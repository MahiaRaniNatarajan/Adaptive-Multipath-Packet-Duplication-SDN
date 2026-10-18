"""M1 - Monitoring interface + simulated backend.

Any monitor must implement `get_metrics(path) -> PathMetrics`.
M2/M3/M4 depend ONLY on this interface, so they can work with SimMonitor before the testbed exists.
"""
import random
from abc import ABC, abstractmethod
from typing import Dict

from ampd.common.types import Path, PathMetrics


class BaseMonitor(ABC):
    @abstractmethod
    def get_metrics(self, path: Path) -> PathMetrics: ...


class SimMonitor(BaseMonitor):
    """Deterministic-ish synthetic metrics for dev/testing without Mininet."""

    def __init__(self, profiles: Dict[str, PathMetrics] = None, noise: float = 0.0, seed: int = 1):
        self.profiles = profiles or {}
        self.noise = noise
        self.rng = random.Random(seed)

    def set_profile(self, path_id: str, m: PathMetrics) -> None:
        self.profiles[path_id] = m

    def get_metrics(self, path: Path) -> PathMetrics:
        m = self.profiles.get(path.id, PathMetrics())
        if not self.noise:
            return m
        j = lambda v: max(0.0, v * (1 + self.rng.uniform(-self.noise, self.noise)))
        return PathMetrics(min(1, j(m.loss)), j(m.delay_ms), j(m.jitter_ms),
                           min(1, j(m.utilization)), m.availability)
