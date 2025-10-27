from qsdsan.processes import mass2mol_conversion
import numpy as np

class MockCmps:
    def __init__(self):
        self.i_mass = np.array([23.0, 35.5, 40.0, 24.0])  # g/mol for Na, Cl, Ca, Mg
        self.chem_MW = self.i_mass

cmps = MockCmps()
result = mass2mol_conversion(cmps)

print("Molecular weights [g/mol]:", cmps.i_mass)
print("unit_conversion array:", result)
print("\nFor 0.1 kg/m³ Na (= 100 mg/L):")
print(f"  Concentration in mol/L = 0.1 × {result[0]:.6f} = {0.1 * result[0]:.6f} mol/L")
print(f"  Expected: 100 mg/L ÷ 23000 mg/mol = {100/23000:.6f} mol/L")
print(f"  Or: 0.1 g/L ÷ 23 g/mol = {0.1/23:.6f} mol/L")
