#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Calculate H₂S COD from biogas ppm (the correct method).

The reported h2s_biogas_kg_S_d (451.9 kg S/d) is wrong - it uses COD-based units.
Instead, calculate from ppm and biogas flow.
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import json

# Load simulation results
with open('simulation_results_final_corrected.json', 'r') as f:
    results = json.load(f)

print("="*80)
print("H₂S COD FROM PPM - Correct Method")
print("="*80)

# Extract data
gas = results['streams']['biogas']
sulfur = results['sulfur']

# Biogas data
total_flow_m3_d = gas['flow_total']  # m3/d at 35°C
h2s_ppm = sulfur['h2s_biogas_ppm']  # ppmv

print(f"\n## BIOGAS DATA")
print(f"Total flow (35°C): {total_flow_m3_d:.2f} m³/d")
print(f"H₂S concentration: {h2s_ppm:.1f} ppmv = {h2s_ppm/1e4:.4f}%")

# Convert to mole fraction
h2s_mole_fraction = h2s_ppm / 1e6

# Calculate H₂S flow at STP
T_op = 273.15 + 35  # 35°C
T_stp = 273.15      # 0°C
total_flow_stp = total_flow_m3_d * (T_stp / T_op)
h2s_flow_stp = total_flow_stp * h2s_mole_fraction  # Nm³/d

print(f"\n## H₂S VOLUMETRIC FLOW")
print(f"Total flow (STP): {total_flow_stp:.2f} Nm³/d")
print(f"H₂S flow (STP): {h2s_flow_stp:.4f} Nm³/d")

# Convert to mass flow
# At STP: 1 mol gas = 22.414 L
# H₂S molar mass = 34 g/mol
# Therefore: 1 Nm³ H₂S = (1000 L / 22.414 L/mol) × 34 g/mol = 1.517 kg H₂S
# Sulfur content: 32 g S / 34 g H₂S = 0.941 kg S / kg H₂S
kg_H2S_per_Nm3 = (1000 / 22.414) * 34 / 1000  # 1.517 kg H₂S/Nm³
kg_S_per_Nm3 = kg_H2S_per_Nm3 * (32/34)  # 1.427 kg S/Nm³

h2s_mass_kg_d = h2s_flow_stp * kg_H2S_per_Nm3
sulfur_mass_kg_S_d = h2s_flow_stp * kg_S_per_Nm3

print(f"\n## H₂S MASS FLOW")
print(f"H₂S mass: {h2s_mass_kg_d:.4f} kg H₂S/d")
print(f"Sulfur mass: {sulfur_mass_kg_S_d:.4f} kg S/d")
print(f"\nCompare to reported: {sulfur['h2s_biogas_kg_S_d']:.4f} kg S/d (WRONG!)")
print(f"Ratio (reported/correct): {sulfur['h2s_biogas_kg_S_d']/sulfur_mass_kg_S_d:.1f}x")

# Calculate H₂S COD
# H₂S oxidation: H₂S + 2 O₂ → SO₄²⁻ + 2 H⁺
# 1 mol H₂S (34 g) → 2 mol O₂ (64 g)
# COD = 64 g O₂ / 34 g H₂S = 1.882 kg COD/kg H₂S
COD_per_kg_H2S = 64 / 34  # 1.882 kg COD/kg H₂S
h2s_cod_kg_d = h2s_mass_kg_d * COD_per_kg_H2S

print(f"\n## H₂S COD")
print(f"COD stoichiometry: 64 g O₂ / 34 g H₂S = {COD_per_kg_H2S:.3f} kg COD/kg H₂S")
print(f"**H₂S COD (CORRECT)**: {h2s_cod_kg_d:.1f} kg COD/d")

# Load original balance
inf = results['streams']['influent']
eff = results['streams']['effluent']

cod_in = inf['flow'] * inf['COD'] / 1e3
cod_eff = eff['flow'] * eff['COD'] / 1e3

# Biogas COD (CH₄ + H₂)
T_op = 273.15 + 35
T_stp = 273.15
ch4_flow_stp = gas['methane_flow'] * (T_stp / T_op)
h2_flow_stp = gas['h2_flow'] * (T_stp / T_op)
ch4_cod = ch4_flow_stp * 2.856
h2_cod = h2_flow_stp * 0.714

print("\n" + "="*80)
print("REVISED COD BALANCE")
print("="*80)

print(f"\nCOD IN: {cod_in:.1f} kg/d")
print(f"\nCOD OUT:")
print(f"  Effluent:        {cod_eff:.1f} kg/d")
print(f"  CH₄:            {ch4_cod:.1f} kg/d")
print(f"  H₂:             {h2_cod:.1f} kg/d")
print(f"  H₂S (CORRECT):  {h2s_cod_kg_d:.1f} kg/d")
print(f"  ─────────────────────────────")
total_out = cod_eff + ch4_cod + h2_cod + h2s_cod_kg_d
print(f"  TOTAL:          {total_out:.1f} kg/d")

imbalance = cod_in - total_out
print(f"\n## IMBALANCE")
print(f"Missing COD: {imbalance:.1f} kg/d ({100*imbalance/cod_in:.1f}%)")

print("\n" + "="*80)
if abs(imbalance) < 0.1 * cod_in:
    print("✓ COD balance CLOSES!")
else:
    print("✗ Still missing significant COD")
    print("\nCodex said 1,500 kg COD/d should be in H₂S...")
    print(f"But we only found {h2s_cod_kg_d:.1f} kg COD/d")
    print("\nThe mystery continues...")
print("="*80)
