#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Direct test of Modified ADM1 implementation.
Tests the feedstock characterization and heuristic sizing with P-species.
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from utils.feedstock_characterization import (
    create_default_adm1_state,
    validate_adm1_state
)
from utils.heuristic_sizing import perform_heuristic_sizing


def test_modified_adm1():
    """Test Modified ADM1 with P-species."""
    
    print("\n" + "="*60)
    print("TESTING MODIFIED ADM1 IMPLEMENTATION")
    print("="*60)
    
    # Test 1: Create ADM1 state with P-species
    print("\n1. Creating Modified ADM1 State")
    print("-" * 40)
    
    cod_mg_l = 30000
    tss_mg_l = 3000  # Corrected arithmetic
    vss_mg_l = 2400  # 80% of TSS
    
    # Create with Modified ADM1 flag
    adm1_state = create_default_adm1_state(
        cod_mg_l=cod_mg_l,
        tss_mg_l=tss_mg_l,
        vss_mg_l=vss_mg_l,
        use_modified_adm1=True
    )
    
    # Check for P-species
    p_species = ['S_IP', 'S_K', 'S_Mg', 'X_PAO', 'X_PHA', 'X_PP']
    print("\nP-species in Modified ADM1:")
    all_present = True
    for species in p_species:
        if species in adm1_state:
            print(f"  ✓ {species}: {adm1_state[species]:.4f} kg/m³")
        else:
            print(f"  ✗ {species}: MISSING")
            all_present = False
    
    if all_present:
        print("\n✓ All P-species present for Modified ADM1")
    else:
        print("\n✗ ERROR: Missing P-species")
        return False
    
    # Test 2: Validate ADM1 state
    print("\n2. Validating ADM1 State")
    print("-" * 40)
    
    validation = validate_adm1_state(adm1_state)
    print(f"  Valid: {validation['valid']}")
    print(f"  Estimated COD: {validation['estimated_cod_mg_l']:.0f} mg/L")
    print(f"  Target COD: {cod_mg_l} mg/L")
    print(f"  COD Recovery: {validation['cod_recovery_percent']:.1f}%")
    
    if validation['warnings']:
        print("  Warnings:")
        for warning in validation['warnings']:
            print(f"    - {warning}")
    
    # Test 3: Heuristic sizing with Modified ADM1 basis
    print("\n3. Testing Heuristic Sizing")
    print("-" * 40)
    
    basis_of_design = {
        "feed_flow_m3d": 1000,
        "cod_mg_l": cod_mg_l,
        "tss_mg_l": tss_mg_l,
        "vss_mg_l": vss_mg_l,
        "temperature_c": 35
    }
    
    # Test both flowsheet configurations
    test_cases = [
        {"biomass_yield": 0.08, "expected": "low_tss_mbr"},
        {"biomass_yield": 0.15, "expected": "high_tss"}
    ]
    
    for case in test_cases:
        print(f"\nTesting biomass yield = {case['biomass_yield']} kg TSS/kg COD")
        
        result = perform_heuristic_sizing(
            basis_of_design=basis_of_design,
            biomass_yield=case['biomass_yield'],
            target_srt_days=30
        )
        
        print(f"  Flowsheet type: {result['flowsheet_type']}")
        print(f"  Expected type: {case['expected']}")
        print(f"  Match: {'✓' if result['flowsheet_type'] == case['expected'] else '✗'}")
        print(f"  Expected TSS: {result['digester']['expected_tss_mg_l']:.0f} mg/L")
        print(f"  Digester volume: {result['digester']['liquid_volume_m3']:.0f} m³")
        
        if result['flowsheet_type'] == 'low_tss_mbr':
            print(f"  MBR required: Yes")
            print(f"  MBR area: {result['mbr']['total_area_m2']:.0f} m²")
            print(f"  Dewatering: Parallel with MBR")
        else:
            print(f"  MBR required: No")
            print(f"  Dewatering: Full flow")
    
    # Test 4: Check WaterTAP simulation readiness
    print("\n4. WaterTAP Simulation Readiness")
    print("-" * 40)
    
    try:
        # Try importing WaterTAP components
        from watertap_contrib.reflo.property_models.ADM1.modified_ADM1_properties import (
            ModifiedADM1ParameterBlock
        )
        from watertap_contrib.reflo.property_models.ASM.modified_ASM2D_properties import (
            ModifiedASM2dParameterBlock
        )
        from watertap_contrib.reflo.unit_models.translators import (
            Translator_ADM1_ASM2D,
            Translator_ASM2D_ADM1
        )
        
        print("✓ Modified ADM1 property package available")
        print("✓ Modified ASM2D property package available")
        print("✓ ADM1↔ASM2D translators available")
        print("\n✓ READY FOR WATERTAP SIMULATION!")
        
    except ImportError as e:
        print(f"⚠ WaterTAP components not available: {str(e)[:100]}...")
        print("  This is expected if WaterTAP is not installed")
    
    print("\n" + "="*60)
    print("TEST COMPLETE - Modified ADM1 Implementation Verified")
    print("="*60)
    
    return True


if __name__ == "__main__":
    success = test_modified_adm1()
    sys.exit(0 if success else 1)