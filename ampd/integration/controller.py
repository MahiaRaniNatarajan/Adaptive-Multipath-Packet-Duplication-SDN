"""M4 - AMPD controller: wires M1 (monitor) + M2 (score/select) + M3 (duplicate/cancel) + feedback.

Pure Python, no SDN framework. The monitor and the data-plane applier are injected, so the same
loop runs against SimMonitor (dev) or LiveMonitor + ovs-ofctl (Mininet testbed).
"""
from typing import Callable, List, Optional

from ampd import config
from ampd.common.types import DuplicationDecision, FlowOutcome, Path
from ampd.duplication.adaptive import min_k
from ampd.duplication.cancellation import marginal_efficiency, overhead, should_cancel
from ampd.integration.classifier import classify
from ampd.integration.feedback import FeedbackTuner
from ampd.monitoring.monitor import BaseMonitor
from ampd.scoring.path_selection import select_independent
from ampd.scoring.reliability import score_path


class AMPDController:
    def __init__(self, monitor: BaseMonitor, paths: List[Path],
                 apply_fn: Optional[Callable[[DuplicationDecision], None]] = None):
        self.monitor, self.paths, self.apply_fn = monitor, paths, apply_fn
        self.tuner = FeedbackTuner()

    def decide(self, flow: dict) -> DuplicationDecision:
        cls = classify(flow)
        w = self.tuner.weights[cls]
        scored = [score_path(p, self.monitor.get_metrics(p), w) for p in self.paths]
        independent = select_independent(scored)
        k, rt = min_k(independent, config.TRAFFIC_CLASS_TARGETS[cls])
        decision = DuplicationDecision(flow["id"], cls, k, independent[:k], rt)
        if self.apply_fn:
            self.apply_fn(decision)
        return decision

    def finish(self, d: DuplicationDecision, delivered_ratio: float) -> bool:
        """Called on first ACK. Returns True if duplicates were cancelled; feeds outcome back."""
        cancel = False
        if d.k > 1:
            prev = 1 - (1 - d.paths[0].score)
            eta = marginal_efficiency(prev, d.r_total, d.k)
            cancel = should_cancel(eta, delivered=delivered_ratio >= 1.0)
        self.tuner.update(FlowOutcome(d.flow_id, d.traffic_class, d.k,
                                      config.TRAFFIC_CLASS_TARGETS[d.traffic_class],
                                      delivered_ratio, overhead(d.k)))
        return cancel
