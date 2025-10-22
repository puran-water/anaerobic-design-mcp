#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Diagnostic script to verify COD balance in mADM1 simulation.

This script directly examines the influent, effluent, and biogas streams
to verify that COD is conserved: COD_in = COD_out(eff) + COD_out(gas)
"""

import json
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Read simulation results
with open('simulation_results_final_corrected.json', 'r') as f:
    results = json.load(f)

print("="*80)
print("COD BALANCE VERIFICATION")
print("="*80)

# Extract data
inf = results['streams']['influent']
eff = results['streams']['effluent']
gas = results['streams']['biogas']
yields = results['performance']['yields']

print("\n## INFLUENT")
print(f"Flow: {inf['flow']:.1f} m3/d")
print(f"COD: {inf['COD']:.1f} mg/L")
# COD [kg/d] = Flow [m3/d] × COD [mg/L] × [1 kg / 1000 mg] × [1000 L / 1 m3]
# The L and m3 conversions cancel: kg/d = m3/d × mg/L / 1000
cod_in_kg_d = inf['flow'] * inf['COD'] / 1e3
print(f"COD mass flow: {cod_in_kg_d:.1f} kg/d")

print("\n## EFFLUENT")
print(f"Flow: {eff['flow']:.1f} m3/d")
print(f"COD: {eff['COD']:.1f} mg/L")
cod_eff_kg_d = eff['flow'] * eff['COD'] / 1e3
print(f"COD mass flow: {cod_eff_kg_d:.1f} kg/d")

print("\n## BIOGAS")
print(f"Total flow: {gas['flow_total']:.1f} m³/d at operating conditions (35°C)")
print(f"CH4 flow: {gas['methane_flow']:.1f} m3/d ({gas['methane_percent']:.1f}%)")
print(f"CO2 flow: {gas['co2_flow']:.1f} m3/d ({gas['co2_percent']:.1f}%)")
print(f"H2 flow: {gas['h2_flow']:.1f} m3/d ({gas['h2_percent']:.1f}%)")

# Convert to STP (0°C, 1 atm) for COD calculation
T_operating = 273.15 + 35  # 35°C = 308.15 K
T_STP = 273.15  # 0°C
temp_correction = T_STP / T_operating

ch4_flow_stp = gas['methane_flow'] * temp_correction
h2_flow_stp = gas['h2_flow'] * temp_correction

print(f"\nAt STP (0 deg C, 1 atm):")
print(f"CH4 flow: {ch4_flow_stp:.1f} Nm3/d")
print(f"H2 flow: {h2_flow_stp:.1f} Nm3/d")

# COD conversion factors at STP
# 1 Nm3 CH4 = 1000 L / 22.414 L/mol = 44.62 mol
# 1 mol CH4 = 64 g COD
# Therefore: 1 Nm3 CH4 = 44.62 x 64 / 1000 = 2.856 kg COD
COD_per_Nm3_CH4 = 2.856  # kg COD/Nm3
COD_per_Nm3_H2 = 0.714   # kg COD/Nm3 (1 mol H2 = 16 g COD)

cod_ch4_kg_d = ch4_flow_stp * COD_per_Nm3_CH4
cod_h2_kg_d = h2_flow_stp * COD_per_Nm3_H2
cod_gas_kg_d = cod_ch4_kg_d + cod_h2_kg_d

print(f"\nCOD in CH4: {cod_ch4_kg_d:.1f} kg/d")
print(f"COD in H2: {cod_h2_kg_d:.1f} kg/d")
print(f"Total COD in biogas: {cod_gas_kg_d:.1f} kg/d")

print("\n" + "="*80)
print("COD BALANCE")
print("="*80)

print(f"\nCOD IN:  {cod_in_kg_d:.1f} kg/d")
print(f"COD OUT (effluent): {cod_eff_kg_d:.1f} kg/d")
print(f"COD OUT (biogas):   {cod_gas_kg_d:.1f} kg/d")
cod_out_total = cod_eff_kg_d + cod_gas_kg_d
print(f"COD OUT (total):    {cod_out_total:.1f} kg/d")

cod_imbalance = cod_in_kg_d - cod_out_total
imbalance_pct = (cod_imbalance / cod_in_kg_d) * 100

print(f"\nCOD IMBALANCE: {cod_imbalance:.1f} kg/d ({imbalance_pct:.1f}%)")

if abs(imbalance_pct) < 5:
    print("✓ COD balance is ACCEPTABLE (< 5% imbalance)")
elif abs(imbalance_pct) < 10:
    print("⚠ COD balance has MODERATE imbalance (5-10%)")
else:
    print("✗ COD balance has SEVERE imbalance (> 10%)")
    print("\nPOSSIBLE CAUSES:")
    print("1. System not at steady state (biomass still accumulating)")
    print("2. Biogas flow calculation error")
    print("3. Effluent COD calculation error")
    print("4. Missing output stream (e.g., waste sludge)")

# Check if biomass could explain the imbalance
if abs(imbalance_pct) > 10:
    print(f"\n## BIOMASS ANALYSIS")
    cod_removed = yields['COD_removal_kg_d']
    vss_produced = yields.get('VSS_produced_kg_d', 0)

    # VSS to COD conversion: 1 kg VSS ≈ 1.42 kg COD (typical for biomass)
    cod_in_biomass = vss_produced * 1.42

    print(f"COD removed: {cod_removed:.1f} kg/d")
    print(f"VSS produced: {vss_produced:.1f} kg/d")
    print(f"COD in biomass (estimated): {cod_in_biomass:.1f} kg/d")
    print(f"COD imbalance: {cod_imbalance:.1f} kg/d")

    if abs(cod_in_biomass - abs(cod_imbalance)) / abs(cod_imbalance) < 0.2:
        print("\n✓ Imbalance matches biomass accumulation!")
        print("  → System may not be at true steady state")
    else:
        print("\n✗ Biomass does NOT explain the imbalance")
        print("  → There may be a calculation error")

print("\n" + "="*80)
