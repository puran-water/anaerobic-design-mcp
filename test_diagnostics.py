"""Test script to check if diagnostic data is available after simulation"""
import json

# Check simulation results
with open('simulation_results_fixed.json', 'r') as f:
    results = json.load(f)

print("="*80)
print("CURRENT DIAGNOSTIC DATA IN RESULTS")
print("="*80)
print()

print("Top-level keys:", list(results.keys()))
print()

print("Performance data:")
for key, value in results['performance'].items():
    print(f"  {key}: {value}")
print()

print("="*80)
print("MISSING DIAGNOSTIC DATA")
print("="*80)
print()
print("The following diagnostic data is being calculated but NOT reported:")
print("  - Inhibition factors (pH, H2, NH3, H2S) for all process groups")
print("  - Monod factors (substrate limitation) for all processes")
print("  - Biomass concentrations for all functional groups")
print("  - Process rates (rhos) for all 63 processes")
print("  - Precipitation rates for all mineral species")
print("  - Net sludge yields (VSS/TSS production)")
print()
print("These are populated in qsdsan_madm1.py:878-941 via root.data")
print("but not extracted and returned in simulation results")
