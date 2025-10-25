#!/usr/bin/env python3
"""
COD Mass Balance Diagnostic Script

Investigates the 14% COD gap by:
1. Checking if QSDsan's stream.COD accounts for all 62 mADM1 components
2. Manually calculating COD from component concentrations
3. Verifying methane flow calculations
4. Recalculating complete COD balance

Critical Question: Does QSDsan's .COD property sum ALL 62 components or only base ADM1?
"""

import json
import sys

# Component COD coefficients (kg O₂/kg component)
# From qsdsan_madm1.py component definitions
COMPONENT_COD = {
    # Soluble organics - ADM1 base
    'S_su': 1.0,      # Sugars
    'S_aa': 1.0,      # Amino acids
    'S_fa': 1.0,      # Long-chain fatty acids
    'S_va': 1.0,      # Valerate
    'S_bu': 1.0,      # Butyrate
    'S_pro': 1.0,     # Propionate
    'S_ac': 1.0,      # Acetate
    'S_h2': 8.0,      # Hydrogen (H₂ + 0.5 O₂ → H₂O)
    'S_ch4': 4.0,     # Methane (CH₄ + 2 O₂ → CO₂ + 2H₂O)

    # Particulate organics - ADM1 base
    'X_ch': 1.0,      # Carbohydrates
    'X_pr': 1.0,      # Proteins
    'X_li': 1.0,      # Lipids
    'S_I': 1.0,       # Soluble inerts
    'X_I': 1.0,       # Particulate inerts

    # Biomass - ADM1 base (C₅H₇O₂NP₀.₁₁₃)
    'X_su': 1.42,     # Sugar degraders (i_mass = 1/1.393, i_COD ≈ 1.42)
    'X_aa': 1.42,     # Amino acid degraders
    'X_fa': 1.42,     # LCFA degraders
    'X_c4': 1.42,     # Valerate/butyrate degraders
    'X_pro': 1.42,    # Propionate degraders
    'X_ac': 1.42,     # Acetoclastic methanogens
    'X_h2': 1.42,     # Hydrogenotrophic methanogens

    # Extensions - mADM1 additions
    'X_PAO': 1.42,    # PAO biomass (same as ADM1 biomass)
    'X_PHA': 1.0,     # Storage polymer (polyhydroxyalkanoates) - ADDED in M@r fix
    'X_hSRB': 1.42,   # H₂-utilizing SRB
    'X_aSRB': 1.42,   # Acetate-utilizing SRB
    'X_pSRB': 1.42,   # Propionate-utilizing SRB
    'X_c4SRB': 1.42,  # Butyrate/valerate-utilizing SRB

    # Inorganic components - NO COD
    'S_IC': 0.0,      # Inorganic carbon (CO₂)
    'S_IN': 0.0,      # Inorganic nitrogen (NH₄⁺)
    'S_IP': 0.0,      # Inorganic phosphorus (PO₄³⁻)
    'S_K': 0.0,       # Potassium
    'S_Mg': 0.0,      # Magnesium
    'S_SO4': 0.0,     # Sulfate
    'S_IS': 0.0,      # Sulfide (H₂S/HS⁻) - measured_as='S' (FIXED)
    'S_S0': 0.0,      # Elemental sulfur - measured_as='S' (FIXED)
    'S_Fe2': 0.0,     # Ferrous iron - measured_as='Fe' (FIXED)
    'S_Fe3': 0.0,     # Ferric iron
    'S_Ca': 0.0,      # Calcium
    'S_Al': 0.0,      # Aluminum
    'S_Na': 0.0,      # Sodium
    'S_Cl': 0.0,      # Chloride
    'X_PP': 0.0,      # Polyphosphate

    # Precipitates - NO COD (all minerals)
    'X_HFO_H': 0.0,
    'X_HFO_L': 0.0,
    'X_HFO_old': 0.0,
    'X_HFO_HP': 0.0,
    'X_HFO_LP': 0.0,
    'X_HFO_HP_old': 0.0,
    'X_HFO_LP_old': 0.0,
    'X_CCM': 0.0,     # Calcite
    'X_ACC': 0.0,     # Aragonite
    'X_ACP': 0.0,     # Amorphous calcium phosphate
    'X_HAP': 0.0,     # Hydroxylapatite
    'X_DCPD': 0.0,
    'X_OCP': 0.0,
    'X_struv': 0.0,   # Struvite
    'X_newb': 0.0,
    'X_magn': 0.0,
    'X_kstruv': 0.0,
    'X_FeS': 0.0,     # Iron sulfide
    'X_Fe3PO42': 0.0,
    'X_AlPO4': 0.0,
    'H2O': 0.0,
}

