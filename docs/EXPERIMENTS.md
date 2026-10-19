# AMPD Strategy Comparison

## Objective

Compare three packet-duplication strategies:
1. No duplication (k = 1)
2. Fixed duplication (k = 2)
3. Adaptive Multipath Packet Duplication (AMPD)

## Methodology

The experiment uses the project's existing path-scoring, independent-path
selection, adaptive controller, reliability calculation, and simulated
monitoring components.

The path metrics are illustrative simulation inputs, not measurements from
a live network.

Combined reliability:

R_total = 1 - product(1 - R_i)

Additional duplication overhead:

Overhead = (k - 1) * 1500 bytes per packet

## Results

| Traffic | Strategy | k | Reliability | Target | Target met? |
|---|---|---:|---:|---:|---|
| Normal | No duplication | 1 | 0.8850 | 0.950 | No |
| Normal | Fixed k=2 | 2 | 0.9853 | 0.950 | Yes |
| Normal | Adaptive AMPD | 2 | 0.9853 | 0.950 | Yes |
| Critical | No duplication | 1 | 0.8850 | 0.999 | No |
| Critical | Fixed k=2 | 2 | 0.9853 | 0.999 | No |
| Critical | Adaptive AMPD | 3 | 0.9976 | 0.999 | No |

## Interpretation

- No duplication fails to reach either traffic class's reliability target.
- Fixed k=2 reaches the normal traffic target.
- AMPD selects two paths for normal traffic and three for critical traffic.
- For critical traffic, AMPD improves modelled reliability over fixed k=2,
  but still does not reach the 0.999 target.
- Higher k increases duplication overhead.
- These results are model-based and do not establish live-network performance.

## How to Run

From the repository root, with the virtual environment activated:

    python experiments/compare_strategies.py
    python experiments/run_analytical.py
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q

## Generated Outputs

The strategy comparison generates:

- results/strategy_comparison.csv
- results/fig5_strategy_reliability.png
- results/fig6_strategy_overhead.png

The analytical experiment generates:

- results/fig3_reliability.png
- results/fig4_overhead_efficiency.png

All outputs are based on the current model and configured inputs, not live
network measurements.
