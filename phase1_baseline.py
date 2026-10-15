"""
Phase 1 - Baseline load flow on a SimBench LV feeder.

Code chosen: 1-LV-semiurb4--0-sw
  1        -> SimBench dataset release 1
  LV       -> low-voltage feeder (0.4 kV, the last-mile network to houses)
  semiurb4 -> semi-urban region type, variant 4 (a mix of houses + some
              commercial load - realistic mid-stress feeder)
  --0      -> scenario 0 = "present" (today's grid, not a future projection)
  -sw      -> includes the switch/ring topology (normally-open tie switches),
              needed later for restoration studies
"""
import pandapower as pp
import simbench as sb

CODE = "1-LV-semiurb4--0-sw"

net = sb.get_simbench_net(CODE)

print("=== Network summary ===")
print(net)

print("\n=== Bus voltage levels present ===")
print(net.bus.vn_kv.unique())

print("\n=== Counts ===")
print("buses:", len(net.bus))
print("lines:", len(net.line))
print("loads:", len(net.load))
print("sgens (static generators, e.g. rooftop PV):", len(net.sgen))
print("trafos:", len(net.trafo))

# Steady-state AC power flow, Newton-Raphson (pandapower default).
pp.runpp(net)

print("\n=== Load flow converged? ===")
print("Yes" if net.converged else "NO - did not converge")

print("\n=== Bus voltage results (per-unit) ===")
print(net.res_bus.vm_pu.describe())

print("\n=== Line loading results (% of thermal rating) ===")
print(net.res_line.loading_percent.describe())

print("\n=== Transformer loading (%) ===")
print(net.res_trafo.loading_percent.describe())

# Save network + results so the later phases start from the same state
pp.to_json(net, "baseline_net.json")
print("\nSaved baseline network + results to baseline_net.json")
