#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test if stream.COD property is correctly calculated for mADM1 streams.

Hypothesis: QSDsan's stream.COD property might not correctly handle
the mADM1 sulfur components (S_SO4, S_IS, X_hSRB) when calculating total COD.

This test will:
1. Load the effluent stream from simulation
2. Calculate COD manually from component concentrations and i_COD values
3. Compare with stream.COD property
4. Identify any discrepancies
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
import numpy as np

async def test_stream_cod():
    # Load components first
    from utils.qsdsan_loader import get_qsdsan_components
    print("Loading QSDsan components...")
    components = await get_qsdsan_components()
    print(f"Loaded {len(components)} components\n")

    # Import after components loaded
    from qsdsan import WasteStream
    from utils.qsdsan_madm1 import ModifiedADM1, create_madm1_cmps
    from utils.qsdsan_simulation_sulfur import create_influent_stream_sulfur

    # Load ADM1 state
    with open('simulation_basis.json', 'r') as f:
        basis = json.load(f)
    with open('simulation_adm1_state.json', 'r') as f:
        adm1_state = json.load(f)

    # Create influent stream (same as simulation)
    Q = basis['Q']
    Temp = 273.15 + basis['Temp']
    inf = create_influent_stream_sulfur(Q, Temp, adm1_state)

    print("="*80)
    print("STREAM COD PROPERTY VERIFICATION")
    print("="*80)

    print(f"\n## INFLUENT STREAM")
    print(f"Flow: {inf.F_vol*24:.1f} m³/d")
    print(f"Temperature: {inf.T-273.15:.1f} °C")

    # Get stream.COD property
    stream_COD = inf.COD  # mg/L
    print(f"\nstream.COD property: {stream_COD:.1f} mg/L")

    # Calculate COD manually from component concentrations
    print(f"\n## MANUAL COD CALCULATION")
    print("Component contributions to COD:")

    total_manual_COD = 0
    cmps = components

    # Get component concentrations in kg/m3
    conc = inf.conc  # kg/m3 array

    for i, cmp_id in enumerate(cmps.IDs):
        c = conc[i]  # kg/m3
        if c > 1e-10:  # Only show non-zero components
            i_COD = cmps.i_COD[i]  # kg COD/kg component
            cod_contribution = c * i_COD * 1000  # mg COD/L
            total_manual_COD += cod_contribution

            if cod_contribution > 1:  # Only show significant contributors
                print(f"  {cmp_id:15s}: {c:10.6f} kg/m³ × {i_COD:.3f} = {cod_contribution:8.1f} mg/L")

    print(f"\n  {'TOTAL':15s}:                                      {total_manual_COD:8.1f} mg/L")

    # Compare
    print(f"\n## COMPARISON")
    print(f"stream.COD:    {stream_COD:.1f} mg/L")
    print(f"Manual calc:   {total_manual_COD:.1f} mg/L")
    diff = stream_COD - total_manual_COD
    pct_diff = 100 * diff / stream_COD if stream_COD > 0 else 0
    print(f"Difference:    {diff:.1f} mg/L ({pct_diff:.2f}%)")

    if abs(pct_diff) < 1:
        print("\n✓ stream.COD matches manual calculation")
        print("  → QSDsan correctly calculates COD for mADM1 components")
    else:
        print(f"\n✗ stream.COD DISAGREES with manual calculation by {abs(pct_diff):.1f}%!")
        print("  → This could be the source of the COD imbalance")
        print("\n  Possible causes:")
        print("  1. Some mADM1 components have incorrect i_COD values")
        print("  2. stream.COD property doesn't include all components")
        print("  3. stream.COD uses different units/calculation method")

    # Check i_COD values for sulfur components
    print(f"\n## SULFUR COMPONENT i_COD VALUES")
    sulfur_cmps = ['S_SO4', 'S_IS', 'X_hSRB', 'S_H2S', 'S_HS']
    for cmp_id in sulfur_cmps:
        if cmp_id in cmps.IDs:
            idx = cmps.index(cmp_id)
            i_COD = cmps.i_COD[idx]
            measured_as = getattr(cmps[cmp_id], 'measured_as', 'N/A')
            print(f"  {cmp_id:10s}: i_COD = {i_COD:.6f}, measured_as = {measured_as}")
        else:
            print(f"  {cmp_id:10s}: NOT FOUND in component list")

    print("\n" + "="*80)

# Run the async test
if __name__ == "__main__":
    asyncio.run(test_stream_cod())
