"""
Basic integration test for QSDsan ADM1+sulfur simulation.

Tests the complete refactored simulation workflow:
1. Create influent with 30 components
2. Run simulation to steady state
3. Analyze results
4. Verify sulfur metrics

This is a smoke test to ensure the refactoring is functional.
"""

import sys
import os
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.qsdsan_simulation_sulfur import (
    run_simulation_sulfur,
    initialize_30_component_state
)
from utils.stream_analysis_sulfur import (
    analyze_liquid_stream,
    analyze_gas_stream,
    calculate_sulfur_metrics
)

logging.basicConfig(level=logging.INFO)

print("="*80)
print("QSDsan ADM1+Sulfur Simulation - Basic Integration Test")
print("="*80)
print()

# 1. Set up test parameters
print("1. Setting up test parameters...")
basis = {
    'Q': 100,  # m3/d
    'Temp': 308.15  # 35°C
}

# Simple ADM1 state (primary sludge-like)
adm1_state = {
    'S_su': 0.012,
    'S_aa': 0.005,
    'S_fa': 0.099,
    'S_va': 0.012,
    'S_bu': 0.013,
    'S_pro': 0.016,
    'S_ac': 0.2,
    'S_h2': 2.5e-7,
    'S_ch4': 0.055,
    'S_IC': 0.04,
    'S_IN': 0.01,
    'S_I': 0.02,
    'X_c': 2.0,
    'X_ch': 5.0,
    'X_pr': 20.0,
    'X_li': 5.0,
    'X_su': 0.42,
    'X_aa': 1.18,
    'X_fa': 0.24,
    'X_c4': 0.43,
    'X_pro': 0.14,
    'X_ac': 0.76,
    'X_h2': 0.32,
    'X_I': 25.6,
    'S_cat': 0.04,
    'S_an': 0.02,
    # Sulfur components
    'S_SO4': 0.1,  # 100 mg S/L
    'S_IS': 0.001,  # 1 mg S/L initial
    'X_SRB': 0.01  # 10 mg COD/L SRB biomass
}

HRT = 20  # days

print(f"   Flow rate: {basis['Q']} m3/d")
print(f"   Temperature: {basis['Temp']} K")
print(f"   HRT: {HRT} days")
print(f"   Initial sulfate: {adm1_state['S_SO4']*1000} mg S/L")
print()

# 2. Initialize state with defaults
print("2. Initializing 30-component state...")
init_state = initialize_30_component_state(adm1_state)
print(f"   S_SO4: {init_state['S_SO4']:.4f} kg S/m3")
print(f"   S_IS: {init_state['S_IS']:.6f} kg S/m3")
print(f"   X_SRB: {init_state['X_SRB']:.4f} kg COD/m3")
print()

# 3. Run simulation
print("3. Running simulation to steady state...")
print("   (This may take 30-60 seconds)")
try:
    sys, inf, eff, gas, converged_at, status = run_simulation_sulfur(
        basis, init_state, HRT, simulation_time=150
    )
    print(f"   [OK] Simulation {status} at t={converged_at} days")
except Exception as e:
    print(f"   [FAILED] Simulation error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# 4. Analyze results
print("4. Analyzing results...")

influent = analyze_liquid_stream(inf, include_components=False)
effluent = analyze_liquid_stream(eff, include_components=False)
biogas = analyze_gas_stream(gas)
sulfur = calculate_sulfur_metrics(inf, eff, gas)

print(f"   Influent COD: {influent['COD']:.1f} mg/L")
print(f"   Effluent COD: {effluent['COD']:.1f} mg/L")
print(f"   COD removal: {(1 - effluent['COD']/influent['COD'])*100:.1f}%")
print()
print(f"   Biogas production: {biogas['flow_total']:.2f} m3/d")
print(f"   Methane content: {biogas['methane_percent']:.1f}%")
print(f"   H2S content: {biogas['h2s_ppm']:.1f} ppm")
print()
print(f"   Effluent pH: {effluent['pH']:.2f}")
print(f"   Effluent alkalinity: {effluent['alkalinity']:.2f} meq/L")
print()

# 5. Sulfur balance
print("5. Sulfur mass balance:")
print(f"   Sulfate in: {sulfur['sulfate_in_kg_S_d']:.3f} kg S/d")
print(f"   Sulfate out: {sulfur['sulfate_out_kg_S_d']:.3f} kg S/d")
print(f"   Sulfate reduced: {sulfur['sulfate_in_kg_S_d'] - sulfur['sulfate_out_kg_S_d']:.3f} kg S/d")
print(f"   Sulfide in effluent: {sulfur['sulfide_out_kg_S_d']:.3f} kg S/d")
print(f"   H2S in biogas: {sulfur['h2s_biogas_kg_S_d']:.3f} kg S/d")
print()

# 6. H2S speciation
print("6. H2S speciation:")
print(f"   Total sulfide: {sulfur['H2S_dissolved_kg_m3'] + sulfur['HS_dissolved_mg_L']/1000:.4f} kg S/m3")
print(f"   H2S (molecular): {sulfur['H2S_dissolved_kg_m3']:.6f} kg S/m3")
print(f"   HS- (ionic): {sulfur['HS_dissolved_mg_L']/1000:.4f} kg S/m3")
print(f"   Fraction H2S: {sulfur['fraction_H2S']:.3f}")
print()

# 7. Validation checks
print("7. Validation checks:")
checks_passed = 0
checks_total = 0

# Check COD removal
checks_total += 1
cod_removal = (1 - effluent['COD']/influent['COD'])*100
if 40 <= cod_removal <= 95:
    print(f"   [OK] COD removal {cod_removal:.1f}% is reasonable")
    checks_passed += 1
else:
    print(f"   [WARNING] COD removal {cod_removal:.1f}% is outside normal range (40-95%)")

# Check biogas production
checks_total += 1
if biogas['flow_total'] > 0:
    print(f"   [OK] Biogas production {biogas['flow_total']:.2f} m3/d > 0")
    checks_passed += 1
else:
    print(f"   [FAIL] No biogas production")

# Check methane content
checks_total += 1
if 50 <= biogas['methane_percent'] <= 80:
    print(f"   [OK] Methane content {biogas['methane_percent']:.1f}% is reasonable")
    checks_passed += 1
else:
    print(f"   [WARNING] Methane content {biogas['methane_percent']:.1f}% is outside normal range (50-80%)")

# Check pH
checks_total += 1
if 6.5 <= effluent['pH'] <= 8.0:
    print(f"   [OK] pH {effluent['pH']:.2f} is in acceptable range")
    checks_passed += 1
else:
    print(f"   [WARNING] pH {effluent['pH']:.2f} is outside normal range (6.5-8.0)")

# Check H2S inhibition
checks_total += 1
I_h2s = sulfur['inhibition_acetoclastic_factor']
if I_h2s > 0.5:
    print(f"   [OK] H2S inhibition factor {I_h2s:.3f} > 0.5 (acceptable)")
    checks_passed += 1
else:
    print(f"   [WARNING] H2S inhibition factor {I_h2s:.3f} < 0.5 (severe inhibition)")

print()
print(f"Validation: {checks_passed}/{checks_total} checks passed")
print()

if checks_passed == checks_total:
    print("[SUCCESS] All validation checks passed!")
    sys.exit(0)
elif checks_passed >= checks_total * 0.6:
    print("[PARTIAL SUCCESS] Most validation checks passed")
    sys.exit(0)
else:
    print("[FAILURE] Too many validation checks failed")
    sys.exit(1)
