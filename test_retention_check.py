#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Check if AnaerobicCSTRmADM1 reactor has particulate retention enabled.

This script instantiates the reactor and checks the _f_retain attribute.
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

async def test_retention():
    # Load components first
    from utils.qsdsan_loader import get_qsdsan_components
    print("Loading QSDsan components...")
    components = await get_qsdsan_components()
    print(f"Loaded {len(components)} components\n")

    # Import after components loaded
    from qsdsan import WasteStream
    from utils.qsdsan_madm1 import ModifiedADM1, create_madm1_cmps
    from utils.qsdsan_reactor_madm1 import AnaerobicCSTRmADM1
    from utils.qsdsan_simulation_sulfur import create_influent_stream_sulfur

    # Load ADM1 state
    with open('simulation_basis.json', 'r') as f:
        basis = json.load(f)
    with open('simulation_adm1_state.json', 'r') as f:
        adm1_state = json.load(f)

    # Create model (same as simulation)
    print("Creating mADM1 model...")
    madm1_cmps = create_madm1_cmps()
    madm1_model = ModifiedADM1(components=madm1_cmps)

    # Create influent
    Q = basis['Q']
    Temp = 273.15 + basis['Temp']
    inf = create_influent_stream_sulfur(Q, Temp, adm1_state)
    eff = WasteStream('Effluent', T=Temp)
    gas = WasteStream('Biogas')

    # Create reactor (same as simulation)
    HRT = 30
    V_liq = Q * HRT
    V_gas = V_liq * 0.1

    print(f"Creating AnaerobicCSTRmADM1...")
    AD = AnaerobicCSTRmADM1(
        'AD',
        ins=inf,
        outs=(gas, eff),
        model=madm1_model,
        V_liq=V_liq,
        V_gas=V_gas,
        T=Temp,
        isdynamic=True
    )

    print("\n" + "="*80)
    print("PARTICULATE RETENTION CHECK")
    print("="*80)

    # Check retention parameters
    print(f"\nReactor ID: {AD.ID}")
    print(f"V_liq: {AD.V_liq:.1f} m3")
    print(f"V_gas: {AD.V_gas:.1f} m3")

    # Check _f_retain attribute
    if hasattr(AD, '_f_retain'):
        f_rtn = AD._f_retain
        print(f"\n_f_retain shape: {f_rtn.shape}")
        print(f"_f_retain min: {f_rtn.min():.6f}")
        print(f"_f_retain max: {f_rtn.max():.6f}")
        print(f"_f_retain mean: {f_rtn.mean():.6f}")

        # Check which components have retention
        retained = []
        for i, val in enumerate(f_rtn):
            if val > 0:
                retained.append((components.IDs[i], val))

        if retained:
            print(f"\n✗ RETENTION ENABLED for {len(retained)} components:")
            for comp_id, rtn in retained[:10]:  # Show first 10
                print(f"  {comp_id}: {rtn:.6f}")
            if len(retained) > 10:
                print(f"  ... and {len(retained)-10} more")
        else:
            print("\n✓ NO RETENTION - all components pass through (standard CSTR)")
    else:
        print("\n⚠ No _f_retain attribute found!")

    # Check retain_cmps parameter
    if hasattr(AD, 'retain_cmps'):
        print(f"\nretain_cmps: {AD.retain_cmps}")

    if hasattr(AD, 'fraction_retain'):
        print(f"fraction_retain: {AD.fraction_retain}")

    print("\n" + "="*80)
    print("CONCLUSION")
    print("="*80)

    if hasattr(AD, '_f_retain') and AD._f_retain.max() > 0:
        print("\n✗ Reactor IS retaining particulates!")
        print("  → This explains the 2,028 kg COD/d 'missing' from balance")
        print("  → COD is accumulating in reactor inventory, not leaving with effluent")
        print("\n  To simulate a true CSTR (no retention), add:")
        print("  → retain_cmps=() (default, but explicit)")
        print("  → OR ensure fraction_retain=0")
    else:
        print("\n✓ Reactor operates as standard CSTR (no retention)")
        print("  → All particulates should leave with effluent")
        print("  → COD imbalance has another cause")

# Run the async test
if __name__ == "__main__":
    asyncio.run(test_retention())
