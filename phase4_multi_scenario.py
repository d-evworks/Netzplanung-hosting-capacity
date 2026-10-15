"""
Phase 4 - Multi-scenario hosting capacity (using SimBench's own loadcases).

Why this phase exists:
  Phases 1-3 all used the network's default snapshot - a single, somewhat
  arbitrary "average" load/generation condition. Real hosting-capacity
  studies don't do that: they test the bounding scenarios, because the
  worst case for a thermal violation (high load, low local generation)
  and the worst case for a voltage violation (low load, high local PV
  generation, which also coincides with a higher upstream MV voltage) are
  DIFFERENT conditions. SimBench ships this network with exactly those
  bounding scenarios pre-defined in net.loadcases, so this phase uses
  them.

The six SimBench loadcases and what each represents:
  hL   heavy Load               - peak demand, no renewable generation
  n1   (same scaling as hL)     - NOTE: SimBench's "n1" is meant to be run
                                   together with an N-1 topology contingency
                                   (a line/switch outage). No topology
                                   change is modelled here, so this run
                                   is scaling-equivalent to hL and is
                                   included for completeness only - it does
                                   not represent a true N-1 check.
  hW   heavy Wind                - peak load + peak wind (irrelevant here,
                                   this LV network has no wind generators)
  hPV  heavy PV                  - peak load coincident with near-peak solar
  lW   light Wind + light load   - (no wind here, included for completeness)
  lPV  light PV                  - MINIMUM load + near-peak solar + elevated
                                   upstream (MV) voltage. This is the
                                   classic worst case for voltage rise from
                                   rooftop PV and is the scenario most
                                   textbooks actually mean by "hosting
                                   capacity study."

Method:
  For each loadcase, scale net.load (p_mw, q_mvar), the network's existing
  PV sgen, and the external grid's slack voltage according to that
  loadcase's row in net.loadcases. Then run the same per-household
  rooftop-PV sweep as Phase 2 (added sgens scaled the same way, since they
  represent solar output under that scenario's irradiance level), and find
  each scenario's hosting capacity and binding constraint.

Scope note: this uses the ORIGINAL (unreinforced) network, not the Phase 3
reinforced one - combining scenario analysis with reinforcement at the same
time adds too many dimensions to interpret cleanly in one pass.
"""
import copy
import pandapower as pp
import pandas as pd

VOLTAGE_LIMIT_PU = 1.10
LOADING_LIMIT_PCT = 100.0
PV_KWP_RANGE = list(range(0, 26, 1))

net_base = pp.from_json("baseline_net.json")
loadcases = net_base.loadcases

lv_load_buses = net_base.load[net_base.load.bus.isin(
    net_base.bus[net_base.bus.vn_kv == 0.4].index
)].bus.unique()


def build_scenario_network(case_name):
    """Return a copy of the baseline network scaled for one SimBench loadcase."""
    row = loadcases.loc[case_name]
    net = copy.deepcopy(net_base)

    net.load["p_mw"] = net_base.load["p_mw"] * row.pload
    net.load["q_mvar"] = net_base.load["q_mvar"] * row.qload

    # Existing generation is all type "PV" in this network (checked directly)
    is_pv = net.sgen["type"] == "PV"
    net.sgen.loc[is_pv, "p_mw"] = net_base.sgen.loc[is_pv, "p_mw"] * row.PV_p

    net.ext_grid["vm_pu"] = row.Slack_vm
    return net, row.PV_p


def run_sweep(case_name, pv_range):
    net_template, pv_scaling = build_scenario_network(case_name)
    results = []
    for kwp in pv_range:
        net = copy.deepcopy(net_template)
        p_mw_per_house = (kwp / 1000.0) * pv_scaling  # scale rooftop PV output too
        for bus in lv_load_buses:
            pp.create_sgen(net, bus=bus, p_mw=p_mw_per_house, q_mvar=0.0,
                            name=f"rooftop_pv_bus{bus}")
        pp.runpp(net)

        max_v = net.res_bus.vm_pu.max()
        min_v = net.res_bus.vm_pu.min()
        max_line_loading = net.res_line.loading_percent.max()
        max_trafo_loading = net.res_trafo.loading_percent.max()

        voltage_violation = bool(max_v > VOLTAGE_LIMIT_PU or min_v < 0.90)
        thermal_violation = bool(max_line_loading > LOADING_LIMIT_PCT or
                                  max_trafo_loading > LOADING_LIMIT_PCT)

        results.append({
            "loadcase": case_name,
            "pv_kwp_per_house": kwp,
            "max_voltage_pu": round(max_v, 4),
            "min_voltage_pu": round(min_v, 4),
            "max_line_loading_pct": round(max_line_loading, 2),
            "max_trafo_loading_pct": round(max_trafo_loading, 2),
            "voltage_violation": voltage_violation,
            "thermal_violation": thermal_violation,
        })
    df = pd.DataFrame(results)
    df.to_csv(f"hosting_capacity_sweep_{case_name}.csv", index=False)
    return df


def first_violation_kwp(df):
    v = df[df.voltage_violation | df.thermal_violation]
    return int(v.iloc[0].pv_kwp_per_house) if len(v) else None


summary = []
for case_name in loadcases.index:
    print(f"\n=== Running loadcase {case_name} "
          f"(pload={loadcases.loc[case_name].pload}, "
          f"PV_p={loadcases.loc[case_name].PV_p}, "
          f"Slack_vm={loadcases.loc[case_name].Slack_vm}) ===")
    df = run_sweep(case_name, PV_KWP_RANGE)
    limit = first_violation_kwp(df)
    if limit:
        row = df[df.pv_kwp_per_house == limit].iloc[0]
        binding = []
        if row.voltage_violation:
            binding.append("voltage")
        if row.thermal_violation:
            binding.append("thermal")
        capacity = limit - 1
        binding_str = "+".join(binding)
    else:
        capacity = f">{PV_KWP_RANGE[-1]}"
        binding_str = "none found in range"
    print(f"  -> hosting capacity: {capacity} kWp/household, binding: {binding_str}")
    summary.append({"loadcase": case_name, "hosting_capacity_kwp": capacity,
                     "binding_constraint": binding_str})

summary_df = pd.DataFrame(summary)
summary_df.to_csv("phase4_scenario_summary.csv", index=False)
print("\n=== SUMMARY ACROSS ALL SCENARIOS ===")
print(summary_df.to_string(index=False))
print("\nSaved phase4_scenario_summary.csv and one hosting_capacity_sweep_<loadcase>.csv per scenario.")
