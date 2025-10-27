"""
Test to understand QSDsan's unit conventions.
"""

# Test 1: Unit equivalence
print("="*60)
print("Test 1: Unit Equivalence")
print("="*60)
print("1 mol/L = ? kmol/m³")
print("  1 mol / 1 L")
print("  = 1 mol / 0.001 m³")
print("  = 1000 mol/m³")
print("  = 1 kmol/m³")
print("\n[OK] So mol/L = kmol/m3 (they're the same!)")

# Test 2: Mass units
print("\n" + "="*60)
print("Test 2: Mass Unit Conversion")
print("="*60)
print("For Na (MW = 23 g/mol):")
print("  0.1 kg/m³ = ?")
print("  = 0.1 kg/m3 x (1 m3/1000 L) = 0.0001 kg/L")
print("  = 0.1 g/L")
print("  = (0.1 g/L) / (23 g/mol) = 0.00435 mol/L")
print("\n  Conversion factor: 0.00435 / 0.1 = 1/23 = 0.0435")

# Test 3: QSDsan's mass2mol_conversion
print("\n" + "="*60)
print("Test 3: QSDsan's mass2mol_conversion")
print("="*60)

from qsdsan.processes import mass2mol_conversion
import numpy as np

# Create a minimal mock
class SimpleCmps:
    def __init__(self):
        # Na+: measured as Na, MW = 23
        self.i_mass = np.array([23.0])  # g/mol
        self.chem_MW = np.array([23.0])  # g/mol

cmps = SimpleCmps()
uc = mass2mol_conversion(cmps)
print(f"  i_mass: {cmps.i_mass[0]} g/mol")
print(f"  chem_MW: {cmps.chem_MW[0]} g/mol")
print(f"  mass2mol_conversion: {uc[0]}")
print(f"  Returns: i_mass / chem_MW = {cmps.i_mass[0]/cmps.chem_MW[0]}")

# Test 4: What are the actual state units?
print("\n" + "="*60)
print("Test 4: Deducing Actual State Units")
print("="*60)
print("If mass2mol_conversion returns 1.0 for Na,")
print("and we multiply state by it to get mol/L,")
print("then:")
print("  state x 1.0 = mol/L")
print("  state = mol/L")
print("\nBut comments say state is in kg/m³...")
print("HYPOTHESIS: Maybe state is actually in kmol/m³ already?")
print("  kmol/m3 x 1.0 = kmol/m3 = mol/L [OK]")
print("\nOr maybe i_mass and chem_MW are NOT both 23?")

# Test 5: Check with more complex component (S_IN - nitrogen)
print("\n" + "="*60)
print("Test 5: Complex Component (S_IN - Nitrogen)")
print("="*60)
print("S_IN = inorganic nitrogen (NH4+ + NH3)")
print("Measured as: N (atomic nitrogen, MW = 14 g/mol)")
print("Component: NH4+ (MW = 18 g/mol) + NH3 (MW = 17 g/mol)")
print("\nIn QSDsan:")
print("  i_mass = 14 g/mol (mass of N)")
print("  chem_MW = 14 g/mol (measured as N)")
print("  mass2mol_conversion = 14/14 = 1.0")
print("\nSo 0.1 kg/m³ of S_IN means:")
print("  0.1 kg/m³ of N")
print("  = 0.1 g/L of N")
print("  = 0.1/14 mol-N/L")
print("  But mass2mol gives: 0.1 x 1.0 = 0.1")
print("\n[ERROR] This doesn't match! Unless...")
print("  Unless state is in kmol-N/m3:")
print("  0.1 kmol-N/m3 x 1.0 = 0.1 kmol-N/m3 = 0.1 mol-N/L [OK]")

print("\n" + "="*60)
print("CONCLUSION")
print("="*60)
print("State units in QSDsan appear to be kmol[measured_as]/m³,")
print("NOT kg[measured_as]/m³ as I assumed!")
print("\nThis means for the test:")
print("  100 mg/L Na = 0.1 g/L Na")
print("  = 0.1/23 mol/L Na")
print("  = 0.00435 mol/L Na")
print("  = 0.00435 kmol/m³ Na")
print("\nSo state_arr should be:")
print("  np.array([0.00435, 0.00282, 0.00125, 0.00104])  # kmol/m³")
print("\nAnd unit_conversion should be:")
print("  np.array([1.0, 1.0, 1.0, 1.0])  # kmol/m3 -> kmol/m3")
