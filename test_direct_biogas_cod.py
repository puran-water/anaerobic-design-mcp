#!/usr/bin/env python
"""
Direct test: Calculate biogas COD from imass values.

This bypasses the stream analysis to directly access gas.imass['S_ch4']
which should be in kg COD/hr according to BIOGAS_BUG_ANALYSIS.md.
"""

import sys
sys.path.insert(0, '/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp')

# Patch fluids before QSDsan import
import fluids.numerics
if not hasattr(fluids.numerics, 'PY37'):
    fluids.numerics.PY37 = True

import json
from utils.qsdsan_simulation_sulfur import run_simulation_sulfur

# Load configuration
with open('simulation_basis.json', 'r') as f:
    basis = json.load(f)
with open('simulation_adm1_state.json', 'r') as f:
    adm1_state = json.load(f)

# Run a short simulation
print("Running simulation...")
sys_d, inf_d, eff_d, gas_d, converged_at, status = run_simulation_sulfur(
    basis, adm1_state, HRT=30, simulation_time=50  # Just 50 days for testing
)

print("\n" + "="*80)
print("DIRECT BIOGAS COD CALCULATION")
print("="*80)

# Method 1: Using imass (kg COD/hr)
print("\n## METHOD 1: Direct from imass (kg COD/hr)")
try:
    ch4_cod_hr = gas_d.imass['S_ch4']  # kg COD/hr
    h2_cod_hr = gas_d.imass['S_h2']    # kg COD/hr
    total_cod_hr = ch4_cod_hr + h2_cod_hr
    total_cod_d = total_cod_hr * 24    # kg COD/d

    print(f"CH4 COD: {ch4_cod_hr:.2f} kg COD/hr = {ch4_cod_hr*24:.1f} kg COD/d")
    print(f"H2 COD:  {h2_cod_hr:.2f} kg COD/hr = {h2_cod_hr*24:.1f} kg COD/d")
    print(f"TOTAL:   {total_cod_hr:.2f} kg COD/hr = {total_cod_d:.1f} kg COD/d")
except Exception as e:
    print(f"ERROR: {e}")

# Method 2: Using F_vol and mole fractions (current approach)
print("\n## METHOD 2: From volumetric flow (current approach)")
try:
    F_vol_hr = gas_d.F_vol  # m3/hr at operating conditions
    F_mol_hr = gas_d.F_mol  # kmol/hr

    ch4_frac = gas_d.imol['S_ch4'] / F_mol_hr if F_mol_hr > 0 else 0
    h2_frac = gas_d.imol['S_h2'] / F_mol_hr if F_mol_hr > 0 else 0

    ch4_flow_m3_d = F_vol_hr * 24 * ch4_frac
    h2_flow_m3_d = F_vol_hr * 24 * h2_frac

    # Convert to STP
    T_op = 308.15  # 35°C
    T_stp = 273.15
    ch4_flow_stp = ch4_flow_m3_d * (T_stp / T_op)
    h2_flow_stp = h2_flow_m3_d * (T_stp / T_op)

    # Convert to COD
    ch4_cod = ch4_flow_stp * 2.856  # kg COD/d
    h2_cod = h2_flow_stp * 0.714    # kg COD/d
    total_cod = ch4_cod + h2_cod

    print(f"F_vol: {F_vol_hr:.4f} m3/hr = {F_vol_hr*24:.2f} m3/d")
    print(f"F_mol: {F_mol_hr:.6f} kmol/hr")
    print(f"CH4 fraction: {ch4_frac:.4f}")
    print(f"H2 fraction: {h2_frac:.6f}")
    print(f"CH4 flow (35°C): {ch4_flow_m3_d:.2f} m3/d")
    print(f"CH4 flow (STP): {ch4_flow_stp:.2f} Nm3/d")
    print(f"CH4 COD: {ch4_cod:.1f} kg COD/d")
    print(f"H2 COD: {h2_cod:.1f} kg COD/d")
    print(f"TOTAL: {total_cod:.1f} kg COD/d")
except Exception as e:
    print(f"ERROR: {e}")

# Method 3: Check raw stream state
print("\n## METHOD 3: Raw stream inspection")
try:
    print(f"gas.state shape: {gas_d.state.shape}")
    print(f"gas.state[-1] (should be F_vol): {gas_d.state[-1]:.6f}")
    print(f"Components: {gas_d.components.IDs}")
    print(f"\nComponent imass values (kg COD/hr):")
    for comp_id in ['S_ch4', 'S_h2', 'S_IC']:
        if comp_id in gas_d.components.IDs:
            print(f"  {comp_id}: {gas_d.imass[comp_id]:.6f} kg COD/hr")
except Exception as e:
    print(f"ERROR: {e}")

# COD Balance check
print("\n" + "="*80)
print("COD BALANCE CHECK")
print("="*80)

cod_in = inf_d.F_vol * 24 * inf_d.COD / 1e3  # m3/d * mg/L / 1000 = kg/d
cod_eff = eff_d.F_vol * 24 * eff_d.COD / 1e3

print(f"COD IN:  {cod_in:.1f} kg/d")
print(f"COD OUT (effluent): {cod_eff:.1f} kg/d")
print(f"COD OUT (biogas Method 1): {total_cod_d if 'total_cod_d' in locals() else 'N/A'}")
print(f"COD OUT (biogas Method 2): {total_cod if 'total_cod' in locals() else 'N/A'} kg/d")

if 'total_cod_d' in locals():
    imbalance_1 = cod_in - cod_eff - total_cod_d
    print(f"\nImbalance (Method 1): {imbalance_1:.1f} kg/d ({100*imbalance_1/cod_in:.1f}%)")

if 'total_cod' in locals():
    imbalance_2 = cod_in - cod_eff - total_cod
    print(f"Imbalance (Method 2): {imbalance_2:.1f} kg/d ({100*imbalance_2/cod_in:.1f}%)")