# Standard constants
CH4_MW = 16.04  # kg/kmol
H2_MW = 2.016   # kg/kmol
S_MW = 32.065   # kg/kmol
STD_MOLAR_VOLUME = 22.414  # m³/kmol at STP

def calculate_cod_from_components(stream_components, flow_m3_d):
    """
    Manually calculate COD from individual component concentrations.

    Args:
        stream_components: Dict of component concentrations (mg/L or kg/m³)
        flow_m3_d: Flow rate (m³/d)

    Returns:
        Dict with total COD (mg/L), COD breakdown by component, and COD load (kg/d)
    """
    cod_mg_L = 0.0
    cod_breakdown = {}
    organic_components = []
    missing_components = []

    for comp_id, conc_mg_L in stream_components.items():
        if comp_id == 'H2O':
            continue

        if comp_id not in COMPONENT_COD:
            missing_components.append(comp_id)
            print(f"  WARNING: Component '{comp_id}' not in COD coefficient table")
            continue

        cod_coef = COMPONENT_COD[comp_id]
        comp_cod_mg_L = conc_mg_L * cod_coef

        if cod_coef > 0:
            organic_components.append(comp_id)
            cod_breakdown[comp_id] = {
                'concentration_mg_L': conc_mg_L,
                'cod_coefficient': cod_coef,
                'cod_contribution_mg_L': comp_cod_mg_L
            }

        cod_mg_L += comp_cod_mg_L

    cod_load_kg_d = cod_mg_L * flow_m3_d / 1000.0

    return {
        'total_cod_mg_L': cod_mg_L,
        'total_cod_kg_d': cod_load_kg_d,
        'breakdown': cod_breakdown,
        'organic_component_count': len(organic_components),
        'organic_components': organic_components,
        'missing_components': missing_components
    }


def verify_methane_calculation(biogas_data, cod_removed_kg_d):
    """
    Verify methane flow calculation and COD equivalence.

    Args:
        biogas_data: Biogas stream data from JSON
        cod_removed_kg_d: COD removed (kg/d)

    Returns:
        Dict with methane analysis
    """
    ch4_flow_nm3_d = biogas_data.get('methane_flow', 0)  # Nm³/d at STP

    # Convert Nm³/d to kg/d
    # Nm³/d → kmol/d → kg/d
    ch4_kmol_d = ch4_flow_nm3_d / STD_MOLAR_VOLUME
    ch4_kg_d = ch4_kmol_d * CH4_MW

    # Calculate COD equivalent
    # CH₄ + 2O₂ → CO₂ + 2H₂O
    # 1 kg CH₄ needs 4 kg O₂
    ch4_cod_kg_d = ch4_kg_d * 4.0

    # Calculate yield
    ch4_yield_m3_kg_cod = ch4_flow_nm3_d / cod_removed_kg_d if cod_removed_kg_d > 0 else 0
    theoretical_yield = 0.35  # Nm³ CH₄/kg COD at STP
    efficiency_pct = (ch4_yield_m3_kg_cod / theoretical_yield) * 100 if theoretical_yield > 0 else 0

    return {
        'methane_flow_nm3_d': ch4_flow_nm3_d,
        'methane_mass_kg_d': ch4_kg_d,
        'methane_cod_kg_d': ch4_cod_kg_d,
        'methane_yield_m3_kg_cod': ch4_yield_m3_kg_cod,
        'methane_yield_theoretical': theoretical_yield,
        'methane_yield_efficiency_pct': efficiency_pct
    }


