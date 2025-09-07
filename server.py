#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Anaerobic Digester Design MCP Server

A modular MCP server for anaerobic digester design.
Provides tools for parameter elicitation, heuristic sizing, 
WaterTAP simulation, and economic analysis.
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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import tool implementations
from tools.basis_of_design import elicit_basis_of_design
from tools.state_management import get_design_state, reset_design
from tools.validation import (
    validate_adm1_state,
    compute_bulk_composites,
    check_strong_ion_balance
)
from tools.sizing import heuristic_sizing_ad
from tools.simulation import simulate_ad_system_tool

# Create FastMCP instance
mcp = FastMCP("Anaerobic Digester Design Server")

# Register tools
mcp.tool()(elicit_basis_of_design)
mcp.tool()(get_design_state)
mcp.tool()(reset_design)
mcp.tool()(validate_adm1_state)
mcp.tool()(compute_bulk_composites)
mcp.tool()(check_strong_ion_balance)
mcp.tool()(heuristic_sizing_ad)
mcp.tool()(simulate_ad_system_tool)


def main():
    """Run the MCP server."""
    logger.info("="*60)
    logger.info("Anaerobic Digester Design MCP Server")
    logger.info("="*60)
    logger.info("")
    logger.info("Available tools:")
    logger.info("  - elicit_basis_of_design: Collect design parameters")
    logger.info("  - validate_adm1_state: Validate ADM1 state against composites")
    logger.info("  - compute_bulk_composites: Compute COD/TSS/VSS/TKN/TP from ADM1 state")
    logger.info("  - check_strong_ion_balance: Check cation/anion balance consistency vs pH")
    logger.info("  - heuristic_sizing_ad: Perform heuristic sizing")
    logger.info("  - simulate_ad_system_tool: Run WaterTAP simulation")
    logger.info("  - get_design_state: View current design state")
    logger.info("  - reset_design: Reset design state")
    logger.info("")
    logger.info("Starting server...")
    logger.info("="*60)
    
    mcp.run()


if __name__ == "__main__":
    main()