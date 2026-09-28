import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

df = pd.read_csv("hosting_capacity_sweep.csv")

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 7), sharex=True)

ax1.plot(df.pv_kwp_per_house, df.max_voltage_pu, marker="o", color="#1f4e79")
ax1.axhline(1.10, color="crimson", linestyle="--", label="Statutory voltage limit (1.10 pu)")
ax1.set_ylabel("Max bus voltage (pu)")
ax1.set_title("Hosting capacity sweep — 1-LV-semiurb4--0-sw")
ax1.legend()
ax1.grid(alpha=0.3)

ax2.plot(df.pv_kwp_per_house, df.max_line_loading_pct, marker="o", label="Max line loading (%)", color="#2e7d32")
ax2.plot(df.pv_kwp_per_house, df.max_trafo_loading_pct, marker="s", label="Max transformer loading (%)", color="#e65100")
ax2.axhline(100, color="crimson", linestyle="--", label="Thermal limit (100%)")
ax2.set_xlabel("Rooftop PV installed per household (kWp)")
ax2.set_ylabel("Loading (% of thermal rating)")
ax2.legend()
ax2.grid(alpha=0.3)

plt.tight_layout()
plt.savefig("hosting_capacity_sweep.png", dpi=150)
print("Saved plot to hosting_capacity_sweep.png")
