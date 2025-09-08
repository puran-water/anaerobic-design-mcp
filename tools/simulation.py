"""WaterTAP simulation tool for anaerobic digesters."""

import anyio
import logging
from typing import Dict, Any, Optional
from core.state import design_state
from core.utils import coerce_to_dict
from core.subprocess_runner import (
    run_simulation_in_subprocess,
    filter_simulation_response,
    save_full_logs
)

logger = logging.getLogger(__name__)


async def simulate_ad_system_tool(
    use_current_state: bool = True,
    costing_method: str = "WaterTAPCosting",
    initialize_only: bool = False,
    detail_level: str = "summary",
    custom_inputs: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Simulate anaerobic digester system using WaterTAP with Modified ADM1.
    
    This tool runs a full process simulation based on the current design state,
    including initialization with SequentialDecomposition for recycle convergence
    and optional economic analysis.
    
    Args:
        use_current_state: Use parameters from current design state (default True)
        costing_method: Costing approach - "WaterTAPCosting" or None
        initialize_only: Only build and initialize model (don't solve)
        detail_level: Response detail - "summary" for KPIs only, "full" for all details
        custom_inputs: Optional custom basis, ADM1 state, and config
    
    Returns:
        Dictionary containing:
        - status: Success/error status
        - flowsheet_type: Configuration simulated
        - operational_results: Biogas, methane, flows
        - economic_results: CAPEX, OPEX, LCOW (if costing enabled)
        - convergence_info: Solver statistics
    """
    try:
        # Prepare simulation inputs
        if use_current_state:
            if not design_state.basis_of_design:
                return {
                    "status": "error",
                    "message": "No basis of design found. Run elicit_basis_of_design first."
                }
            if not design_state.adm1_state:
                return {
                    "status": "error",
                    "message": "No ADM1 state found. Characterize feedstock first."
                }
            if not design_state.heuristic_config:
                return {
                    "status": "error",
                    "message": "No heuristic sizing found. Run heuristic_sizing_ad first."
                }
            
            basis = design_state.basis_of_design
            adm1_state = design_state.adm1_state
            heuristic_config = design_state.heuristic_config
        else:
            custom_inputs = coerce_to_dict(custom_inputs) or {}
            basis = custom_inputs.get("basis_of_design", {})
            adm1_state = custom_inputs.get("adm1_state", {})
            heuristic_config = custom_inputs.get("heuristic_config", {})
            
            if not all([basis, adm1_state, heuristic_config]):
                return {
                    "status": "error",
                    "message": "Custom inputs must include basis_of_design, adm1_state, and heuristic_config"
                }
        
        # Build simulation input
        sim_input = {
            "basis_of_design": basis,
            "adm1_state": adm1_state,
            "heuristic_config": heuristic_config,
            "costing_method": costing_method,
            "initialize_only": initialize_only,
            "tee": False  # Never tee in production
        }
        
        sim_results = await anyio.to_thread.run_sync(run_simulation_in_subprocess, sim_input)
        
        # Store results in design state if successful
        if sim_results.get("status") == "success":
            design_state.simulation_results = sim_results
            
            # Extract economic results if available
            if "economic_results" in sim_results:
                design_state.economic_results = sim_results["economic_results"]
        
        # Always save full logs to disk for debugging (per user request)
        if sim_results.get("status") in ["success", "failed"]:
            log_file = save_full_logs(sim_results)
            if log_file:
                logger.info(f"Full simulation results saved to: {log_file}")
        
        # Filter response based on detail level for MCP return
        filtered_results = filter_simulation_response(sim_results, detail_level)
        
        # Add log file path to results if saved
        if 'log_file' in locals() and log_file:
            filtered_results["full_log_saved_to"] = log_file
        
        return filtered_results
        
    except Exception as e:
        logger.error(f"Error in simulate_ad_system_tool: {str(e)}")
        return {
            "status": "error",
            "message": f"Simulation failed: {str(e)}"
        }