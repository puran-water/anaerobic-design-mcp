#!/usr/bin/env python3
"""
Token-efficient parser for anaerobic digester simulation results.

Reads only the compact summary JSON files (7 KB total) instead of the full
simulation_results.json (159 KB), saving ~95% of tokens.

Usage:
    python utils/parse_simulation_results.py [performance.json] [inhibition.json] [precipitation.json]

    Default files:
    - simulation_performance.json
    - simulation_inhibition.json
    - simulation_precipitation.json
"""

import json
import sys

def parse_and_display_results(perf_file='simulation_performance.json',
                              inhib_file='simulation_inhibition.json',
                              precip_file='simulation_precipitation.json'):
    """Parse and display simulation results in three tables."""

    # Read the three summary files
    with open(perf_file) as f:
        perf = json.load(f)
    with open(inhib_file) as f:
        inhib = json.load(f)
    with open(precip_file) as f:
        precip = json.load(f)

    # Performance Metrics Table
    print("=" * 90)
    print("TABLE 1: PERFORMANCE METRICS")
    print("=" * 90)
    print(f"{'Metric':<50} {'Value':<20} {'Units':<20}")
    print("-" * 90)

    # Influent characteristics
    print("\n--- Influent Characteristics ---")
    inf = perf['streams']['influent']
    print(f"{'Flow Rate':<50} {inf['flow_m3_d']:<20.2f} {'m³/d':<20}")
    print(f"{'COD':<50} {inf['COD_mg_L']:<20.1f} {'mg/L':<20}")
    print(f"{'VSS':<50} {inf['VSS_mg_L']:<20.1f} {'mg/L':<20}")
    print(f"{'pH':<50} {inf['pH']:<20.2f} {'':<20}")
    print(f"{'Alkalinity':<50} {inf['alkalinity_meq_L']:<20.1f} {'meq/L':<20}")

    # Effluent characteristics
    print("\n--- Effluent Characteristics ---")
    eff = perf['streams']['effluent']
    print(f"{'pH':<50} {eff['pH']:<20.2f} {'':<20}")
    print(f"{'COD':<50} {eff['COD_mg_L']:<20.1f} {'mg/L':<20}")
    print(f"{'VSS':<50} {eff['VSS_mg_L']:<20.1f} {'mg/L':<20}")
    print(f"{'Total VFA':<50} {eff['total_VFA_mg_L']:<20.1f} {'mg/L':<20}")
    print(f"{'Alkalinity':<50} {eff['alkalinity_meq_L']:<20.1f} {'meq/L':<20}")

    # Biogas production
    print("\n--- Biogas Production ---")
    bg = perf['streams']['biogas']
    print(f"{'Total Biogas Production':<50} {bg['flow_total_m3_d']:<20.2f} {'m³/d':<20}")
    print(f"{'Methane Production':<50} {bg['methane_flow_m3_d']:<20.2f} {'m³/d':<20}")
    print(f"{'Methane Content':<50} {bg['methane_percent']:<20.2f} {'%':<20}")
    print(f"{'CO₂ Content':<50} {bg['co2_percent']:<20.2f} {'%':<20}")
    print(f"{'H₂ Content':<50} {bg['h2_percent']:<20.2f} {'%':<20}")
    print(f"{'H₂S Content':<50} {bg['h2s_ppm']:<20.1f} {'ppmv':<20}")

    # Yields
    print("\n--- Process Yields (KEY METRICS) ---")
    yld = perf['yields']
    print(f"{'COD Removal Efficiency':<50} {yld['COD_removal_efficiency_percent']:<20.2f} {'%':<20}")

    # Methane yields
    my = yld['methane_yields']
    spec_yield = my['specific_methane_yield_m3_kg_COD_removed']
    if spec_yield == 0 or spec_yield is None:
        # Calculate manually
        cod_removed_kg_d = (inf['COD_mg_L'] - eff['COD_mg_L']) * inf['flow_m3_d'] / 1000
        if cod_removed_kg_d > 0:
            spec_yield = bg['methane_flow_m3_d'] / cod_removed_kg_d
        else:
            spec_yield = 0

    print(f"{'★ SPECIFIC METHANE YIELD':<50} {spec_yield:<20.3f} {'m³/kg COD removed':<20}")
    print(f"{'★ SPECIFIC METHANE YIELD':<50} {spec_yield*1000:<20.1f} {'L/kg COD removed':<20}")
    print(f"{'Theoretical Methane Yield':<50} {my['theoretical_methane_yield_m3_kg_COD']:<20.3f} {'m³/kg COD':<20}")

    # Biomass yields
    by = yld['biomass_yields']
    print(f"{'★ NET VSS YIELD':<50} {by['net_VSS_yield_kg_kg_COD_removed']:<20.3f} {'kg VSS/kg COD removed':<20}")
    print(f"{'★ NET TSS YIELD':<50} {by['net_TSS_yield_kg_kg_COD_removed']:<20.3f} {'kg TSS/kg COD removed':<20}")

    print("=" * 90)
    print()

    # Inhibition Metrics Table
    print("=" * 90)
    print("TABLE 2: INHIBITION METRICS")
    print("=" * 90)
    print(f"{'Metric':<50} {'Value':<20} {'Units':<20}")
    print("-" * 90)

    # Overall health
    print("\n--- Overall Methanogen Health ---")
    summ = inhib['summary']
    print(f"{'Acetoclastic Methanogen Health':<50} {summ['acetoclastic_methanogen_health_percent']:<20.1f} {'%':<20}")
    print(f"{'Hydrogenotrophic Methanogen Health':<50} {summ['hydrogenotrophic_methanogen_health_percent']:<20.1f} {'%':<20}")
    print(f"{'Overall Methanogen Health':<50} {summ['overall_methanogen_health_percent']:<20.1f} {'%':<20}")
    print(f"{'Primary Limiting Factor':<50} {summ['primary_limiting_factor']:<20} {'':<20}")
    print(f"{'Secondary Limiting Factor':<50} {summ.get('secondary_limiting_factor', 'None'):<20} {'':<20}")

    # pH inhibition
    print("\n--- pH Inhibition ---")
    ph_ac = inhib['pH_inhibition']['acetoclastic_methanogens']
    ph_h2 = inhib['pH_inhibition']['hydrogenotrophic_methanogens']
    print(f"{'Actual pH':<50} {ph_ac['actual_pH']:<20.2f} {'':<20}")
    print(f"{'Acetoclastic Methanogens Inhibition':<50} {ph_ac['inhibition_percent']:<20.1f} {'%':<20}")
    print(f"{'Hydrogenotrophic Methanogens Inhibition':<50} {ph_h2['inhibition_percent']:<20.1f} {'%':<20}")
    print(f"{'Optimal pH Range (Acetogens)':<50} {f"{ph_ac['pH_lower_limit']}-{ph_ac['pH_upper_limit']}":<20} {'':<20}")

    # Ammonia inhibition
    print("\n--- Ammonia Inhibition ---")
    nh3 = inhib['ammonia_inhibition']['free_ammonia_inhibition']
    print(f"{'Free Ammonia Inhibition':<50} {nh3['inhibition_percent']:<20.2f} {'%':<20}")

    # H2 inhibition
    print("\n--- Hydrogen Inhibition ---")
    h2_prop = inhib['h2_inhibition']['propionate']
    h2_lcfa = inhib['h2_inhibition']['LCFA_uptake']
    print(f"{'Propionate Degradation Inhibition':<50} {h2_prop['inhibition_percent']:<20.1f} {'%':<20}")
    print(f"{'LCFA Uptake Inhibition':<50} {h2_lcfa['inhibition_percent']:<20.1f} {'%':<20}")

    print("=" * 90)
    print()

    # Precipitation Metrics Table
    print("=" * 90)
    print("TABLE 3: PRECIPITATION METRICS")
    print("=" * 90)
    print(f"{'Metric':<50} {'Value':<20} {'Units':<20}")
    print("-" * 90)

    # Summary
    print("\n--- Precipitation Summary ---")
    p_summ = precip['summary']
    print(f"{'Total Precipitation Rate':<50} {p_summ['total_precipitation_kg_d']:<20.3f} {'kg/d':<20}")
    print(f"{'Phosphorus Precipitated':<50} {p_summ['total_phosphorus_precipitated_kg_P_d']:<20.3f} {'kg-P/d':<20}")
    print(f"{'Sulfur Precipitated':<50} {p_summ['total_sulfur_precipitated_kg_S_d']:<20.3f} {'kg-S/d':<20}")

    # Major minerals
    print("\n--- Major Mineral Species ---")
    mins = precip['minerals']
    mineral_list = [
        ('Struvite (MgNH₄PO₄)', 'struvite_MgNH4PO4'),
        ('K-Struvite (KMgPO₄)', 'K_struvite'),
        ('Hydroxyapatite (Ca₅(PO₄)₃OH)', 'HAP_Ca5PO43OH'),
        ('Calcium Carbonate (CaCO₃)', 'calcium_carbonate_CaCO3'),
        ('Iron Sulfide (FeS)', 'iron_sulfide_FeS'),
        ('Ferrous Phosphate (Fe₃(PO₄)₂)', 'ferrous_phosphate_Fe3PO42'),
    ]

    for label, key in mineral_list:
        if key in mins:
            rate = mins[key].get('rate_kg_d', 0)
            conc = mins[key].get('concentration_mg_L', 0)
            if abs(rate) > 0.001 or abs(conc) > 0.001:
                print(f"{label + ' Rate':<50} {rate:<20.4f} {'kg/d':<20}")
                print(f"{label + ' Concentration':<50} {conc:<20.2f} {'mg/L':<20}")

    print("=" * 90)
    print()

    # Overall Assessment
    print("=" * 90)
    print("OVERALL ASSESSMENT")
    print("=" * 90)

    # Check for critical issues
    issues = []
    warnings = []

    # pH is critically low
    if eff['pH'] < 6.0:
        issues.append(f"CRITICAL: Effluent pH = {eff['pH']:.2f} (target: 6.5-7.5) - Severe acidification")

    # VFA accumulation
    if eff['total_VFA_mg_L'] > 1000:
        issues.append(f"CRITICAL: VFA accumulation = {eff['total_VFA_mg_L']:.0f} mg/L (target: <500 mg/L)")

    # Low methane content
    if bg['methane_percent'] < 50:
        warnings.append(f"WARNING: Low CH₄ content = {bg['methane_percent']:.1f}% (typical: 60-70%)")

    # High H2 content
    if bg['h2_percent'] > 1:
        warnings.append(f"WARNING: High H₂ content = {bg['h2_percent']:.1f}% (indicates incomplete methanogenesis)")

    # Methanogen health
    if summ['overall_methanogen_health_percent'] < 50:
        issues.append(f"CRITICAL: Methanogen health = {summ['overall_methanogen_health_percent']:.1f}% (target: >70%)")

    if issues:
        print("\n❌ CRITICAL ISSUES:")
        for issue in issues:
            print(f"  • {issue}")

    if warnings:
        print("\n⚠️  WARNINGS:")
        for warn in warnings:
            print(f"  • {warn}")

    if not issues and not warnings:
        print("\n✅ System operating within normal parameters")

    print("\n" + "=" * 90)

    # Summary note
    print("\nKEY FINDINGS:")
    print(f"  • Specific Methane Yield: {spec_yield:.3f} m³/kg COD = {spec_yield*1000:.1f} L/kg COD")
    print(f"  • Net Biomass Yield: {by['net_VSS_yield_kg_kg_COD_removed']:.3f} kg VSS/kg COD")
    print(f"  • Digester Status: {'FAILED - pH Collapse' if eff['pH'] < 6.0 else 'OPERATIONAL'}")
    print("=" * 90)


if __name__ == "__main__":
    # Parse command line arguments
    if len(sys.argv) == 4:
        perf_file = sys.argv[1]
        inhib_file = sys.argv[2]
        precip_file = sys.argv[3]
        parse_and_display_results(perf_file, inhib_file, precip_file)
    elif len(sys.argv) == 1:
        # Use default files
        parse_and_display_results()
    else:
        print("Usage: python utils/parse_simulation_results.py [performance.json] [inhibition.json] [precipitation.json]")
        print("\nIf no arguments provided, uses default files:")
        print("  - simulation_performance.json")
        print("  - simulation_inhibition.json")
        print("  - simulation_precipitation.json")
        sys.exit(1)
