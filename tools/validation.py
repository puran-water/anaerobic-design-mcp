"""Validation tools for ADM1 state variables."""

import logging
from typing import Dict, Any, Optional
from core.state import design_state
from core.utils import coerce_to_dict, to_float

# Always use WaterTAP validation
from utils.watertap_validation import (
    validate_adm1_state_with_watertap,
    calculate_composites_with_watertap,
    enforce_electroneutrality
)
from utils.adm1_validation import calculate_strong_ion_residual

logger = logging.getLogger(__name__)
logger.info("Using WaterTAP-based validation")


async def validate_adm1_state(
    adm1_state: Dict[str, Any],
    user_parameters: Dict[str, float],
    tolerance: float = 0.10,
    force_store: bool = False,
    enforce_electroneutrality: bool = True  # NEW parameter
) -> Dict[str, Any]:
    """
    Validate ADM1 state variables against composite parameters.
    
    Args:
        adm1_state: Dictionary of ADM1 component concentrations
        user_parameters: Dictionary with measured values
        tolerance: Relative tolerance for validation (default 10%)
        force_store: If True, store ADM1 state even if validation fails
        enforce_electroneutrality: If True, auto-adjust S_cat/S_an for charge balance
    
    Returns:
        Dictionary containing validation results and deviations
    """
    try:
        # Normalize inputs
        adm1_state = coerce_to_dict(adm1_state) or {}
        
        # Clean ADM1 state - handle [value, unit, description] format
        clean_state = {}
        for key, value in adm1_state.items():
            if isinstance(value, list) and len(value) > 0:
                clean_state[key] = to_float(value[0])
            else:
                clean_state[key] = to_float(value)
        
        # Use WaterTAP validation
        validation_result = validate_adm1_state_with_watertap(
            adm1_state=clean_state,
            user_parameters=user_parameters,
            tolerance=tolerance,
            enforce_balance=enforce_electroneutrality
        )
        # Extract the adjusted state if electroneutrality was enforced
        if enforce_electroneutrality and validation_result.get("electroneutrality_adjustment", {}).get("adjusted"):
            # Update clean_state with the adjustment
            adj_info = validation_result["electroneutrality_adjustment"]
            clean_state[adj_info["component_adjusted"]] = adj_info["new_value"]
        
        # Store in design state if valid or forced
        if validation_result["valid"] or force_store:
            design_state.adm1_state = clean_state
            stored = True
        else:
            stored = False
            
        # Create message based on validation result
        if validation_result["valid"]:
            message = "ADM1 state validation PASSED - all parameters within tolerance"
        else:
            message = f"ADM1 state validation FAILED - {len(validation_result.get('warnings', []))} warnings"
        
        # Add electroneutrality adjustment info to message if applicable
        if validation_result.get("electroneutrality_adjustment", {}).get("adjusted"):
            adj_info = validation_result["electroneutrality_adjustment"]
            message += f". {adj_info['message']}"
        
        return {
            "status": "success",
            "valid": validation_result["valid"],
            "calculated_parameters": validation_result["calculated_parameters"],
            "user_parameters": user_parameters,
            "deviations": validation_result["deviations"],
            "warnings": validation_result.get("warnings", []),
            "pass_fail": validation_result["pass_fail"],
            "stored": stored,
            "message": message,
            "electroneutrality_adjustment": validation_result.get("electroneutrality_adjustment", {})
        }
        
    except Exception as e:
        logger.error(f"Error in validate_adm1_state: {str(e)}")
        return {
            "status": "error",
            "message": f"Validation failed: {str(e)}"
        }


async def compute_bulk_composites(
    adm1_state: Dict[str, Any],
    temperature_c: float = 35.0
) -> Dict[str, Any]:
    """
    Compute COD, TSS, VSS, TKN, TP (mg/L) from an ADM1 state.
    
    Args:
        adm1_state: ADM1 state dict (accepts [value, unit, note] entries)
        temperature_c: Temperature in Celsius (default 35°C)
    
    Returns:
        Calculated composite values
    """
    try:
        adm1_state = coerce_to_dict(adm1_state) or {}
        
        # Clean state
        clean_state = {}
        for key, value in adm1_state.items():
            if isinstance(value, list) and len(value) > 0:
                clean_state[key] = to_float(value[0])
            else:
                clean_state[key] = to_float(value)
        
        # Use WaterTAP
        temperature_k = 273.15 + temperature_c
        comps = calculate_composites_with_watertap(clean_state, temperature_k)
        
        return {"status": "success", "composites_mg_l": comps}
    except Exception as e:
        logger.error(f"Error in compute_bulk_composites: {e}")
        return {"status": "error", "message": str(e)}


async def check_strong_ion_balance(
    adm1_state: Dict[str, Any],
    ph: float = 7.0,
    max_imbalance_percent: float = 5.0,
    auto_fix: bool = False
) -> Dict[str, Any]:
    """
    Check strong-ion charge balance consistency vs pH.
    
    Args:
        adm1_state: ADM1 state dict
        ph: pH to use for acid-base speciation
        max_imbalance_percent: Threshold for pass/fail
        auto_fix: If True, return corrected state with electroneutrality
    
    Returns:
        Status, residual metrics, pass/fail recommendation
    """
    try:
        adm1_state = coerce_to_dict(adm1_state) or {}
        
        # Clean state
        clean_state = {}
        for key, value in adm1_state.items():
            if isinstance(value, list) and len(value) > 0:
                clean_state[key] = to_float(value[0])
            else:
                clean_state[key] = to_float(value)
        
        if auto_fix:
            # Use WaterTAP's electroneutrality enforcement
            corrected_state, adjustment_info = enforce_electroneutrality(
                clean_state, target_ph=ph
            )
            
            # Still calculate the balance for reporting
            result = calculate_strong_ion_residual(corrected_state, ph)
            
            return {
                "status": "success",
                "residual_meq_l": result["residual_meq_l"],
                "total_cations_meq_l": result["cations"]["total"],
                "total_anions_meq_l": result["anions"]["total"],
                "imbalance_percent": result["imbalance_percent"],
                "balanced": result["balanced"],
                "cations": result["cations"],
                "anions": result["anions"],
                "suggestion": result.get("suggestion", ""),
                "message": f"Charge imbalance: {result['imbalance_percent']:.1f}% ({'PASS' if result['balanced'] else 'FAIL'})",
                "corrected_state": corrected_state if auto_fix else None,
                "adjustment_info": adjustment_info if auto_fix else None
            }
        else:
            # Use existing calculation
            result = calculate_strong_ion_residual(clean_state, ph)
            
            # The function already returns all needed fields
            return {
                "status": "success",
                "residual_meq_l": result["residual_meq_l"],
                "total_cations_meq_l": result["cations"]["total"],
                "total_anions_meq_l": result["anions"]["total"],
                "imbalance_percent": result["imbalance_percent"],
                "balanced": result["balanced"],
                "cations": result["cations"],
                "anions": result["anions"],
                "suggestion": result.get("suggestion", ""),
                "message": f"Charge imbalance: {result['imbalance_percent']:.1f}% ({'PASS' if result['balanced'] else 'FAIL'})"
            }
    except Exception as e:
        logger.error(f"Error in check_strong_ion_balance: {e}")
        return {"status": "error", "message": str(e)}