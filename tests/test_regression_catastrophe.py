#!/usr/bin/env python
"""
P0: Regression test to pin and reproduce catastrophic AD failure.

This test documents the current failure state with:
- TAN = 77,195 mg-N/L (toxic ammonia levels)
- pH = 4.0 (severe acidification)
- Total VFAs = 47.5 kg/m³ (VFA accumulation)
- I_nh3 = 0.0084 (99.2% methanogenic inhibition)
- TSS = 1 mg/L (complete biomass washout)

The test is marked with xfail to document the baseline failure without
blocking CI. Once P1/P2 fixes are implemented, this test should pass.
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.watertap_simulation_modified import simulate_ad_system


@pytest.mark.xfail(reason="P0: Documenting catastrophic failure - TAN toxicity, pH collapse, VFA accumulation")
def test_catastrophic_failure_baseline():
    """
    Reproduce and pin the catastrophic AD failure for baseline measurement.
    
    This test captures the complete process failure with:
    1. Extreme ammonia accumulation (77 g-N/L)
    2. pH collapse to 4.0
    3. VFA accumulation at 47.5 kg/m³
    4. Near-complete methanogenic inhibition
    5. Total biomass washout
    """
    
    # Exact inputs from test_simulation_fixes.py that produce failure
    basis_of_design = {
        "feed_flow_m3d": 1000.0,
        "cod_mg_l": 500.0,
        "tss_mg_l": 220.0,
        "vss_mg_l": 180.0,
        "tkn_mg_l": 40.0,
        "tp_mg_l": 8.0,
        "alkalinity_meq_l": 7.0,
        "temperature_c": 35.0,
        "ph": 7.0
    }
    
    # Municipal wastewater ADM1 state with problematic S_IN
    adm1_state = {
        "S_su": 0.012,
        "S_aa": 0.005,
        "S_fa": 0.099,
        "S_va": 0.012,
        "S_bu": 0.014,
        "S_pro": 0.016,
        "S_ac": 0.020,
        "S_h2": 2.3e-7,
        "S_ch4": 5.5e-5,
        "S_IC": 0.15,
        "S_IN": 0.04,  # This accumulates to toxic levels
        "S_IP": 0.008,
        "S_I": 0.033,
        "X_c": 0.031,
        "X_ch": 0.028,
        "X_pr": 0.020,
        "X_li": 0.029,
        "X_su": 0.42,
        "X_aa": 0.028,
        "X_fa": 0.024,
        "X_c4": 0.042,
        "X_pro": 0.013,
        "X_ac": 0.076,
        "X_h2": 0.032,
        "X_I": 0.025,
        "X_PHA": 0.001,
        "X_PP": 0.001,
        "X_PAO": 0.001,
        "S_K": 0.028,
        "S_Mg": 0.006,
        "S_cat": 0.040,
        "S_an": 0.040
    }
    
    # Low TSS MBR configuration
    heuristic_config = {
        "flowsheet_type": "low_tss_mbr",
        "digester": {
            "liquid_volume_m3": 3400.0,
            "vapor_volume_m3": 340.0,
            "srt_days": 30.0
        },
        "mbr": {
            "sigma_soluble": 1.0,  # Full passage of dissolved species
            "sigma_particulate": 1e-4,  # Near-complete rejection
            "auto_correct_sigma": False,  # Prevent auto-correction
            "recirc_ratio": 4.0
        },
        "dewatering": {
            "volume_fraction": 0.06,
            "capture_fraction": 0.95,
            "cake_solids_fraction": 0.22
        },
        "operating_conditions": {
            "temperature_k": 308.15,
            "pressure_atm": 1.0
        }
    }
    
    # Run simulation - expect solver failure but capture metrics
    results = simulate_ad_system(
        basis_of_design=basis_of_design,
        adm1_state=adm1_state,
        heuristic_config=heuristic_config,
        costing_method=None,
        initialize_only=False,
        tee=False
    )
    
    # Verify we get results even with solver failure
    assert results is not None, "Simulation should return results even on failure"
    assert results.get("status") in ["error", "failed"], "Expected simulation failure status"
    
    # Extract digester performance metrics if available
    digester_perf = results.get("digester_performance", {})
    
    if digester_perf:
        # 1. AMMONIA TOXICITY - Expect extreme TAN accumulation
        tan_mg_l = digester_perf.get("digestate_TAN_mg_N_L", 0)
        assert tan_mg_l > 50000, f"Expected TAN > 50,000 mg-N/L, got {tan_mg_l}"
        # Document actual value: 77,195 mg-N/L
        
        # 2. pH COLLAPSE - Expect severe acidification
        ph = digester_perf.get("digestate_pH", 7)
        assert ph < 5.0, f"Expected pH < 5.0 (acidification), got {ph}"
        # Document actual value: 4.0
        
        # 3. VFA ACCUMULATION - Expect massive VFA buildup
        total_vfa = digester_perf.get("digestate_total_VFA_kg_m3", 0)
        assert total_vfa > 40, f"Expected VFAs > 40 kg/m³, got {total_vfa}"
        # Document actual value: 47.5 kg/m³
        
        # 4. METHANOGENIC INHIBITION - Expect near-complete inhibition
        inhibition = digester_perf.get("inhibition_factors", {})
        i_nh3 = inhibition.get("I_nh3", 1.0)
        assert i_nh3 < 0.01, f"Expected I_nh3 < 0.01 (>99% inhibition), got {i_nh3}"
        # Document actual value: 0.0084 (99.2% inhibition)
        
        # 5. BIOMASS WASHOUT - Expect near-zero biomass
        tss = digester_perf.get("digestate_TSS_mg_L", 1000)
        assert tss < 10, f"Expected TSS < 10 mg/L (washout), got {tss}"
        # Document actual value: 1 mg/L
        
        # 6. HYDROGEN INHIBITION - Secondary inhibitions from H2 accumulation
        i_h2_fa = inhibition.get("I_h2_fa", 1.0)
        assert i_h2_fa < 0.01, f"Expected I_h2_fa < 0.01, got {i_h2_fa}"
        # Document actual value: 0.004
    
    # 7. SOLVER STATUS - Expect convergence failure
    solver_status = results.get("solver_status", "unknown")
    assert solver_status != "optimal", f"Expected non-optimal solver status, got {solver_status}"
    
    # Document the catastrophic failure for baseline
    print("\n" + "="*60)
    print("CATASTROPHIC FAILURE BASELINE CAPTURED")
    print("="*60)
    if digester_perf:
        print(f"TAN: {digester_perf.get('digestate_TAN_mg_N_L', 'N/A')} mg-N/L")
        print(f"pH: {digester_perf.get('digestate_pH', 'N/A')}")
        print(f"Total VFAs: {digester_perf.get('digestate_total_VFA_kg_m3', 'N/A')} kg/m³")
        print(f"I_nh3: {inhibition.get('I_nh3', 'N/A')}")
        print(f"TSS: {digester_perf.get('digestate_TSS_mg_L', 'N/A')} mg/L")
    print(f"Solver status: {solver_status}")
    print("="*60)


def test_metrics_structure():
    """
    Verify that simulate_ad_system returns expected metric structure.
    
    This test ensures the metrics we rely on for assertions are present
    in the simulation output, even during failure conditions.
    """
    # Minimal valid inputs just to check structure
    basis = {"feed_flow_m3d": 100, "cod_mg_l": 100}
    adm1 = {"S_IN": 0.01}  # Minimal state
    config = {"flowsheet_type": "low_tss_mbr"}
    
    # We expect this to fail but still return structured results
    results = simulate_ad_system(
        basis_of_design=basis,
        adm1_state=adm1,
        heuristic_config=config,
        costing_method=None,
        initialize_only=True,  # Just initialize, don't solve
        tee=False
    )
    
    # Check that results have expected structure
    assert isinstance(results, dict), "Results should be a dictionary"
    assert "status" in results, "Results should have status field"
    
    # When digester_performance is present, check its structure
    if "digester_performance" in results:
        perf = results["digester_performance"]
        # Check for key metrics we use in assertions
        expected_keys = [
            "digestate_TAN_mg_N_L",
            "digestate_pH", 
            "digestate_total_VFA_kg_m3",
            "inhibition_factors",
            "digestate_TSS_mg_L"
        ]
        for key in expected_keys:
            assert key in perf or perf == {}, f"Missing expected key: {key}"


if __name__ == "__main__":
    # Run with pytest for xfail support, or directly for debugging
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--direct":
        test_catastrophic_failure_baseline()
        test_metrics_structure()
    else:
        pytest.main([__file__, "-v", "-s"])