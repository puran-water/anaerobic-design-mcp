#!/usr/bin/env python3
"""Direct test of WaterTAP simulation to extract digester metrics."""

import sys
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from utils.watertap_simulation_modified import simulate_ad_system

def test_direct_simulation():
    """Run simulation directly and extract digester metrics."""
    
    # Load test data
    with open("adm1_state.json", "r") as f:
        adm1_state = json.load(f)
    
    basis_of_design = {
        "feed_flow_m3d": 1000,
        "cod_mg_l": 50000,
        "tss_mg_l": 35000,
        "vss_mg_l": 28000,
        "tkn_mg_l": 2500,
        "tp_mg_l": 500,
        "alkalinity_meq_l": 100,
        "ph": 7.0,
        "temperature_c": 35
    }
    
    heuristic_config = {
        "flowsheet_type": "low_tss_mbr",
        "digester": {
            "volume_m3": 3750,
            "liquid_volume_m3": 3375,
            "vapor_volume_m3": 375,
            "hrt_days": 3.375,
            "target_srt_days": 30
        },
        "mbr": {
            "type": "submerged",
            "membrane_area_m2": 5000,
            "permeate_flux_lmh": 15,
            "mlss_concentration_mg_l": 12000,
            "expected_permeate_m3d": 999,
            "sigma_soluble": 0.0,
            "sigma_particulate": 1.0
        },
        "dewatering": {
            "tss_removal_efficiency": 0.98,
            "tss_concentration_kg_m3": 15.0,
            "cake_flow_fraction": 1/15
        },
        "operating_conditions": {
            "temperature_k": 308.15,
            "pressure_atm": 1.0
        }
    }
    
    print("\n" + "="*80)
    print("DIRECT SIMULATION TEST - DIGESTER METRICS EXTRACTION")
    print("="*80)
    
    print("\nRunning simulation...")
    
    # Run simulation with initialize_only first to debug
    result = simulate_ad_system(
        basis_of_design=basis_of_design,
        adm1_state=adm1_state,
        heuristic_config=heuristic_config,
        costing_method=None,
        initialize_only=False,
        tee=False
    )
    
    print(f"\nSimulation status: {result['status']}")
    
    if result['status'] == 'success':
        print("\n--- OPERATIONAL RESULTS ---")
        print(f"Biogas production: {result['operational_results']['biogas_production_m3d']:.1f} m³/d")
        print(f"Methane fraction: {result['operational_results']['methane_fraction']:.1%}")
        print(f"MBR permeate flow: {result['operational_results']['mbr_permeate_flow_m3d']:.1f} m³/d")
        
        if 'digester_performance' in result:
            metrics = result['digester_performance']
            print("\n--- DIGESTER PERFORMANCE ---")
            
            if 'digestate_pH' in metrics:
                print(f"Digestate pH: {metrics['digestate_pH']:.2f}")
            
            if 'digestate_total_VFA_kg_m3' in metrics:
                print(f"Total VFAs: {metrics['digestate_total_VFA_kg_m3']:.2f} kg/m³")
                
            if 'digestate_VFAs_kg_m3' in metrics:
                for vfa, conc in metrics['digestate_VFAs_kg_m3'].items():
                    print(f"  {vfa}: {conc:.3f} kg/m³")
            
            if 'digestate_TAN_mg_N_L' in metrics:
                print(f"TAN: {metrics['digestate_TAN_mg_N_L']:.1f} mg-N/L")
            
            if 'inhibition_factors' in metrics:
                print("\n--- INHIBITION FACTORS ---")
                for name, value in metrics['inhibition_factors'].items():
                    status = "OK" if value > 0.5 else "INHIBITED"
                    print(f"  {name}: {value:.3f} [{status}]")
            
            if 'critical_inhibitions' in metrics and metrics['critical_inhibitions']:
                print("\n--- CRITICAL INHIBITIONS (<0.5) ---")
                for inhib in metrics['critical_inhibitions']:
                    print(f"  WARNING: {inhib}")
            
            # Save full metrics to file
            output_file = "digester_metrics_direct.json"
            with open(output_file, 'w') as f:
                json.dump(metrics, f, indent=2, default=str)
            print(f"\nFull digester metrics saved to: {output_file}")
            
    elif result['status'] == 'failed':
        print("\n--- FAILED RESULTS ---")
        print(f"Solver status: {result.get('convergence_info', {}).get('solver_status', 'unknown')}")
        print(f"DOF: {result.get('convergence_info', {}).get('degrees_of_freedom', 'unknown')}")
        
        # Still try to get operational results
        if 'operational_results' in result:
            print(f"\nBiogas production: {result['operational_results']['biogas_production_m3d']:.1f} m³/d")
            print(f"Methane fraction: {result['operational_results']['methane_fraction']:.1%}")
            print(f"MBR permeate flow: {result['operational_results']['mbr_permeate_flow_m3d']:.1f} m³/d")
    
    else:
        print(f"\nError: {result.get('message', 'Unknown error')}")
    
    # Always save full result
    with open("simulation_result_direct.json", 'w') as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\nFull result saved to: simulation_result_direct.json")
    
    return result['status'] == 'success'

if __name__ == "__main__":
    success = test_direct_simulation()
    sys.exit(0 if success else 1)