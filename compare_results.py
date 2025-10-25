import json

# Load both result files
with open('simulation_results_CO2_FIXED.json') as f:
    co2_fixed = json.load(f)

with open('simulation_results_HENRY_FIXED.json') as f:
    henry_fixed = json.load(f)

print("="*80)
print("COMPARISON: CO2_FIXED vs HENRY_FIXED")
print("="*80)

# Diagnostic pH (PCM solver, in reactor)
print("\n1. DIAGNOSTIC pH (PCM solver in reactor):")
print(f"   CO2_FIXED:    {co2_fixed['diagnostics']['speciation']['pH']:.2f}")
print(f"   HENRY_FIXED:  {henry_fixed['diagnostics']['speciation']['pH']:.2f}")

# Biogas composition
print("\n2. BIOGAS COMPOSITION:")
print(f"   CO2_FIXED:")
print(f"     - CH4:  {co2_fixed['streams']['biogas']['methane_percent']:.1f}%")
print(f"     - CO2:  {co2_fixed['streams']['biogas']['co2_percent']:.1f}%")
print(f"     - H2S:  {co2_fixed['streams']['biogas']['h2s_ppm']:.0f} ppm")
print(f"   HENRY_FIXED:")
print(f"     - CH4:  {henry_fixed['streams']['biogas']['methane_percent']:.1f}%")
print(f"     - CO2:  {henry_fixed['streams']['biogas']['co2_percent']:.1f}%")
print(f"     - H2S:  {henry_fixed['streams']['biogas']['h2s_ppm']:.0f} ppm")

# Dissolved species (mol/L)
print("\n3. DISSOLVED SPECIES IN REACTOR (molar):")
print(f"   CO2_FIXED:")
print(f"     - CO2(aq):  {co2_fixed['diagnostics']['speciation']['co2_M']*1000:.2f} mM")
print(f"     - H2S(aq):  {co2_fixed['diagnostics']['speciation']['h2s_M']*1000:.3f} mM")
print(f"   HENRY_FIXED:")
print(f"     - CO2(aq):  {henry_fixed['diagnostics']['speciation']['co2_M']*1000:.2f} mM")
print(f"     - H2S(aq):  {henry_fixed['diagnostics']['speciation']['h2s_M']*1000:.3f} mM")

# Thermodynamic check
pH = henry_fixed['diagnostics']['speciation']['pH']
pKa_CO2 = 6.35
pKa_H2S = 7.0

hco3_to_co2_ratio = 10 ** (pH - pKa_CO2)
co2_fraction = 1 / (1 + hco3_to_co2_ratio)

hs_to_h2s_ratio = 10 ** (pH - pKa_H2S)
h2s_fraction = 1 / (1 + hs_to_h2s_ratio)

print(f"\n4. THERMODYNAMIC CONSISTENCY CHECK (at pH {pH:.2f}):")
print(f"   Henderson-Hasselbalch predictions:")
print(f"     - CO2 fraction:  {co2_fraction*100:.1f}% of S_IC")
print(f"     - H2S fraction:  {h2s_fraction*100:.1f}% of S_IS")

# Performance metrics
print("\n5. PERFORMANCE METRICS:")
print(f"   CO2_FIXED:")
print(f"     - COD removal:    {co2_fixed['performance']['yields']['COD_removal_efficiency']:.1f}%")
print(f"     - CH4 yield:      {co2_fixed['streams']['biogas']['methane_yield_efficiency_percent']:.1f}% of theoretical")
print(f"     - Biogas flow:    {co2_fixed['streams']['biogas']['flow_total']:.1f} m³/d")
print(f"   HENRY_FIXED:")
print(f"     - COD removal:    {henry_fixed['performance']['yields']['COD_removal_efficiency']:.1f}%")
print(f"     - CH4 yield:      {henry_fixed['streams']['biogas']['methane_yield_efficiency_percent']:.1f}% of theoretical")
print(f"     - Biogas flow:    {henry_fixed['streams']['biogas']['flow_total']:.1f} m³/d")

print("\n" + "="*80)
print("CRITICAL FINDINGS:")
print("="*80)

print("\n✗ MAJOR PROBLEM DETECTED:")
print("  Henry's law 'fix' caused a SEVERE performance collapse!")
print(f"  - Methane yield: 94% → 6% (15× WORSE)")
print(f"  - Reactor pH: 8.61 → 6.54 (dropped 2 pH units)")
print(f"  - Biogas CO2: 52% → 27% (reduced but still high)")
print(f"  - Dissolved CO2: 0.18 mM → 15.9 mM (88× HIGHER)")
print("")
print("This suggests the original 1e3 multiplier was NOT a bug!")
print("It may have been compensating for other unit issues in QSDsan.")

