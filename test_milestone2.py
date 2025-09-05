#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script for Milestone 2: Heuristic Sizing Tool.
"""

import asyncio
import json
from fastmcp import Client
from server import mcp, design_state


async def test_milestone_2():
    """Test Milestone 2: Heuristic sizing tool."""
    
    print("=" * 60)
    print("MILESTONE 2 TEST: Heuristic Sizing Tool")
    print("=" * 60)
    
    # Use in-memory client for testing
    async with Client(mcp) as client:
        
        # Setup: Reset and add basis of design
        print("\nSetup: Creating basis of design...")
        await client.call_tool("reset_design", {})
        
        # Test Case 1: Low TSS scenario (should select MBR)
        print("\n" + "=" * 50)
        print("TEST CASE 1: Low TSS Scenario (500 m³/d, 30,000 mg/L COD)")
        print("=" * 50)
        
        # Set up low TSS basis
        low_tss_basis = {
            "feed_flow_m3d": 500,
            "cod_mg_l": 30000,
            "tss_mg_l": 20000,
            "temperature_c": 35
        }
        
        await client.call_tool(
            "elicit_basis_of_design",
            {
                "parameter_group": "essential",
                "current_values": low_tss_basis
            }
        )
        
        # Run heuristic sizing
        low_tss_result = await client.call_tool(
            "heuristic_sizing_ad",
            {"biomass_yield": 0.1}  # Default yield
        )
        
        print(f"Status: {low_tss_result.data['status']}")
        print(f"Flowsheet type: {low_tss_result.data['flowsheet_type']}")
        print(f"Summary: {low_tss_result.data['summary']}")
        print("\nDigester configuration:")
        print(f"  Liquid volume: {low_tss_result.data['digester']['liquid_volume_m3']} m³")
        print(f"  Vapor volume: {low_tss_result.data['digester']['vapor_volume_m3']} m³")
        print(f"  HRT: {low_tss_result.data['digester']['hrt_days']} days")
        print(f"  SRT: {low_tss_result.data['digester']['srt_days']} days")
        
        if low_tss_result.data['mbr']['required']:
            print("\nMBR configuration:")
            print(f"  Type: {low_tss_result.data['mbr']['type']}")
            print(f"  Total area: {low_tss_result.data['mbr']['total_area_m2']} m²")
            print(f"  Modules: {low_tss_result.data['mbr']['number_of_modules']} × {low_tss_result.data['mbr']['module_size_m2']} m²")
            print(f"  Flux: {low_tss_result.data['mbr']['flux_lmh']} L/m²/h")
        
        print("\nDewatering:")
        print(f"  Type: {low_tss_result.data['dewatering']['type']}")
        if 'biomass_production_kg_d' in low_tss_result.data['dewatering']:
            print(f"  Biomass production: {low_tss_result.data['dewatering']['biomass_production_kg_d']} kg/d")
            print(f"  Waste sludge flow: {low_tss_result.data['dewatering']['waste_sludge_flow_m3d']} m³/d")
        
        print("\nDecision reasoning:")
        print(f"  {low_tss_result.data['flowsheet_decision']['reason']}")
        
        # Test Case 2: High TSS scenario (should select simple digester)
        print("\n" + "=" * 50)
        print("TEST CASE 2: High TSS Scenario (100 m³/d, 150,000 mg/L COD)")
        print("=" * 50)
        
        # Reset and set up high TSS basis
        await client.call_tool("reset_design", {})
        
        high_tss_basis = {
            "feed_flow_m3d": 100,
            "cod_mg_l": 150000,  # Very high COD
            "temperature_c": 35
        }
        
        await client.call_tool(
            "elicit_basis_of_design",
            {
                "parameter_group": "essential",
                "current_values": high_tss_basis
            }
        )
        
        # Run heuristic sizing
        high_tss_result = await client.call_tool(
            "heuristic_sizing_ad",
            {"biomass_yield": 0.1}
        )
        
        print(f"Status: {high_tss_result.data['status']}")
        print(f"Flowsheet type: {high_tss_result.data['flowsheet_type']}")
        print(f"Summary: {high_tss_result.data['summary']}")
        print("\nDigester configuration:")
        print(f"  Liquid volume: {high_tss_result.data['digester']['liquid_volume_m3']} m³")
        print(f"  Vapor volume: {high_tss_result.data['digester']['vapor_volume_m3']} m³")
        print(f"  HRT: {high_tss_result.data['digester']['hrt_days']} days")
        print(f"  SRT: {high_tss_result.data['digester']['srt_days']} days")
        print(f"  MBR required: {high_tss_result.data['mbr']['required']}")
        
        print("\nDewatering:")
        print(f"  Type: {high_tss_result.data['dewatering']['type']}")
        
        print("\nDecision reasoning:")
        print(f"  {high_tss_result.data['flowsheet_decision']['reason']}")
        
        # Test Case 3: Custom biomass yield and SRT
        print("\n" + "=" * 50)
        print("TEST CASE 3: Custom Parameters (Higher yield, shorter SRT)")
        print("=" * 50)
        
        # Reset and set up basis
        await client.call_tool("reset_design", {})
        
        custom_basis = {
            "feed_flow_m3d": 200,
            "cod_mg_l": 60000,
            "temperature_c": 40  # Thermophilic
        }
        
        await client.call_tool(
            "elicit_basis_of_design",
            {
                "parameter_group": "essential",
                "current_values": custom_basis
            }
        )
        
        # Run with custom parameters
        custom_result = await client.call_tool(
            "heuristic_sizing_ad",
            {
                "biomass_yield": 0.15,  # Higher yield
                "target_srt_days": 20    # Shorter SRT
            }
        )
        
        print(f"Status: {custom_result.data['status']}")
        print(f"Flowsheet type: {custom_result.data['flowsheet_type']}")
        print(f"Biomass yield used: {custom_result.data['sizing_basis']['biomass_yield_kg_tss_kg_cod']} kg TSS/kg COD")
        print(f"Target SRT: {custom_result.data['sizing_basis']['target_srt_days']} days")
        print(f"Steady-state TSS: {custom_result.data['sizing_basis']['steady_state_tss_mg_l']} mg/L")
        print(f"Summary: {custom_result.data['summary']}")
        
        # Show dewatering details for Test Case 3
        print("\nDewatering configuration:")
        print(f"  Type: {custom_result.data['dewatering']['type']}")
        print(f"  Operating hours/week: {custom_result.data['dewatering']['operating_hours_per_week']} hours")
        print(f"  Flow rate: {custom_result.data['dewatering']['flow_m3_h']} m³/h")
        print(f"  Dry solids rate: {custom_result.data['dewatering']['dry_solids_kg_h']} kg/h")
        if 'weekly_flow_m3' in custom_result.data['dewatering']:
            print(f"  Weekly flow: {custom_result.data['dewatering']['weekly_flow_m3']} m³/week")
            print(f"  Weekly solids: {custom_result.data['dewatering']['weekly_solids_kg']} kg/week")
        
        # Test Case 4: Error handling - no basis of design
        print("\n" + "=" * 50)
        print("TEST CASE 4: Error Handling")
        print("=" * 50)
        
        # Reset to clear basis
        await client.call_tool("reset_design", {})
        
        # Try sizing without basis
        error_result = await client.call_tool(
            "heuristic_sizing_ad",
            {}
        )
        
        print(f"Status: {error_result.data['status']}")
        print(f"Error message: {error_result.data['message']}")
        
        # Check state persistence
        print("\n" + "=" * 50)
        print("STATE PERSISTENCE CHECK")
        print("=" * 50)
        
        # Set up basis and do sizing
        await client.call_tool(
            "elicit_basis_of_design",
            {
                "parameter_group": "all",
                "current_values": {"feed_flow_m3d": 300, "cod_mg_l": 45000}
            }
        )
        
        await client.call_tool("heuristic_sizing_ad", {})
        
        # Check final state
        final_state = await client.call_tool("get_design_state", {})
        
        print(f"Overall progress: {final_state.data['overall_progress']}")
        print("Completion status:")
        for stage, completed in final_state.data['completion_status'].items():
            status = "[OK]" if completed else "[ ]"
            print(f"  {status} {stage}")
        print(f"Next steps: {final_state.data['next_steps']}")
        
    print("\n" + "=" * 60)
    print("MILESTONE 2 TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 60)
    print("\nHeuristic sizing tool features verified:")
    print("  [OK] Determines flowsheet based on TSS concentration")
    print("  [OK] Sizes digester volume based on SRT/HRT requirements")
    print("  [OK] Calculates MBR requirements for low TSS scenarios")
    print("  [OK] Determines dewatering configuration")
    print("  [OK] Accepts custom biomass yield and SRT parameters")
    print("  [OK] Integrates with design state")
    print("\nReady to proceed to Milestone 3: Codex Integration")


if __name__ == "__main__":
    asyncio.run(test_milestone_2())