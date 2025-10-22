#!/usr/bin/env python
"""
Test script to verify precipitate tracking by adding base to increase pH.

Strategy:
- Start with converged simulation state
- Add strong base (NaOH) via S_cat to increase pH
- This should push pH > 7.5 and trigger precipitation
"""

# CRITICAL FIX: Patch fluids.numerics BEFORE any QSDsan imports
import fluids.numerics
if not hasattr(fluids.numerics, 'PY37'):
    fluids.numerics.PY37 = True

import json
import sys

# Load base inputs
with open('simulation_basis.json', 'r') as f:
    basis = json.load(f)
with open('simulation_adm1_state.json', 'r') as f:
    adm1_state_base = json.load(f)
with open('simulation_heuristic_config.json', 'r') as f:
    heuristic_config = json.load(f)

# Modify ADM1 state to add strong base for higher pH
adm1_state = adm1_state_base.copy()

# Strategy: Add strong cations (S_cat) to shift pH upward
# S_cat represents strong base cations (Na+, K+) in equivalents
# Typical influent might have 0.01-0.04 M (10-40 meq/L)
# To push pH > 7.5, we need to overcome VFA acidity

# Increase S_cat to add strong base
adm1_state['S_cat'] = 0.15  # 150 meq/L of strong base (very high, like NaOH addition)

# Also ensure we have nutrients for precipitation
adm1_state['S_IN'] = 100.0   # 100 mg-N/L ammonia (for struvite)
adm1_state['S_IP'] = 30.0    # 30 mg-P/L phosphate (for struvite & Ca-P)
adm1_state['S_Mg'] = 200.0   # 200 mg/L magnesium (for struvite)
adm1_state['S_Ca'] = 1000.0  # 1000 mg/L calcium (for calcium phosphates)

print("="*80)
print("TESTING PRECIPITATE FORMATION WITH BASE ADDITION")
print("="*80)
print("\nModified conditions:")
print(f"  S_cat (strong base): {adm1_state['S_cat']:.3f} M ({adm1_state['S_cat']*1000:.0f} meq/L)")
print(f"  S_IN (ammonia): {adm1_state['S_IN']:.1f} mg-N/L")
print(f"  S_IP (phosphate): {adm1_state['S_IP']:.1f} mg-P/L")
print(f"  S_Mg (magnesium): {adm1_state['S_Mg']:.1f} mg/L")
print(f"  S_Ca (calcium): {adm1_state['S_Ca']:.1f} mg/L")

print("\nLoading QSDsan components...")
from utils.qsdsan_simulation_sulfur import run_simulation_sulfur
from utils.stream_analysis_sulfur import analyze_biomass_yields, extract_diagnostics
from utils.qsdsan_loader import get_qsdsan_components
import anyio

async def _load():
    return await get_qsdsan_components()

components = anyio.run(_load)
print(f"Loaded {len(components)} components")

print("\nRunning simulation with base addition...")
HRT = heuristic_config['digester']['HRT_days']
sys_d, inf_d, eff_d, gas_d, converged_at, status = run_simulation_sulfur(
    basis, adm1_state, HRT
)

print(f"Simulation completed: {status} at t={converged_at} days")
print(f"Effluent pH: {eff_d.pH:.2f}")

print("\n" + "="*80)
print("ANALYZING PRECIPITATE FORMATION")
print("="*80)

# Extract diagnostics
print("\nExtracting diagnostics...")
diagnostics = extract_diagnostics(sys_d)

# Calculate yields
print("Calculating biomass yields and precipitate formation...")
yields = analyze_biomass_yields(inf_d, eff_d, system=sys_d, diagnostics=diagnostics)

if yields.get('success') and 'detailed' in yields:
    detailed = yields['detailed']
    overall = detailed['overall']

    print("\n--- OVERALL RESULTS ---")
    print(f"  pH: {eff_d.pH:.2f}")
    print(f"  VSS yield: {overall['VSS_yield_kg_per_kg_COD']:.4f} kg/kg COD")
    print(f"  TSS yield (total): {overall['TSS_yield_kg_per_kg_COD']:.4f} kg/kg COD")
    print(f"  TSS yield (biomass): {overall['biomass_TSS_yield']:.4f} kg/kg COD")
    print(f"  TSS yield (precipitate): {overall['precipitate_TSS_yield']:.4f} kg/kg COD")

    print("\n--- PRECIPITATE FORMATION ---")
    precipitates = detailed['precipitates']
    print(f"  Active precipitate species: {len(precipitates)}")
    print(f"  Total formation: {detailed['total_precipitate_formation_kg_d']:.2f} kg/d")
    print(f"  Total TSS contribution: {detailed['total_precipitate_formation_kg_TSS_d']:.2f} kg TSS/d")

    if precipitates:
        print("\n  Active precipitates:")
        # Sort by formation rate
        sorted_precip = sorted(precipitates.items(),
                               key=lambda x: abs(x[1]['formation_kg_d']),
                               reverse=True)

        for precip_id, data in sorted_precip:
            print(f"    {precip_id:12s}: {data['formation_kg_d']:10.4f} kg/d " +
                  f"(rate: {data['rate_kg_m3_d']:8.6f} kg/m3/d, " +
                  f"conc: {data['concentration_out_kg_m3']:.6f} kg/m3)")

        # Check process rates directly
        print("\n  Verification - Process rates (indices 46-58):")
        process_rates = diagnostics.get('process_rates', [])
        if len(process_rates) >= 59:
            precip_rates = process_rates[46:59]
            non_zero = sum(1 for r in precip_rates if abs(r) > 1e-10)
            print(f"    Total precipitation processes: 13")
            print(f"    Active processes (rate > 0): {non_zero}")
            if non_zero > 0:
                print(f"    Rates: {[f'{r:.6f}' for r in precip_rates if abs(r) > 1e-10]}")
    else:
        print("\n  [NOTICE] No active precipitation detected")
        print(f"  Effluent pH: {eff_d.pH:.2f}")
        if eff_d.pH < 7.5:
            print(f"  pH too low for precipitation (need pH > 7.5)")
            print("  Try increasing S_cat (strong base) further")
        print("\n  Checking process rates anyway:")
        process_rates = diagnostics.get('process_rates', [])
        if len(process_rates) >= 59:
            precip_rates = process_rates[46:59]
            max_rate = max(abs(r) for r in precip_rates)
            print(f"    Max precipitation rate: {max_rate:.9f} kg/m3/d")
            if max_rate > 0:
                print(f"    All rates: {precip_rates}")

    # Save results
    with open('test_precipitate_with_base_output.json', 'w') as f:
        json.dump(yields, f, indent=2)
    print("\n[SUCCESS] Results saved to: test_precipitate_with_base_output.json")

else:
    print(f"\n[FAILED] Yield calculation failed: {yields.get('message')}")

print("\n" + "="*80)
print("TEST COMPLETE")
print("="*80)
