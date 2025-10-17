"""
QSDsan simulation tool for anaerobic digesters with ADM1+sulfur model.

Clean implementation replacing WaterTAP with QSDsan native simulation.
No backward compatibility - fresh start with proper QSDsan patterns.
"""

import anyio
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from core.state import design_state
from core.utils import coerce_to_dict

# Import simulation and analysis modules
from utils.qsdsan_simulation_sulfur import (
    run_simulation_sulfur,
    run_dual_hrt_simulation
)
from utils.stream_analysis_sulfur import (
    analyze_liquid_stream,
    analyze_gas_stream,
    analyze_inhibition,
    calculate_sulfur_metrics,
    analyze_biomass_yields
)

logger = logging.getLogger(__name__)


async def simulate_ad_system_tool(
    use_current_state: bool = True,
    validate_hrt: bool = True,
    hrt_variation: float = 0.2,
    costing_method: Optional[str] = None,
    custom_inputs: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Simulate anaerobic digester using QSDsan with ADM1+sulfur model.

    Clean implementation - no backward compatibility with WaterTAP.
    Uses proper dynamic simulation with early-stop convergence checking.

    Parameters
    ----------
    use_current_state : bool, optional
        Use parameters from current design state (default True)
    validate_hrt : bool, optional
        Run dual-HRT validation for robustness check (default True)
    hrt_variation : float, optional
        HRT variation for validation as fraction (default 0.2 = ±20%)
    costing_method : str or None, optional
        Costing approach (not yet implemented)
    custom_inputs : dict or None, optional
        Custom basis, ADM1 state, and heuristic config

    Returns
    -------
    dict
        Clean structure with:
        - success: bool
        - streams: {influent, effluent, biogas} with full properties
        - performance: {yields, inhibition}
        - sulfur: Comprehensive sulfur analysis
        - validation: Robustness check results (if validate_hrt=True)
        - convergence: Simulation convergence info

    Notes
    -----
    **Key Changes from WaterTAP version**:
    1. Native QSDsan simulation (no subprocess)
    2. Proper dynamic tracking with set_dynamic_tracker
    3. Early-stop convergence checking
    4. Dual-HRT validation for robustness
    5. H2S speciation and inhibition
    6. Clean metric structure (no WaterTAP compatibility)

    **CRITICAL** (per Codex review):
    - Must use set_dynamic_tracker before simulate()
    - Must initialize sulfur components with non-zero values
    - Must report H2S/HS⁻ speciation
    - Must validate design isn't on a performance cliff
    """
    try:
        start_time = datetime.now()

        # 1. Validate inputs and prepare simulation parameters
        logger.info("=== Starting ADM1+Sulfur Simulation ===")

        if use_current_state:
            # Use design state
            if not design_state.basis_of_design:
                return {
                    "success": False,
                    "message": "No basis of design found. Run elicit_basis_of_design first."
                }
            if not design_state.adm1_state:
                return {
                    "success": False,
                    "message": "No ADM1 state found. Characterize feedstock first."
                }
            if not design_state.heuristic_config:
                return {
                    "success": False,
                    "message": "No heuristic sizing found. Run heuristic_sizing_ad first."
                }

            # Get state and normalize keys for simulation
            basis_raw = design_state.basis_of_design
            adm1_state = design_state.adm1_state
            heuristic_config_raw = design_state.heuristic_config

            # Normalize basis keys: feed_flow_m3d → Q, temperature_c → Temp (K)
            # Handle None values defensively
            temp_c = basis_raw.get('temperature_c')
            temp_k = basis_raw.get('Temp')

            if temp_c is not None:
                # Convert from Celsius to Kelvin
                temp_final = temp_c + 273.15
            elif temp_k is not None:
                # Already in Kelvin
                temp_final = temp_k
            else:
                # Default to 35°C = 308.15 K
                temp_final = 308.15

            basis = {
                'Q': basis_raw.get('feed_flow_m3d') or basis_raw.get('Q'),
                'Temp': temp_final,
                **{k: v for k, v in basis_raw.items() if k not in ['feed_flow_m3d', 'temperature_c']}
            }

            # Normalize heuristic_config keys: hrt_days → HRT_days
            heuristic_config = heuristic_config_raw.copy()
            if 'digester' in heuristic_config:
                digester = heuristic_config['digester'].copy()
                if 'hrt_days' in digester and 'HRT_days' not in digester:
                    digester['HRT_days'] = digester.pop('hrt_days')
                heuristic_config['digester'] = digester

            logger.info(f"Using design state: Q={basis.get('Q', 'N/A')} m3/d, "
                       f"T={basis.get('Temp', 'N/A')} K")

        else:
            # Use custom inputs
            custom_inputs = coerce_to_dict(custom_inputs) or {}
            basis = custom_inputs.get("basis_of_design", {})
            adm1_state = custom_inputs.get("adm1_state", {})
            heuristic_config = custom_inputs.get("heuristic_config", {})

            if not all([basis, adm1_state, heuristic_config]):
                return {
                    "success": False,
                    "message": "Custom inputs must include basis_of_design, adm1_state, and heuristic_config"
                }

            logger.info(f"Using custom inputs: Q={basis.get('Q', 'N/A')} m3/d")

        # 2. Run simulation(s)
        logger.info(f"Validate HRT: {validate_hrt}, Variation: ±{hrt_variation*100:.0f}%")

        if validate_hrt:
            # Dual-HRT simulation for robustness check
            logger.info("Running dual-HRT validation...")

            results_design, results_check, warnings = await anyio.to_thread.run_sync(
                run_dual_hrt_simulation,
                basis, adm1_state, heuristic_config, hrt_variation
            )

            # Unpack design results
            sys_d, inf_d, eff_d, gas_d, converged_at_d, status_d = results_design

            # Unpack check results (we'll report these separately)
            sys_c, inf_c, eff_c, gas_c, converged_at_c, status_c = results_check

            logger.info(f"Design HRT: {status_d} at t={converged_at_d} days")
            logger.info(f"Check HRT: {status_c} at t={converged_at_c} days")

            if warnings:
                logger.warning(f"Robustness warnings: {len(warnings)}")
                for warning in warnings:
                    logger.warning(f"  - {warning}")

        else:
            # Single simulation at design HRT
            logger.info("Running single simulation at design HRT...")

            HRT_design = heuristic_config['digester']['HRT_days']
            sys_d, inf_d, eff_d, gas_d, converged_at_d, status_d = await anyio.to_thread.run_sync(
                run_simulation_sulfur,
                basis, adm1_state, HRT_design
            )

            logger.info(f"Simulation: {status_d} at t={converged_at_d} days")

            # No validation results
            warnings = []

        # 3. Analyze results from design simulation
        logger.info("Analyzing simulation results...")

        influent = analyze_liquid_stream(inf_d, include_components=True)
        effluent = analyze_liquid_stream(eff_d, include_components=True)
        biogas = analyze_gas_stream(gas_d)
        yields = analyze_biomass_yields(inf_d, eff_d)

        # Calculate sulfur metrics first (includes speciation)
        sulfur = calculate_sulfur_metrics(inf_d, eff_d, gas_d)

        # Pass speciation to inhibition analysis to avoid recalculation
        inhibition = analyze_inhibition((sys_d, inf_d, eff_d, gas_d), speciation=sulfur.get("speciation"))

        logger.info(f"COD removal: {yields.get('COD_removal_efficiency', 0):.1f}%")
        logger.info(f"Biogas: {biogas.get('flow_total', 0):.1f} m3/d, "
                   f"CH4: {biogas.get('methane_percent', 0):.1f}%")
        logger.info(f"H2S: {biogas.get('h2s_ppm', 0):.1f} ppm")

        # 4. Cache results for both workflow tracking and optional analysis tools
        # simulation_results: lightweight summary for workflow progress tracking
        design_state.simulation_results = {
            "success": True,
            "status": status_d,
            "converged_at_days": converged_at_d,
            "cod_removal_pct": yields.get('COD_removal_efficiency', 0),
            "biogas_m3_d": biogas.get('flow_total', 0),
            "methane_pct": biogas.get('methane_percent', 0),
            "h2s_ppm": biogas.get('h2s_ppm', 0)
        }

        # last_simulation: full stream objects for optional analysis tools
        design_state.last_simulation = {
            "sys": sys_d,
            "inf": inf_d,
            "eff": eff_d,
            "gas": gas_d,
            "timestamp": datetime.now(),
            "converged_at": converged_at_d,
            "status": status_d
        }

        logger.info("Simulation results cached for workflow tracking and optional analysis tools")

        # 5. Build validation section if dual-HRT was run
        validation_results = None
        if validate_hrt:
            # Analyze check simulation
            effluent_check = analyze_liquid_stream(eff_c)
            biogas_check = analyze_gas_stream(gas_c)
            yields_check = analyze_biomass_yields(inf_c, eff_c)

            validation_results = {
                "hrt_design": heuristic_config['digester']['HRT_days'],
                "hrt_check": heuristic_config['digester']['HRT_days'] * (1 + hrt_variation),
                "converged_at_design": converged_at_d,
                "converged_at_check": converged_at_c,
                "status_design": status_d,
                "status_check": status_c,
                "performance_comparison": {
                    "cod_removal_design": yields.get('COD_removal_efficiency', 0),
                    "cod_removal_check": yields_check.get('COD_removal_efficiency', 0),
                    "biogas_design": biogas.get('flow_total', 0),
                    "biogas_check": biogas_check.get('flow_total', 0),
                    "methane_pct_design": biogas.get('methane_percent', 0),
                    "methane_pct_check": biogas_check.get('methane_percent', 0),
                    "h2s_ppm_design": biogas.get('h2s_ppm', 0),
                    "h2s_ppm_check": biogas_check.get('h2s_ppm', 0)
                },
                "warnings": warnings
            }

        # 6. Calculate runtime
        end_time = datetime.now()
        runtime_seconds = (end_time - start_time).total_seconds()

        logger.info(f"Simulation completed in {runtime_seconds:.1f} seconds")
        logger.info("=== Simulation Complete ===")

        # 7. Return clean structure
        return {
            "success": True,
            "message": f"Simulation completed: {status_d} at t={converged_at_d} days",

            # Stream properties (all 30 components + composites)
            "streams": {
                "influent": influent,
                "effluent": effluent,
                "biogas": biogas
            },

            # Performance metrics
            "performance": {
                "yields": yields,
                "inhibition": inhibition
            },

            # Sulfur analysis (NEW - sulfur-specific)
            "sulfur": sulfur,

            # Validation results (if dual-HRT was run)
            "validation": validation_results,

            # Convergence info
            "convergence": {
                "converged_at_days": converged_at_d,
                "status": status_d,
                "runtime_seconds": runtime_seconds
            }
        }

    except Exception as e:
        logger.error(f"Error in simulate_ad_system_tool: {str(e)}", exc_info=True)
        return {
            "success": False,
            "message": f"Simulation failed: {str(e)}"
        }
