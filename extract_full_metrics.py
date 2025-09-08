#!/usr/bin/env python3
"""Extract comprehensive metrics from WaterTAP simulation."""

import json
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.watertap_simulation_modified import simulate_ad_system

def extract_full_metrics():
    """Run simulation and extract all metrics."""
    
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
    
    # Load heuristic config
    with open("heuristic_sizing_config.json", "r") as f:
        heuristic_config = json.load(f)
    
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
    
    print("\n" + "="*80)
    print("FULL SIMULATION METRICS EXTRACTION")
    print("="*80)
    
    # Run simulation
    results = simulate_ad_system(
        basis,
        adm1_dict,
        heuristic_config,
        detail_level="full",
        costing_method="WaterTAPCosting"
    )
    
    if results["status"] == "success":
        print("\n✓ Simulation converged successfully")
    else:
        print(f"\n✗ Simulation failed: {results.get('convergence_info', {}).get('solver_status', 'Unknown')}")
    
    # Extract all available metrics
    metrics = {
        "simulation_status": results["status"],
        "flowsheet_type": results["flowsheet_type"],
        "convergence": results.get("convergence_info", {}),
        "operational": results.get("operational_results", {}),
        "economic": results.get("economic_results", {}),
        "stream_data": {},
        "inhibition_factors": {},
        "biomass_concentrations": {},
        "digestate_conditions": {}
    }
    
    # Try to get detailed stream data if available
    if "stream_data" in results:
        metrics["stream_data"] = results["stream_data"]
    
    # Try to get inhibition factors
    if "inhibition_factors" in results:
        metrics["inhibition_factors"] = results["inhibition_factors"]
    
    # Try to get biomass data
    if "biomass_data" in results:
        metrics["biomass_concentrations"] = results["biomass_data"]
    
    # Try to get digestate conditions
    if "digestate_conditions" in results:
        metrics["digestate_conditions"] = results["digestate_conditions"]
    
    # Load digester metrics if available
    import glob
    digester_files = sorted(glob.glob("simulation_logs/digester_metrics_*.json"))
    if digester_files:
        latest_file = digester_files[-1]
        print(f"\nLoading digester metrics from: {latest_file}")
        with open(latest_file, "r") as f:
            digester_metrics = json.load(f)
            metrics["digester_metrics"] = digester_metrics
    
    # Print comprehensive summary
    print("\n" + "="*80)
    print("COMPREHENSIVE METRICS SUMMARY")
    print("="*80)
    
    print("\n1. OPERATIONAL RESULTS:")
    print("-" * 40)
    op = metrics["operational"]
    print(f"  Biogas Production: {op.get('biogas_production_m3d', 'N/A'):.1f} m³/d")
    print(f"  Methane Fraction: {op.get('methane_fraction', 0)*100:.1f}%")
    print(f"  Sludge Production: {op.get('sludge_production_m3d', 'N/A'):.1f} m³/d")
    print(f"  Centrate Flow: {op.get('centrate_flow_m3d', 'N/A'):.1f} m³/d")
    print(f"  MBR Permeate: {op.get('mbr_permeate_flow_m3d', 'N/A'):.1f} m³/d")
    
    if "digester_metrics" in metrics:
        dm = metrics["digester_metrics"]
        print("\n2. DIGESTATE CONDITIONS:")
        print("-" * 40)
        print(f"  pH: {dm.get('digestate_pH', 'N/A')}")
        print(f"  Total VFA: {dm.get('digestate_total_VFA_kg_m3', 'N/A'):.2f} kg/m³")
        print(f"  TAN: {dm.get('digestate_TAN_mg_N_L', 'N/A'):.0f} mg-N/L")
        print(f"  TSS: {dm.get('digestate_TSS_mg_L', 'N/A'):.0f} mg/L")
        print(f"  VSS: {dm.get('digestate_VSS_mg_L', 'N/A'):.0f} mg/L")
        
        print("\n3. VFA BREAKDOWN (kg/m³):")
        print("-" * 40)
        vfas = dm.get("digestate_VFAs_kg_m3", {})
        for vfa, conc in vfas.items():
            print(f"  {vfa}: {conc:.3f}")
        
        print("\n4. INHIBITION FACTORS (0-1):")
        print("-" * 40)
        inhib = dm.get("inhibition_factors", {})
        for factor, value in inhib.items():
            if not factor.endswith("_raw"):
                status = "✓" if value > 0.5 else "✗" if value < 0.1 else "⚠"
                print(f"  {status} {factor}: {value:.6f}")
        
        print("\n5. BIOMASS CONCENTRATIONS (kg/m³):")
        print("-" * 40)
        biomass = dm.get("biomass_kg_m3", {})
        for species, conc in biomass.items():
            print(f"  {species}: {conc:.6f}")
        
        print("\n6. CRITICAL INHIBITIONS:")
        print("-" * 40)
        for crit in dm.get("critical_inhibitions", []):
            print(f"  ⚠ {crit}")
    
    print("\n7. CONVERGENCE INFO:")
    print("-" * 40)
    conv = metrics["convergence"]
    print(f"  Solver Status: {conv.get('solver_status', 'N/A')}")
    print(f"  DOF: {conv.get('degrees_of_freedom', 'N/A')}")
    
    # Save full metrics
    output_file = "simulation_logs/full_metrics_summary.json"
    with open(output_file, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"\n✓ Full metrics saved to: {output_file}")
    
    return metrics

if __name__ == "__main__":
    metrics = extract_full_metrics()