def main(results_file):
    """Main diagnostic function."""

    # Load simulation results
    with open(results_file, 'r') as f:
        results = json.load(f)

    print("="*80)
    print("COD MASS BALANCE DIAGNOSTIC")
    print("="*80)
    print()

    # Extract data
    inf_stream = results['streams']['influent']
    eff_stream = results['streams']['effluent']
    biogas = results['streams']['biogas']
    sulfur = results.get('sulfur', {})

    flow_m3_d = inf_stream.get('flow', 1000.0)

    # ============================================================================
    # STEP 1: Component Array Coverage Check
    # ============================================================================
    print("STEP 1: Component Array Coverage")
    print("-" * 80)

    inf_components = inf_stream.get('components', {})
    eff_components = eff_stream.get('components', {})

    num_components = len([c for c in inf_components.keys() if c != 'H2O'])
    print(f"Number of components in stream: {num_components}")
    print(f"Expected (mADM1): 62 components")
    print()

    # Check for key extension components
    extension_components = ['X_PHA', 'X_PAO', 'X_hSRB', 'X_aSRB', 'X_pSRB', 'X_c4SRB']
    print("Extension components present:")
    for comp in extension_components:
        present = comp in inf_components
        conc = inf_components.get(comp, 0.0)
        print(f"  {comp}: {'✓' if present else '✗'} ({conc:.4f} mg/L in influent)")
    print()

    # ============================================================================
    # STEP 2: Manual COD Calculation
    # ============================================================================
    print("STEP 2: Manual COD Calculation from Components")
    print("-" * 80)

    print("\nInfluent Stream:")
    inf_cod_calc = calculate_cod_from_components(inf_components, flow_m3_d)
    inf_cod_reported = inf_stream.get('COD', 0.0)

    print(f"  Reported COD (stream.COD): {inf_cod_reported:.2f} mg/L")
    print(f"  Manual COD (sum of components): {inf_cod_calc['total_cod_mg_L']:.2f} mg/L")
    print(f"  Organic components counted: {inf_cod_calc['organic_component_count']}")
    print(f"  Discrepancy: {inf_cod_calc['total_cod_mg_L'] - inf_cod_reported:.2f} mg/L ({(inf_cod_calc['total_cod_mg_L'] / inf_cod_reported - 1) * 100:.1f}%)")

    if inf_cod_calc['missing_components']:
        print(f"  WARNING: {len(inf_cod_calc['missing_components'])} components not in COD table:")
        for comp in inf_cod_calc['missing_components']:
            print(f"    - {comp}")

    print("\nEffluent Stream:")
    eff_cod_calc = calculate_cod_from_components(eff_components, flow_m3_d)
    eff_cod_reported = eff_stream.get('COD', 0.0)

    print(f"  Reported COD (stream.COD): {eff_cod_reported:.2f} mg/L")
    print(f"  Manual COD (sum of components): {eff_cod_calc['total_cod_mg_L']:.2f} mg/L")
    print(f"  Organic components counted: {eff_cod_calc['organic_component_count']}")
    print(f"  Discrepancy: {eff_cod_calc['total_cod_mg_L'] - eff_cod_reported:.2f} mg/L ({(eff_cod_calc['total_cod_mg_L'] / eff_cod_reported - 1) * 100:.1f}%)")

    print()

    # ============================================================================
    # STEP 3: COD Removed Calculation
    # ============================================================================
    print("STEP 3: COD Removed Comparison")
    print("-" * 80)

    # Reported (from JSON)
    cod_removed_reported = (inf_cod_reported - eff_cod_reported) * flow_m3_d / 1000.0

    # Manual (from component sums)
    cod_removed_manual = (inf_cod_calc['total_cod_mg_L'] - eff_cod_calc['total_cod_mg_L']) * flow_m3_d / 1000.0

    print(f"COD Removed (reported): {cod_removed_reported:.2f} kg/d")
    print(f"COD Removed (manual): {cod_removed_manual:.2f} kg/d")
    print(f"Difference: {cod_removed_manual - cod_removed_reported:.2f} kg/d ({(cod_removed_manual / cod_removed_reported - 1) * 100:.1f}%)")
    print()

    # ============================================================================
    # STEP 4: Methane Verification
    # ============================================================================
    print("STEP 4: Methane Flow Verification")
    print("-" * 80)

    ch4_analysis = verify_methane_calculation(biogas, cod_removed_reported)

    print(f"Methane flow: {ch4_analysis['methane_flow_nm3_d']:.2f} Nm³/d")
    print(f"Methane mass: {ch4_analysis['methane_mass_kg_d']:.2f} kg/d")
    print(f"Methane COD equivalent: {ch4_analysis['methane_cod_kg_d']:.2f} kg/d")
    print(f"Methane yield: {ch4_analysis['methane_yield_m3_kg_cod']:.4f} Nm³ CH₄/kg COD")
    print(f"Theoretical yield: {ch4_analysis['methane_yield_theoretical']:.4f} Nm³ CH₄/kg COD")
    print(f"Efficiency: {ch4_analysis['methane_yield_efficiency_pct']:.2f}%")
    print()

    # ============================================================================
    # STEP 5: Complete COD Balance
    # ============================================================================
    print("STEP 5: Complete COD Mass Balance")
    print("=" * 80)

    # Use manual COD removed if discrepancy found
    cod_removed = cod_removed_manual if abs(cod_removed_manual - cod_removed_reported) / cod_removed_reported > 0.05 else cod_removed_reported

    print(f"\nCOD Input (removed): {cod_removed:.2f} kg/d (100.0%)")
    print()

    # Sink 1: Methane
    cod_methane = ch4_analysis['methane_cod_kg_d']
    print(f"SINK 1: Methane")
    print(f"  Flow: {ch4_analysis['methane_flow_nm3_d']:.2f} Nm³/d")
    print(f"  Mass: {ch4_analysis['methane_mass_kg_d']:.2f} kg CH₄/d")
    print(f"  COD: {cod_methane:.2f} kg/d ({cod_methane / cod_removed * 100:.1f}%)")
    print()

    # Sink 2: Hydrogen
    h2_flow_nm3_d = biogas.get('h2_flow', 0)
    h2_kmol_d = h2_flow_nm3_d / STD_MOLAR_VOLUME
    h2_kg_d = h2_kmol_d * H2_MW
    cod_h2 = h2_kg_d * 8.0  # H₂ + 0.5 O₂ → H₂O
    print(f"SINK 2: Hydrogen")
    print(f"  Flow: {h2_flow_nm3_d:.4f} Nm³/d")
    print(f"  Mass: {h2_kg_d:.6f} kg H₂/d")
    print(f"  COD: {cod_h2:.4f} kg/d ({cod_h2 / cod_removed * 100:.3f}%)")
    print()

    # Sink 3: Sulfate reduction
    so4_in_kg_S_d = sulfur.get('sulfate_in_kg_S_d', 0)
    so4_out_kg_S_d = sulfur.get('sulfate_out_kg_S_d', 0)
    so4_reduced_kg_S_d = so4_in_kg_S_d - so4_out_kg_S_d
    cod_sulfate = so4_reduced_kg_S_d * 2.0  # SO₄²⁻ + 8e⁻ → HS⁻ needs 2 mol O₂ per mol S
    print(f"SINK 3: Sulfate Reduction")
    print(f"  SO₄ reduced: {so4_reduced_kg_S_d:.2f} kg S/d")
    print(f"  COD: {cod_sulfate:.2f} kg/d ({cod_sulfate / cod_removed * 100:.1f}%)")
    print(f"  (Using 2 kg COD/kg S)")
    print()

    # Sink 4: Dissolved methane in effluent
    s_ch4_mg_L = eff_components.get('S_ch4', 0)
    dissolved_ch4_kg_d = s_ch4_mg_L * flow_m3_d / 1000.0
    cod_dissolved_ch4 = dissolved_ch4_kg_d * 4.0
    print(f"SINK 4: Dissolved Methane")
    print(f"  S_ch4 in effluent: {s_ch4_mg_L:.4f} mg/L")
    print(f"  Mass: {dissolved_ch4_kg_d:.4f} kg CH₄/d")
    print(f"  COD: {cod_dissolved_ch4:.4f} kg/d ({cod_dissolved_ch4 / cod_removed * 100:.3f}%)")
    print()

    # Total
    cod_accounted = cod_methane + cod_h2 + cod_sulfate + cod_dissolved_ch4
    cod_gap = cod_removed - cod_accounted
    closure_pct = (cod_accounted / cod_removed) * 100

    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"COD Input (removed):      {cod_removed:10.2f} kg/d (100.0%)")
    print(f"  Methane (biogas):       {cod_methane:10.2f} kg/d ({cod_methane / cod_removed * 100:5.1f}%)")
    print(f"  Hydrogen (biogas):      {cod_h2:10.2f} kg/d ({cod_h2 / cod_removed * 100:5.1f}%)")
    print(f"  Sulfate reduction:      {cod_sulfate:10.2f} kg/d ({cod_sulfate / cod_removed * 100:5.1f}%)")
    print(f"  Dissolved CH₄:          {cod_dissolved_ch4:10.2f} kg/d ({cod_dissolved_ch4 / cod_removed * 100:5.1f}%)")
    print(f"  {'─' * 60}")
    print(f"Total Accounted:          {cod_accounted:10.2f} kg/d ({closure_pct:5.1f}%)")
    print(f"Gap (unexplained):        {cod_gap:10.2f} kg/d ({cod_gap / cod_removed * 100:5.1f}%)")
    print("=" * 80)

    # Verdict
    if abs(closure_pct - 100.0) <= 5.0:
        print("\n✓ PASS: COD mass balance closes within ±5%")
        return 0
    else:
        print(f"\n✗ FAIL: COD closure {closure_pct:.1f}% (target: 95-105%)")
        print(f"   Gap of {cod_gap:.2f} kg/d ({abs(cod_gap / cod_removed * 100):.1f}%) requires investigation")

        # Diagnostic hints
        print("\nPossible causes:")
        if abs(inf_cod_calc['total_cod_mg_L'] - inf_cod_reported) / inf_cod_reported > 0.05:
            print("  - Influent COD calculation discrepancy detected")
        if abs(eff_cod_calc['total_cod_mg_L'] - eff_cod_reported) / eff_cod_reported > 0.05:
            print("  - Effluent COD calculation discrepancy detected")
        if num_components < 62:
            print(f"  - Only {num_components} components found (expected 62)")

        return 1


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python verify_cod_from_components.py <simulation_results.json>")
        sys.exit(1)

    sys.exit(main(sys.argv[1]))
