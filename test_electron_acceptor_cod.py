#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Calculate COD consumed by alternative electron acceptors (sulfate, nitrate).

In anaerobic digestion, COD can be consumed by electron acceptors OTHER than methanogenesis:
1. Sulfate reduction: SO4²⁻ + organic COD → H2S + CO2
2. Nitrate reduction: NO3⁻ + organic COD → N2 + CO2

This COD is "removed" but does NOT produce CH4 in the biogas!
It's a hidden COD sink that standard CH4-based calculations miss.

Stoichiometry:
- Sulfate: SO4²⁻ (96 g) + 2 CH2O (60 g COD) → H2S (34 g) + 2 CO2
  → 1 kg SO4 consumes 60/96 = 0.625 kg COD
  → 1 kg S consumes 60/32 = 1.875 kg COD

- Nitrate: 2 NO3⁻ (124 g) + 5 CH2O (150 g COD) → N2 + 5 CO2 + H2O
  → 1 kg NO3-N consumes 150/28 = 5.357 kg COD
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import json

# Load simulation results
with open('simulation_results_final_corrected.json', 'r') as f:
    results = json.load(f)

print("="*80)
print("ELECTRON ACCEPTOR COD CONSUMPTION")
print("="*80)

# Extract data
inf = results['streams']['influent']
eff = results['streams']['effluent']
sulfur = results['sulfur']

# Sulfate reduction
S_in = sulfur['sulfate_in_kg_S_d']
S_out = sulfur['sulfate_out_kg_S_d']
S_reduced = S_in - S_out

# Convert to SO4 mass for stoichiometry
SO4_reduced_kg_d = S_reduced * (96/32)  # kg SO4/d

# COD consumed by sulfate reduction
# SO4²⁻ + 2 CH2O → H2S + 2 HCO3⁻
# 96 g SO4 + 60 g COD → products
COD_per_kg_SO4 = 60/96  # 0.625 kg COD/kg SO4
COD_sulfate_kg_d = SO4_reduced_kg_d * COD_per_kg_SO4

# Alternative calculation using sulfur mass:
# 32 g S requires 60 g COD
COD_per_kg_S = 60/32  # 1.875 kg COD/kg S
COD_sulfate_kg_d_alt = S_reduced * COD_per_kg_S

print("\n## SULFATE REDUCTION")
print(f"SO4 reduced: {SO4_reduced_kg_d:.2f} kg SO4/d ({S_reduced:.2f} kg S/d)")
print(f"Stoichiometry: 96 g SO4 + 60 g COD → H2S + CO2")
print(f"COD consumed: {COD_sulfate_kg_d:.1f} kg COD/d")
print(f"(Alt calc from S: {COD_sulfate_kg_d_alt:.1f} kg COD/d)")

# Check if we have nitrate data
print("\n## NITRATE REDUCTION")
# Try to get TKN data (Total Kjeldahl Nitrogen)
tkn_in = inf.get('TKN', 0)
tkn_out = eff.get('TKN', 0)

if tkn_in > 0:
    # TKN includes organic N and NH4-N, but not NO3-N
    # If TKN increased, it suggests denitrification (NO3 → N2 gas, reducing TKN)
    # But we don't have NO3 data in the results
    print("TKN data available, but NO3 data not in results")
    print(f"TKN IN: {tkn_in:.1f} mg-N/L")
    print(f"TKN OUT: {tkn_out:.1f} mg-N/L")
    print("→ Cannot calculate nitrate reduction without explicit NO3 data")
else:
    print("No nitrate/TKN data in results")
    print("→ Assuming zero nitrate reduction")

COD_nitrate_kg_d = 0  # No data

# Total electron acceptor COD
total_electron_acceptor_COD = COD_sulfate_kg_d + COD_nitrate_kg_d

print("\n" + "="*80)
print("REVISED COD BALANCE WITH ELECTRON ACCEPTORS")
print("="*80)

# Original balance
cod_in = inf['flow'] * inf['COD'] / 1e3
cod_eff = eff['flow'] * eff['COD'] / 1e3

# Biogas COD
gas = results['streams']['biogas']
T_op = 273.15 + 35
T_stp = 273.15
ch4_flow_stp = gas['methane_flow'] * (T_stp / T_op)
h2_flow_stp = gas['h2_flow'] * (T_stp / T_op)
ch4_cod = ch4_flow_stp * 2.856
h2_cod = h2_flow_stp * 0.714

# H2S COD (tiny)
h2s_ppm = sulfur['h2s_biogas_ppm']
h2s_mole_frac = h2s_ppm / 1e6
total_flow_stp = gas['flow_total'] * (T_stp / T_op)
h2s_flow_stp = total_flow_stp * h2s_mole_frac
h2s_cod = h2s_flow_stp * (1000/22.414) * (34/1000) * (64/34)

print(f"\nCOD IN: {cod_in:.1f} kg/d")
print(f"\nCOD OUT:")
print(f"  Effluent:                {cod_eff:.1f} kg/d")
print(f"  CH₄:                     {ch4_cod:.1f} kg/d")
print(f"  H₂:                      {h2_cod:.1f} kg/d")
print(f"  H₂S:                     {h2s_cod:.1f} kg/d")
print(f"  Sulfate reduction:       {COD_sulfate_kg_d:.1f} kg/d  ← NEW!")
print(f"  Nitrate reduction:       {COD_nitrate_kg_d:.1f} kg/d")
print(f"  ─────────────────────────────────────")
total_out = cod_eff + ch4_cod + h2_cod + h2s_cod + total_electron_acceptor_COD
print(f"  TOTAL:                   {total_out:.1f} kg/d")

imbalance_old = cod_in - (cod_eff + ch4_cod + h2_cod + h2s_cod)
imbalance_new = cod_in - total_out

print(f"\n## IMBALANCE")
print(f"Without electron acceptors: {imbalance_old:.1f} kg/d ({100*imbalance_old/cod_in:.1f}%)")
print(f"With electron acceptors:    {imbalance_new:.1f} kg/d ({100*imbalance_new/cod_in:.1f}%)")

print("\n" + "="*80)
print("CONCLUSION")
print("="*80)

improvement = abs(imbalance_old) - abs(imbalance_new)
print(f"\nElectron acceptor COD explains: {improvement:.1f} kg/d ({100*improvement/abs(imbalance_old):.1f}% of gap)")
print(f"Remaining mystery: {abs(imbalance_new):.1f} kg/d ({abs(100*imbalance_new/cod_in):.1f}%)")

if abs(imbalance_new) < 0.1 * cod_in:
    print("\n✓ COD balance CLOSES!")
else:
    print("\n✗ Still significant COD missing")
    print(f"\nSulfate reduction only explains ~{100*improvement/abs(imbalance_old):.0f}% of the gap.")
    print("The bulk of the missing COD must have another explanation.")

print("="*80)
