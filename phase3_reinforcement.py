"""
Phase 3 - Grid reinforcement.

Question we're answering (the natural follow-up to Phase 2):
  "Phase 2 found the feeder's hosting capacity is limited by cable thermal
   overload on the backbone trunk, at ~11 kWp/household. If we reinforce
   that specific bottleneck - upgrade the trunk to a larger cable
   cross-section - how much more PV can the feeder then support, and what
   becomes the new binding constraint?"

Method:
  1. Reload the baseline network and re-run the Phase 2 sweep logic once, at
     the kWp level where Phase 2 first found a violation (12 kWp/house), to
     programmatically identify exactly which line(s) are the bottleneck
     (rather than hardcoding bus numbers from a one-off inspection).
  2. "Reinforce" those bottleneck lines by swapping their standard type
     from NAYY 4x150SE 0.6/1kV (150 mm^2, 0.27 kA) to
     NAYY 4x240SE 0.6/1kV (240 mm^2, 0.357 kA) - a realistic, off-the-shelf
     conductor upgrade (not a hypothetical cable - both types are in
     pandapower's standard library), same voltage class.
  3. Re-run the full hosting-capacity sweep (extended further, since the
     old ceiling no longer applies) on both the original and reinforced
     network for a clean before/after comparison.

Judgment call, flagged for the write-up:
  This reinforces only the specific overloaded lines (targeted
  reinforcement), not the whole feeder - this mirrors how a DSO would
  actually scope a reinforcement project (upgrade what's overloaded, not
  rebuild everything). An alternative scope (upgrade the whole trunk from
  the transformer outward, or add a parallel line instead of upsizing) is
  a legitimate different design choice - see the note at the end.
"""
import copy
import pandapower as pp
import pandas as pd

VOLTAGE_LIMIT_PU = 1.10
LOADING_LIMIT_PCT = 100.0
OLD_STD_TYPE = "NAYY 4x150SE 0.6/1kV"
NEW_STD_TYPE = "NAYY 4x240SE 0.6/1kV"   # realistic off-the-shelf upgrade

net_base = pp.from_json("baseline_net.json")

lv_load_buses = net_base.load[net_base.load.bus.isin(
    net_base.bus[net_base.bus.vn_kv == 0.4].index
)].bus.unique()


def run_sweep(net_template, pv_range, label):
    """Run the PV sweep on a given (already-modified) network template."""
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


# --- Step 1: identify the bottleneck line(s) from the ORIGINAL Phase 2 result ---
net_check = copy.deepcopy(net_base)
for bus in lv_load_buses:
    pp.create_sgen(net_check, bus=bus, p_mw=12 / 1000.0, q_mvar=0.0)
pp.runpp(net_check)
bottleneck_lines = net_check.res_line[net_check.res_line.loading_percent > 95].index.tolist()

print(f"Bottleneck lines identified at 12 kWp/house (>95% loaded): {bottleneck_lines}")
print(net_base.line.loc[bottleneck_lines, ["from_bus", "to_bus", "std_type", "length_km"]].to_string())

# --- Step 2: reinforce - upgrade those specific lines to a larger cable ---
net_reinforced = copy.deepcopy(net_base)
for line_idx in bottleneck_lines:
    assert net_reinforced.line.at[line_idx, "std_type"] == OLD_STD_TYPE
    pp.change_std_type(net_reinforced, line_idx, name=NEW_STD_TYPE, element="line")

print(f"\nReinforced {len(bottleneck_lines)} line(s): {OLD_STD_TYPE} -> {NEW_STD_TYPE}")

# --- Step 3: re-run the full sweep on both networks, extended range ---
pv_range = list(range(0, 31, 1))  # extended past 20 - old ceiling no longer holds

print("\n=== BEFORE reinforcement (baseline lines) ===")
df_before = run_sweep(net_base, pv_range, "before_reinforcement")

print("\n=== AFTER reinforcement (upgraded backbone) ===")
df_after = run_sweep(net_reinforced, pv_range, "after_reinforcement")


# --- Step 4: compare ---
def first_violation_kwp(df):
    v = df[df.voltage_violation | df.thermal_violation]
    return int(v.iloc[0].pv_kwp_per_house) if len(v) else None


before_limit = first_violation_kwp(df_before)
after_limit = first_violation_kwp(df_after)

print("\n=== COMPARISON ===")
before_txt = f"{before_limit - 1} kWp/household" if before_limit else f">{pv_range[-1]} kWp/household"
after_txt = f"{after_limit - 1} kWp/household" if after_limit else f">{pv_range[-1]} kWp/household"
print(f"Hosting capacity BEFORE reinforcement: {before_txt}")
print(f"Hosting capacity AFTER reinforcement:  {after_txt}")

if after_limit:
    row = df_after[df_after.pv_kwp_per_house == after_limit].iloc[0]
    binding = []
    if row.voltage_violation:
        binding.append("voltage")
    if row.thermal_violation:
        binding.append("thermal (line or transformer)")
    print(f"New binding constraint after reinforcement: {', '.join(binding)}")
else:
    print("No new violation found within the extended 0-30 kWp/house range tested.")

print("\nSaved hosting_capacity_sweep_before_reinforcement.csv and "
      "hosting_capacity_sweep_after_reinforcement.csv")
