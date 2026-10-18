"""Central configuration (owned by M4, read by everyone)."""
# Default Eq.(1) weights; must sum to 1. Tuned per class by feedback loop.
DEFAULT_WEIGHTS = {"loss": 0.30, "delay": 0.20, "jitter": 0.15, "congestion": 0.20, "availability": 0.15}

# Per-class reliability targets (R_target in Eq. 4)
TRAFFIC_CLASS_TARGETS = {"critical": 0.999, "normal": 0.95}

# Normalisation ceilings used to map raw metrics into [0, 1]
MAX_DELAY_MS = 200.0
MAX_JITTER_MS = 50.0

I_MIN = 0.5          # path independence threshold (Eq. 2)
TAU = 1e-6           # marginal-efficiency cancellation threshold (Eq. 5)
MONITOR_INTERVAL_S = 1.0
PACKET_SIZE = 1500   # bytes (S in Eq. 5)
MAX_K = 3
