#!/usr/bin/env python3
"""
Minimal MCP server for ADM1 validation tools.
Isolated from main server to prevent tool exposure.
"""

from fastmcp import FastMCP
import logging
from typing import Dict, Any
from utils.adm1_validation import (
    compute_bulk_composites,
    calculate_strong_ion_residual
)
from utils.state_utils import clean_adm1_state

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create minimal server
mcp = FastMCP("ADM1 Validation Server")

@mcp.tool()
async def validate_bulk_composites(
    adm1_state: Dict[str, Any]
) -> Dict[str, float]:
    """
    Compute COD, TSS, VSS, TKN, TP from ADM1 state variables.
    Returns concentrations in mg/L.
    
    Args:
        adm1_state: Dictionary of ADM1 component concentrations
                   Can be in format {"S_su": value} or {"S_su": [value, unit, explanation]}
    
    Returns:
        Dictionary with:
        - cod_mg_l: Total COD in mg/L
        - tss_mg_l: Total suspended solids in mg/L
        - vss_mg_l: Volatile suspended solids in mg/L
        - tkn_mg_l: Total Kjeldahl nitrogen in mg/L
        - tp_mg_l: Total phosphorus in mg/L
    """
    try:
        clean_state, warnings = clean_adm1_state(adm1_state)
        if warnings:
            logger.warning(f"State cleaning warnings: {warnings}")
        return compute_bulk_composites(clean_state)
    except Exception as e:
        logger.error(f"Error computing bulk composites: {e}")
        return {"error": str(e)}

@mcp.tool()
async def validate_ion_balance(
    adm1_state: Dict[str, Any],
    ph: float = 7.0,
    mode: str = "watertap"
) -> Dict[str, Any]:
    """
    Check electroneutrality with proper speciation.
    S_cat/S_an are treated as OTHER ions only (not including K+, Mg2+, NH4+, VFAs, etc.).
    
    Args:
        adm1_state: ADM1 component concentrations
        ph: pH value (default 7.0)
        mode: "watertap" (match S_H_cons, no CO3--) or "general" (include CO3--)
    
    Returns:
        Detailed ion balance including:
        - cations: Breakdown of all cation contributions (mol/m³)
        - anions: Breakdown of all anion contributions (mol/m³)
        - residual_meq_l: Charge imbalance in meq/L
        - imbalance_percent: Percentage imbalance
        - balanced: True if imbalance < 5%
        - suggestion: How to correct the imbalance
        - message: Summary message
    """
    try:
        clean_state, warnings = clean_adm1_state(adm1_state)
        if warnings:
            logger.warning(f"State cleaning warnings: {warnings}")
        
        result = calculate_strong_ion_residual(clean_state, ph, mode)
        
        # Add summary message
        if result["balanced"]:
            result["message"] = f"Ion balance OK ({result['imbalance_percent']:.1f}% imbalance)"
        else:
            result["message"] = f"Ion imbalance: {result['imbalance_percent']:.1f}%. {result['suggestion']}"
        
        # Log detailed breakdown for debugging
        logger.info(f"Ion balance at pH {ph}:")
        logger.info(f"  Cations: {result['cations']['total']:.1f} mol/m³")
        logger.info(f"  Anions: {result['anions']['total']:.1f} mol/m³")
        logger.info(f"  Residual: {result['residual_meq_l']:.1f} meq/L")
        
        return result
    except Exception as e:
        logger.error(f"Error checking ion balance: {e}")
        return {"error": str(e), "balanced": False, "message": f"Error: {e}"}

# Add a convenience tool for Codex to use
@mcp.tool()
async def validate_adm1_complete(
    adm1_state: Dict[str, Any],
    ph: float = 7.0,
    target_cod_mg_l: float = None,
    target_tss_mg_l: float = None
) -> Dict[str, Any]:
    """
    Complete validation of ADM1 state including bulk composites and ion balance.
    
    Args:
        adm1_state: ADM1 component concentrations
        ph: pH value
        target_cod_mg_l: Expected COD (for comparison)
        target_tss_mg_l: Expected TSS (for comparison)
    
    Returns:
        Combined validation results with deviations from targets
    """
    try:
        # Get bulk composites
        composites = await validate_bulk_composites(adm1_state)
        
        # Get ion balance
        ion_balance = await validate_ion_balance(adm1_state, ph)
        
        # Calculate deviations if targets provided
        deviations = {}
        if target_cod_mg_l:
            cod_dev = 100 * (composites.get("cod_mg_l", 0) - target_cod_mg_l) / target_cod_mg_l
            deviations["cod_percent"] = cod_dev
        
        if target_tss_mg_l:
            tss_dev = 100 * (composites.get("tss_mg_l", 0) - target_tss_mg_l) / target_tss_mg_l
            deviations["tss_percent"] = tss_dev
        
        return {
            "composites": composites,
            "ion_balance": ion_balance,
            "deviations": deviations,
            "overall_valid": ion_balance.get("balanced", False) and 
                           all(abs(v) < 10 for v in deviations.values())
        }
    except Exception as e:
        logger.error(f"Error in complete validation: {e}")
        return {"error": str(e), "overall_valid": False}

if __name__ == "__main__":
    logger.info("Starting ADM1 Validation Server...")
    logger.info("Available tools:")
    logger.info("  - validate_bulk_composites: Compute COD/TSS/VSS/TKN/TP")
    logger.info("  - validate_ion_balance: Check electroneutrality")
    logger.info("  - validate_adm1_complete: Full validation suite")
    mcp.run()