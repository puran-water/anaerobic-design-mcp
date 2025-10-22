#!/usr/bin/env python
"""
Quick test to verify diagnostic extraction works with existing simulation.
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
from utils.stream_analysis_sulfur import extract_diagnostics
from utils.qsdsan_loader import get_qsdsan_components
import anyio

async def _load():
    return await get_qsdsan_components()

components = anyio.run(_load)
print(f"Loaded {len(components)} components")

print("\nRunning simulation at design HRT (10 days)...")
HRT = heuristic_config['digester']['HRT_days']
sys_d, inf_d, eff_d, gas_d, converged_at, status = run_simulation_sulfur(
    basis, adm1_state, HRT
)

print(f"Simulation completed: {status} at t={converged_at} days")

print("\n" + "="*80)
print("TESTING DIAGNOSTIC EXTRACTION")
print("="*80)

diagnostics = extract_diagnostics(sys_d)

print(f"\nDiagnostic extraction success: {diagnostics.get('success')}")

if diagnostics.get('success'):
    print("\n--- SPECIATION ---")
    for key, value in diagnostics['speciation'].items():
        print(f"  {key}: {value}")

    print("\n--- INHIBITION CATEGORIES ---")
    for category, data in diagnostics['inhibition'].items():
        print(f"  {category}: {len(data)} factors")

    print("\n--- BIOMASS CONCENTRATIONS (kg/m³) ---")
    for biomass, conc in diagnostics['biomass_kg_m3'].items():
        print(f"  {biomass}: {conc:.4f}")

    print(f"\n--- SUBSTRATE LIMITATION ---")
    monod = diagnostics['substrate_limitation']['Monod']
    print(f"  Monod factors: {len(monod)} values")
    print(f"  Min: {min(monod):.4f}, Max: {max(monod):.4f}")

    print(f"\n--- PROCESS RATES ---")
    rates = diagnostics['process_rates']
    print(f"  Total processes: {len(rates)}")
    print(f"  Non-zero processes: {sum(1 for r in rates if abs(r) > 1e-10)}")

    # Save to file
    with open('test_diagnostics_output.json', 'w') as f:
        json.dump(diagnostics, f, indent=2)
    print("\n[SUCCESS] Full diagnostic data saved to: test_diagnostics_output.json")

else:
    print(f"\n[FAILED] Diagnostic extraction failed: {diagnostics.get('message')}")

print("\n" + "="*80)
print("TEST COMPLETE")
print("="*80)
