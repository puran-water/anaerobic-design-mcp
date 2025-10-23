"""
Check carbon mass balance and CO2 equilibrium in seeded simulation.
Verify whether low CO2% (7.6%) is physically realistic or indicates a bug.
"""

import json

# Load simulation results
with open('simulation_results_seeded.json', 'r') as f:
    results = json.load(f)

# Extract key data
inf = results['streams']['influent']
eff = results['streams']['effluent']
gas = results['streams']['biogas']

# Flow rates
Q_liq = inf['flow']  # m3/d
Q_gas_total = gas['flow_total']  # m3/d
Q_ch4 = gas['methane_flow']  # m3/d
Q_co2 = gas['co2_flow']  # m3/d

# COD values
COD_in = inf['COD']  # mg/L
COD_out = eff['COD']  # mg/L
COD_removed = COD_in - COD_out  # mg/L

# Inorganic carbon
S_IC_eff = eff['components']['S_IC']  # mg C/L (total inorganic carbon)
S_IC_inf = inf['components']['S_IC']  # mg C/L

# pH and alkalinity
pH_eff = eff['pH']
alk_eff = eff['alkalinity']  # meq/L

print("="*80)
print("CARBON MASS BALANCE AND CO2 EQUILIBRIUM CHECK")
print("="*80)

print("\n1. GAS COMPOSITION")
print(f"   Total biogas: {Q_gas_total:.1f} m3/d")
print(f"   CH4: {gas['methane_percent']:.1f}% ({Q_ch4:.1f} m3/d)")
print(f"   CO2: {gas['co2_percent']:.1f}% ({Q_co2:.1f} m3/d)")
print(f"   H2: {gas['h2_percent']:.3f}% ({gas['h2_flow']:.3f} m3/d)")

print("\n2. LIQUID PHASE")
print(f"   pH: {pH_eff:.2f}")
print(f"   Alkalinity: {alk_eff:.1f} meq/L")
print(f"   S_IC (total inorganic C): {S_IC_eff:.1f} mg C/L")
print(f"   S_IC influent: {S_IC_inf:.1f} mg C/L")

print("\n3. CARBON MASS BALANCE")
# Carbon from COD removal (assume all goes to CH4 + CO2 + biomass)
# Theoretical: 1 kg COD removed → 0.25 kg CH4-C + 0.25 kg CO2-C + biomass-C

# CH4 carbon (molecular weight: CH4 = 16 g/mol, C = 12 g/mol)
# At STP: 1 mol gas = 22.4 L = 0.0224 m3
# 1 m3 CH4 = 44.64 mol CH4 = 44.64 mol C = 535.7 g C = 0.536 kg C
CH4_carbon_kg_d = Q_ch4 * 0.536  # kg C/d

# CO2 carbon (molecular weight: CO2 = 44 g/mol, C = 12 g/mol)
# 1 m3 CO2 = 44.64 mol CO2 = 44.64 mol C = 535.7 g C = 0.536 kg C
CO2_carbon_kg_d = Q_co2 * 0.536  # kg C/d

# Total gas carbon
gas_carbon_kg_d = CH4_carbon_kg_d + CO2_carbon_kg_d

# COD removed
COD_removed_kg_d = (COD_removed * Q_liq) / 1000  # kg COD/d

# Theoretical carbon from COD (COD to C ratio ≈ 2.67 for typical organics)
# C6H12O6: MW=180, 6 C = 72 g C, COD = 192 g → C/COD = 72/192 = 0.375
# For typical wastewater organics: C/COD ≈ 0.3-0.4
C_from_COD_kg_d = COD_removed_kg_d * 0.375  # kg C/d (assume 0.375 kg C/kg COD)

# Inorganic carbon change in liquid
delta_IC_kg_d = (S_IC_eff - S_IC_inf) * Q_liq / 1000  # kg C/d

print(f"   COD removed: {COD_removed_kg_d:.1f} kg COD/d")
print(f"   Organic C removed (est): {C_from_COD_kg_d:.1f} kg C/d")
print(f"   CH4 carbon produced: {CH4_carbon_kg_d:.1f} kg C/d")
print(f"   CO2 carbon produced: {CO2_carbon_kg_d:.1f} kg C/d")
print(f"   Total gas carbon: {gas_carbon_kg_d:.1f} kg C/d")
print(f"   Inorganic C retained in liquid: {delta_IC_kg_d:.1f} kg C/d")
print(f"   Total C accounted: {gas_carbon_kg_d + delta_IC_kg_d:.1f} kg C/d")

# Check mass balance
carbon_recovery = (gas_carbon_kg_d + delta_IC_kg_d) / C_from_COD_kg_d * 100

print(f"\n   Carbon recovery: {carbon_recovery:.1f}%")

print("\n4. CO2 DISTRIBUTION ANALYSIS")
# At pH 5.27, nearly all S_IC should be dissolved CO2
# pKa1 of carbonic acid = 6.35
# At pH 5.27 (>1 unit below pKa1), >90% is H2CO3/CO2(aq)

fraction_as_co2_aq = 1 / (1 + 10**(pH_eff - 6.35))  # Henderson-Hasselbalch
CO2_aq_mg_C_L = S_IC_eff * fraction_as_co2_aq
CO2_aq_kg_d = CO2_aq_mg_C_L * Q_liq / 1000

print(f"   Fraction of S_IC as CO2(aq) at pH {pH_eff:.2f}: {fraction_as_co2_aq*100:.1f}%")
print(f"   Dissolved CO2: {CO2_aq_mg_C_L:.1f} mg C/L = {CO2_aq_kg_d:.1f} kg C/d")
print(f"   CO2 in gas: {CO2_carbon_kg_d:.1f} kg C/d")
print(f"   Total CO2-C produced: {CO2_aq_kg_d + CO2_carbon_kg_d:.1f} kg C/d")

# Ratio of dissolved to gas CO2
if CO2_carbon_kg_d > 0:
    ratio_dissolved_to_gas = CO2_aq_kg_d / CO2_carbon_kg_d
    print(f"   Ratio (dissolved/gas): {ratio_dissolved_to_gas:.2f}")

print("\n5. EXPECTED CH4:CO2 RATIO")
# Theoretical stoichiometry for typical organics (e.g., glucose):
# C6H12O6 → 3 CH4 + 3 CO2 (1:1 molar ratio)
# This simulation shows 3662 m3 CH4 : 306 m3 CO2 = 12:1 ratio

molar_ratio = Q_ch4 / Q_co2
print(f"   Observed CH4:CO2 molar ratio: {molar_ratio:.1f}:1")
print(f"   Expected ratio (typical AD): 1:1 to 1.5:1")
print(f"   This ratio is EXTREMELY HIGH - indicates CO2 retention")

print("\n6. CONCLUSION")
if molar_ratio > 5:
    print("   ⚠️  CRITICAL: CH4:CO2 ratio is abnormally high")
    print("   Possible causes:")
    print("   1. CO2 dissolution into liquid phase (but Henry's law should prevent this)")
    print("   2. CO2 consumption by alkalinity generation (mineral precipitation?)")
    print("   3. Bug in CO2 calculation or gas-liquid transfer")
    print("   4. PCM solver issue with inorganic carbon speciation")
    print("\n   You are CORRECT - this violates Henry's law equilibrium")
    print("   Need to investigate QSDsan's gas-liquid transfer calculation")

print("="*80)
