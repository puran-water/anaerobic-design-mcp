#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Verify Codex's hypothesis: The "missing" COD is H₂S in the biogas.

According to Codex:
- 50 kg S/d influent, 0.82 kg S/d effluent → 49.18 kg S/d reduced
- This sulfur leaves as H₂S in biogas
- H₂S has COD: 1 mol H₂S (34 g) → 2 mol O₂ (64 g) = 1.88 kg COD/kg H₂S
- Expected H₂S COD: 49.18 kg S/d × 1.88 = ~1,500 kg COD/d

This would close the 2,028 kg COD/d gap!
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import json

# Load simulation results
with open('simulation_results_final_corrected.json', 'r') as f:
    results = json.load(f)

print("="*80)
print("H₂S COD VERIFICATION - Codex's Hypothesis")
print("="*80)

# Extract data
inf = results['streams']['influent']
eff = results['streams']['effluent']
gas = results['streams']['biogas']
sulfur = results.get('sulfur', {})

print("\n## SULFUR MASS BALANCE")
print(f"Influent SO₄: {sulfur.get('sulfate_in_kg_S_d', 'N/A')} kg S/d")
print(f"Effluent SO₄: {sulfur.get('sulfate_out_kg_S_d', 'N/A')} kg S/d")
print(f"H₂S in biogas (reported): {sulfur.get('h2s_biogas_kg_S_d', 'N/A')} kg S/d")
print(f"H₂S ppm (reported): {sulfur.get('h2s_biogas_ppm', 'N/A')} ppm")

# Calculate sulfur reduction
S_in = sulfur.get('sulfate_in_kg_S_d', 0)
S_eff = sulfur.get('sulfate_out_kg_S_d', 0)
S_reduced = S_in - S_eff

print(f"\n**Sulfur reduced**: {S_reduced:.2f} kg S/d")

# Calculate H₂S COD using stoichiometry
# H₂S (34 g/mol) oxidation: H₂S + 2 O₂ → SO₄²⁻ + 2 H⁺
# 1 mol H₂S = 2 mol O₂ = 64 g O₂
# COD per kg S: (64 g O₂ / 32 g S) = 2.0 kg O₂/kg S
# BUT: We're measuring sulfur, so COD/kg S = 64/32 = 2.0
COD_per_kg_S = 2.0  # kg COD / kg S

H2S_COD_kg_d = S_reduced * COD_per_kg_S

print(f"\n## H₂S COD CALCULATION")
print(f"COD stoichiometry: 1 mol H₂S (34 g) → 2 mol O₂ (64 g)")
print(f"COD per kg S: {COD_per_kg_S:.2f} kg COD/kg S")
print(f"**H₂S COD**: {H2S_COD_kg_d:.1f} kg COD/d")

print("\n" + "="*80)
print("COMPLETE COD BALANCE")
print("="*80)

# Original balance (without H₂S COD)
cod_in = inf['flow'] * inf['COD'] / 1e3
cod_eff = eff['flow'] * eff['COD'] / 1e3

# Biogas COD (CH₄ + H₂ only)
T_op = 273.15 + 35
T_stp = 273.15
ch4_flow_stp = gas['methane_flow'] * (T_stp / T_op)
h2_flow_stp = gas['h2_flow'] * (T_stp / T_op)
ch4_cod = ch4_flow_stp * 2.856
h2_cod = h2_flow_stp * 0.714
biogas_cod_without_h2s = ch4_cod + h2_cod

print(f"\nCOD IN: {cod_in:.1f} kg/d")
print(f"\nCOD OUT:")
print(f"  Effluent:        {cod_eff:.1f} kg/d")
print(f"  CH₄:            {ch4_cod:.1f} kg/d")
print(f"  H₂:             {h2_cod:.1f} kg/d")
print(f"  H₂S (MISSING):  {H2S_COD_kg_d:.1f} kg/d  ← THIS WAS THE BUG!")
print(f"  ─────────────────────────────")
print(f"  TOTAL:          {cod_eff + biogas_cod_without_h2s + H2S_COD_kg_d:.1f} kg/d")

imbalance_old = cod_in - cod_eff - biogas_cod_without_h2s
imbalance_new = cod_in - cod_eff - biogas_cod_without_h2s - H2S_COD_kg_d

print(f"\n## IMBALANCE")
print(f"Without H₂S COD: {imbalance_old:.1f} kg/d ({100*imbalance_old/cod_in:.1f}%)")
print(f"With H₂S COD:    {imbalance_new:.1f} kg/d ({100*imbalance_new/cod_in:.1f}%)")

print("\n" + "="*80)
print("CONCLUSION")
print("="*80)

if abs(imbalance_new) < 0.1 * abs(imbalance_old):
    print("\n✓ ✓ ✓ COD BALANCE CLOSES WITH H₂S COD! ✓ ✓ ✓")
    print(f"\n  Improvement: {abs(imbalance_old) - abs(imbalance_new):.1f} kg/d")
    print(f"  Residual imbalance: {abs(100*imbalance_new/cod_in):.1f}%")
    print("\n**ROOT CAUSE IDENTIFIED**: test_cod_balance.py was missing H₂S COD!")
    print("\n**BUG LOCATION**: utils/stream_analysis_sulfur.py")
    print("  → _analyze_gas_stream_core() only calculates CH₄ and H₂ COD")
    print("  → Must add H₂S COD calculation using stoichiometry")
else:
    print(f"\n⚠ H₂S COD only explains {abs(imbalance_old - imbalance_new):.1f} kg/d")
    print(f"  Still missing: {abs(imbalance_new):.1f} kg/d ({abs(100*imbalance_new/cod_in):.1f}%)")

print("\n" + "="*80)
