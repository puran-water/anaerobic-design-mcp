#!/usr/bin/env python3
"""Check flow balance from most recent simulation."""

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from utils.watertap_simulation_modified import simulate_ad_system

def check_flow_balance():
    """Run simulation and extract detailed flow balance."""
    
    # Load current state
    with open("adm1_state.json", "r") as f:
        adm1_state = json.load(f)
    
    # Convert to simple dict
    adm1_dict = {}
    for key, value in adm1_state.items():
        if isinstance(value, list):
            adm1_dict[key] = value[0]
        else:
            adm1_dict[key] = value
    
    basis_of_design = {
        "flow_m3d": 1000,
        "cod_mg_l": 50000,
        "tss_mg_l": 35000,
        "vss_mg_l": 28000,
        "tkn_mg_l": 2500,
        "tp_mg_l": 500,
        "temperature_c": 35,
        "ph": 7.0
    }
    
    heuristic_config = {
        "flowsheet_type": "low_tss_mbr",
        "digester": {
            "volume_m3": 3750,
            "hrt_days": 3.75,
            "srt_days": 30
        },
        "mbr": {
            "sigma_soluble": 1.0,  # Fixed value
            "sigma_particulate": 1e-4  # Fixed value
        },
        "dewatering": {
            "tss_concentration_kg_m3": 15.0
        }
    }
    
    print("\n" + "="*80)
    print("FLOW BALANCE CHECK - POST-FIX SIMULATION")
    print("="*80)
    
    # Run simulation
    result = simulate_ad_system(
        basis_of_design=basis_of_design,
        adm1_state=adm1_dict,
        heuristic_config=heuristic_config,
        costing_method=None,
        initialize_only=False,
        tee=False
    )
    
    print(f"\nSimulation Status: {result['status']}")
    
    if 'operational_results' in result:
        op = result['operational_results']
        
        print("\n" + "-"*60)
        print("LIQUID FLOW BALANCE (m³/d)")
        print("-"*60)
        
        # Inputs
        feed_flow = 1000.0
        print(f"\nINPUTS:")
        print(f"  Feed water:          {feed_flow:8.1f} m³/d")
        print(f"  TOTAL IN:            {feed_flow:8.1f} m³/d")
        
        # Outputs
        mbr_permeate = op.get('mbr_permeate_flow_m3d', 0)
        sludge_flow = op.get('sludge_production_m3d', 0)
        centrate_flow = op.get('centrate_flow_m3d', 0)
        
        print(f"\nOUTPUTS:")
        print(f"  MBR permeate:        {mbr_permeate:8.1f} m³/d")
        print(f"  Dewatered sludge:    {sludge_flow:8.1f} m³/d")
        print(f"  Centrate:            {centrate_flow:8.1f} m³/d")
        
        total_liquid_out = mbr_permeate + sludge_flow + centrate_flow
        print(f"  TOTAL OUT:           {total_liquid_out:8.1f} m³/d")
        
        # Balance check
        imbalance = feed_flow - total_liquid_out
        imbalance_pct = 100 * abs(imbalance) / feed_flow
        
        print(f"\nBALANCE:")
        print(f"  Imbalance:           {imbalance:8.1f} m³/d ({imbalance_pct:.2f}%)")
        
        if imbalance_pct < 0.1:
            print(f"  Status:              ✓ EXCELLENT (< 0.1% error)")
        elif imbalance_pct < 1.0:
            print(f"  Status:              ✓ GOOD (< 1% error)")
        elif imbalance_pct < 5.0:
            print(f"  Status:              ⚠ ACCEPTABLE (< 5% error)")
        else:
            print(f"  Status:              ✗ POOR (> 5% error)")
        
        # Flow distribution analysis
        print("\n" + "-"*60)
        print("FLOW DISTRIBUTION ANALYSIS")
        print("-"*60)
        
        print(f"\nPERCENTAGE OF FEED:")
        print(f"  To MBR permeate:     {100*mbr_permeate/feed_flow:6.2f}%")
        print(f"  To sludge waste:     {100*sludge_flow/feed_flow:6.2f}%")
        print(f"  To centrate:         {100*centrate_flow/feed_flow:6.2f}%")
        
        # MBR performance
        if mbr_permeate > 0:
            mbr_recovery = mbr_permeate / feed_flow
            print(f"\nMBR RECOVERY:")
            print(f"  Recovery ratio:      {mbr_recovery:.3f}")
            print(f"  Concentrate factor:  {1/(1-mbr_recovery):.1f}x")
        
        # Biogas production
        biogas_flow = op.get('biogas_production_m3d', 0)
        ch4_fraction = op.get('methane_fraction', 0)
        
        print("\n" + "-"*60)
        print("GAS PRODUCTION")
        print("-"*60)
        print(f"\nBIOGAS:")
        print(f"  Total production:    {biogas_flow:8.1f} m³/d")
        print(f"  CH4 content:         {ch4_fraction*100:6.2f}%")
        print(f"  CH4 flow:            {biogas_flow*ch4_fraction:8.1f} m³/d")
        print(f"  CO2 flow:            {biogas_flow*(1-ch4_fraction):8.1f} m³/d")
        
        # Ratios
        print(f"\nRATIOS:")
        print(f"  Biogas/Feed:         {biogas_flow/feed_flow:.2f} m³/m³")
        print(f"  CH4/Feed:            {biogas_flow*ch4_fraction/feed_flow:.2f} m³/m³")
        
        # COD balance estimate
        feed_cod = feed_flow * basis_of_design['cod_mg_l'] / 1000  # kg/d
        ch4_to_cod = 0.35  # kg CH4/kg COD theoretical
        ch4_kg_d = biogas_flow * ch4_fraction * 0.656  # kg/d (density ~0.656 kg/m³)
        cod_to_ch4 = ch4_kg_d / ch4_to_cod  # kg COD/d
        cod_removal = 100 * cod_to_ch4 / feed_cod
        
        print("\n" + "-"*60)
        print("COD BALANCE (APPROXIMATE)")
        print("-"*60)
        print(f"\nCOD FLOWS:")
        print(f"  Feed COD:            {feed_cod:8.1f} kg/d")
        print(f"  To CH4 (estimated):  {cod_to_ch4:8.1f} kg/d")
        print(f"  COD removal:         {cod_removal:6.2f}%")
        
        # Nitrogen balance if available
        if 'nitrogen_balance' in result:
            nb = result['nitrogen_balance']
            print("\n" + "-"*60)
            print("NITROGEN BALANCE AT MBR")
            print("-"*60)
            print(f"\nCONCENTRATIONS:")
            print(f"  S_IN inlet:          {nb.get('S_IN_inlet_kg_m3', 0):.3f} kg/m³")
            print(f"  S_IN permeate:       {nb.get('S_IN_permeate_kg_m3', 0):.3f} kg/m³")
            print(f"  S_IN retentate:      {nb.get('S_IN_retentate_kg_m3', 0):.3f} kg/m³")
            
            print(f"\nFLOWS:")
            print(f"  N in:                {nb.get('N_flow_in_kg_d', 0):.1f} kg/d")
            print(f"  N to permeate:       {nb.get('N_flow_permeate_kg_d', 0):.1f} kg/d")
            print(f"  N to retentate:      {nb.get('N_flow_retentate_kg_d', 0):.1f} kg/d")
            
            print(f"\nPASSAGE:")
            print(f"  S_IN passage:        {nb.get('S_IN_passage_fraction', 0):.3f}")
            print(f"  H2O passage:         {nb.get('H2O_passage_fraction', 0):.3f}")
            print(f"  Expected S_IN:       {nb.get('expected_S_IN_passage', 0):.3f}")
            
            if nb.get('anomalous_rejection', False):
                print(f"  Status:              ✗ ANOMALOUS REJECTION DETECTED")
            else:
                print(f"  Status:              ✓ NORMAL PASSAGE")
        
        # Summary assessment
        print("\n" + "="*60)
        print("OVERALL ASSESSMENT")
        print("="*60)
        
        issues = []
        if imbalance_pct > 5:
            issues.append(f"Flow imbalance {imbalance_pct:.1f}%")
        if ch4_fraction < 0.60:
            issues.append(f"Low CH4 {ch4_fraction*100:.1f}%")
        if mbr_recovery < 0.95:
            issues.append(f"Low MBR recovery {mbr_recovery:.3f}")
        if result.get('nitrogen_balance', {}).get('anomalous_rejection', False):
            issues.append("Nitrogen rejection at MBR")
        
        if not issues:
            print("✓ All flow balances within acceptable ranges")
            print("✓ CH4 production exceeds target (>60%)")
            print("✓ MBR operating normally")
            print("\nSTATUS: SYSTEM OPERATING WELL")
        else:
            print("Issues detected:")
            for issue in issues:
                print(f"  ✗ {issue}")
            print(f"\nSTATUS: {len(issues)} ISSUE(S) NEED ATTENTION")
    
    else:
        print("\n✗ No operational results available - simulation may have failed")
    
    return result

if __name__ == "__main__":
    result = check_flow_balance()
    print("\n" + "="*80)