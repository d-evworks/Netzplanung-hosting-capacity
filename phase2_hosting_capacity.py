"""
Phase 2 - Hosting capacity sweep.

Question (the typical Netzplanung task):
  "If every household on this feeder installed rooftop PV of size X kWp,
   at what X does the feeder start violating its limits?"

Method: for each LV load bus, add a rooftop-PV static generator (sgen).
Sweep the per-household PV size from 0 kWp upward, rerun the load flow
at each step, and record the worst-case voltage and loading. The point
where a limit is first crossed is the feeder's hosting capacity.
"""
import pandapower as pp
import pandas as pd

VOLTAGE_LIMIT_PU = 1.10      # absolute upper limit (EN 50160 band).
                              # The stricter German 3 % voltage-rise rule
                              # (VDE-AR-N 4105) is checked in phase4b.
LOADING_LIMIT_PCT = 100.0    # thermal limit for lines/transformer

net_base = pp.from_json("baseline_net.json")

# Every LV bus that already carries a household load is a PV-eligible roof.
lv_load_buses = net_base.load[net_base.load.bus.isin(
    net_base.bus[net_base.bus.vn_kv == 0.4].index
)].bus.unique()

print(f"PV-eligible household buses: {len(lv_load_buses)}")

results = []
pv_sizes_kwp = list(range(0, 21, 1))   # 0 to 20 kWp per household, 1 kWp steps

for kwp in pv_sizes_kwp:
    net = pp.from_json("baseline_net.json")  # fresh copy each step

    p_mw_per_house = kwp / 1000.0
    for bus in lv_load_buses:
        pp.create_sgen(net, bus=bus, p_mw=p_mw_per_house, q_mvar=0.0,
                        name=f"rooftop_pv_bus{bus}")

    pp.runpp(net)

    max_v = net.res_bus.vm_pu.max()
    max_line_loading = net.res_line.loading_percent.max()
    max_trafo_loading = net.res_trafo.loading_percent.max()

    voltage_violation = max_v > VOLTAGE_LIMIT_PU
    thermal_violation = (max_line_loading > LOADING_LIMIT_PCT or
                          max_trafo_loading > LOADING_LIMIT_PCT)

    results.append({
        "pv_kwp_per_house": kwp,
        "max_voltage_pu": round(max_v, 4),
        "max_line_loading_pct": round(max_line_loading, 2),
        "max_trafo_loading_pct": round(max_trafo_loading, 2),
        "voltage_violation": voltage_violation,
        "thermal_violation": thermal_violation,
    })

    status = []
    if voltage_violation:
        status.append("VOLTAGE LIMIT BREACHED")
    if thermal_violation:
        status.append("THERMAL LIMIT BREACHED")
    status_str = " | ".join(status) if status else "OK"
    print(f"{kwp:2d} kWp/house  ->  max V = {max_v:.4f} pu, "
          f"max line = {max_line_loading:5.1f}%, "
          f"max trafo = {max_trafo_loading:5.1f}%   [{status_str}]")

df = pd.DataFrame(results)
df.to_csv("hosting_capacity_sweep.csv", index=False)

# Find the first violation - this IS the hosting capacity answer.
violations = df[df.voltage_violation | df.thermal_violation]
if len(violations) > 0:
    first_violation = violations.iloc[0]
    print(f"\n=== HOSTING CAPACITY LIMIT ===")
    print(f"Feeder can support up to "
          f"{first_violation.pv_kwp_per_house - 1} kWp/household safely.")
    print(f"At {int(first_violation.pv_kwp_per_house)} kWp/household, "
          f"limits are breached.")
else:
    print("\nNo violation found in the 0-20 kWp/house range tested - "
          "feeder has more headroom than this sweep covered.")

print("\nSaved full sweep results to hosting_capacity_sweep.csv")
