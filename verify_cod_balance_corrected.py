#!/usr/bin/env python3
"""
Corrected COD Mass Balance Verification Script

Fixes from user feedback:
1. SO₄ reduction: Use 2 kg COD/kg S (not 4)
2. SO₄ reduced: Use (SO₄_in - SO₄_out) only (don't subtract H₂S gas)
3. Add H₂ as COD sink: H₂_mass × 8 kg O₂/kg H₂
"""

import json
import sys

# Constants
STD_MOLAR_VOLUME_M3_KMOL = 22.414  # m³/kmol at STP (0°C, 1 atm)
CH4_MW = 16.04  # kg/kmol
H2_MW = 2.016  # kg/kmol
S_MW = 32.065  # kg/kmol

# Stoichiometry constants (CORRECTED)
COD_PER_KG_S_REDUCTION = 2.0  # kg O₂ per kg S (SO₄²⁻ → HS⁻ needs 8 e⁻, i.e., 2 mol O₂ per mol S)
COD_PER_KG_H2 = 8.0  # kg O₂ per kg H₂ (H₂ → H₂O needs 1/2 O₂)


def main(results_file):
    """Calculate corrected COD mass balance from simulation results."""

    # Load simulation results
    with open(results_file, 'r') as f:
        results = json.load(f)

    # Extract data
    biogas = results['biogas']
    performance = results['performance_metrics']
    sulfur = results.get('sulfur_analysis', {})
    streams = results.get('streams', {})

    # ============================================================================
    # INPUT COD
    # ============================================================================
    COD_removed_kg_d = performance['COD_removed_kg_d']

    print("="*80)
    print("CORRECTED COD MASS BALANCE VERIFICATION")
    print("="*80)
    print(f"\nCOD Input (removed): {COD_removed_kg_d:.2f} kg/d\n")

    # ============================================================================
    # SINK 1: METHANE
    # ============================================================================
    # CH₄ oxidation: CH₄ + 2O₂ → CO₂ + 2H₂O
    # 1 mol CH₄ needs 2 mol O₂ → 1 kg CH₄ needs 4 kg O₂
    ch4_kg_d = biogas['methane_mass_kg_d']
    COD_methane = ch4_kg_d * 4.0  # kg O₂/kg CH₄

    print(f"SINK 1: Methane Production")
    print(f"  CH₄ mass: {ch4_kg_d:.2f} kg/d")
    print(f"  COD as methane: {COD_methane:.2f} kg/d ({COD_methane/COD_removed_kg_d*100:.1f}%)")

    # ============================================================================
    # SINK 2: BIOMASS PRODUCTION
    # ============================================================================
    # From M@r calculation (now corrected, should be 250-400 kg COD/d)
    biomass_yields = performance.get('yields', {})
    detailed_yields = biomass_yields.get('per_functional_group', {})

    COD_biomass = 0.0
    for group_id, group_data in detailed_yields.items():
        net_prod_vss = group_data.get('net_production_kg_VSS_d', 0.0)
        # Approximate conversion: VSS ≈ 0.55 kg COD/kg VSS (typical for biomass)
        # Better: use actual i_mass from components, but this is diagnostic script
        COD_biomass += net_prod_vss / 0.55  # Rough estimate

    # Alternative: use total biomass from performance if available
    if 'total_biomass_production_kg_COD_d' in performance:
        COD_biomass = performance['total_biomass_production_kg_COD_d']

    print(f"\nSINK 2: Biomass Production")
    print(f"  COD as biomass: {COD_biomass:.2f} kg/d ({COD_biomass/COD_removed_kg_d*100:.1f}%)")

    # ============================================================================
    # SINK 3: SULFATE REDUCTION (CORRECTED)
    # ============================================================================
    # CORRECTED: Use 2 kg COD/kg S (not 4)
    # SO₄²⁻ + 2H⁺ + 8e⁻ → HS⁻ + 4OH⁻
    # 8 electrons = 2 mol O₂ = 64 g O₂ per 32 g S = 2 kg O₂/kg S

    # CORRECTED: Use (SO₄_in - SO₄_out) total, don't subtract H₂S gas
    inf_stream = streams.get('influent', {})
    eff_stream = streams.get('effluent', {})

    SO4_in_mg_L = inf_stream.get('S_SO4_mg_L', 0.0)
    SO4_out_mg_L = eff_stream.get('S_SO4_mg_L', 0.0)
    Q_m3_d = inf_stream.get('flow_m3_d', 1000.0)

    SO4_in_kg_S_d = SO4_in_mg_L * Q_m3_d / 1000.0  # mg/L × m³/d → kg S/d
    SO4_out_kg_S_d = SO4_out_mg_L * Q_m3_d / 1000.0
    SO4_reduced_kg_S_d = SO4_in_kg_S_d - SO4_out_kg_S_d

    COD_sulfate = SO4_reduced_kg_S_d * COD_PER_KG_S_REDUCTION  # kg S × 2 kg O₂/kg S

    print(f"\nSINK 3: Sulfate Reduction (CORRECTED)")
    print(f"  SO₄ reduced: {SO4_reduced_kg_S_d:.2f} kg S/d")
    print(f"  COD consumed: {COD_sulfate:.2f} kg/d ({COD_sulfate/COD_removed_kg_d*100:.1f}%)")
    print(f"  (Using 2 kg COD/kg S, NOT 4)")

    # ============================================================================
    # SINK 4: HYDROGEN (NEW)
    # ============================================================================
    # H₂ oxidation: H₂ + 1/2 O₂ → H₂O
    # 1 mol H₂ needs 0.5 mol O₂ → 1 kg H₂ needs 8 kg O₂

    biogas_total_m3_d = biogas.get('total_flow_Nm3_d', 0.0)
    h2_percent = biogas.get('h2_percent', 0.0)

    # H₂ mass at STP: Nm³/d → kmol/d → kg/d
    h2_kmol_d = (biogas_total_m3_d * h2_percent / 100.0) / STD_MOLAR_VOLUME_M3_KMOL
    h2_kg_d = h2_kmol_d * H2_MW

    COD_h2 = h2_kg_d * COD_PER_KG_H2  # kg H₂ × 8 kg O₂/kg H₂

    print(f"\nSINK 4: Hydrogen (NEW)")
    print(f"  H₂ in biogas: {h2_percent:.4f}%")
    print(f"  H₂ mass: {h2_kg_d:.6f} kg/d")
    print(f"  COD as H₂: {COD_h2:.4f} kg/d ({COD_h2/COD_removed_kg_d*100:.3f}%)")

    # ============================================================================
    # TOTAL BALANCE
    # ============================================================================
    COD_accounted = COD_methane + COD_biomass + COD_sulfate + COD_h2
    COD_gap = COD_removed_kg_d - COD_accounted
    closure_percent = (COD_accounted / COD_removed_kg_d) * 100.0

    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"COD Input (removed):      {COD_removed_kg_d:10.2f} kg/d (100.0%)")
    print(f"  Methane:                {COD_methane:10.2f} kg/d ({COD_methane/COD_removed_kg_d*100:5.1f}%)")
    print(f"  Biomass:                {COD_biomass:10.2f} kg/d ({COD_biomass/COD_removed_kg_d*100:5.1f}%)")
    print(f"  Sulfate reduction:      {COD_sulfate:10.2f} kg/d ({COD_sulfate/COD_removed_kg_d*100:5.1f}%)")
    print(f"  Hydrogen:               {COD_h2:10.2f} kg/d ({COD_h2/COD_removed_kg_d*100:5.1f}%)")
    print(f"  {'─'*60}")
    print(f"Total Accounted:          {COD_accounted:10.2f} kg/d ({closure_percent:5.1f}%)")
    print(f"Gap (unexplained):        {COD_gap:10.2f} kg/d ({COD_gap/COD_removed_kg_d*100:5.1f}%)")
    print("="*80)

    # Verdict
    if abs(closure_percent - 100.0) <= 5.0:
        print("\n✓ PASS: COD mass balance closes within ±5%")
        return 0
    else:
        print(f"\n✗ FAIL: COD closure {closure_percent:.1f}% (target: 95-105%)")
        print(f"   Gap of {COD_gap:.2f} kg/d ({abs(COD_gap/COD_removed_kg_d*100):.1f}%) is too large")
        return 1


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python verify_cod_balance_corrected.py <simulation_results.json>")
        sys.exit(1)

    sys.exit(main(sys.argv[1]))
