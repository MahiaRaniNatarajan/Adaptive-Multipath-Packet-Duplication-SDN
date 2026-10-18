"""M4 - Feedback mechanism: retunes Eq.(1) weights per traffic class from FlowOutcome records."""
from collections import defaultdict
from copy import deepcopy

from ampd import config
from ampd.common.types import FlowOutcome


class FeedbackTuner:
    def __init__(self, lr: float = 0.05):
        self.lr = lr
        self.weights = defaultdict(lambda: deepcopy(config.DEFAULT_WEIGHTS))

    def update(self, o: FlowOutcome, dominant_failure: str = "loss") -> dict:
        """If a flow missed its target, shift weight toward the metric that explained the miss."""
        w = self.weights[o.traffic_class]
        if o.delivered_ratio < o.target and dominant_failure in w:
            w[dominant_failure] += self.lr
            total = sum(w.values())
            for k in w:
                w[k] /= total  # renormalise so weights sum to 1
        return w
