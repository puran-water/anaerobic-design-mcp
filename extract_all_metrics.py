#!/usr/bin/env python3
"""Extract comprehensive metrics from WaterTAP simulation with all stream data."""

import json
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.watertap_simulation_modified import simulate_ad_system
from utils.heuristic_sizing import heuristic_sizing_ad

def extract_all_metrics():
    """Run simulation and extract ALL metrics including stream data."""
    
    print("\n" + "="*80)
    print("COMPREHENSIVE METRICS EXTRACTION WITH STREAM DATA")
    print("="*80)
    
    # Load current ADM1 state
    with open("adm1_state.json", "r") as f:
        adm1_state = json.load(f)
    
    # Convert to simple dict
    adm1_dict = {}
    for key, value in adm1_state.items():
        if isinstance(value, list):
            adm1_dict[key] = value[0]
        else:
            adm1_dict[key] = value
    
    # Basis of design
    basis = {
        "flow_m3d": 1000,
        "cod_mg_l": 60000,
        "tss_mg_l": 40000,
        "vss_mg_l": 32000,
        "tkn_mg_l": 3000,
        "tp_mg_l": 500,
        "temperature_c": 35,
        "ph": 7.0,
        "alkalinity_mg_caco3_l": 5000
    }
    
    # Run heuristic sizing
    print("\n1. Running heuristic sizing...")
    heuristic_config = heuristic_sizing_ad(
        basis_of_design=basis,
        adm1_state=adm1_dict,
        biomass_yield=0.1,
        target_srt_days=30
    )
    
    print(f"   Flowsheet type: {heuristic_config['flowsheet_type']}")
    print(f"   Digester volume: {heuristic_config['digester']['volume_m3']:.0f} m³")
    
    # Run simulation
    print("\n2. Running WaterTAP simulation...")
    results = simulate_ad_system(
        basis,
        adm1_dict,
        heuristic_config,
        detail_level="full",
        costing_method="WaterTAPCosting"
    )
    
    if results["status"] == "success":
        print("   ✓ Simulation converged successfully")
    else:
        print(f"   ✗ Simulation failed: {results.get('convergence_info', {}).get('solver_status', 'Unknown')}")
    
    # Load latest digester metrics
    import glob
    digester_files = sorted(glob.glob("simulation_logs/digester_metrics_*.json"))
    digester_metrics = {}
    if digester_files:
        latest_file = digester_files[-1]
        print(f"\n3. Loading digester metrics from: {os.path.basename(latest_file)}")
        with open(latest_file, "r") as f:
            digester_metrics = json.load(f)
    
    # Compile comprehensive metrics
    print("\n" + "="*80)
    print("FULL METRICS SUMMARY")
    print("="*80)
    
    # A. FLOW RATES AND MASS BALANCES
    print("\n━━━ A. FLOW RATES AND MASS BALANCES ━━━")
    print("-" * 40)
    op = results.get("operational_results", {})
    
    print("Flows (m³/d):")
    print(f"  • Feed:           1000.0")
    print(f"  • MBR Permeate:   {op.get('mbr_permeate_flow_m3d', 0):.1f}")
    print(f"  • Centrate:       {op.get('centrate_flow_m3d', 0):.1f}")
    print(f"  • Sludge:         {op.get('sludge_production_m3d', 0):.1f}")
    print(f"  • Biogas:         {op.get('biogas_production_m3d', 0):.1f}")
    
    print("\nMass Balance Check:")
    total_out = (op.get('mbr_permeate_flow_m3d', 0) + 
                 op.get('centrate_flow_m3d', 0) + 
                 op.get('sludge_production_m3d', 0))
    print(f"  • Liquid In:      1000.0 m³/d")
    print(f"  • Liquid Out:     {total_out:.1f} m³/d")
    print(f"  • Balance:        {100 * total_out / 1000:.1f}%")
    
    # B. STATE VARIABLES IN EACH STREAM
    print("\n━━━ B. STATE VARIABLES IN STREAMS ━━━")
    print("-" * 40)
    
    print("\nFeed Stream (ADM1 State):")
    key_components = ["S_su", "S_aa", "S_fa", "S_ac", "S_IC", "S_IN", "S_cat", "S_an", "X_c", "X_ch", "X_pr", "X_li"]
    for comp in key_components:
        if comp in adm1_dict:
            val = adm1_dict[comp]
            print(f"  • {comp:8s}: {val:8.3f} kg/m³")
    
    if digester_metrics:
        print("\nDigestate Stream:")
        print(f"  • pH:             {digester_metrics.get('digestate_pH', 'N/A')}")
        print(f"  • Total VFA:      {digester_metrics.get('digestate_total_VFA_kg_m3', 0):.2f} kg/m³")
        print(f"  • TAN:            {digester_metrics.get('digestate_TAN_mg_N_L', 0):.0f} mg-N/L")
        print(f"  • TSS:            {digester_metrics.get('digestate_TSS_mg_L', 0):.0f} mg/L")
        print(f"  • VSS:            {digester_metrics.get('digestate_VSS_mg_L', 0):.0f} mg/L")
        
        print("\n  VFA Speciation (kg/m³):")
        vfas = digester_metrics.get("digestate_VFAs_kg_m3", {})
        for vfa, conc in vfas.items():
            print(f"    - {vfa:6s}: {conc:8.3f}")
    
    # C. INHIBITION FACTORS
    print("\n━━━ C. ALL INHIBITION FACTORS ━━━")
    print("-" * 40)
    
    if digester_metrics:
        inhib = digester_metrics.get("inhibition_factors", {})
        
        print("\npH Inhibition (0=dead, 1=healthy):")
        for key in ["I_pH_aa", "I_pH_ac", "I_pH_h2"]:
            if key in inhib:
                val = inhib[key]
                status = "✓" if val > 0.5 else "✗" if val < 0.1 else "⚠"
                print(f"  {status} {key:12s}: {val:.6f}")
        
        print("\nH2 Inhibition (0=dead, 1=healthy):")
        for key in ["I_h2_fa", "I_h2_c4", "I_h2_pro"]:
            if key in inhib:
                val = inhib[key]
                status = "✓" if val > 0.5 else "✗" if val < 0.1 else "⚠"
                print(f"  {status} {key:12s}: {val:.6f}")
        
        print("\nNutrient Limitation (0=starved, 1=sufficient):")
        for key in ["I_IN_lim", "I_IP_lim"]:
            if key in inhib:
                val = inhib[key]
                status = "✓" if val > 0.9 else "✗" if val < 0.5 else "⚠"
                print(f"  {status} {key:12s}: {val:.6f}")
        
        print("\nAmmonia/H2S Inhibition (0=toxic, 1=safe):")
        for key in ["I_nh3", "I_h2s_ac", "I_h2s_c4", "I_h2s_h2", "I_h2s_pro"]:
            if key in inhib:
                val = inhib[key]
                status = "✓" if val > 0.5 else "✗" if val < 0.1 else "⚠"
                print(f"  {status} {key:12s}: {val:.6f}")
    
    # D. BIOMASS CONCENTRATIONS
    print("\n━━━ D. BIOMASS YIELD DATA ━━━")
    print("-" * 40)
    
    if digester_metrics:
        biomass = digester_metrics.get("biomass_kg_m3", {})
        
        print("\nMethanogens (kg COD/m³):")
        print(f"  • X_ac (acetoclastic):     {biomass.get('X_ac', 0):.6f}")
        print(f"  • X_h2 (hydrogenotrophic): {biomass.get('X_h2', 0):.6f}")
        
        print("\nAcidogens (kg COD/m³):")
        print(f"  • X_su (sugar degraders):  {biomass.get('X_su', 0):.6f}")
        print(f"  • X_aa (amino degraders):  {biomass.get('X_aa', 0):.6f}")
        print(f"  • X_fa (LCFA degraders):   {biomass.get('X_fa', 0):.6f}")
        
        print("\nAcetogens (kg COD/m³):")
        print(f"  • X_c4 (C4 degraders):     {biomass.get('X_c4', 0):.6f}")
        print(f"  • X_pro (propionate deg):  {biomass.get('X_pro', 0):.6f}")
        
        total_biomass = sum(biomass.values())
        print(f"\nTotal Active Biomass: {total_biomass:.3f} kg COD/m³")
    
    # E. PERFORMANCE METRICS
    print("\n━━━ E. PERFORMANCE METRICS ━━━")
    print("-" * 40)
    
    print("\nBiogas Production:")
    print(f"  • Volume:         {op.get('biogas_production_m3d', 0):.1f} m³/d")
    print(f"  • CH4 content:    {op.get('methane_fraction', 0)*100:.1f}%")
    print(f"  • Target CH4:     65%")
    print(f"  • Status:         {'✓ PASS' if op.get('methane_fraction', 0) > 0.60 else '✗ FAIL'}")
    
    print("\nCOD Removal:")
    feed_cod = 1000 * 60  # kg/d
    biogas_cod = op.get('biogas_production_m3d', 0) * op.get('methane_fraction', 0) * 2.86  # kg COD/m³ CH4
    cod_removal = 100 * biogas_cod / feed_cod if feed_cod > 0 else 0
    print(f"  • Feed COD:       {feed_cod:.0f} kg/d")
    print(f"  • To CH4:         {biogas_cod:.0f} kg/d")
    print(f"  • Removal:        {cod_removal:.1f}%")
    
    print("\nHydraulic Performance:")
    print(f"  • HRT:            {heuristic_config['digester']['hrt_days']:.1f} days")
    print(f"  • SRT:            {heuristic_config['digester']['srt_days']:.1f} days")
    print(f"  • SRT/HRT:        {heuristic_config['digester']['srt_days']/heuristic_config['digester']['hrt_days']:.1f}")
    
    # F. CRITICAL ISSUES
    print("\n━━━ F. CRITICAL ISSUES ━━━")
    print("-" * 40)
    
    issues = []
    
    if digester_metrics:
        if digester_metrics.get('digestate_pH', 7) < 6.5:
            issues.append(f"✗ pH too low: {digester_metrics.get('digestate_pH', 'N/A')}")
        
        if digester_metrics.get('digestate_total_VFA_kg_m3', 0) > 5:
            issues.append(f"✗ VFA accumulation: {digester_metrics.get('digestate_total_VFA_kg_m3', 0):.1f} kg/m³")
        
        inhib = digester_metrics.get("inhibition_factors", {})
        for key, val in inhib.items():
            if not key.endswith("_lim") and val < 0.1:
                issues.append(f"✗ Severe inhibition: {key} = {val:.3f}")
    
    if op.get('methane_fraction', 0) < 0.60:
        issues.append(f"✗ Low methane: {op.get('methane_fraction', 0)*100:.1f}% (target 65%)")
    
    if issues:
        for issue in issues:
            print(f"  {issue}")
    else:
        print("  ✓ No critical issues detected")
    
    # Save full report
    full_report = {
        "basis_of_design": basis,
        "adm1_state": adm1_dict,
        "heuristic_config": heuristic_config,
        "simulation_results": results,
        "digester_metrics": digester_metrics,
        "summary": {
            "ch4_percent": op.get('methane_fraction', 0) * 100,
            "biogas_m3d": op.get('biogas_production_m3d', 0),
            "digestate_pH": digester_metrics.get('digestate_pH', 'N/A'),
            "total_vfa_kg_m3": digester_metrics.get('digestate_total_VFA_kg_m3', 0),
            "critical_issues": issues
        }
    }
    
    output_file = "full_metrics_report.json"
    with open(output_file, "w") as f:
        json.dump(full_report, f, indent=2)
    
    print(f"\n✓ Full report saved to: {output_file}")
    print("="*80)
    
    return full_report

if __name__ == "__main__":
    report = extract_all_metrics()