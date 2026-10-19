"""M2 - Per-traffic-class starting weights for Eq. 1 (each set sums to 1).

critical: loss and availability matter most (a lost packet is costly).
normal:   delay, jitter and congestion matter more (quality of experience).
The feedback tuner (M4) still adjusts these at run time; presets are only the starting point.
"""
from typing import Dict

from ampd import config

CLASS_WEIGHTS: Dict[str, Dict[str, float]] = {
    "critical": {"loss": 0.40, "delay": 0.10, "jitter": 0.10, "congestion": 0.15, "availability": 0.25},
    "normal": {"loss": 0.20, "delay": 0.25, "jitter": 0.15, "congestion": 0.25, "availability": 0.15},
}


def weights_for(traffic_class: str) -> Dict[str, float]:
    return dict(CLASS_WEIGHTS.get(traffic_class, config.DEFAULT_WEIGHTS))
