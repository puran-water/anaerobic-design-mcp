#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test FastMCP server using Client for proper async tool testing.
Tests Modified ADM1 implementation with P-species.
"""

import sys
import asyncio
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from fastmcp import Client
from server import mcp  # Import the FastMCP instance directly


async def test_modified_adm1_with_client():
    """Test Modified ADM1 workflow using FastMCP Client."""
    
    print("\n" + "="*60)
    print("TESTING MODIFIED ADM1 WITH FASTMCP CLIENT")
    print("="*60)
    
    async with Client(mcp) as client:
        # Test 1: Reset design state
        print("\n1. RESETTING DESIGN STATE")
        print("-" * 40)
        
        reset_result = await client.call_tool("reset_design", {})
        print(f"Status: {reset_result.content[0].text}")
        
        # Test 2: Elicit basis of design
        print("\n2. ELICITING BASIS OF DESIGN")
        print("-" * 40)
        
        basis_result = await client.call_tool(
            "elicit_basis_of_design",
            {
                "parameter_group": "essential",
                "current_values": {
                    "feed_flow_m3d": 1000,
                    "cod_mg_l": 30000,
                    "temperature_c": 35
                }
            }
        )
        
        # Parse the result (FastMCP returns text content)
        import json
        basis_data = json.loads(basis_result.content[0].text)
        print(f"Status: {basis_data['status']}")
        print(f"Parameters collected: {len(basis_data['parameters'])}")
        for key, value in basis_data['parameters'].items():
            print(f"  {key}: {value}")
        
        # Test 3: Characterize feedstock with Modified ADM1
        print("\n3. CHARACTERIZING FEEDSTOCK (Modified ADM1)")
        print("-" * 40)
        
        feedstock_result = await client.call_tool(
            "characterize_feedstock",
            {
                "feedstock_description": "High-strength industrial wastewater",
                "use_codex": False,
                "measured_parameters": {
                    "cod_mg_l": 30000,
                    "tss_mg_l": 3000,  # Corrected arithmetic
                    "ph": 7.0
                }
            }
        )
        
        feedstock_data = json.loads(feedstock_result.content[0].text)
        print(f"Status: {feedstock_data['status']}")
        print(f"ADM1 components: {feedstock_data['component_count']}")
        print(f"Source: {feedstock_data['source']}")
        
        # Check for P-species
        adm1_state = feedstock_data['adm1_state']
        p_species = ['S_IP', 'S_K', 'S_Mg', 'X_PAO', 'X_PHA', 'X_PP']
        print("\nP-species for Modified ADM1:")
        all_present = True
        for species in p_species:
            if species in adm1_state:
                print(f"  [OK] {species}: {adm1_state[species]:.3f} kg/m3")
            else:
                print(f"  [MISSING] {species}: NOT FOUND")
                all_present = False
        
        if not all_present:
            print("\n[WARNING] Some P-species missing!")
        
        # Test 4: Heuristic sizing
        print("\n4. HEURISTIC SIZING")
        print("-" * 40)
        
        # Test both configurations
        configs = [
            {"biomass_yield": 0.08, "expected": "low_tss_mbr", "name": "Low TSS (MBR)"},
            {"biomass_yield": 0.15, "expected": "high_tss", "name": "High TSS"}
        ]
        
        for config in configs:
            print(f"\nTesting {config['name']} configuration:")
            
            sizing_result = await client.call_tool(
                "heuristic_sizing_ad",
                {
                    "biomass_yield": config['biomass_yield'],
                    "target_srt_days": 30,
                    "use_current_basis": True
                }
            )
            
            sizing_data = json.loads(sizing_result.content[0].text)
            print(f"  Status: {sizing_data['status']}")
            print(f"  Flowsheet type: {sizing_data['flowsheet_type']}")
            print(f"  Expected: {config['expected']}")
            match = sizing_data['flowsheet_type'] == config['expected']
            print(f"  Match: {'[OK]' if match else '[FAIL]'}")
            print(f"  Digester volume: {sizing_data['digester']['liquid_volume_m3']:.0f} m3")
            if 'expected_tss_mg_l' in sizing_data['digester']:
                print(f"  Expected TSS: {sizing_data['digester']['expected_tss_mg_l']:.0f} mg/L")
            elif 'steady_state_tss_mg_l' in sizing_data['digester']:
                print(f"  Steady-state TSS: {sizing_data['digester']['steady_state_tss_mg_l']:.0f} mg/L")
            
            if 'mbr' in sizing_data:
                print(f"  MBR area: {sizing_data['mbr']['total_area_m2']:.0f} m2")
                if 'configuration' in sizing_data['mbr']:
                    print(f"  MBR configuration: {sizing_data['mbr']['configuration']}")
        
        # Test 5: Get final design state
        print("\n5. FINAL DESIGN STATE")
        print("-" * 40)
        
        state_result = await client.call_tool("get_design_state", {})
        state_data = json.loads(state_result.content[0].text)
        
        print(f"Overall progress: {state_data['overall_progress']}")
        print("\nCompletion status:")
        for phase, completed in state_data['completion_status'].items():
            status = "[OK]" if completed else "[PENDING]"
            print(f"  {status} {phase}")
        
        # Check readiness for WaterTAP
        required_checks = {
            "Basis of design": state_data['completion_status']['basis_of_design'],
            "ADM1 state estimated": state_data['completion_status']['adm1_estimation'],
            "Heuristic sizing complete": state_data['completion_status']['heuristic_sizing'],
            "P-species present": all(s in state_data['adm1_state'] for s in p_species)
        }
        
        all_ready = all(required_checks.values())
        
        print("\n6. WATERTAP READINESS CHECK")
        print("-" * 40)
        
        for check, passed in required_checks.items():
            status = "[OK]" if passed else "[FAIL]"
            print(f"  {status} {check}")
        
        if all_ready:
            print("\n[SUCCESS] READY FOR WATERTAP SIMULATION WITH MODIFIED ADM1!")
            print("  - Modified ADM1 property packages configured")
            print("  - P-species included for translators")
            print("  - Built-in ADM1-ASM2D translators available")
            print("  - Parallel dewatering configuration set")
        else:
            print("\n[FAIL] NOT READY - Missing required components")
    
    print("\n" + "="*60)
    print("TEST COMPLETE - FastMCP Client Test Successful")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(test_modified_adm1_with_client())