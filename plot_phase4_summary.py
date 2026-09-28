import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

summary = pd.read_csv("phase4_scenario_summary.csv")

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

# --- Left: hosting capacity by scenario ---
labels = summary.loadcase
# ">25" strings -> plot as 25 with a hatch to mark "no violation found in range"
caps = []
capped = []
for v in summary.hosting_capacity_kwp:
    if isinstance(v, str) and v.startswith(">"):
        caps.append(float(v[1:]))
        capped.append(True)
    else:
        caps.append(float(v))
        capped.append(False)

colors = ["#9e9e9e" if c else "#1f4e79" for c in capped]
bars = ax1.bar(labels, caps, color=colors)
for bar, is_capped, val in zip(bars, capped, caps):
    label = f">{int(val)}*" if is_capped else f"{int(val)}"
    ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3, label,
              ha="center", fontsize=9)
ax1.set_ylabel("Hosting capacity (kWp/household)")
ax1.set_title("Hosting capacity by SimBench loadcase")
ax1.set_ylim(0, max(caps) + 3)
ax1.text(0.02, 0.98, "*hL/n1: PV output = 0 in these scenarios by definition -\nsweep has no effect, not genuine headroom",
          transform=ax1.transAxes, fontsize=7.5, va="top", color="#555555")

# --- Right: voltage trajectory, hPV vs lPV ---
for case, color in [("hPV", "#e65100"), ("lPV", "#1565c0")]:
    df = pd.read_csv(f"hosting_capacity_sweep_{case}.csv")
    ax2.plot(df.pv_kwp_per_house, df.max_voltage_pu, marker="o", markersize=3,
              color=color, label=f"{case} - max bus voltage")
ax2.axhline(1.10, color="crimson", linestyle="--", label="Voltage ceiling (1.10 pu)")
ax2.set_xlabel("Rooftop PV installed per household (kWp)")
ax2.set_ylabel("Max bus voltage (pu)")
ax2.set_title("Voltage headroom: worst-case PV scenarios\n(both still hit thermal limit before voltage limit)")
ax2.legend(fontsize=8)
ax2.grid(alpha=0.3)

plt.tight_layout()
plt.savefig("phase4_scenario_summary.png", dpi=150)
print("Saved plot to phase4_scenario_summary.png")
