import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

before = pd.read_csv("hosting_capacity_sweep_before_reinforcement.csv")
after = pd.read_csv("hosting_capacity_sweep_after_reinforcement.csv")

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 7), sharex=True)

ax1.plot(before.pv_kwp_per_house, before.max_line_loading_pct, marker="o",
         color="#c62828", label="Before reinforcement (max line loading)")
ax1.plot(after.pv_kwp_per_house, after.max_line_loading_pct, marker="o",
         color="#2e7d32", label="After reinforcement (max line loading)")
ax1.axhline(100, color="black", linestyle="--", linewidth=1, label="Thermal limit (100%)")
ax1.axvline(11, color="#c62828", linestyle=":", linewidth=1)
ax1.axvline(13, color="#2e7d32", linestyle=":", linewidth=1)
ax1.set_ylabel("Max line loading (%)")
ax1.set_title("Phase 3 - Backbone reinforcement: before vs after\n"
              "(lines 1–31–7–20–14 upgraded 150mm² → 240mm²)")
ax1.legend(fontsize=8)
ax1.grid(alpha=0.3)

ax2.plot(before.pv_kwp_per_house, before.max_trafo_loading_pct, marker="s",
         color="#c62828", linestyle="--", label="Before - transformer loading")
ax2.plot(after.pv_kwp_per_house, after.max_trafo_loading_pct, marker="s",
         color="#2e7d32", linestyle="--", label="After - transformer loading")
ax2.axhline(100, color="black", linestyle="--", linewidth=1)
ax2.set_xlabel("Rooftop PV installed per household (kWp)")
ax2.set_ylabel("Transformer loading (%)")
ax2.legend(fontsize=8)
ax2.grid(alpha=0.3)

plt.tight_layout()
plt.savefig("phase3_reinforcement_comparison.png", dpi=150)
print("Saved plot to phase3_reinforcement_comparison.png")
