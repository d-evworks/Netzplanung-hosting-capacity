"""
Phase 5 - Medium-voltage grid study: load flow, short circuit (IEC 60909)
and a true N-1 contingency analysis with restoration switching.

Network: SimBench 1-MV-semiurb--0-sw
  A German semi-urban 20 kV distribution grid fed from 110 kV through two
  40 MVA transformers. Open-ring topology: 8 normally-open switches split
  the rings into radial feeders, exactly how DSOs operate MV networks.

Why this phase exists:
  Phases 1-4 answered one question on one LV feeder (PV hosting capacity).
  A DSO grid-planning engineer also runs three standard studies on the MV
  level. All three are done here with free tools (pandapower + SimBench),
  replicating what PowerFactory is normally used for:

  5a Load flow in three SimBench loadcases (hL = peak load, hPV = peak
     load + PV, lPV = light load + peak PV) -> voltage band and thermal
     loading.
  5b Short-circuit calculation to IEC 60909 (max and min, 3-phase) at every
     20 kV bus -> needed for equipment rating (max) and protection
     settings (min).
  5c N-1: every 20 kV line is taken out of service one at a time under
     peak load. If customers lose supply, the script searches the
     normally-open tie switches for one that restores all load without
     creating a new voltage or thermal violation (Wiederversorgung).

Limits used (typical DSO planning values):
  voltage band 0.90-1.10 pu, 100 % thermal loading.

Assumptions (the SimBench file does not include short-circuit data for the
upstream 110 kV grid, so typical values are set explicitly):
  110 kV infeed Sk'' max 5000 MVA / min 3000 MVA, R/X = 0.1
  converter-based generation contributes 1.2 x rated current (max case only)
"""
import copy
import warnings
import pandas as pd
import pandapower as pp
import pandapower.shortcircuit as sc
import pandapower.topology as top
import simbench as sb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")
CODE = "1-MV-semiurb--0-sw"
V_MIN, V_MAX, LOAD_MAX = 0.90, 1.10, 100.0

base = sb.get_simbench_net(CODE)
lc = base.loadcases
mv_buses = base.bus[base.bus.vn_kv == 20].index


def scenario(case):
    """Copy of the grid scaled to one SimBench loadcase."""
    r = lc.loc[case]
    net = copy.deepcopy(base)
    net.load.p_mw = base.load.p_mw * r.pload
    net.load.q_mvar = base.load.q_mvar * r.qload
    for t, f in [("Wind", r.Wind_p), ("PV", r.PV_p), ("RES", r.RES_p)]:
        m = net.sgen.type.astype(str).str.contains(t)
        net.sgen.loc[m, "p_mw"] = base.sgen.loc[m, "p_mw"] * f
    m = ~net.sgen.type.astype(str).str.contains("Wind|PV|RES")
    net.sgen.loc[m, "p_mw"] = base.sgen.loc[m, "p_mw"] * r.RES_p
    net.ext_grid.vm_pu = r.Slack_vm
    return net


def check(net):
    mv = net.res_bus.loc[net.res_bus.index.isin(mv_buses)].dropna()
    return dict(v_min=mv.vm_pu.min(), v_max=mv.vm_pu.max(),
                line_max=net.res_line.loading_percent.max(),
                trafo_max=net.res_trafo.loading_percent.max())


# ---------------------------------------------------------------- 5a
print("=== 5a Load flow (bounding loadcases) ===")
lf = []
for case in ["hL", "hPV", "lPV"]:
    net = scenario(case)
    pp.runpp(net)
    r = check(net)
    r["case"] = case
    r["violation"] = (r["v_min"] < V_MIN or r["v_max"] > V_MAX
                      or r["line_max"] > LOAD_MAX or r["trafo_max"] > LOAD_MAX)
    lf.append(r)
    print(f"{case}: V {r['v_min']:.3f}-{r['v_max']:.3f} pu | line max "
          f"{r['line_max']:.1f} % | trafo max {r['trafo_max']:.1f} %")
lf = pd.DataFrame(lf)[["case", "v_min", "v_max", "line_max", "trafo_max", "violation"]]
lf.round(3).to_csv("phase5a_loadflow.csv", index=False)

