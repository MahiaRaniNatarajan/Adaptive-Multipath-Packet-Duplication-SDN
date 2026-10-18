"""M4 - Reproduce analytical Figs. 3-5 from the paper (Eqs. 3 & 5)."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from ampd.duplication.adaptive import r_total
from ampd.duplication.cancellation import marginal_efficiency, overhead

os.makedirs("results", exist_ok=True)
ks = range(1, 7)

plt.figure()
for r in (0.8, 0.9, 0.95):
    plt.plot(ks, [r_total([r] * k) for k in ks], marker="o", label=f"R_i={r}")
plt.axhline(0.999, ls="--", c="gray", label="R_target=0.999")
plt.xlabel("Duplication factor k"); plt.ylabel("R_total(k)"); plt.legend()
plt.savefig("results/fig3_reliability.png", dpi=150)

plt.figure()
r = 0.9
plt.bar(ks, [overhead(k) for k in ks])
plt.xlabel("k"); plt.ylabel("O(k) bytes")
plt.twinx().plot(list(ks)[1:], [marginal_efficiency(r_total([r] * (k - 1)), r_total([r] * k), k) for k in list(ks)[1:]], "r-o")
plt.savefig("results/fig4_overhead_efficiency.png", dpi=150)
print("wrote results/fig3_reliability.png, results/fig4_overhead_efficiency.png")
