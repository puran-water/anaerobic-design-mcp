#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Anaerobic Digester Design MCP Server

A modular MCP server for anaerobic digester design using ADM1+sulfur model.
Provides tools for:
- Parameter elicitation and feedstock characterization (via Codex MCP)
- ADM1 state validation (ion balance, bulk composites, precipitation risk)
- Heuristic sizing (digesters, MBR, auxiliary equipment)
- QSDsan dynamic simulation with ADM1+sulfur (30 components)
- Sulfur analysis and H2S treatment evaluation
"""

import os
import sys
import logging
from pathlib import Path

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
from utils.qsdsan_loader import get_qsdsan_components
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastMCP lifespan: DISABLED - Background loading causes file I/O contention
# The asyncio.create_task() for QSDsan loading interferes with file operations
# in validation tools, causing intermittent 90+ second hangs
@asynccontextmanager
async def lifespan(server):
    """Lifespan context manager (currently disabled to avoid I/O contention)."""
    # import asyncio
    # logger.info("Scheduling QSDsan component warmup as background task...")
    # asyncio.create_task(get_qsdsan_components())

    logger.info("FastMCP lifespan started (background QSDsan loading DISABLED)")
    yield
    # No cleanup needed

# Create FastMCP instance with lifespan
mcp = FastMCP("Anaerobic Digester Design Server", lifespan=lifespan)

# ==============================================================================
# LAZY IMPORTS: Tools are imported only when called to speed up server startup
# Heavy dependencies (QSDsan, thermosteam) take ~23 seconds to import
# ==============================================================================

# Core workflow tools (registered with lazy imports)
@mcp.tool()
async def elicit_basis_of_design(parameter_group: str = "essential", current_values: dict = None):
    """
    Collect basis of design parameters for anaerobic digester sizing.

    Args:
        parameter_group: "essential", "solids", "nutrients", "alkalinity", or "all"
        current_values: Dictionary of parameter values to use
    """
    from tools.basis_of_design import elicit_basis_of_design as _impl
    return await _impl(parameter_group, current_values)

@mcp.tool()
async def get_design_state():
    """Get current design state with completion status and next steps."""
    from tools.state_management import get_design_state as _impl
    return await _impl()

@mcp.tool()
async def reset_design():
    """Reset design state to start a new project."""
    from tools.state_management import reset_design as _impl
    return await _impl()

@mcp.tool()
async def load_adm1_state(file_path: str = "./adm1_state.json"):
    """
    Load ADM1 state from JSON file into design_state.

    Args:
        file_path: Path to JSON file with ADM1 state (default: ./adm1_state.json)

    Returns:
        Status and number of components loaded
    """
    import json
    from core.state import design_state

    try:
        with open(file_path, 'r') as f:
            adm1_data = json.load(f)

        design_state.adm1_state = adm1_data
        return {
            "status": "success",
            "components_loaded": len(adm1_data),
            "message": f"Loaded {len(adm1_data)} ADM1 components from {file_path}"
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to load ADM1 state: {str(e)}"}

@mcp.tool()
async def validate_adm1_state(user_parameters: dict, tolerance: float = 0.10, use_current_adm1: bool = True):
    """
    Validate ADM1 state variables against measured bulk composites.

    Computes COD, TSS, VSS, TKN, TP from ADM1 components and compares
    to target values (if provided).

    Args:
        user_parameters: Target values (cod_mg_l, tss_mg_l, vss_mg_l, tkn_mg_l, tp_mg_l, ph)
        tolerance: Relative tolerance for validation (default 0.10 = 10%)
        use_current_adm1: Use ADM1 state from design_state (default True)
    """
    from tools.validation import validate_adm1_state as _impl
    from core.state import design_state

    if use_current_adm1:
        adm1_state = design_state.adm1_state
        if not adm1_state:
            return {"status": "error", "message": "No ADM1 state in design_state. Run characterization first."}
    else:
        return {"status": "error", "message": "Must set use_current_adm1=True or provide adm1_state directly"}

    return await _impl(adm1_state, user_parameters, tolerance)

@mcp.tool()
async def compute_bulk_composites(temperature_c: float = 35.0, use_current_adm1: bool = True):
    """
    Compute bulk composites (COD, TSS, VSS, TKN, TP) from ADM1 state.

    Useful for converting ADM1 component concentrations to standard
    wastewater characterization parameters.

    Args:
        temperature_c: Temperature in Celsius (default 35°C)
        use_current_adm1: Use ADM1 state from design_state (default True)
    """
    from tools.validation import compute_bulk_composites as _impl
    from core.state import design_state

    if use_current_adm1:
        adm1_state = design_state.adm1_state
        if not adm1_state:
            return {"status": "error", "message": "No ADM1 state in design_state"}
    else:
        return {"status": "error", "message": "Must set use_current_adm1=True"}

    return await _impl(adm1_state, temperature_c)

@mcp.tool()
async def check_strong_ion_balance(ph: float = 7.0, max_imbalance_percent: float = 5.0, use_current_adm1: bool = True):
    """
    Check cation/anion balance for electroneutrality consistency with pH.

    Verifies that S_cat/S_an are properly set to balance the system.

    Args:
        ph: Target pH for electroneutrality check (default 7.0)
        max_imbalance_percent: Maximum acceptable imbalance (default 5%)
        use_current_adm1: Use ADM1 state from design_state (default True)
    """
    from tools.validation import check_strong_ion_balance as _impl
    from core.state import design_state

    if use_current_adm1:
        adm1_state = design_state.adm1_state
        if not adm1_state:
            return {"status": "error", "message": "No ADM1 state in design_state"}
    else:
        return {"status": "error", "message": "Must set use_current_adm1=True"}

    return await _impl(adm1_state, ph, max_imbalance_percent)

@mcp.tool()
async def heuristic_sizing_ad(
    biomass_yield: float = None,
    target_srt_days: float = None,
    use_current_basis: bool = True,
    custom_basis: dict = None
):
    """
    Perform heuristic sizing for anaerobic digester and auxiliary equipment.

    Sizes digester, MBR (if required), and estimates biogas production.
    """
    from tools.sizing import heuristic_sizing_ad as _impl
    return await _impl(biomass_yield, target_srt_days, use_current_basis, custom_basis)

@mcp.tool()
async def simulate_ad_system_tool(
    use_current_state: bool = True,
    validate_hrt: bool = True,
    hrt_variation: float = 0.2,
    costing_method: str = None,
    custom_inputs: dict = None
):
    """
    Run QSDsan dynamic simulation with ADM1+sulfur model (30 components).

    Returns comprehensive results including:
    - Stream analysis (influent, effluent, biogas)
    - Performance metrics (yields, inhibition)
    - Sulfur analysis (mass balance, speciation, H2S in biogas)
    - HRT validation (if validate_hrt=True)
    """
    from tools.simulation import simulate_ad_system_tool as _impl
    return await _impl(use_current_state, validate_hrt, hrt_variation, costing_method, custom_inputs)


def main():
    """Run the MCP server."""
    logger.info("="*60)
    logger.info("Anaerobic Digester Design MCP Server")
    logger.info("="*60)
    logger.info("")
    logger.info("Registered tools (9 total):")
    logger.info("  1. elicit_basis_of_design - Collect design parameters")
    logger.info("  2. load_adm1_state - Load ADM1 state from JSON file")
    logger.info("  3. validate_adm1_state - Validate ADM1 state against composites")
    logger.info("  4. compute_bulk_composites - Compute COD/TSS/VSS/TKN/TP from ADM1")
    logger.info("  5. check_strong_ion_balance - Check cation/anion electroneutrality")
    logger.info("  6. heuristic_sizing_ad - Size digester and auxiliary equipment")
    logger.info("  7. simulate_ad_system_tool - Run QSDsan ADM1+sulfur simulation")
    logger.info("  8. get_design_state - View current design state and next steps")
    logger.info("  9. reset_design - Reset design state for new project")
    logger.info("")
    logger.info("Note: Simulation output includes comprehensive stream analysis,")
    logger.info("      process health metrics, and sulfur balance data.")
    logger.info("")
    logger.info("Starting server...")
    logger.info("QSDsan loading DISABLED in lifespan to avoid file I/O contention")
    logger.info("Components will lazy-load on first simulation call (~18s)")
    logger.info("="*60)

    mcp.run()


if __name__ == "__main__":
    main()