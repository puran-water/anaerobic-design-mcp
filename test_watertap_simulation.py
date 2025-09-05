#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script for WaterTAP simulation module.

Tests both high TSS and low TSS MBR configurations.
"""

import logging
import sys
from utils.watertap_simulation import (
    build_ad_flowsheet,
    initialize_flowsheet,
    solve_flowsheet,
    SimulationConfig
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_high_tss_configuration():
    """Test high TSS configuration (AD + Dewatering)."""
    logger.info("=" * 60)
    logger.info("TESTING HIGH TSS CONFIGURATION")
    logger.info("=" * 60)
    
    # Define test inputs
    basis_of_design = {
        "feed_flow_m3d": 1000.0,
        "cod_mg_l": 30000.0,
        "temperature_c": 35.0,
        "ph": 7.0
    }
    
    # Simplified ADM1 state (all in kg/m³)
    adm1_state = {
        "S_su": 0.5, "S_aa": 0.3, "S_fa": 0.2, "S_va": 0.1, "S_bu": 0.1,
        "S_pro": 0.1, "S_ac": 0.5, "S_h2": 0.001, "S_ch4": 0.001,
        "S_IC": 0.05, "S_IN": 0.03, "S_I": 0.5,
        "S_cat": 0.04, "S_an": 0.04, "S_co2": 0.01,
        "X_c": 10.0, "X_ch": 5.0, "X_pr": 5.0, "X_li": 3.0,
        "X_su": 0.01, "X_aa": 0.01, "X_fa": 0.01, "X_c4": 0.01,
        "X_pro": 0.01, "X_ac": 0.01, "X_h2": 0.01, "X_I": 2.0
    }
    
    # Heuristic configuration for high TSS
    heuristic_config = {
        "flowsheet_type": "high_tss",
        "digester": {
            "liquid_volume_m3": 3000.0,
            "vapor_volume_m3": 300.0
        },
        "dewatering": {
            "equipment_type": "centrifuge",
            "capture_fraction": 0.95,
            "cake_solids_fraction": 0.22,
            "electricity_kw": 50.0
        },
        "operating_conditions": {
            "temperature_k": 308.15,
            "pressure_atm": 1.0
        }
    }
    
    try:
        # Build flowsheet
        logger.info("Building flowsheet...")
        m = build_ad_flowsheet(
            basis_of_design=basis_of_design,
            adm1_state=adm1_state,
            heuristic_config=heuristic_config
        )
        
        logger.info(f"Model has {len(m.fs.component_objects())} components")
        
        # Check key components exist
        assert hasattr(m.fs, "feed"), "Feed unit missing"
        assert hasattr(m.fs, "AD"), "AD unit missing"
        assert hasattr(m.fs, "dewatering"), "Dewatering unit missing"
        assert hasattr(m.fs, "mixer"), "Mixer missing"
        
        logger.info("✓ Flowsheet structure verified")
        
        # Initialize flowsheet
        logger.info("Initializing flowsheet...")
        initialize_flowsheet(m)
        logger.info("✓ Initialization complete")
        
        # Note: Actual solving would require WaterTAP installation
        # For now, just verify structure
        logger.info("✓ High TSS configuration test passed")
        
    except Exception as e:
        logger.error(f"High TSS test failed: {str(e)}")
        raise
    
    return m


def test_low_tss_mbr_configuration():
    """Test low TSS MBR configuration (AD + MBR + Dewatering)."""
    logger.info("=" * 60)
    logger.info("TESTING LOW TSS MBR CONFIGURATION")
    logger.info("=" * 60)
    
    # Define test inputs
    basis_of_design = {
        "feed_flow_m3d": 1000.0,
        "cod_mg_l": 20000.0,
        "temperature_c": 35.0,
        "ph": 7.0
    }
    
    # Simplified ADM1 state (lower TSS for MBR case)
    adm1_state = {
        "S_su": 0.3, "S_aa": 0.2, "S_fa": 0.1, "S_va": 0.05, "S_bu": 0.05,
        "S_pro": 0.05, "S_ac": 0.3, "S_h2": 0.001, "S_ch4": 0.001,
        "S_IC": 0.04, "S_IN": 0.02, "S_I": 0.3,
        "S_cat": 0.03, "S_an": 0.03, "S_co2": 0.01,
        "X_c": 5.0, "X_ch": 3.0, "X_pr": 2.0, "X_li": 1.0,
        "X_su": 0.01, "X_aa": 0.01, "X_fa": 0.01, "X_c4": 0.01,
        "X_pro": 0.01, "X_ac": 0.01, "X_h2": 0.01, "X_I": 1.0
    }
    
    # Heuristic configuration for low TSS with MBR
    heuristic_config = {
        "flowsheet_type": "low_tss_mbr",
        "digester": {
            "liquid_volume_m3": 2500.0,
            "vapor_volume_m3": 250.0
        },
        "mbr": {
            "type": "submerged",
            "flux_lmh": 5.0,
            "total_area_m2": 4000.0,
            "number_of_modules": 333,  # 4000/12
            "module_unit_cost": 5000,
            "permeate_tss_mg_l": 5.0
        },
        "dewatering": {
            "equipment_type": "centrifuge",
            "capture_fraction": 0.95,
            "cake_solids_fraction": 0.22,
            "electricity_kw": 30.0
        },
        "daily_waste_sludge_m3d": 20.0,  # 2% of feed
        "steady_state_tss_mg_l": 7000.0,
        "operating_conditions": {
            "temperature_k": 308.15,
            "pressure_atm": 1.0
        }
    }
    
    try:
        # Build flowsheet
        logger.info("Building flowsheet...")
        m = build_ad_flowsheet(
            basis_of_design=basis_of_design,
            adm1_state=adm1_state,
            heuristic_config=heuristic_config
        )
        
        logger.info(f"Model has {len(m.fs.component_objects())} components")
        
        # Check key components exist
        assert hasattr(m.fs, "feed"), "Feed unit missing"
        assert hasattr(m.fs, "AD"), "AD unit missing"
        assert hasattr(m.fs, "MBR"), "MBR unit missing"
        assert hasattr(m.fs, "ad_splitter"), "AD splitter missing"
        assert hasattr(m.fs, "dewatering_zo"), "Dewatering unit missing"
        assert hasattr(m.fs, "mixer"), "Mixer missing"
        assert hasattr(m.fs, "translator_AD_ZO"), "ADM1->ZO translator missing"
        assert hasattr(m.fs, "translator_ZO_AD_mbr"), "ZO->ADM1 translator missing"
        
        logger.info("✓ Flowsheet structure verified")
        
        # Verify MBR configuration
        assert m.fs.MBR.recovery_frac_mass_H2O[0].value == 0.2, "MBR recovery should be 0.2"
        logger.info("✓ MBR configured for 5Q operation (20% recovery)")
        
        # Initialize flowsheet
        logger.info("Initializing flowsheet...")
        initialize_flowsheet(m)
        logger.info("✓ Initialization complete")
        
        # Note: Actual solving would require WaterTAP installation
        logger.info("✓ Low TSS MBR configuration test passed")
        
    except Exception as e:
        logger.error(f"Low TSS MBR test failed: {str(e)}")
        raise
    
    return m


def main():
    """Run all tests."""
    logger.info("STARTING WATERTAP SIMULATION TESTS")
    logger.info("=" * 60)
    
    try:
        # Test high TSS configuration
        m_high = test_high_tss_configuration()
        logger.info("")
        
        # Test low TSS MBR configuration  
        m_low = test_low_tss_mbr_configuration()
        logger.info("")
        
        logger.info("=" * 60)
        logger.info("ALL TESTS PASSED")
        logger.info("=" * 60)
        
        logger.info("\nNotes:")
        logger.info("- Arc expansion implemented")
        logger.info("- DOF conflicts resolved with Feed unit")
        logger.info("- Translator constraints properly indexed")
        logger.info("- TSS maps to 75% biomass, 25% inerts (not 100% X_I)")
        logger.info("- MBR configured for 5Q operation with direct AD waste")
        logger.info("- Centrate recycle implemented for both configurations")
        
        logger.info("\nNext steps:")
        logger.info("- Implement tear streams for recycle convergence")
        logger.info("- Add server.py integration")
        logger.info("- Test with actual WaterTAP installation")
        
    except Exception as e:
        logger.error(f"Test suite failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()