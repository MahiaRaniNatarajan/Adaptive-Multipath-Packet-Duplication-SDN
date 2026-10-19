"""Compare no duplication, fixed k=2, and adaptive AMPD.

Uses the project's SimMonitor and real scoring/selection/controller functions.
Results are model-based, not measurements from a live network.
"""
import csv
import sys
from pathlib import Path as FilePath

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = FilePath(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ampd import config
from ampd.common.types import Path, PathMetrics
from ampd.integration.controller import AMPDController
from ampd.monitoring.monitor import SimMonitor
from ampd.scoring.path_selection import select_independent
from ampd.scoring.reliability import score_path
from ampd.duplication.adaptive import r_total
from ampd.duplication.cancellation import overhead


def main():
    results_dir = ROOT / "results"
    results_dir.mkdir(exist_ok=True)

    paths = [
        Path("primary", ["h1", "s1", "s2", "s5", "h2"]),
        Path("secondary", ["h1", "s1", "s3", "s5", "h2"]),
        Path("backup", ["h1", "s1", "s4", "s5", "h2"]),
    ]

    # Same illustrative metrics used by the project's simulation.
    monitor = SimMonitor({
        "primary": PathMetrics(0.02, 20, 3, 0.4),
        "secondary": PathMetrics(0.05, 35, 6, 0.3),
        "backup": PathMetrics(0.10, 60, 10, 0.2),
    })

    controller = AMPDController(monitor, paths)
    strategies = ["No duplication", "Fixed k=2", "AMPD"]
    rows = []

    for traffic_class in ("normal", "critical"):
        target = config.TRAFFIC_CLASS_TARGETS[traffic_class]
        weights = controller.tuner.weights[traffic_class]

        scored = [
            score_path(path, monitor.get_metrics(path), weights)
            for path in paths
        ]
        independent = select_independent(scored)

        if not independent:
            raise RuntimeError(f"No independent paths for {traffic_class}")

        # Baseline 1: one copy on the best selected path.
        cases = [
            ("No duplication", 1,
             r_total([independent[0].score])),
        ]

        # Baseline 2: fixed duplication factor of two.
        fixed_paths = independent[:min(2, len(independent))]
        cases.append((
            "Fixed k=2",
            len(fixed_paths),
            r_total([p.score for p in fixed_paths]),
        ))

        # Proposed strategy: use the actual AMPD controller decision.
        decision = controller.decide({
            "id": f"comparison-{traffic_class}",
            "class": traffic_class,
        })
        cases.append(("AMPD", decision.k, decision.r_total))

        for strategy, k, reliability in cases:
            rows.append({
                "traffic_class": traffic_class,
                "strategy": strategy,
                "k": k,
                "reliability": reliability,
                "target": target,
                "target_met": reliability >= target,
                "overhead_bytes_per_packet": overhead(k),
            })

    csv_path = results_dir / "strategy_comparison.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    # Figure 1: modelled reliability versus target.
    fig, ax = plt.subplots(figsize=(10, 5.5))
    x_positions = list(range(6))
    values = [row["reliability"] for row in rows]
    labels = [
        f'{row["traffic_class"]}\n{row["strategy"]}'
        for row in rows
    ]
    ax.bar(x_positions, values)
    ax.set_xticks(x_positions, labels)
    ax.set_ylabel("Modelled total reliability")
    ax.set_ylim(0, 1.05)
    ax.set_title("Reliability comparison: no duplication vs fixed k=2 vs AMPD")
    ax.grid(axis="y", alpha=0.25)

    for class_index, traffic_class in enumerate(("normal", "critical")):
        target = config.TRAFFIC_CLASS_TARGETS[traffic_class]
        center = class_index * 3 + 1
        ax.hlines(
            target, center - 0.45, center + 0.45,
            linestyles="--", linewidth=2,
            label=f"{traffic_class} target ({target})",
        )

    ax.legend()
    fig.tight_layout()
    fig.savefig(results_dir / "fig5_strategy_reliability.png", dpi=160)
    plt.close(fig)

    # Figure 2: additional bytes sent per original packet.
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.bar(x_positions, [r["overhead_bytes_per_packet"] for r in rows])
    ax.set_xticks(x_positions, labels)
    ax.set_ylabel("Extra bytes per original packet")
    ax.set_title("Duplication overhead comparison")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(results_dir / "fig6_strategy_overhead.png", dpi=160)
    plt.close(fig)

    print("Strategy comparison:")
    for row in rows:
        print(
            f'{row["traffic_class"]:8s} | '
            f'{row["strategy"]:14s} | '
            f'k={row["k"]} | '
            f'R_total={row["reliability"]:.4f} | '
            f'target={row["target"]:.3f} | '
            f'target_met={row["target_met"]} | '
            f'overhead={row["overhead_bytes_per_packet"]} bytes'
        )

    print(f"\nCSV: {csv_path.relative_to(ROOT)}")
    print("Figures: results/fig5_strategy_reliability.png")
    print("         results/fig6_strategy_overhead.png")


if __name__ == "__main__":
    main()
