"""
Test the chemical dosing MCP tool.
"""

import asyncio
import json
from tools.chemical_dosing import estimate_chemical_dosing_tool

print("="*60)
print("MCP CHEMICAL DOSING TOOL TEST")
print("="*60)

async def test_with_custom_params():
    """Test with custom parameters (no design state needed)."""
    print("\n=== Test 1: Custom Parameters (High-Strength Wastewater) ===")

    result = await estimate_chemical_dosing_tool(
        use_current_state=False,
        custom_params={
            'sulfide_mg_L': 100,
            'phosphate_mg_P_L': 50,
            'alkalinity_meq_L': 40,
            'pH_current': 6.8
        },
        objectives={
            'sulfide_removal': 0.95,
            'phosphate_removal': 0.80,
            'pH_target': 7.2
        }
    )

    print(f"\nSuccess: {result['success']}")
    print(f"Message: {result['message']}")

    if result['success']:
        print("\nFeedstock Parameters:")
        for key, value in result['feedstock_parameters'].items():
            print(f"  {key}: {value}")

        print("\nTreatment Objectives:")
        for key, value in result['treatment_objectives'].items():
            print(f"  {key}: {value}")

        print("\nSummary (Combined Dosing):")
        summary = result['summary']
        print(f"  Total FeCl3: {summary['total_fecl3_mg_L']:.1f} mg/L")
        print(f"  NaOH: {summary['naoh_mg_L']:.1f} mg/L")
        print(f"  Na2CO3: {summary['na2co3_mg_L']:.1f} mg/L")
        print(f"  Fe3+ added: {summary['fe3_added_mg_L']:.1f} mg/L")
        print(f"  Cl- added: {summary['cl_added_mg_L']:.1f} mg/L")
        print(f"  Na+ added: {summary['na_added_mg_L']:.1f} mg/L")

        print("\nRationale:")
        for item in result['rationale']:
            print(f"  - {item}")

        print(f"\n{result['validation_note']}")

        # Check detailed calculations
        if result['detailed_calculations']['fecl3_for_sulfide']:
            fecl3_s = result['detailed_calculations']['fecl3_for_sulfide']
            assert fecl3_s['fecl3_dose_mg_L'] > 0, "FeCl3 for sulfide should be calculated"
            print(f"\n  Detailed: FeCl3 for sulfide = {fecl3_s['fecl3_dose_mg_L']:.1f} mg/L")

        if result['detailed_calculations']['naoh_for_ph']:
            naoh = result['detailed_calculations']['naoh_for_ph']
            assert naoh['naoh_dose_mg_L'] > 0, "NaOH should be calculated"
            print(f"  Detailed: NaOH = {naoh['naoh_dose_mg_L']:.1f} mg/L")

        print("\n[OK] MCP tool returns complete, structured response")
        return True
    else:
        print(f"\n[ERROR] Tool failed: {result.get('message')}")
        return False


async def test_with_missing_state():
    """Test error handling when design state is missing."""
    print("\n=== Test 2: Missing Design State (Should Fail Gracefully) ===")

    result = await estimate_chemical_dosing_tool(
        use_current_state=True  # Try to use design state (which doesn't exist)
    )

    print(f"\nSuccess: {result['success']}")
    print(f"Message: {result['message']}")

    assert not result['success'], "Should fail when design state is missing"
    assert "No basis of design" in result['message'], "Should explain the error"
    print("[OK] Proper error handling for missing design state")
    return True


async def test_no_dosing_needed():
    """Test when no dosing is required."""
    print("\n=== Test 3: No Dosing Needed (Already Optimal) ===")

    result = await estimate_chemical_dosing_tool(
        use_current_state=False,
        custom_params={
            'sulfide_mg_L': 10,  # Low sulfide
            'phosphate_mg_P_L': 5,  # Low phosphate
            'alkalinity_meq_L': 60,
            'pH_current': 7.5  # Already at target
        },
        objectives={
            'sulfide_removal': 0.90,
            'phosphate_removal': 0.80,
            'pH_target': 7.5  # Same as current
        }
    )

    print(f"\nSuccess: {result['success']}")

    if result['success']:
        summary = result['summary']
        print(f"Total FeCl3: {summary['total_fecl3_mg_L']:.1f} mg/L")
        print(f"NaOH: {summary['naoh_mg_L']:.1f} mg/L")

        print("\nRationale:")
        for item in result['rationale']:
            print(f"  - {item}")

        # Should still calculate FeCl3 for low sulfide, but NaOH should be 0
        assert summary['naoh_mg_L'] == 0, "No NaOH needed when pH already at target"
        print("[OK] Correctly skips NaOH when pH already at target")
        return True
    else:
        print(f"\n[ERROR] Tool failed: {result.get('message')}")
        return False


async def test_json_serializable():
    """Test that response is JSON serializable."""
    print("\n=== Test 4: JSON Serialization (MCP Compatibility) ===")

    result = await estimate_chemical_dosing_tool(
        use_current_state=False,
        custom_params={'sulfide_mg_L': 50, 'phosphate_mg_P_L': 25,
                      'alkalinity_meq_L': 45, 'pH_current': 7.0},
        objectives={'sulfide_removal': 0.90, 'pH_target': 7.5}
    )

    try:
        json_str = json.dumps(result, indent=2)
        print(f"\nJSON length: {len(json_str)} characters")
        print("[OK] Response is JSON serializable")

        # Verify structure
        parsed = json.loads(json_str)
        assert 'success' in parsed, "Must have success field"
        assert 'summary' in parsed, "Must have summary field"
        assert 'rationale' in parsed, "Must have rationale field"
        print("[OK] JSON structure is valid for MCP")
        return True
    except Exception as e:
        print(f"\n[ERROR] JSON serialization failed: {e}")
        return False


async def main():
    """Run all tests."""
    results = []

    results.append(await test_with_custom_params())
    results.append(await test_with_missing_state())
    results.append(await test_no_dosing_needed())
    results.append(await test_json_serializable())

    print("\n" + "="*60)
    print(f"TEST RESULTS: {sum(results)}/{len(results)} passed")
    print("="*60)

    if all(results):
        print("\n[OK] All MCP tool tests passed!")
        print("[OK] Chemical dosing tool ready for MCP server integration")
        return 0
    else:
        print("\n[ERROR] Some tests failed")
        return 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    exit(exit_code)
