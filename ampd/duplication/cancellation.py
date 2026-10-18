"""M3 - Smart Duplicate Cancellation (Eq. 5)."""
from ampd import config


def overhead(k: int, packet_size: int = config.PACKET_SIZE) -> int:
    """O(k) = (k-1) * S."""
    return (k - 1) * packet_size


def marginal_efficiency(r_prev: float, r_curr: float, k: int, packet_size: int = config.PACKET_SIZE) -> float:
    """eta(k) = dR_total(k) / O(k)."""
    o = overhead(k, packet_size)
    return (r_curr - r_prev) / o if o else float("inf")


def should_cancel(eta: float, tau: float = config.TAU, delivered: bool = False) -> bool:
    """Withdraw copies once first copy is delivered or marginal gain/byte < tau."""
    return delivered or eta < tau
