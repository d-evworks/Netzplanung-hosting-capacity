"""
Phase 4b - German 3 % voltage-rise check (VDE-AR-N 4105) for the lPV case.

Phase 4 only checked the absolute 1.10 pu ceiling. German DSOs use a
stricter rule for PV in low-voltage grids: all generation together may
raise the voltage at any connection point by at most 3 % compared with
the same situation without the new generation.

Method: build the lPV scenario (light load, near-peak PV, elevated
upstream voltage), run it once without the added rooftop PV as the
reference, then repeat the sweep and compare every LV bus voltage
against that reference. The worst bus gives the voltage rise.

Note: the reference case still contains the one existing PV system of the
SimBench feeder, so the rise measured here is the rise caused by the new
rooftop PV only.
"""
import copy
import pandas as pd
import pandapower as pp

RISE_LIMIT_PCT = 3.0
LOADING_LIMIT_PCT = 100.0
CASE = "lPV"

net_base = pp.from_json("baseline_net.json")
row = net_base.loadcases.loc[CASE]
lv_buses = net_base.bus[net_base.bus.vn_kv == 0.4].index
house_buses = net_base.load[net_base.load.bus.isin(lv_buses)].bus.unique()

net_case = copy.deepcopy(net_base)
net_case.load["p_mw"] = net_base.load["p_mw"] * row.pload
net_case.load["q_mvar"] = net_base.load["q_mvar"] * row.qload
is_pv = net_case.sgen["type"] == "PV"
net_case.sgen.loc[is_pv, "p_mw"] = net_base.sgen.loc[is_pv, "p_mw"] * row.PV_p
net_case.ext_grid["vm_pu"] = row.Slack_vm

ref = copy.deepcopy(net_case)
pp.runpp(ref)
v_ref = ref.res_bus.vm_pu.loc[lv_buses]

rows = []
for kwp in range(0, 16):
    net = copy.deepcopy(net_case)
    for b in house_buses:
        pp.create_sgen(net, bus=b, p_mw=kwp / 1000 * row.PV_p, q_mvar=0.0)
    pp.runpp(net)
    rise = (net.res_bus.vm_pu.loc[lv_buses] - v_ref) * 100
    line_max = net.res_line.loading_percent.max()
    trafo_max = net.res_trafo.loading_percent.max()
    rows.append(dict(pv_kwp_per_house=kwp,
                     max_voltage_rise_pct=round(rise.max(), 2),
                     max_line_loading_pct=round(line_max, 1),
                     max_trafo_loading_pct=round(trafo_max, 1),
                     rise_violation=rise.max() > RISE_LIMIT_PCT,
                     thermal_violation=max(line_max, trafo_max) > LOADING_LIMIT_PCT))

df = pd.DataFrame(rows)
df.to_csv("phase4b_vde4105_lPV.csv", index=False)
print(df.to_string(index=False))


def last_ok(col):
    bad = df[df[col]]
    return int(bad.iloc[0].pv_kwp_per_house) - 1 if len(bad) else None


print(f"\nLimit from 3 % voltage-rise rule: {last_ok('rise_violation')} kWp/household")
print(f"Limit from thermal loading:        {last_ok('thermal_violation')} kWp/household")
