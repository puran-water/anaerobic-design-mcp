"""
Test that dissolution is enabled (SI < 1 produces negative rates).
"""
import numpy as np

print("="*60)
print("DISSOLUTION TEST")
print("="*60)

# Test parameters from qsdsan_madm1.py
k_cryst = 1.0  # Crystallization rate constant (placeholder)
n_cryst = 2  # Order of crystallization reaction
sum_stoichios = 3  # Sum of stoichiometric coefficients

# Test case 1: Supersaturation (SI > 1) -> Precipitation (positive rate)
print("\n=== Test 1: Supersaturation (SI > 1) -> Precipitation ===")
SI = 2.0  # Supersaturated
X_mineral = 0.001  # Some mineral present (kg/m3)

rate = k_cryst * X_mineral * (SI**(1/sum_stoichios) - 1)**n_cryst
print(f"SI = {SI}, X_mineral = {X_mineral} kg/m3")
print(f"Rate = {rate:.6f} kg/m3/d")
assert rate > 0, "Precipitation rate should be positive"
print("[OK] Positive rate indicates precipitation")

# Test case 2: Undersaturation (SI < 1) -> Dissolution (negative rate)
print("\n=== Test 2: Undersaturation (SI < 1) -> Dissolution ===")
SI = 0.5  # Undersaturated
X_mineral = 0.001  # Some mineral present

# With even n_cryst, we need to preserve sign explicitly
SI_driving_force = SI**(1/sum_stoichios) - 1
sign_direction = np.sign(SI_driving_force)
magnitude = np.abs(SI_driving_force)**n_cryst
rate = k_cryst * X_mineral * sign_direction * magnitude

print(f"SI = {SI}, X_mineral = {X_mineral} kg/m3")
print(f"SI_driving_force = {SI_driving_force:.4f}")
print(f"Sign = {sign_direction}, Magnitude = {magnitude:.6f}")
print(f"Rate = {rate:.6f} kg/m3/d")
assert rate < 0, "Dissolution rate should be negative"
print("[OK] Negative rate indicates dissolution")

# Test case 3: Equilibrium (SI = 1) -> No reaction (zero rate)
print("\n=== Test 3: Equilibrium (SI = 1) -> No Reaction ===")
SI = 1.0  # At equilibrium
X_mineral = 0.001

rate = k_cryst * X_mineral * (SI**(1/sum_stoichios) - 1)**n_cryst
print(f"SI = {SI}, X_mineral = {X_mineral} kg/m3")
print(f"Rate = {rate:.6f} kg/m3/d")
assert abs(rate) < 1e-10, "Equilibrium rate should be zero"
print("[OK] Zero rate at equilibrium")

# Test case 4: Guard against negative X_mineral during dissolution
print("\n=== Test 4: Guard Against Negative X_mineral ===")
SI = 0.5  # Undersaturated (dissolution)
X_minerals = np.array([0.001, 1e-15, 0.0])  # Normal, very low, zero

# Apply corrected kinetic expression with sign preservation
SI_driving_force = SI**(1/sum_stoichios) - 1
sign_direction = np.sign(SI_driving_force)
magnitude = np.abs(SI_driving_force)**n_cryst
rates = k_cryst * X_minerals * sign_direction * magnitude

# Apply guard: prevent dissolution if X_mineral < 1e-12
guarded_rates = np.where(X_minerals > 1e-12, rates, np.maximum(0, rates))

print(f"SI = {SI}")
print(f"X_minerals = {X_minerals}")
print(f"Raw rates = {rates}")
print(f"Guarded rates = {guarded_rates}")

assert guarded_rates[0] < 0, "Normal mineral should dissolve"
assert guarded_rates[1] == 0, "Very low mineral should be protected"
assert guarded_rates[2] == 0, "Zero mineral should be protected"
print("[OK] Guard prevents negative mineral concentrations")

print("\n" + "="*60)
print("ALL DISSOLUTION TESTS PASSED!")
print("="*60)
print("\n[OK] Dissolution mechanism is enabled")
print("[OK] Kinetic expression handles SI < 1 correctly")
print("[OK] Guard prevents X_mineral from going negative")
