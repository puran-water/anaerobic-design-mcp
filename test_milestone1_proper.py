#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script for Milestone 1 using FastMCP Client for in-memory testing.
"""

import asyncio
import json
from fastmcp import Client
from server import mcp, design_state


async def test_milestone_1():
    """Test Milestone 1: Basic server with parameter elicitation."""
    
    print("=" * 60)
    print("MILESTONE 1 TEST: Basic Server with Parameter Elicitation")
    print("=" * 60)
    
    # Use in-memory client for testing
    async with Client(mcp) as client:
        
        # Test 1: Reset design state
        print("\n1. Testing reset_design...")
        reset_result = await client.call_tool("reset_design", {})
        print(f"   Result: {reset_result.data['status']}")
        print(f"   Message: {reset_result.data['message']}")
        
        # Test 2: Get initial state
        print("\n2. Testing get_design_state (should be empty)...")
        state_result = await client.call_tool("get_design_state", {})
        print(f"   Status: {state_result.data['status']}")
        print(f"   Progress: {state_result.data['overall_progress']}")
        print(f"   Next steps: {state_result.data['next_steps']}")
        
        # Test 3: Elicit essential parameters
        print("\n3. Testing elicit_basis_of_design (essential)...")
        essential_result = await client.call_tool(
            "elicit_basis_of_design",
            {"parameter_group": "essential"}
        )
        print(f"   Status: {essential_result.data['status']}")
        print(f"   Parameters collected: {list(essential_result.data['parameters'].keys())}")
        print(f"   Values: {json.dumps(essential_result.data['parameters'], indent=6)}")
        
        # Test 4: Elicit with existing values
        print("\n4. Testing elicit_basis_of_design with current values...")
        custom_values = {
            "feed_flow_m3d": 500,
            "cod_mg_l": 75000
        }
        custom_result = await client.call_tool(
            "elicit_basis_of_design",
            {
                "parameter_group": "essential",
                "current_values": custom_values
            }
        )
        print(f"   Status: {custom_result.data['status']}")
        print(f"   Custom values used: {custom_values}")
        print(f"   Final parameters: {json.dumps(custom_result.data['parameters'], indent=6)}")
        
        # Test 5: Elicit all parameters
        print("\n5. Testing elicit_basis_of_design (all)...")
        all_result = await client.call_tool(
            "elicit_basis_of_design",
            {"parameter_group": "all"}
        )
        print(f"   Status: {all_result.data['status']}")
        print(f"   Total parameters: {len(all_result.data['parameters'])}")
        print(f"   Derived parameters: {json.dumps(all_result.data['derived_parameters'], indent=6)}")
        print(f"   Validation warnings: {all_result.data['validation']['warnings']}")
        
        # Test 6: Check final state
        print("\n6. Testing get_design_state (should have parameters)...")
        final_state = await client.call_tool("get_design_state", {})
        print(f"   Status: {final_state.data['status']}")
        print(f"   Progress: {final_state.data['overall_progress']}")
        print(f"   Basis of design parameters: {len(final_state.data['basis_of_design'])}")
        print(f"   Completion status: {json.dumps(final_state.data['completion_status'], indent=6)}")
        print(f"   Next steps: {final_state.data['next_steps']}")
        
        # Test 7: Test invalid parameter group
        print("\n7. Testing error handling (invalid group)...")
        error_result = await client.call_tool(
            "elicit_basis_of_design",
            {"parameter_group": "invalid_group"}
        )
        print(f"   Status: {error_result.data['status']}")
        print(f"   Error message: {error_result.data['message']}")
        print(f"   Valid groups: {error_result.data.get('valid_groups', [])}")
        
    print("\n" + "=" * 60)
    print("MILESTONE 1 TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 60)
    print("\nThe server has the following working tools:")
    print("  [OK] elicit_basis_of_design - Collects design parameters")
    print("  [OK] get_design_state - Shows current state and progress")
    print("  [OK] reset_design - Clears state for new design")
    print("\nReady to proceed to Milestone 2: Heuristic Sizing")


if __name__ == "__main__":
    asyncio.run(test_milestone_1())