# ---------------------------------------------------------------- 5b
print("\n=== 5b Short circuit IEC 60909 (3-phase) ===")
net = copy.deepcopy(base)
net.ext_grid["s_sc_max_mva"], net.ext_grid["s_sc_min_mva"] = 5000.0, 3000.0
net.ext_grid["rx_max"], net.ext_grid["rx_min"] = 0.1, 0.1
net.sgen["k"] = 1.2
net.line["endtemp_degree"] = 80.0
sc.calc_sc(net, case="max", ip=True)
ik_max = net.res_bus_sc[["ikss_ka", "ip_ka"]].copy()
sc.calc_sc(net, case="min")
ik_min = net.res_bus_sc[["ikss_ka"]].rename(columns={"ikss_ka": "ikss_min_ka"})
scr = ik_max.rename(columns={"ikss_ka": "ikss_max_ka"}).join(ik_min)
scr = scr.loc[scr.index.isin(mv_buses)]
scr.insert(0, "bus_name", base.bus.loc[scr.index, "name"])
scr.round(3).to_csv("phase5b_short_circuit.csv")
print(f"Ik'' max: {scr.ikss_max_ka.min():.2f}-{scr.ikss_max_ka.max():.2f} kA "
      f"(peak ip up to {scr.ip_ka.max():.1f} kA)")
print(f"Ik'' min: {scr.ikss_min_ka.min():.2f}-{scr.ikss_min_ka.max():.2f} kA")
sk_mva = scr.ikss_max_ka.max() * 20 * 3 ** 0.5
print(f"Max fault level at 20 kV busbar: {sk_mva:.0f} MVA "
      f"(check against 20 kV switchgear rating, typically 16-20 kA)")

# ---------------------------------------------------------------- 5c
print("\n=== 5c N-1 line outages under peak load (hL) with restoration ===")
peak = scenario("hL")
open_ties = peak.switch[(peak.switch.et == "l") & (~peak.switch.closed)].index
mv_lines = peak.line[peak.line.from_bus.isin(mv_buses) & peak.line.in_service].index
load_buses = set(peak.load.bus)


def unsupplied(net):
    return set(top.unsupplied_buses(net)) & load_buses


rows = []
for li in mv_lines:
    net = copy.deepcopy(peak)
    net.line.at[li, "in_service"] = False
    lost = unsupplied(net)
    lost_mw = net.load[net.load.bus.isin(lost)].p_mw.sum()
    res = dict(line=li, line_name=peak.line.at[li, "name"],
               lost_load_buses=len(lost), lost_load_mw=round(lost_mw, 3))
    if not lost:
        pp.runpp(net)
        r = check(net)
        ok = r["v_min"] >= V_MIN and r["v_max"] <= V_MAX and r["line_max"] <= LOAD_MAX
        res.update(outcome="no interruption" if ok else "violation", tie_closed="-",
                   **{k: round(v, 3) for k, v in r.items()})
    else:
        res.update(outcome="no alternative path (spur line)", tie_closed="none")
        fallback = None
        for sw in open_ties:
            trial = copy.deepcopy(net)
            trial.switch.at[sw, "closed"] = True
            if unsupplied(trial):
                continue
            try:
                pp.runpp(trial)
            except Exception:
                continue
            r = check(trial)
            if r["v_min"] >= V_MIN and r["v_max"] <= V_MAX and r["line_max"] <= LOAD_MAX:
                res.update(outcome="restored by switching", tie_closed=int(sw),
                           **{k: round(v, 3) for k, v in r.items()})
                fallback = None
                break
            if fallback is None or r["line_max"] < fallback[1]["line_max"]:
                fallback = (sw, r)
        if fallback is not None and res["outcome"] != "restored by switching":
            sw, r = fallback
            res.update(outcome="restorable only with limit violation", tie_closed=int(sw),
                       **{k: round(v, 3) for k, v in r.items()})
    rows.append(res)
n1 = pd.DataFrame(rows)
n1.to_csv("phase5c_n1_contingency.csv", index=False)
summary = n1.outcome.value_counts()
print(summary.to_string())
worst = n1[n1.outcome == "restorable only with limit violation"].sort_values("v_min").head(8)
print("\nWorst outages (lowest voltage / highest loading after best restoration):")
print(worst[["line_name", "outcome", "tie_closed", "line_max", "v_min"]].to_string(index=False))

# ---------------------------------------------------------------- plots
fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))
s = scr.sort_values("ikss_max_ka", ascending=False).reset_index(drop=True)
ax[0].plot(s.index, s.ikss_max_ka, label="Ik'' max")
ax[0].plot(s.index, s.ikss_min_ka, label="Ik'' min")
ax[0].set(title="IEC 60909 short-circuit current, 20 kV buses",
          xlabel="Buses (sorted)", ylabel="kA")
ax[0].legend(frameon=False)
counts = n1.outcome.value_counts()
ax[1].barh(counts.index, counts.values)
ax[1].set(title=f"N-1 outcome for {len(n1)} MV line outages (peak load)",
          xlabel="Number of outages")
for a in ax:
    a.spines[["top", "right"]].set_visible(False)
plt.tight_layout()
plt.savefig("phase5_mv_summary.png", dpi=150)
print("\nSaved: phase5a_loadflow.csv, phase5b_short_circuit.csv, "
      "phase5c_n1_contingency.csv, phase5_mv_summary.png")
