#!/usr/bin/env python
"""
Test script to verify precipitate tracking with iron salt addition (FeCl3).

Strategy:
- Add ferric chloride (FeCl3) to precipitate phosphorus
- Should form iron phosphate (X_Fe3PO42) and potentially iron sulfide (X_FeS)
- Iron phosphate formation is less pH-dependent than struvite/Ca-P
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

# Modify ADM1 state to add iron for precipitation
adm1_state = adm1_state_base.copy()

# Add ferric iron (Fe3+) for phosphate precipitation
# Use SMALL amounts to avoid breaking pH solver
# Keep existing S_IP from base state (~18 mg-P/L)
# Just add modest iron without drastically changing the base state

# Add small amount of ferric iron
adm1_state['S_Fe3'] = 5.0e-4  # 0.5 mmol/L = 28 mg-Fe/L (modest dose)

# Add chloride to balance ferric iron (FeCl3 → Fe3+ + 3Cl-)
# 0.5 mmol Fe3+ × 3 Cl- per Fe3+ = 1.5 mmol Cl-
adm1_state['S_Cl'] = adm1_state.get('S_Cl', 0) + 1.5e-3  # Add 1.5 mmol/L Cl-

# Add small amount of ferrous iron for FeS formation (from FeCl2)
adm1_state['S_Fe2'] = 2.0e-4  # 0.2 mmol/L = 11 mg-Fe/L

# Add chloride to balance ferrous iron (FeCl2 → Fe2+ + 2Cl-)
# 0.2 mmol Fe2+ × 2 Cl- per Fe2+ = 0.4 mmol Cl-
adm1_state['S_Cl'] = adm1_state.get('S_Cl', 0) + 0.4e-3  # Add 0.4 mmol/L Cl-

# Keep base sulfate level
# adm1_state['S_SO4'] already set in base state

print("="*80)
print("TESTING PRECIPITATE FORMATION WITH IRON SALT ADDITION (FeCl3 + FeCl2)")
print("="*80)
print("\nModified conditions:")
print(f"  S_IP (phosphate): {adm1_state.get('S_IP', 0):.1f} mg-P/L")
print(f"  S_Fe3 (ferric iron): {adm1_state['S_Fe3']*1000:.2f} mmol/L ({adm1_state['S_Fe3']*55.845*1000:.0f} mg-Fe/L)")
print(f"  S_Fe2 (ferrous iron): {adm1_state['S_Fe2']*1000:.2f} mmol/L ({adm1_state['S_Fe2']*55.845*1000:.0f} mg-Fe/L)")
print(f"  S_Cl (chloride): {adm1_state.get('S_Cl', 0)*1000:.2f} mmol/L (added to balance iron salts)")
print(f"  S_SO4 (sulfate): {adm1_state.get('S_SO4', 0):.1f} mg-S/L")
if adm1_state.get('S_IP', 0) > 0:
    print(f"  Fe:P molar ratio: {(adm1_state['S_Fe3']*1000) / (adm1_state['S_IP']/31*1000):.3f}:1")

print("\nExpected precipitates:")
print("  - X_Fe3PO42 (ferric phosphate): FePO4")
print("  - X_FeS (iron sulfide): FeS")
print("  Note: Iron phosphate forms across wide pH range (4-8)")

print("\nLoading QSDsan components...")
from utils.qsdsan_simulation_sulfur import run_simulation_sulfur
from utils.stream_analysis_sulfur import analyze_biomass_yields, extract_diagnostics
from utils.qsdsan_loader import get_qsdsan_components
import anyio

async def _load():
    return await get_qsdsan_components()

components = anyio.run(_load)
print(f"Loaded {len(components)} components")

print("\nRunning simulation with iron salt addition...")
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
    print(f"  Total formation: {detailed['total_precipitate_formation_kg_d']:.4f} kg/d")
    print(f"  Total TSS contribution: {detailed['total_precipitate_formation_kg_TSS_d']:.4f} kg TSS/d")

    if precipitates:
        print("\n  [SUCCESS] Active precipitates detected:")
        # Sort by formation rate
        sorted_precip = sorted(precipitates.items(),
                               key=lambda x: abs(x[1]['formation_kg_d']),
                               reverse=True)

        for precip_id, data in sorted_precip:
            print(f"    {precip_id:12s}: {data['formation_kg_d']:10.6f} kg/d " +
                  f"(rate: {data['rate_kg_m3_d']:10.8f} kg/m3/d, " +
                  f"conc: {data['concentration_out_kg_m3']:.8f} kg/m3)")

        # Check process rates directly
        print("\n  Verification - Process rates (indices 46-58):")
        process_rates = diagnostics.get('process_rates', [])
        if len(process_rates) >= 59:
            precip_rates = process_rates[46:59]
            non_zero = sum(1 for r in precip_rates if abs(r) > 1e-10)
            print(f"    Total precipitation processes: 13")
            print(f"    Active processes (rate > 1e-10): {non_zero}")
            if non_zero > 0:
                print(f"\n    Non-zero rates:")
                PRECIP_NAMES = [
                    'X_CCM', 'X_ACC', 'X_ACP', 'X_HAP', 'X_DCPD', 'X_OCP',
                    'X_struv', 'X_newb', 'X_magn', 'X_kstruv',
                    'X_FeS', 'X_Fe3PO42', 'X_AlPO4'
                ]
                for i, (name, rate) in enumerate(zip(PRECIP_NAMES, precip_rates)):
                    if abs(rate) > 1e-10:
                        print(f"      [{46+i}] {name:12s}: {rate:.8f} kg/m3/d")

        print("\n  [SUCCESS] Precipitate tracking implementation VERIFIED!")
        print("  The corrected process-rate-based method successfully detects precipitation.")
    else:
        print("\n  [NOTICE] No active precipitation detected")
        print(f"  Effluent pH: {eff_d.pH:.2f}")
        print("\n  Checking process rates for small values:")
        process_rates = diagnostics.get('process_rates', [])
        if len(process_rates) >= 59:
            precip_rates = process_rates[46:59]
            max_rate = max(abs(r) for r in precip_rates)
            print(f"    Max precipitation rate: {max_rate:.12f} kg/m3/d")
            if max_rate > 0:
                print(f"\n    All precipitation rates:")
                PRECIP_NAMES = [
                    'X_CCM', 'X_ACC', 'X_ACP', 'X_HAP', 'X_DCPD', 'X_OCP',
                    'X_struv', 'X_newb', 'X_magn', 'X_kstruv',
                    'X_FeS', 'X_Fe3PO42', 'X_AlPO4'
                ]
                for i, (name, rate) in enumerate(zip(PRECIP_NAMES, precip_rates)):
                    print(f"      [{46+i}] {name:12s}: {rate:.12e} kg/m3/d")
            else:
                print("    All rates are exactly zero")
                print("    Possible reasons:")
                print("      - Iron precipitation kinetics not active at this pH")
                print("      - Insufficient supersaturation")
                print("      - Iron may be consumed by other reactions")

    # Check iron and phosphate concentrations
    print("\n--- PHOSPHORUS AND IRON BALANCE ---")
    print("  Influent:")
    print(f"    S_IP: {adm1_state['S_IP']:.1f} mg-P/L")
    print(f"    S_Fe3: {adm1_state['S_Fe3']*1000:.2f} mmol/L = {adm1_state['S_Fe3']*55.845*1000:.0f} mg-Fe/L")
    print(f"    S_Fe2: {adm1_state['S_Fe2']*1000:.2f} mmol/L = {adm1_state['S_Fe2']*55.845*1000:.0f} mg-Fe/L")

    # Try to get effluent concentrations
    try:
        eff_P = getattr(eff_d, 'imass', {}).get('P', 0) * 1000  # kg/m3 → mg/L
        print(f"\n  Effluent:")
        print(f"    Total P: {eff_P:.1f} mg-P/L")
        if eff_P > 0 and adm1_state['S_IP'] > 0:
            p_removal = (adm1_state['S_IP'] - eff_P) / adm1_state['S_IP'] * 100
            print(f"    P removal: {p_removal:.1f}%")
    except:
        print("  (Effluent P concentration not available)")

    # Save results
    with open('test_precipitate_iron_output.json', 'w') as f:
        json.dump(yields, f, indent=2)
    print("\n[SUCCESS] Results saved to: test_precipitate_iron_output.json")

else:
    print(f"\n[FAILED] Yield calculation failed: {yields.get('message')}")

print("\n" + "="*80)
print("TEST COMPLETE")
print("="*80)
