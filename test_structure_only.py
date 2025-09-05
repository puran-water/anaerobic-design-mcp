#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Simplified test to verify flowsheet structure without full WaterTAP simulation.

This test focuses on validating that the server tools work correctly.
"""

import asyncio
import logging
from server import (
    elicit_basis_of_design,
    characterize_feedstock,
    heuristic_sizing_ad,
    get_design_state,
    reset_design
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_full_workflow():
    """Test the complete workflow through the MCP server tools."""
    
    logger.info("=" * 60)
    logger.info("TESTING MCP SERVER WORKFLOW")
    logger.info("=" * 60)
    
    # Reset state
    logger.info("\n1. Resetting design state...")
    result = await reset_design()
    assert result["status"] == "success"
    logger.info("✓ Reset successful")
    
    # Elicit basis of design
    logger.info("\n2. Eliciting basis of design...")
    result = await elicit_basis_of_design(
        parameter_group="essential",
        current_values={
            "feed_flow_m3d": 1000.0,
            "cod_mg_l": 30000.0,
            "temperature_c": 35.0
        }
    )
    assert result["status"] == "success"
    assert result["parameters"]["feed_flow_m3d"] == 1000.0
    logger.info(f"✓ Basis collected: {result['parameters']}")
    
    # Characterize feedstock
    logger.info("\n3. Characterizing feedstock...")
    result = await characterize_feedstock(
        feedstock_description="High-strength dairy wastewater",
        use_codex=False,  # Use pattern matching for simplicity
        measured_parameters={
            "cod_mg_l": 30000.0,
            "tss_mg_l": 15000.0,
            "ph": 7.0
        }
    )
    assert result["status"] == "success"
    assert "adm1_state" in result
    logger.info(f"✓ ADM1 state generated with {len(result['adm1_state'])} components")
    
    # Heuristic sizing - High TSS case
    logger.info("\n4a. Testing heuristic sizing for HIGH TSS...")
    result = await heuristic_sizing_ad(
        biomass_yield=0.1,
        target_srt_days=30
    )
    assert result["status"] == "success"
    assert result["flowsheet_type"] == "high_tss"
    logger.info(f"✓ High TSS configuration: Volume={result['digester']['liquid_volume_m3']} m³")
    logger.info(f"  Dewatering: {result['dewatering']['equipment_type']}")
    
    # Reset and test Low TSS case
    logger.info("\n4b. Testing heuristic sizing for LOW TSS...")
    await reset_design()
    await elicit_basis_of_design(
        parameter_group="essential",
        current_values={
            "feed_flow_m3d": 1000.0,
            "cod_mg_l": 15000.0,  # Lower COD
            "temperature_c": 35.0
        }
    )
    await characterize_feedstock(
        feedstock_description="Municipal wastewater",
        use_codex=False,
        measured_parameters={
            "cod_mg_l": 15000.0,
            "tss_mg_l": 5000.0,
            "ph": 7.0
        }
    )
    
    result = await heuristic_sizing_ad(
        biomass_yield=0.1,
        target_srt_days=30
    )
    assert result["status"] == "success"
    assert result["flowsheet_type"] == "low_tss_mbr"
    logger.info(f"✓ Low TSS MBR configuration: Volume={result['digester']['liquid_volume_m3']} m³")
    logger.info(f"  MBR area: {result['mbr']['total_area_m2']} m²")
    logger.info(f"  MBR modules: {result['mbr']['number_of_modules']}")
    
    # Get final design state
    logger.info("\n5. Getting final design state...")
    state = await get_design_state()
    assert state["basis_of_design"] is not None
    assert state["adm1_state"] is not None
    assert state["heuristic_config"] is not None
    logger.info(f"✓ Complete design state retrieved")
    logger.info(f"  Completion status: {state['completion_status']}")
    
    logger.info("\n" + "=" * 60)
    logger.info("ALL TESTS PASSED!")
    logger.info("=" * 60)
    
    # Summary
    logger.info("\nSUMMARY:")
    logger.info("- MCP server tools working correctly")
    logger.info("- Heuristic sizing properly selects flowsheet type")
    logger.info("- High TSS (>10,000 mg/L) → Simple AD + dewatering")
    logger.info("- Low TSS (<10,000 mg/L) → AD + MBR + dewatering")
    logger.info("- Design state management working")
    logger.info("- ADM1 state generation working")
    
    logger.info("\nNEXT STEPS:")
    logger.info("- Fix WaterTAP property package issues separately")
    logger.info("- Consider using IDAES Separator instead of ZO units")
    logger.info("- Or create minimal custom dewatering unit")
    logger.info("- Focus on getting simulation running with simplified approach")


async def main():
    """Run all tests."""
    try:
        await test_full_workflow()
    except Exception as e:
        logger.error(f"Test failed: {str(e)}")
        raise


if __name__ == "__main__":
    asyncio.run(main())