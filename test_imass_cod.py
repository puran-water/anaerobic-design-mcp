#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test to extract raw imass values from gas stream and calculate COD directly.

According to BIOGAS_BUG_ANALYSIS.md:
"In ADM1/mADM1, `imass` stores *kg COD/hr*, not actual kilograms of sulfur."

So gas.imass['S_ch4'] should directly give kg COD/hr, which we multiply by 24 to get kg COD/d.
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp')

# Patch fluids before QSDsan import
import fluids.numerics
if not hasattr(fluids.numerics, 'PY37'):
    fluids.numerics.PY37 = True

import json
import asyncio

async def test_imass_cod():
    # Load components first
    from utils.qsdsan_loader import get_qsdsan_components
    print("Loading QSDsan components...")
    components = await get_qsdsan_components()
    print(f"Loaded {len(components)} components\n")

    # Now import simulation after components are loaded
    from utils.qsdsan_simulation_sulfur import run_simulation_sulfur

    # Load configuration
    with open('simulation_basis.json', 'r') as f:
        basis = json.load(f)
    with open('simulation_adm1_state.json', 'r') as f:
        adm1_state = json.load(f)

    # Run a short simulation (just to get the streams)
    print("Running simulation (50 days)...")
    sys_d, inf_d, eff_d, gas_d, converged_at, status = run_simulation_sulfur(
        basis, adm1_state, HRT=30, simulation_time=50
    )

    print("\n" + "="*80)
    print("BIOGAS COD CALCULATION COMPARISON")
    print("="*80)

    # METHOD 1: Direct from imass (should be kg COD/hr)
    print("\n## METHOD 1: Direct from imass (kg COD/hr)")
    try:
        ch4_imass = gas_d.imass['S_ch4']  # Should be kg COD/hr
        h2_imass = gas_d.imass['S_h2']    # Should be kg COD/hr

        ch4_cod_d = ch4_imass * 24  # kg COD/d
        h2_cod_d = h2_imass * 24    # kg COD/d
        total_imass_cod_d = ch4_cod_d + h2_cod_d

        print(f"gas.imass['S_ch4']: {ch4_imass:.6f} kg COD/hr")
        print(f"gas.imass['S_h2']:  {h2_imass:.6f} kg COD/hr")
        print(f"CH4 COD: {ch4_cod_d:.1f} kg COD/d")
        print(f"H2 COD:  {h2_cod_d:.1f} kg COD/d")
        print(f"TOTAL:   {total_imass_cod_d:.1f} kg COD/d")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        total_imass_cod_d = None

    # METHOD 2: From volumetric flow (current approach in stream_analysis_sulfur.py)
    print("\n## METHOD 2: From volumetric flow + mole fractions (current method)")
    try:
        F_vol_hr = gas_d.F_vol  # m3/hr at operating conditions
        F_mol_hr = gas_d.F_mol  # kmol/hr

        ch4_frac = gas_d.imol['S_ch4'] / F_mol_hr if F_mol_hr > 0 else 0
        h2_frac = gas_d.imol['S_h2'] / F_mol_hr if F_mol_hr > 0 else 0

        ch4_flow_m3_d = F_vol_hr * 24 * ch4_frac
        h2_flow_m3_d = F_vol_hr * 24 * h2_frac

        # Convert to STP
        T_op = 273.15 + 35  # 35°C
        T_stp = 273.15      # 0°C
        ch4_flow_stp = ch4_flow_m3_d * (T_stp / T_op)
        h2_flow_stp = h2_flow_m3_d * (T_stp / T_op)

        # Convert to COD
        ch4_cod = ch4_flow_stp * 2.856  # kg COD/Nm3
        h2_cod = h2_flow_stp * 0.714    # kg COD/Nm3
        total_vol_cod_d = ch4_cod + h2_cod

        print(f"F_vol: {F_vol_hr:.6f} m3/hr = {F_vol_hr*24:.2f} m3/d")
        print(f"F_mol: {F_mol_hr:.6f} kmol/hr")
        print(f"CH4 mole fraction: {ch4_frac:.6f}")
        print(f"CH4 flow (35°C): {ch4_flow_m3_d:.2f} m3/d")
        print(f"CH4 flow (STP): {ch4_flow_stp:.2f} Nm3/d")
        print(f"CH4 COD: {ch4_cod:.1f} kg COD/d")
        print(f"H2 COD:  {h2_cod:.1f} kg COD/d")
        print(f"TOTAL:   {total_vol_cod_d:.1f} kg COD/d")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        total_vol_cod_d = None

    # Comparison
    if total_imass_cod_d is not None and total_vol_cod_d is not None:
        ratio = total_imass_cod_d / total_vol_cod_d
        print(f"\n## COMPARISON")
        print(f"Method 1 (imass):  {total_imass_cod_d:.1f} kg COD/d")
        print(f"Method 2 (volume): {total_vol_cod_d:.1f} kg COD/d")
        print(f"Ratio (imass/volume): {ratio:.4f}x")

        if abs(ratio - 1.0) > 0.01:
            print(f"\n⚠ WARNING: Methods disagree by {abs(ratio-1)*100:.1f}%!")
            if ratio > 2:
                print("   → imass method gives MUCH higher COD")
                print("   → This could explain the missing COD in the balance!")
        else:
            print("\n✓ Methods agree (within 1%)")

    # COD Balance check
    print("\n" + "="*80)
    print("COD BALANCE CHECK")
    print("="*80)

    cod_in = inf_d.F_vol * 24 * inf_d.COD / 1e3  # kg/d
    cod_eff = eff_d.F_vol * 24 * eff_d.COD / 1e3  # kg/d

    print(f"\nCOD IN:  {cod_in:.1f} kg/d")
    print(f"COD OUT (effluent): {cod_eff:.1f} kg/d")

    if total_imass_cod_d is not None:
        print(f"COD OUT (biogas - imass method):  {total_imass_cod_d:.1f} kg/d")
        imbalance_1 = cod_in - cod_eff - total_imass_cod_d
        pct_1 = 100 * imbalance_1 / cod_in
        print(f"IMBALANCE (imass): {imbalance_1:.1f} kg/d ({pct_1:.1f}%)")

        if abs(pct_1) < 10:
            print("✓ COD balance CLOSES with imass method!")
        elif abs(pct_1) < 20:
            print("⚠ Moderate imbalance (10-20%)")
        else:
            print("✗ Severe imbalance (>20%)")

    if total_vol_cod_d is not None:
        print(f"\nCOD OUT (biogas - volume method): {total_vol_cod_d:.1f} kg/d")
        imbalance_2 = cod_in - cod_eff - total_vol_cod_d
        pct_2 = 100 * imbalance_2 / cod_in
        print(f"IMBALANCE (volume): {imbalance_2:.1f} kg/d ({pct_2:.1f}%)")

        if abs(pct_2) < 10:
            print("✓ COD balance CLOSES with volume method!")
        elif abs(pct_2) < 20:
            print("⚠ Moderate imbalance (10-20%)")
        else:
            print("✗ Severe imbalance (>20%)")

    print("\n" + "="*80)
    print("CONCLUSION")
    print("="*80)

    if total_imass_cod_d is not None and total_vol_cod_d is not None:
        if abs(imbalance_1) < abs(imbalance_2):
            print("\n✓ Using imass directly gives BETTER COD balance!")
            print(f"  Improvement: {abs(imbalance_2) - abs(imbalance_1):.1f} kg/d")
            print("\n  → RECOMMENDATION: Use gas.imass directly instead of volumetric conversion")
            print("  → The bug is in stream_analysis_sulfur.py: _analyze_gas_stream_core()")
        else:
            print("\n✓ Volumetric method is correct")
            print("  → The imbalance has another cause")

# Run the async test
if __name__ == "__main__":
    asyncio.run(test_imass_cod())
