# Team Split — AMPD (4 members, no Ryu)

Each member owns ONE package and works ONLY on their own branch. **Nanthini is the integrator:**
she is the only person who merges into `main` and keeps the integrated system working.
Shared contracts live in `ampd/common/types.py` and `ampd/config.py` (change only via PR reviewed by Nanthini).

| Member | Role | Owns (package) | Paper sections | Branch |
|---|---|---|---|---|
| **Sandhiya G** | M1 – Network & Emulation | `ampd/monitoring/`, `ampd/emulation/` | IV-B (Network State Monitor), V (Mininet/NetEm/iPerf3 testbed) | `feat/monitoring-emulation` |
| **Mahia Rani N** | M2 – Scoring & Path Selection | `ampd/scoring/` | IV-A Eq. (1), Eq. (2), Independent Path Selection | `feat/scoring-paths` |
| **Karthika T** | M3 – Duplication & Cancellation | `ampd/duplication/` | IV-A Eqs. (3)–(5), Adaptive Duplication, Smart Duplicate Cancellation | `feat/duplication-cancel` |
| **Nanthini K** | M4 – Integration (lead) | `ampd/integration/`, `ampd/config.py`, `experiments/`, `docs/`, **`main`** | IV-B/C (Classifier, Algorithm 1, Feedback), V (results/figures) | `feat/integration` (+ merges to `main`) |

## Interfaces (the only things you may depend on)

- **M1 provides:** `BaseMonitor.get_metrics(path) -> PathMetrics`, `emulation.flows.apply_duplication(...)`, `cancel_duplicates(...)`
- **M2 provides:** `score_path(path, metrics, weights) -> ScoredPath`, `select_independent(scored) -> List[ScoredPath]`
- **M3 provides:** `min_k(ranked, target) -> (k, R_total)`, `marginal_efficiency(...)`, `should_cancel(...)`
- **M4 provides:** `AMPDController.decide(flow)` / `.finish(decision, delivered_ratio)`, `FeedbackTuner`

Until M1's testbed is ready, everyone develops against `SimMonitor`.

## Task checklists

**M1 – Sandhiya**
- [ ] Finish `LiveMonitor` utilization from `ovs-ofctl dump-ports` counters
- [ ] Verify 3-path topology + `pingAll`
- [ ] NetEm impairment scenarios (loss / jitter / congestion / link failure)
- [ ] iPerf3 critical vs normal flows; Wireshark capture to confirm duplicate copies
- [ ] Wire `flows.apply_duplication` to OVS group tables (ALL buckets)

**M2 – Mahia Rani**
- [ ] Unit-test Eq. (1) (weights sum to 1, monotonic in each metric)
- [ ] Eq. (2) Jaccard independence; threshold `I_MIN` sensitivity
- [ ] Optional: Suurballe disjoint paths ([15]) as alternative to greedy selection
- [ ] Handle graphs with fewer than k independent paths

**M3 – Karthika**
- [ ] Verify `min_k` (Eq. 4) incl. caps when target is unreachable
- [ ] Eq. (5) overhead/efficiency; pick and justify τ
- [ ] Per-packet cancellation on first ACK (hook for M1 data plane)
- [ ] Tests reproducing Fig. 3 / Fig. 4 numbers

**M4 – Nanthini (integration, owns `main`)**
- [ ] Repo owner: branch protection on `main`, only Nanthini merges
- [ ] Review and merge each member's PR; run `pytest` and `python -m ampd.integration.main --sim` after every merge
- [ ] Keep `AMPDController` working as modules land; resolve interface mismatches
- [ ] Learning-based weight tuner (future work in paper)
- [ ] Experiments: baselines (no-dup, fixed k=2) vs AMPD; produce Figs. 3–5 and Table I
- [ ] Final README/report

## Git workflow
1. Each member commits only to their own branch (table above) and opens a PR into `integration` when a piece is ready.
2. `main` is protected: **only Nanthini merges**, after tests pass.
3. Members rebase their branch on `main` after each merge.
4. Merge order: M2 + M3 (pure logic) → M1 (testbed) → M4 final integration.
