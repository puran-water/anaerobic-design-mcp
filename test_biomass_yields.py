#!/usr/bin/env python
"""
Test script for biomass yield and precipitate reporting implementation.
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
print(f"Loaded {len(components)} components")

print("\nRunning simulation at design HRT (10 days)...")
HRT = heuristic_config['digester']['HRT_days']
sys_d, inf_d, eff_d, gas_d, converged_at, status = run_simulation_sulfur(
    basis, adm1_state, HRT
)

print(f"Simulation completed: {status} at t={converged_at} days")

# Extract diagnostics first to get ACTUAL pH
print("\nExtracting diagnostics...")
diagnostics = extract_diagnostics(sys_d)
print(f"Diagnostics extraction: {diagnostics.get('success')}")

# Get actual simulation pH from PCM solver
actual_pH = diagnostics.get('speciation', {}).get('pH', 0)
stream_pH = eff_d.pH

print("\n" + "="*80)
print("pH COMPARISON")
print("="*80)
print(f"Actual simulation pH (PCM solver): {actual_pH:.2f}")
print(f"Stream property pH (post-processed): {stream_pH:.2f}")
if abs(actual_pH - stream_pH) > 0.5:
    print(f"WARNING: pH values differ by {abs(actual_pH - stream_pH):.2f} units!")
    print("  Stream pH uses simplified calculation (S_cat/S_an + VFAs only)")
    print("  Actual pH from PCM accounts for all ions (Ca, Mg, Fe, Cl, etc.)")

print("\n" + "="*80)
print("TESTING BIOMASS YIELD & PRECIPITATE REPORTING")
print("="*80)

# Calculate yields with system object
print("\nCalculating biomass yields and precipitate formation...")
yields = analyze_biomass_yields(inf_d, eff_d, system=sys_d, diagnostics=diagnostics)

print(f"\nYield calculation success: {yields.get('success')}")

if yields.get('success'):
    print("\n--- OVERALL YIELDS ---")
    print(f"  VSS yield: {yields['VSS_yield']:.4f} kg VSS/kg COD")
    print(f"  TSS yield: {yields['TSS_yield']:.4f} kg TSS/kg COD")
    print(f"  COD removal: {yields['COD_removal_efficiency']:.1f}%")

    if 'detailed' in yields:
        detailed = yields['detailed']
        overall = detailed['overall']

        print("\n--- DETAILED OVERALL ---")
        print(f"  VSS yield: {overall['VSS_yield_kg_per_kg_COD']:.4f} kg/kg COD")
        print(f"  TSS yield (total): {overall['TSS_yield_kg_per_kg_COD']:.4f} kg/kg COD")
        print(f"  TSS yield (biomass only): {overall['biomass_TSS_yield']:.4f} kg/kg COD")
        print(f"  TSS yield (precipitate): {overall['precipitate_TSS_yield']:.4f} kg/kg COD")
        print(f"  COD removed: {overall['COD_removed_kg_d']:.2f} kg/d")
        print(f"  Total biomass VSS: {overall['total_biomass_VSS_kg_d']:.2f} kg/d")
        print(f"  Total biomass TSS: {overall['total_biomass_TSS_kg_d']:.2f} kg/d")

        print("\n--- PER-FUNCTIONAL-GROUP YIELDS ---")
        per_group = detailed['per_functional_group']
        print(f"  Total groups: {len(per_group)}")

        # Show top 5 by VSS production
        sorted_groups = sorted(per_group.items(),
                               key=lambda x: x[1]['net_production_kg_VSS_d'],
                               reverse=True)

        print("\n  Top 5 producers (kg VSS/d):")
        for group_id, data in sorted_groups[:5]:
            print(f"    {group_id:12s}: {data['net_production_kg_VSS_d']:8.4f} kg VSS/d " +
                  f"(yield: {data['yield_kg_VSS_per_kg_COD']:.4f} kg/kg COD, " +
                  f"conc: {data['concentration_kg_COD_m3']:.4f} kg COD/m3)")

        print("\n--- PRECIPITATE FORMATION ---")
        precipitates = detailed['precipitates']
        print(f"  Active precipitate species: {len(precipitates)}")
        print(f"  Total formation: {detailed['total_precipitate_formation_kg_d']:.2f} kg/d")
        print(f"  Total TSS contribution: {detailed['total_precipitate_formation_kg_TSS_d']:.2f} kg TSS/d")

        if precipitates:
            print("\n  Active precipitates:")
            for precip_id, data in precipitates.items():
                print(f"    {precip_id:12s}: {data['formation_kg_d']:8.4f} kg/d " +
                      f"(TSS: {data['formation_kg_TSS_d']:.4f} kg/d, " +
                      f"conc: {data['concentration_out_kg_m3']:.4f} kg/m3)")
        else:
            print("  No active precipitation detected")

        # Save detailed results
        with open('test_biomass_yields_output.json', 'w') as f:
            json.dump(yields, f, indent=2)
        print("\n[SUCCESS] Full yield and precipitate data saved to: test_biomass_yields_output.json")

else:
    print(f"\n[FAILED] Yield calculation failed: {yields.get('message')}")

print("\n" + "="*80)
print("TEST COMPLETE")
print("="*80)
