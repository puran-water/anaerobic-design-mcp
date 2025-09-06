#!/usr/bin/env python3
"""Direct test of simulation with fixes."""

import sys
import json
from utils.watertap_simulation_modified import simulate_ad_system

def test_simulation():
    """Test simulation directly with fixed configuration."""
    
    # Configuration matching what MCP server uses
    basis_of_design = {
        "feed_flow_m3d": 1000,
        "cod_mg_l": 50000,
        "temperature_c": 35,
        "tss_mg_l": 20000,
        "vss_mg_l": 17000,
        "tkn_mg_l": 1500,
        "tp_mg_l": 200,
        "ph": 7.2,
        "alkalinity_meq_l": 60
    }
    
    # ADM1 state from file - using balanced version to fix ion imbalance
    with open("fixed_adm1_state.json", "r") as f:
        adm1_state_raw = json.load(f)
    
    # Extract just values
    adm1_state = {}
    for key, value in adm1_state_raw.items():
        if isinstance(value, list):
            adm1_state[key] = value[0]
        else:
            adm1_state[key] = value
    
    # Heuristic config with diagnostics enabled
    heuristic_config = {
        "flowsheet_type": "low_tss_mbr",
        "digester": {
            "liquid_volume_m3": 10000.0,
            "vapor_volume_m3": 1000.0,
            "hrt_days": 10.0,
            "srt_days": 30.0,
            "mlss_mg_l": 15000.0
        },
        "mbr": {
            "required": True,
            "type": "submerged",
            "total_area_m2": 8333.3,
            "flux_lmh": 5.0,
            "permeate_flow_m3d": 1000
        },
        "dewatering": {
            "equipment_type": "centrifuge",
            "cake_solids_fraction": 0.22,
            "solids_capture_fraction": 0.95,
            "daily_waste_sludge_m3d": 333.333,
            "volume_fraction": 0.2
        },
        "diagnostics": {
            "force_mbr_min_constraints": False,  # Don't force - causing infeasibility
            "seed_force_mbr": True,  # Still seed MBR with design flows
            "log_flows": True  # Enable flow logging
        },
        "simulation": {
            "sd_iter_lim": 20,  # More SD iterations
            "use_sd": True,  # Re-enable SD - translator fails without it
            "solver_options": {
                "max_iter": 1000,  # Even more iterations
                "tol": 1e-5,  # Looser tolerance for convergence
                "constr_viol_tol": 1e-5  # Also loosen constraint tolerance
            }
        }
    }
    
    print("Testing simulation with fixes...")
    print("=" * 60)
    
    # Run simulation
    results = simulate_ad_system(
        basis_of_design=basis_of_design,
        adm1_state=adm1_state,
        heuristic_config=heuristic_config,
        costing_method="WaterTAPCosting",
        initialize_only=False
    )
    
    print(f"Status: {results['status']}")
    if 'convergence_info' in results:
        print(f"Solver: {results['convergence_info']['solver_status']}")
        print(f"DOF: {results['convergence_info']['degrees_of_freedom']}")
    else:
        print(f"Error: {results.get('message', 'Unknown error')}")
    if 'operational_results' in results:
        print()
        print("Key flows:")
        print(f"  Biogas: {results['operational_results']['biogas_production_m3d']:.2f} m³/d")
        print(f"  MBR permeate: {results['operational_results']['mbr_permeate_flow_m3d']:.2e} m³/d")
        print(f"  Centrate: {results['operational_results']['centrate_flow_m3d']:.2e} m³/d")
        print(f"  Sludge: {results['operational_results']['sludge_production_m3d']:.2e} m³/d")
        
        # Check if flows are realistic
        if results['operational_results']['mbr_permeate_flow_m3d'] > 100:
            print("\nSUCCESS: MBR permeate flow is realistic!")
        else:
            print("\nFAILURE: Flows are still near-zero")
    else:
        print("\nFAILURE: Simulation did not complete - no operational results")
        print("\nThis indicates the fixes may not be sufficient or there's another issue.")
    
    return results

if __name__ == "__main__":
    results = test_simulation()