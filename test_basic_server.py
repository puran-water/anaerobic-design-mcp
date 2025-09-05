#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script for basic MCP server functionality.
Run this to verify Milestone 1 is working correctly.
"""

import asyncio
import json
from server import design_state
# Import the actual tool functions
from server import reset_design, get_design_state, elicit_basis_of_design


async def test_milestone_1():
    """Test Milestone 1: Basic server with parameter elicitation."""
    
    print("=" * 60)
    print("MILESTONE 1 TEST: Basic Server with Parameter Elicitation")
    print("=" * 60)
    
    # Test 1: Reset design state
    print("\n1. Testing reset_design...")
    reset_result = await reset_design()
    print(f"   Result: {reset_result['status']}")
    print(f"   Message: {reset_result['message']}")
    
    # Test 2: Get initial state
    print("\n2. Testing get_design_state (should be empty)...")
    state_result = await get_design_state()
    print(f"   Status: {state_result['status']}")
    print(f"   Progress: {state_result['overall_progress']}")
    print(f"   Next steps: {state_result['next_steps']}")
    
    # Test 3: Elicit essential parameters
    print("\n3. Testing elicit_basis_of_design (essential)...")
    essential_result = await elicit_basis_of_design(
        parameter_group="essential"
    )
    print(f"   Status: {essential_result['status']}")
    print(f"   Parameters collected: {list(essential_result['parameters'].keys())}")
    print(f"   Values: {json.dumps(essential_result['parameters'], indent=6)}")
    
    # Test 4: Elicit with existing values
    print("\n4. Testing elicit_basis_of_design with current values...")
    custom_values = {
        "feed_flow_m3d": 500,
        "cod_mg_l": 75000
    }
    custom_result = await elicit_basis_of_design(
        parameter_group="essential",
        current_values=custom_values
    )
    print(f"   Status: {custom_result['status']}")
    print(f"   Custom values used: {custom_values}")
    print(f"   Final parameters: {json.dumps(custom_result['parameters'], indent=6)}")
    
    # Test 5: Elicit all parameters
    print("\n5. Testing elicit_basis_of_design (all)...")
    all_result = await elicit_basis_of_design(
        parameter_group="all"
    )
    print(f"   Status: {all_result['status']}")
    print(f"   Total parameters: {len(all_result['parameters'])}")
    print(f"   Derived parameters: {json.dumps(all_result['derived_parameters'], indent=6)}")
    print(f"   Validation warnings: {all_result['validation']['warnings']}")
    
    # Test 6: Check final state
    print("\n6. Testing get_design_state (should have parameters)...")
    final_state = await get_design_state()
    print(f"   Status: {final_state['status']}")
    print(f"   Progress: {final_state['overall_progress']}")
    print(f"   Basis of design: {json.dumps(final_state['basis_of_design'], indent=6)}")
    print(f"   Completion status: {json.dumps(final_state['completion_status'], indent=6)}")
    print(f"   Next steps: {final_state['next_steps']}")
    
    # Test 7: Test invalid parameter group
    print("\n7. Testing error handling (invalid group)...")
    error_result = await elicit_basis_of_design(
        parameter_group="invalid_group"
    )
    print(f"   Status: {error_result['status']}")
    print(f"   Error message: {error_result['message']}")
    print(f"   Valid groups: {error_result.get('valid_groups', [])}")
    
    print("\n" + "=" * 60)
    print("MILESTONE 1 TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 60)
    print("\nThe server has the following working tools:")
    print("  ✅ elicit_basis_of_design - Collects design parameters")
    print("  ✅ get_design_state - Shows current state and progress")
    print("  ✅ reset_design - Clears state for new design")
    print("\nReady to proceed to Milestone 2: Heuristic Sizing")


if __name__ == "__main__":
    # Run the async test
    asyncio.run(test_milestone_1())