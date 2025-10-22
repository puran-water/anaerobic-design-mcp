#!/usr/bin/env python
"""
Test script to verify mADM1 simulation determinism.

Runs the same simulation 3 times with identical inputs and compares:
- Actual pH (from PCM solver)
- Stream pH (post-processed)
- VSS and TSS yields
- COD removal efficiency
- Key biomass group concentrations
"""

# CRITICAL FIX: Patch fluids.numerics BEFORE any QSDsan imports
import fluids.numerics
if not hasattr(fluids.numerics, 'PY37'):
    fluids.numerics.PY37 = True

import json
import sys

# Load inputs
with open('simulation_basis.json', 'r') as f:
    basis = json.load(f)
with open('simulation_adm1_state.json', 'r') as f:
    adm1_state = json.load(f)
with open('simulation_heuristic_config.json', 'r') as f:
    heuristic_config = json.load(f)

print("Loading QSDsan components...")
from utils.qsdsan_simulation_sulfur import run_simulation_sulfur
from utils.stream_analysis_sulfur import analyze_biomass_yields, extract_diagnostics
from utils.qsdsan_loader import get_qsdsan_components
import anyio

async def _load():
    return await get_qsdsan_components()

components = anyio.run(_load)
print(f"Loaded {len(components)} components\n")

print("="*80)
print("DETERMINISM TEST - Running Same Simulation 3 Times")
print("="*80)

HRT = heuristic_config['digester']['HRT_days']
results = []

for run_num in range(1, 4):
    print(f"\n--- RUN {run_num} ---")

    # Run simulation with IDENTICAL inputs
    sys_d, inf_d, eff_d, gas_d, converged_at, status = run_simulation_sulfur(
        basis, adm1_state, HRT
    )

    # Extract diagnostics
    diagnostics = extract_diagnostics(sys_d)

    # Get pH values
    actual_pH = diagnostics.get('speciation', {}).get('pH', 0)
    stream_pH = eff_d.pH

    # Calculate yields
    yields = analyze_biomass_yields(inf_d, eff_d, system=sys_d, diagnostics=diagnostics)

    # Store results
    result = {
        'run': run_num,
        'status': status,
        'converged_at': converged_at,
        'actual_pH': actual_pH,
        'stream_pH': stream_pH,
        'VSS_yield': yields['VSS_yield'],
        'TSS_yield': yields['TSS_yield'],
        'COD_removal': yields['COD_removal_efficiency'],
        'X_ac_conc': yields['detailed']['per_functional_group']['X_ac']['concentration_kg_COD_m3'],
        'X_h2_conc': yields['detailed']['per_functional_group']['X_h2']['concentration_kg_COD_m3'],
    }
    results.append(result)

    print(f"  Status: {status} at t={converged_at:.1f} days")
    print(f"  Actual pH (PCM): {actual_pH:.4f}")
    print(f"  Stream pH (post): {stream_pH:.4f}")
    print(f"  VSS yield: {yields['VSS_yield']:.6f} kg/kg COD")
    print(f"  TSS yield: {yields['TSS_yield']:.6f} kg/kg COD")
    print(f"  COD removal: {yields['COD_removal_efficiency']:.2f}%")

print("\n" + "="*80)
print("DETERMINISM VERIFICATION")
print("="*80)

# Compare results
run1, run2, run3 = results

def compare_values(name, v1, v2, v3, tolerance=1e-6):
    """Compare three values and check if they're identical within tolerance."""
    max_diff = max(abs(v1 - v2), abs(v2 - v3), abs(v1 - v3))
    is_identical = max_diff < tolerance

    status_symbol = "[PASS]" if is_identical else "[FAIL]"
    print(f"{status_symbol} {name:25s}: ", end="")
    print(f"{v1:.8f} | {v2:.8f} | {v3:.8f}", end="")

    if is_identical:
        print(f"  [PASS]")
    else:
        print(f"  [FAIL - max diff: {max_diff:.2e}]")

    return is_identical

print("\nComparing key metrics across 3 runs:")
print(f"{'Metric':<25s}   {'Run 1':>12s} | {'Run 2':>12s} | {'Run 3':>12s}   Status")
print("-" * 80)

all_pass = True
all_pass &= compare_values("Convergence time (days)", run1['converged_at'], run2['converged_at'], run3['converged_at'], 1e-3)
all_pass &= compare_values("Actual pH (PCM)", run1['actual_pH'], run2['actual_pH'], run3['actual_pH'], 1e-6)
all_pass &= compare_values("Stream pH (post)", run1['stream_pH'], run2['stream_pH'], run3['stream_pH'], 1e-6)
all_pass &= compare_values("VSS yield (kg/kg COD)", run1['VSS_yield'], run2['VSS_yield'], run3['VSS_yield'], 1e-8)
all_pass &= compare_values("TSS yield (kg/kg COD)", run1['TSS_yield'], run2['TSS_yield'], run3['TSS_yield'], 1e-8)
all_pass &= compare_values("COD removal (%)", run1['COD_removal'], run2['COD_removal'], run3['COD_removal'], 1e-6)
all_pass &= compare_values("X_ac conc (kg COD/m3)", run1['X_ac_conc'], run2['X_ac_conc'], run3['X_ac_conc'], 1e-8)
all_pass &= compare_values("X_h2 conc (kg COD/m3)", run1['X_h2_conc'], run2['X_h2_conc'], run3['X_h2_conc'], 1e-8)

print("\n" + "="*80)
if all_pass:
    print("[SUCCESS] ALL RUNS PRODUCED IDENTICAL RESULTS")
    print("The mADM1 model is DETERMINISTIC.")
else:
    print("[FAILED] Some values differed between runs")
    print("Model may have non-deterministic behavior.")
print("="*80)

# Save detailed results
with open('test_determinism_results.json', 'w') as f:
    json.dump({'runs': results, 'deterministic': all_pass}, f, indent=2)
print("\nDetailed results saved to: test_determinism_results.json")
