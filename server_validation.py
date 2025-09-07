#!/usr/bin/env python3
"""
Minimal MCP server for ADM1 validation tools.
Isolated from main server for use by Codex ADM1 Estimator.
"""

import os
import sys
import logging
from typing import Dict, Any, Optional

# Set required environment variables
if 'LOCALAPPDATA' not in os.environ:
    if sys.platform == 'win32':
        os.environ['LOCALAPPDATA'] = os.path.join(os.path.expanduser('~'), 'AppData', 'Local')
    else:
        os.environ['LOCALAPPDATA'] = os.path.join(os.path.expanduser('~'), '.local')

# Set Jupyter platform dirs to avoid warnings
if 'JUPYTER_PLATFORM_DIRS' not in os.environ:
    os.environ['JUPYTER_PLATFORM_DIRS'] = '1'

from fastmcp import FastMCP
from utils.adm1_validation import (
    compute_bulk_composites,
    calculate_strong_ion_residual
)
from core.utils import coerce_to_dict, to_float

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create minimal server
mcp = FastMCP("ADM1 Validation Server")


def clean_adm1_state(adm1_state: Dict[str, Any]) -> Dict[str, float]:
    """
    Clean ADM1 state by extracting numeric values from various formats.
    
    Args:
        adm1_state: Raw state dictionary (can have [value, unit, note] format)
    
    Returns:
        Cleaned state with only numeric values
    """
    cleaned = {}
    for key, value in adm1_state.items():
        if isinstance(value, (list, tuple)) and len(value) > 0:
            # Extract first element from [value, unit, explanation] format
            cleaned[key] = to_float(value[0]) or 0.0
        else:
            cleaned[key] = to_float(value) or 0.0
    return cleaned


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
        # Clean the state
        clean_state = clean_adm1_state(adm1_state)
        
        # Compute composites
        composites = compute_bulk_composites(clean_state)
        
        return {
            "cod_mg_l": composites.get("cod_mg_l", 0.0),
            "tss_mg_l": composites.get("tss_mg_l", 0.0),
            "vss_mg_l": composites.get("vss_mg_l", 0.0),
            "tkn_mg_l": composites.get("tkn_mg_l", 0.0),
            "tp_mg_l": composites.get("tp_mg_l", 0.0)
        }
    except Exception as e:
        logger.error(f"Error computing bulk composites: {e}")
        return {
            "error": str(e),
            "cod_mg_l": 0.0,
            "tss_mg_l": 0.0,
            "vss_mg_l": 0.0,
            "tkn_mg_l": 0.0,
            "tp_mg_l": 0.0
        }


@mcp.tool()
async def validate_ion_balance(
    adm1_state: Dict[str, Any],
    ph: float = 7.0
) -> Dict[str, Any]:
    """
    Check electroneutrality with proper speciation.
    S_cat/S_an are treated as OTHER ions only (not including K+, Mg2+, NH4+, VFAs, etc.).
    
    Args:
        adm1_state: ADM1 state variables dictionary
        ph: pH for speciation calculations
    
    Returns:
        Dictionary with:
        - balanced: Boolean indicating if charge balance is within 5%
        - imbalance_percent: Percentage imbalance
        - residual_meq_l: Charge residual in meq/L
        - cations: Detailed cation breakdown
        - anions: Detailed anion breakdown
        - suggestion: Adjustment suggestion if unbalanced
    """
    try:
        # Clean the state
        clean_state = clean_adm1_state(adm1_state)
        
        # Calculate ion balance
        result = calculate_strong_ion_residual(clean_state, ph)
        
        return {
            "balanced": result.get("balanced", False),
            "imbalance_percent": result.get("imbalance_percent", 0.0),
            "residual_meq_l": result.get("residual_meq_l", 0.0),
            "cations": result.get("cations", {}),
            "anions": result.get("anions", {}),
            "suggestion": result.get("suggestion", "")
        }
    except Exception as e:
        logger.error(f"Error checking ion balance: {e}")
        return {
            "error": str(e),
            "balanced": False,
            "imbalance_percent": 100.0,
            "residual_meq_l": 0.0,
            "cations": {},
            "anions": {},
            "suggestion": "Error in calculation"
        }


def main():
    """Run the validation MCP server."""
    logger.info("="*60)
    logger.info("ADM1 Validation MCP Server")
    logger.info("="*60)
    logger.info("")
    logger.info("Available tools:")
    logger.info("  - validate_bulk_composites: Compute COD/TSS/VSS/TKN/TP from ADM1 state")
    logger.info("  - validate_ion_balance: Check electroneutrality and charge balance")
    logger.info("")
    logger.info("This server is used by the Codex ADM1 Estimator for validation.")
    logger.info("Starting server...")
    logger.info("="*60)
    
    mcp.run()


if __name__ == "__main__":
    main()