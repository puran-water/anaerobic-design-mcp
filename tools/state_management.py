"""Tools for managing design state."""

import logging
from typing import Dict, Any, List
from core.state import design_state

logger = logging.getLogger(__name__)


async def get_design_state() -> Dict[str, Any]:
    """
    Get the current state of the anaerobic digester design process.
    
    Returns the complete design state including all collected parameters,
    configurations, and results from various design stages.
    
    Returns:
        Dictionary containing:
        - basis_of_design: Collected design parameters
        - adm1_state: ADM1 state variables (if estimated)
        - heuristic_config: Heuristic sizing configuration (if calculated)
        - simulation_results: WaterTAP simulation results (if available)
        - economic_results: Economic analysis results (if available)
        - completion_status: Status of each design phase
    """
    try:
        # Determine completion status
        completion_status = {
            "basis_of_design": len(design_state.basis_of_design) > 0,
            "adm1_estimation": len(design_state.adm1_state) > 0,
            "heuristic_sizing": len(design_state.heuristic_config) > 0,
            "simulation": len(design_state.simulation_results) > 0,
            "economic_analysis": len(design_state.economic_results) > 0
        }
        
        # Calculate overall progress
        completed = sum(1 for v in completion_status.values() if v)
        total = len(completion_status)
        progress = f"{int(100 * completed / total)}%"
        
        # Get next steps
        next_steps = get_next_steps(completion_status)
        
        return {
            "status": "success",
            **design_state.to_dict(),
            "completion_status": completion_status,
            "overall_progress": progress,
            "next_steps": next_steps
        }
        
    except Exception as e:
        logger.error(f"Error in get_design_state: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to retrieve design state: {str(e)}"
        }


async def reset_design() -> Dict[str, Any]:
    """
    Reset the anaerobic digester design state.
    
    Clears all stored parameters and results to start a new design session.
    
    Returns:
        Confirmation of reset operation
    """
    try:
        design_state.reset()
        
        return {
            "status": "success",
            "message": "Design state has been reset",
            "state": design_state.to_dict()
        }
        
    except Exception as e:
        logger.error(f"Error in reset_design: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to reset design state: {str(e)}"
        }


def get_next_steps(completion_status: Dict[str, bool]) -> List[str]:
    """Determine next steps based on completion status."""
    next_steps = []
    
    if not completion_status["basis_of_design"]:
        next_steps.append("Use elicit_basis_of_design to collect design parameters")
    elif not completion_status["adm1_estimation"]:
        next_steps.append("Characterize feedstock to estimate ADM1 state variables")
    elif not completion_status["heuristic_sizing"]:
        next_steps.append("Use heuristic_sizing_ad to size the digester")
    elif not completion_status["simulation"]:
        next_steps.append("Use simulate_ad_system_tool to run WaterTAP simulation")
    elif not completion_status["economic_analysis"]:
        next_steps.append("Economic analysis pending")
    else:
        next_steps.append("Design complete! Review results with get_design_state")
    
    return next_steps