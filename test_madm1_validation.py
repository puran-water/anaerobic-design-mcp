#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test validation functions with full mADM1 state (63 components).

Verifies that validation tools correctly handle all 62 mADM1 state variables.
"""

import sys
import json
from pathlib import Path

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent))

from utils.qsdsan_validation_sync import (
    validate_adm1_state_sync,
    calculate_composites_sync,
    check_charge_balance_sync
)

def create_test_madm1_state():
    """
    Create a realistic mADM1 state for municipal wastewater AD effluent.

    Target: COD 500 mg/L, TSS 250 mg/L, VSS 200 mg/L, TKN 40 mg-N/L, TP 8 mg-P/L
    """
    state = {
        # Core ADM1 soluble (0-12) - all in kg/m³ (= g/L)
        'S_su': 0.001,      # Sugars (minimal in effluent)
        'S_aa': 0.001,      # Amino acids
        'S_fa': 0.001,      # Long chain fatty acids
        'S_va': 0.002,      # Valerate
        'S_bu': 0.003,      # Butyrate
        'S_pro': 0.004,     # Propionate
        'S_ac': 0.020,      # Acetate (major VFA)
        'S_h2': 2.5e-7,     # Hydrogen
        'S_ch4': 0.055,     # Dissolved methane
        'S_IC': 0.040,      # Inorganic carbon (as C) - 40 mg/L
        'S_IN': 0.040,      # Inorganic nitrogen (as N) - 40 mg-N/L
        'S_IP': 0.008,      # Inorganic phosphorus (as P) - 8 mg-P/L
        'S_I': 0.030,       # Soluble inerts - 30 mg/L

        # Core ADM1 particulates (13-23) - much lower in effluent
        'X_ch': 0.005,      # Carbohydrates
        'X_pr': 0.005,      # Proteins
        'X_li': 0.003,      # Lipids
        'X_su': 0.050,      # Sugar degraders
        'X_aa': 0.015,      # Amino acid degraders
        'X_fa': 0.030,      # LCFA degraders
        'X_c4': 0.050,      # Valerate/butyrate degraders
        'X_pro': 0.020,     # Propionate degraders
        'X_ac': 0.080,      # Acetoclastic methanogens
        'X_h2': 0.040,      # Hydrogenotrophic methanogens
        'X_I': 0.025,       # Particulate inerts

        # EBPR extension (24-26)
        'X_PHA': 0.0,       # Polyhydroxyalkanoates (no EBPR in AD)
        'X_PP': 0.0,        # Polyphosphate
        'X_PAO': 0.0,       # PAO biomass

        # Metal ions (27-28)
        'S_K': 0.028,       # Potassium (28 mg/L)
        'S_Mg': 0.015,      # Magnesium (15 mg/L)

        # Sulfur species (29-35)
        'S_SO4': 0.030,     # Sulfate (30 mg-S/L)
        'S_IS': 0.005,      # Dissolved sulfide (5 mg-S/L)
        'X_hSRB': 0.010,    # Hydrogenotrophic SRB
        'X_aSRB': 0.008,    # Acetoclastic SRB
        'X_pSRB': 0.005,    # Propionate SRB
        'X_c4SRB': 0.003,   # C4 SRB
        'S_S0': 0.0,        # Elemental sulfur

        # Iron species (36-44)
        'S_Fe3': 0.001,     # Ferric iron (1 mg/L)
        'S_Fe2': 0.005,     # Ferrous iron (5 mg/L)
        'X_HFO_H': 0.0,     # Hydrous ferric oxide (high reactivity)
        'X_HFO_L': 0.0,     # HFO (low reactivity)
        'X_HFO_old': 0.0,   # Aged HFO
        'X_HFO_HP': 0.0,    # HFO with high P
        'X_HFO_LP': 0.0,    # HFO with low P
        'X_HFO_HP_old': 0.0,
        'X_HFO_LP_old': 0.0,

        # More metals (45-46)
        'S_Ca': 0.060,      # Calcium (60 mg/L)
        'S_Al': 0.001,      # Aluminum (1 mg/L)

        # Mineral precipitates (47-59) - typically minimal in well-mixed AD
        'X_CCM': 0.0,       # Calcium carbonate (calcite)
        'X_ACC': 0.0,       # Amorphous calcium carbonate
        'X_ACP': 0.0,       # Amorphous calcium phosphate
        'X_HAP': 0.0,       # Hydroxylapatite
        'X_DCPD': 0.0,      # Dicalcium phosphate dihydrate
        'X_OCP': 0.0,       # Octacalcium phosphate
        'X_struv': 0.0,     # Struvite
        'X_newb': 0.0,      # Newberyite
        'X_magn': 0.0,      # Magnesite
        'X_kstruv': 0.0,    # K-struvite
        'X_FeS': 0.0,       # Iron sulfide
        'X_Fe3PO42': 0.0,   # Iron phosphate
        'X_AlPO4': 0.0,     # Aluminum phosphate

        # Final ions (60-61)
        'S_Na': 0.150,      # Sodium (150 mg/L)
        'S_Cl': 0.200,      # Chloride (200 mg/L)

        # Water (62) - not needed in concentration dict
    }

    return state


def main():
    print("="*80)
    print("mADM1 Validation Test (63 components)")
    print("="*80)
    print()

    # Create test state
    print("1. Creating test mADM1 state...")
    adm1_state = create_test_madm1_state()
    print(f"   [OK] Created state with {len(adm1_state)} components")
    print()

    # Test 1: Calculate composites
    print("2. Testing calculate_composites_sync...")
    temperature_k = 273.15 + 35.0

    try:
        composites = calculate_composites_sync(adm1_state, temperature_k)
        print(f"   [OK] Calculated composites:")
        print(f"        COD:  {composites['cod_mg_l']:.1f} mg/L")
        print(f"        TSS:  {composites['tss_mg_l']:.1f} mg/L")
        print(f"        VSS:  {composites['vss_mg_l']:.1f} mg/L")
        print(f"        TKN:  {composites['tkn_mg_l']:.1f} mg-N/L")
        print(f"        TP:   {composites['tp_mg_l']:.1f} mg-P/L")
        print()
    except Exception as e:
        print(f"   [FAIL] Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Test 2: Validate against targets
    print("3. Testing validate_adm1_state_sync...")
    user_params = {
        'cod_mg_l': 500.0,
        'tss_mg_l': 250.0,
        'vss_mg_l': 200.0,
        'tkn_mg_l': 40.0,
        'tp_mg_l': 8.0
    }

    try:
        validation = validate_adm1_state_sync(
            adm1_state=adm1_state,
            user_parameters=user_params,
            tolerance=0.15,  # 15% tolerance
            temperature_k=temperature_k
        )

        print(f"   Validation result: {'PASS' if validation['valid'] else 'FAIL'}")
        print()
        print("   Parameter comparisons:")
        for param, pf in validation['pass_fail'].items():
            dev = validation['deviations'][param]
            calc = dev['calculated']
            target = dev['target']
            deviation = dev['deviation_percent']
            status = '[OK]' if pf == 'PASS' else '[WARN]'
            print(f"   {status} {param.upper():10s}: {calc:6.1f} mg/L (target: {target:6.1f}, dev: {deviation:5.1f}%)")
        print()

        if validation['warnings']:
            print("   Warnings:")
            for warning in validation['warnings']:
                print(f"     - {warning}")
            print()

    except Exception as e:
        print(f"   [FAIL] Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Test 3: Check charge balance
    print("4. Testing check_charge_balance_sync...")

    try:
        balance = check_charge_balance_sync(
            adm1_state=adm1_state,
            ph=7.0,
            temperature_k=temperature_k
        )

        print(f"   Charge balance: {'BALANCED' if balance['balanced'] else 'IMBALANCED'}")
        print(f"   Net charge:     {balance['net_charge_mmol_l']:.4f} mmol/L")
        print(f"   Residual:       {balance['residual_meq_l']:.4f} meq/L")
        print(f"   Imbalance:      {balance['imbalance_percent']:.2f}%")
        print(f"   Calculated pH:  {balance['calculated_ph']:.2f}")
        print(f"   Target pH:      {balance['target_ph']:.2f}")
        print(f"   Status:         {balance['message']}")
        print()

    except Exception as e:
        print(f"   [FAIL] Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    print("="*80)
    print("All validation tests completed successfully")
    print("="*80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
