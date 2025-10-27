"""
Test chemical dosing estimation functions.
"""

from utils.chemical_dosing import (
    estimate_fecl3_for_sulfide_removal,
    estimate_fecl3_for_phosphate_removal,
    estimate_naoh_for_ph_adjustment,
    estimate_na2co3_for_alkalinity
)

print("="*60)
print("CHEMICAL DOSING ESTIMATION TESTS")
print("="*60)

# Test 1: FeCl3 for sulfide removal
print("\n=== Test 1: FeCl3 for Sulfide Removal ===")
result = estimate_fecl3_for_sulfide_removal(
    sulfide_mg_L=100,
    target_removal=0.90,
    safety_factor=1.2
)
print(f"Sulfide: 100 mg-S/L, Target: 90% removal")
print(f"  FeCl3 dose: {result['fecl3_dose_mg_L']:.1f} mg/L")
print(f"  Fe3+ added: {result['fe3_added_mg_L']:.1f} mg/L")
print(f"  Cl- added: {result['cl_added_mg_L']:.1f} mg/L")
print(f"  Molar ratio Fe:S = {result['molar_ratio_fe_to_s']:.2f}")
print(f"  Stoichiometry: {result['stoichiometry']}")
assert result['fecl3_dose_mg_L'] > 0, "FeCl3 dose should be positive"
assert result['sulfide_removed_mg_L'] == 90.0, "Should remove 90 mg-S/L"
print("[OK] FeCl3 for sulfide calculation correct")

# Test 2: FeCl3 for phosphate removal
print("\n=== Test 2: FeCl3 for Phosphate Removal ===")
result = estimate_fecl3_for_phosphate_removal(
    phosphate_mg_P_L=50,
    target_removal=0.80,
    safety_factor=1.5
)
print(f"Phosphate: 50 mg-P/L, Target: 80% removal")
print(f"  FeCl3 dose: {result['fecl3_dose_mg_L']:.1f} mg/L")
print(f"  Fe3+ added: {result['fe3_added_mg_L']:.1f} mg/L")
print(f"  Molar ratio Fe:P = {result['molar_ratio_fe_to_p']:.2f}")
print(f"  Stoichiometry: {result['stoichiometry']}")
assert result['fecl3_dose_mg_L'] > 0, "FeCl3 dose should be positive"
assert result['phosphate_removed_mg_P_L'] == 40.0, "Should remove 40 mg-P/L"
print("[OK] FeCl3 for phosphate calculation correct")

# Test 3: NaOH for pH adjustment
print("\n=== Test 3: NaOH for pH Adjustment ===")
result = estimate_naoh_for_ph_adjustment(
    alkalinity_meq_L=50,
    pH_current=6.5,
    pH_target=7.5,
    temperature_c=35.0
)
print(f"Alkalinity: 50 meq/L, pH: 6.5 -> 7.5")
print(f"  NaOH dose: {result['naoh_dose_mg_L']:.1f} mg/L")
print(f"  Na+ added: {result['na_added_mg_L']:.1f} mg/L")
print(f"  Alkalinity increase: {result['alkalinity_increase_meq_L']:.1f} meq/L")
print(f"  pH change: {result['ph_change']:.1f}")
print(f"  Stoichiometry: {result['stoichiometry']}")
assert result['naoh_dose_mg_L'] > 0, "NaOH dose should be positive"
assert result['ph_change'] == 1.0, "Should increase pH by 1.0 unit"
print("[OK] NaOH for pH adjustment calculation correct")

# Test 4: No base needed (pH already high)
print("\n=== Test 4: NaOH Not Needed (pH Already High) ===")
result = estimate_naoh_for_ph_adjustment(
    alkalinity_meq_L=50,
    pH_current=7.5,
    pH_target=7.0
)
print(f"pH: 7.5 -> 7.0 (decrease)")
print(f"  NaOH dose: {result['naoh_dose_mg_L']:.1f} mg/L")
assert result['naoh_dose_mg_L'] == 0, "No base needed for pH decrease"
print("[OK] Correctly returns zero dose when pH decrease requested")

# Test 5: Na2CO3 for alkalinity
print("\n=== Test 5: Na2CO3 for Alkalinity Increase ===")
result = estimate_na2co3_for_alkalinity(
    alkalinity_current_meq_L=30,
    alkalinity_target_meq_L=60
)
print(f"Alkalinity: 30 -> 60 meq/L")
print(f"  Na2CO3 dose: {result['na2co3_dose_mg_L']:.1f} mg/L")
print(f"  Na+ added: {result['na_added_mg_L']:.1f} mg/L")
print(f"  Alkalinity increase: {result['alkalinity_increase_meq_L']:.1f} meq/L")
print(f"  Stoichiometry: {result['stoichiometry']}")
assert result['na2co3_dose_mg_L'] > 0, "Na2CO3 dose should be positive"
assert result['alkalinity_increase_meq_L'] == 30.0, "Should increase by 30 meq/L"
print("[OK] Na2CO3 for alkalinity calculation correct")

# Test 6: Realistic scenario - high-strength wastewater
print("\n=== Test 6: Realistic High-Strength Wastewater ===")
print("Feedstock: Thickened WAS, 100 mg-S/L H2S, pH 6.8")
sulfide_result = estimate_fecl3_for_sulfide_removal(
    sulfide_mg_L=100,
    target_removal=0.95
)
ph_result = estimate_naoh_for_ph_adjustment(
    alkalinity_meq_L=40,
    pH_current=6.8,
    pH_target=7.2
)
print(f"\nRecommendations:")
print(f"  1. Dose {sulfide_result['fecl3_dose_mg_L']:.0f} mg/L FeCl3 for H2S control")
print(f"  2. Dose {ph_result['naoh_dose_mg_L']:.0f} mg/L NaOH for pH correction")
print(f"\nTotal chemical additions:")
print(f"  Fe3+: {sulfide_result['fe3_added_mg_L']:.1f} mg/L")
print(f"  Cl-:  {sulfide_result['cl_added_mg_L']:.1f} mg/L")
print(f"  Na+:  {ph_result['na_added_mg_L']:.1f} mg/L")
print("[OK] Realistic scenario calculated successfully")

print("\n" + "="*60)
print("ALL TESTS PASSED!")
print("="*60)
print("\n[OK] Chemical dosing estimation functions are working correctly")
print("[OK] Ready for integration into MCP tools")
