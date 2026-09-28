"""
Phase 3b - Stronger reinforcement: parallel line on the same bottleneck.

Why this and not an even bigger single cable:
  Checked pandapower's std_type library for this network - the NAYY 0.4kV/
  LV cable family used throughout this feeder tops out at NAYY 4x240SE
  (240mm^2), which is what Phase 3 already installed. The next sizes up in
  the library (NA2XS2Y 300/400mm^2) are 6/10kV or 12/20kV medium-voltage
  cables - not a realistic substitute for a 0.4kV LV backbone. So the
  next realistic reinforcement step, matching real DSO practice, is
  running a second cable in parallel along the same route rather than
  hunting for a bigger single conductor that doesn't exist in this
  network's cable class.

Method:
  Take the Phase 3 network (backbone already upgraded to 240mm^2) and set
  `parallel = 2` on the same 4 bottleneck lines - pandapower models this
  as two identical circuits sharing the load, which roughly halves the
  effective impedance and doubles the thermal (ampacity) limit on that
  route. Re-run the sweep, extended further, to find the new ceiling and
  see whether the transformer becomes the binding constraint instead.
"""
import copy
import pandapower as pp
import pandas as pd

VOLTAGE_LIMIT_PU = 1.10
LOADING_LIMIT_PCT = 100.0
NEW_STD_TYPE = "NAYY 4x240SE 0.6/1kV"
BOTTLENECK_LINES = [4, 19, 24, 28]  # identified in phase3_reinforcement.py

net_base = pp.from_json("baseline_net.json")

lv_load_buses = net_base.load[net_base.load.bus.isin(
    net_base.bus[net_base.bus.vn_kv == 0.4].index
)].bus.unique()


def run_sweep(net_template, pv_range, label):
    results = []
    for kwp in pv_range:
        net = copy.deepcopy(net_template)
        p_mw_per_house = kwp / 1000.0
        for bus in lv_load_buses:
            pp.create_sgen(net, bus=bus, p_mw=p_mw_per_house, q_mvar=0.0,
                            name=f"rooftop_pv_bus{bus}")
        pp.runpp(net)

        max_v = net.res_bus.vm_pu.max()
        max_line_loading = net.res_line.loading_percent.max()
        bottleneck_line = int(net.res_line.loading_percent.idxmax())
        max_trafo_loading = net.res_trafo.loading_percent.max()

        voltage_violation = bool(max_v > VOLTAGE_LIMIT_PU)
        thermal_violation = bool(max_line_loading > LOADING_LIMIT_PCT or
                                  max_trafo_loading > LOADING_LIMIT_PCT)

        results.append({
            "pv_kwp_per_house": kwp,
            "max_voltage_pu": round(max_v, 4),
            "max_line_loading_pct": round(max_line_loading, 2),
            "bottleneck_line": bottleneck_line,
            "max_trafo_loading_pct": round(max_trafo_loading, 2),
            "voltage_violation": voltage_violation,
            "thermal_violation": thermal_violation,
        })
    df = pd.DataFrame(results)
    df.to_csv(f"hosting_capacity_sweep_{label}.csv", index=False)
    return df


# Build the "Phase 3b" network: 240mm^2 backbone (Phase 3) + parallel 2nd circuit
net_3b = copy.deepcopy(net_base)
for line_idx in BOTTLENECK_LINES:
    pp.change_std_type(net_3b, line_idx, name=NEW_STD_TYPE, element="line")
    net_3b.line.at[line_idx, "parallel"] = 2

print(f"Backbone lines {BOTTLENECK_LINES}: upgraded to {NEW_STD_TYPE} AND set parallel=2")

pv_range = list(range(0, 41, 1))  # extended further - trafo may now be the ceiling

print("\n=== Phase 3b: reinforced 240mm^2 + parallel circuit ===")
df_3b = run_sweep(net_3b, pv_range, "phase3b_parallel")


def first_violation_kwp(df):
    v = df[df.voltage_violation | df.thermal_violation]
    return int(v.iloc[0].pv_kwp_per_house) if len(v) else None


limit_3b = first_violation_kwp(df_3b)

print("\n=== RESULT ===")
if limit_3b:
    row = df_3b[df_3b.pv_kwp_per_house == limit_3b].iloc[0]
    binding = []
    if row.voltage_violation:
        binding.append("voltage")
    if row.thermal_violation:
        binding.append("thermal (line or transformer)")
    print(f"Hosting capacity with parallel-line reinforcement: {limit_3b - 1} kWp/household")
    print(f"Binding constraint: {', '.join(binding)}  (bottleneck element index: {row.bottleneck_line}, "
          f"max trafo loading at that point: {row.max_trafo_loading_pct}%)")
else:
    print(f"No violation found up to {pv_range[-1]} kWp/household - "
          f"headroom now exceeds the tested range.")

print("\nSaved hosting_capacity_sweep_phase3b_parallel.csv")
