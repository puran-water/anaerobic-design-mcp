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

# Configure logging BEFORE any code that uses logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# CRITICAL FIX: Patch MCP STDIO buffer size to prevent WSL2 blocking issue
# Issue: modelcontextprotocol/python-sdk#262, #1333, #1141
# Root cause: max_buffer_size=0 in mcp.server.stdio causes synchronous blocking on WSL2/Linux
# Fix: Replace stdio_server entirely with buffered version (max_buffer_size=256)
#
# ANALYSIS (from Codex 2025-11-02):
# Previous patch only buffered between FastMCP and SDK, but the real bottleneck is INSIDE
# the SDK's stdio transport where anyio.create_memory_object_stream(0) creates synchronous,
# zero-capacity streams. This deeper patch replaces the SDK's stdio_server function itself.
from contextlib import asynccontextmanager
import sys
from io import TextIOWrapper
import anyio
import anyio.lowlevel
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

try:
    import mcp.types as types
    from mcp.shared.message import SessionMessage
    import mcp.server.stdio as mcp_stdio
    import fastmcp.server.server as fastmcp_server

    @asynccontextmanager
    async def buffered_stdio_server(
        stdin: anyio.AsyncFile[str] | None = None,
        stdout: anyio.AsyncFile[str] | None = None,
        max_buffer_size: int = 256  # CRITICAL: Use 256 instead of 0
    ):
        """
        PATCHED stdio_server with buffered memory streams.

        This is a complete replacement of mcp.server.stdio.stdio_server that uses
        max_buffer_size=256 instead of 0 to prevent synchronous blocking on WSL2/Linux.

        Based on mcp.server.stdio.stdio_server from modelcontextprotocol/python-sdk
        with ONLY the buffer size changed from 0 to 256 on lines 57-58.
        """
        # Purposely not using context managers for these, as we don't want to close
        # standard process handles. Encoding of stdin/stdout as text streams on
        # python is platform-dependent (Windows is particularly problematic), so we
        # re-wrap the underlying binary stream to ensure UTF-8.
        if not stdin:
            stdin = anyio.wrap_file(TextIOWrapper(sys.stdin.buffer, encoding="utf-8"))
        if not stdout:
            stdout = anyio.wrap_file(TextIOWrapper(sys.stdout.buffer, encoding="utf-8"))

        read_stream: MemoryObjectReceiveStream[SessionMessage | Exception]
        read_stream_writer: MemoryObjectSendStream[SessionMessage | Exception]

        write_stream: MemoryObjectSendStream[SessionMessage]
        write_stream_reader: MemoryObjectReceiveStream[SessionMessage]

        # CRITICAL FIX: Change from max_buffer_size=0 to max_buffer_size=256
        read_stream_writer, read_stream = anyio.create_memory_object_stream(max_buffer_size)
        write_stream, write_stream_reader = anyio.create_memory_object_stream(max_buffer_size)

        async def stdin_reader():
            try:
                async with read_stream_writer:
                    async for line in stdin:
                        try:
                            message = types.JSONRPCMessage.model_validate_json(line)
                        except Exception as exc:
                            await read_stream_writer.send(exc)
                            continue

                        session_message = SessionMessage(message)
                        await read_stream_writer.send(session_message)
            except anyio.ClosedResourceError:
                await anyio.lowlevel.checkpoint()

        async def stdout_writer():
            try:
                async with write_stream_reader:
                    async for session_message in write_stream_reader:
                        json = session_message.message.model_dump_json(by_alias=True, exclude_none=True)
                        await stdout.write(json + "\n")
                        await stdout.flush()
            except anyio.ClosedResourceError:
                await anyio.lowlevel.checkpoint()

        async with anyio.create_task_group() as tg:
            tg.start_soon(stdin_reader)
            tg.start_soon(stdout_writer)
            yield read_stream, write_stream

    # Apply deep monkey-patch: Replace SDK's stdio_server entirely
    mcp_stdio.stdio_server = buffered_stdio_server
    fastmcp_server.stdio_server = buffered_stdio_server

    # SECOND BLOCKING POINT: Patch ServerSession to use buffered incoming message stream
    # Root cause (from Codex 2025-11-02): ServerSession.__init__ creates zero-capacity queue
    # at mcp/server/session.py:96-98 which causes backpressure even with buffered stdio
    from mcp.server.session import ServerSession
    import mcp.types as mcp_types

    _original_server_session_init = ServerSession.__init__

    def buffered_server_session_init(self, read_stream, write_stream, init_options=None, stateless=False):
        """Patched ServerSession.__init__ with buffered incoming message stream."""
        # Call original __init__ but it will create zero-capacity stream
        _original_server_session_init(self, read_stream, write_stream, init_options, stateless)

        # CRITICAL FIX: Replace the zero-capacity stream with buffered version
        # Close the zero-capacity stream created by original __init__
        import anyio

        # Recreate with buffer size 256
        self._incoming_message_stream_writer, self._incoming_message_stream_reader = (
            anyio.create_memory_object_stream(256)
        )

        # Re-register the close callback (original __init__ already registered it)
        # Note: exit_stack already has the callback, so we don't duplicate it

    ServerSession.__init__ = buffered_server_session_init

    logger.info("Applied DEEP STDIO buffer patch (max_buffer_size=256) to fix WSL2 blocking issue")
    logger.info("Patched: mcp.server.stdio.stdio_server (stdio transport layer)")
    logger.info("Patched: mcp.server.session.ServerSession (incoming message queue)")

except ImportError as e:
    logger.warning(f"Could not apply STDIO buffer patch: {e}")

from fastmcp import FastMCP
from utils.qsdsan_loader import get_qsdsan_components

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

    Returns job_id immediately. Use get_job_status() to check progress and get_job_results() to retrieve results.

    IMPORTANT: This tool now runs in background. Do NOT wait for results - use get_job_status(job_id) instead.
    """
    from utils.job_manager import JobManager
    from core.state import design_state
    import sys
    import json

    if use_current_adm1:
        adm1_state = design_state.adm1_state
        if not adm1_state:
            return {"status": "error", "message": "No ADM1 state in design_state. Run characterization first."}
    else:
        return {"status": "error", "message": "Must set use_current_adm1=True or provide adm1_state directly"}

    # Build command for validate_cli.py
    cmd = [
        sys.executable,
        "utils/validate_cli.py",
        "--output-dir", "jobs/{job_id}",  # Must come before subcommand
        "validate",
        "--adm1-state", "adm1_state.json",
        "--user-params", json.dumps(user_parameters),
        "--tolerance", str(tolerance),
    ]

    # Execute in background
    manager = JobManager()
    job = await manager.execute(cmd=cmd, cwd=".")

    return {
        "job_id": job["id"],
        "status": job["status"],
        "message": "Validation job started. Use get_job_status() to monitor progress.",
        "command": " ".join(cmd[:3]) + " ...",
        "next_steps": [
            f"Check status: get_job_status('{job['id']}')",
            f"Get results: get_job_results('{job['id']}')"
        ]
    }

@mcp.tool()
async def compute_bulk_composites(temperature_c: float = 35.0, use_current_adm1: bool = True):
    """
    Compute bulk composites (COD, TSS, VSS, TKN, TP) from ADM1 state.

    Useful for converting ADM1 component concentrations to standard
    wastewater characterization parameters.

    Args:
        temperature_c: Temperature in Celsius (default 35°C)
        use_current_adm1: Use ADM1 state from design_state (default True)

    Returns job_id immediately. Use get_job_status() to check progress and get_job_results() to retrieve results.

    IMPORTANT: This tool now runs in background. Do NOT wait for results - use get_job_status(job_id) instead.
    """
    from utils.job_manager import JobManager
    from core.state import design_state
    import sys

    if use_current_adm1:
        adm1_state = design_state.adm1_state
        if not adm1_state:
            return {"status": "error", "message": "No ADM1 state in design_state"}
    else:
        return {"status": "error", "message": "Must set use_current_adm1=True"}

    # Build command for validate_cli.py composites subcommand
    cmd = [
        sys.executable,
        "utils/validate_cli.py",
        "--output-dir", "jobs/{job_id}",  # Must come before subcommand
        "composites",
        "--adm1-state", "adm1_state.json",
        "--temperature-c", str(temperature_c),
    ]

    # Execute in background
    manager = JobManager()
    job = await manager.execute(cmd=cmd, cwd=".")

    return {
        "job_id": job["id"],
        "status": job["status"],
        "message": "Bulk composites calculation job started. Use get_job_status() to monitor progress.",
        "command": " ".join(cmd[:3]) + " ...",
        "next_steps": [
            f"Check status: get_job_status('{job['id']}')",
            f"Get results: get_job_results('{job['id']}')"
        ]
    }

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
    custom_basis: dict = None,
    # Tank material and geometry
    tank_material: str = "concrete",
    height_to_diameter_ratio: float = 1.2,
    # Mixing configuration
    mixing_type: str = "mechanical",
    mixing_power_target_w_m3: float = None,
    impeller_type: str = "pitched_blade_turbine",
    pumped_recirculation_turnovers_per_hour: float = 3.0,
    # Biogas handling
    biogas_application: str = "storage",
    biogas_discharge_pressure_kpa: float = None,
    # Thermal analysis
    calculate_thermal_load: bool = True,
    feedstock_inlet_temp_c: float = 10.0,
    insulation_R_value_si: float = 1.76
):
    """
    Perform heuristic sizing for anaerobic digester with integrated mixing, biogas, and thermal analysis.

    Sizes digester, calculates tank dimensions, mixing power, biogas blower sizing, and thermal loads.
    Determines flowsheet configuration (high TSS with dewatering vs. low TSS with MBR).

    Returns job_id immediately. Use get_job_status() to check progress and get_job_results() to retrieve results.

    IMPORTANT: This tool now runs in background. Do NOT wait for results - use get_job_status(job_id) instead.
    """
    from utils.job_manager import JobManager
    import sys

    # Build command for CLI wrapper
    cmd = [
        sys.executable,  # Use same Python interpreter as server
        "utils/heuristic_sizing_cli.py",
        "--output-dir", "jobs/{job_id}",  # {job_id} will be replaced by JobManager
    ]

    # Add optional parameters
    if target_srt_days is not None:
        cmd.extend(["--target-srt", str(target_srt_days)])
    if mixing_type:
        cmd.extend(["--mixing-type", mixing_type])
    if biogas_application:
        cmd.extend(["--biogas-application", biogas_application])
    if height_to_diameter_ratio is not None:
        cmd.extend(["--height-to-diameter-ratio", str(height_to_diameter_ratio)])
    if tank_material:
        cmd.extend(["--tank-material", tank_material])
    if mixing_power_target_w_m3 is not None:
        cmd.extend(["--mixing-power-target", str(mixing_power_target_w_m3)])
    if impeller_type:
        cmd.extend(["--impeller-type", impeller_type])
    if feedstock_inlet_temp_c is not None:
        cmd.extend(["--feedstock-inlet-temp", str(feedstock_inlet_temp_c)])
    if insulation_R_value_si is not None:
        cmd.extend(["--insulation-r-value", str(insulation_R_value_si)])
    if biogas_discharge_pressure_kpa is not None:
        cmd.extend(["--biogas-discharge-pressure", str(biogas_discharge_pressure_kpa)])

    # Execute in background
    manager = JobManager()
    job = await manager.execute(cmd=cmd, cwd=".")

    return {
        "job_id": job["id"],
        "status": job["status"],
        "message": "Heuristic sizing job started. Use get_job_status() to monitor progress.",
        "command": " ".join(cmd[:3]) + " ...",
        "next_steps": [
            f"Check status: get_job_status('{job['id']}')",
            f"Get results: get_job_results('{job['id']}')"
        ]
    }

@mcp.tool()
async def simulate_ad_system_tool(
    use_current_state: bool = True,
    validate_hrt: bool = True,
    hrt_variation: float = 0.2,
    costing_method: str = None,
    custom_inputs: dict = None,
    fecl3_dose_mg_L: float = 0,
    naoh_dose_mg_L: float = 0,
    na2co3_dose_mg_L: float = 0
):
    """
    Run QSDsan dynamic simulation with ADM1+sulfur model (30 components).

    Returns comprehensive results including:
    - Stream analysis (influent, effluent, biogas)
    - Performance metrics (yields, inhibition)
    - Sulfur analysis (mass balance, speciation, H2S in biogas)
    - HRT validation (if validate_hrt=True)
    - Optional chemical dosing (FeCl3, NaOH, Na2CO3)

    Returns job_id immediately. Use get_job_status() to check progress and get_job_results() to retrieve results.

    IMPORTANT: This tool now runs in background. Do NOT wait for results - use get_job_status(job_id) instead.
    """
    from utils.job_manager import JobManager
    import sys

    # Build command for simulate_cli.py
    cmd = [
        sys.executable,
        "utils/simulate_cli.py",
        "--basis", "simulation_basis.json",
        "--adm1-state", "simulation_adm1_state.json",
        "--heuristic-config", "simulation_heuristic_config.json",
        "--output-dir", "jobs/{job_id}",  # {job_id} will be replaced by JobManager
    ]

    # Add optional parameters
    if not validate_hrt:
        cmd.append("--no-validate-hrt")
    if hrt_variation is not None and hrt_variation != 0.2:
        cmd.extend(["--hrt-variation", str(hrt_variation)])
    if fecl3_dose_mg_L > 0:
        cmd.extend(["--fecl3-dose", str(fecl3_dose_mg_L)])
    if naoh_dose_mg_L > 0:
        cmd.extend(["--naoh-dose", str(naoh_dose_mg_L)])
    if na2co3_dose_mg_L > 0:
        cmd.extend(["--na2co3-dose", str(na2co3_dose_mg_L)])

    # Execute in background
    manager = JobManager()
    job = await manager.execute(cmd=cmd, cwd=".")

    return {
        "job_id": job["id"],
        "status": job["status"],
        "message": "QSDsan simulation job started. Use get_job_status() to monitor progress.",
        "command": " ".join(cmd[:2]) + " ...",
        "estimated_time": "2-5 minutes",
        "next_steps": [
            f"Check status: get_job_status('{job['id']}')",
            f"Get results: get_job_results('{job['id']}')"
        ]
    }

@mcp.tool()
async def estimate_chemical_dosing(
    use_current_state: bool = True,
    custom_params: dict = None,
    objectives: dict = None
):
    """
    Estimate chemical dosing requirements for anaerobic digester operation.

    Provides stoichiometric estimates for:
    - FeCl3: Sulfide precipitation (H2S control) and phosphate removal
    - NaOH: pH adjustment
    - Na2CO3: Alkalinity supplementation

    Args:
        use_current_state: Use feedstock from design state (default True)
        custom_params: Custom parameters (sulfide_mg_L, phosphate_mg_P_L, etc.)
        objectives: Treatment objectives (sulfide_removal, pH_target, etc.)

    Returns:
        Dosing recommendations with detailed calculations and rationale
    """
    from tools.chemical_dosing import estimate_chemical_dosing_tool as _impl
    return await _impl(use_current_state, custom_params, objectives)


# ==============================================================================
# BACKGROUND JOB MANAGEMENT TOOLS
# ==============================================================================

@mcp.tool()
async def get_job_status(job_id: str):
    """
    Get status of a background job.

    Args:
        job_id: Job identifier returned by asynchronous tools

    Returns:
        Dict with job_id, status ("starting", "running", "completed", "failed"),
        elapsed_time, and progress hints
    """
    from utils.job_manager import JobManager
    manager = JobManager()
    return await manager.get_status(job_id)


@mcp.tool()
async def get_job_results(job_id: str):
    """
    Get results from a completed background job.

    Args:
        job_id: Job identifier

    Returns:
        Dict with job_id, status, results (parsed JSON), and log file paths.
        Returns error if job is not completed.
    """
    from utils.job_manager import JobManager
    manager = JobManager()
    return await manager.get_results(job_id)


@mcp.tool()
async def list_jobs(status_filter: str = None, limit: int = 20):
    """
    List all background jobs with optional status filter.

    Args:
        status_filter: Filter by status ("running", "completed", "failed", or None for all)
        limit: Maximum number of jobs to return (default: 20)

    Returns:
        Dict with jobs list, total count, running jobs count, and max concurrent limit
    """
    from utils.job_manager import JobManager
    manager = JobManager()
    return await manager.list_jobs(status_filter, limit)


@mcp.tool()
async def terminate_job(job_id: str):
    """
    Terminate a running background job.

    Args:
        job_id: Job identifier

    Returns:
        Dict with termination status and message
    """
    from utils.job_manager import JobManager
    manager = JobManager()
    return await manager.terminate_job(job_id)


def main():
    """Run the MCP server."""
    logger.info("="*60)
    logger.info("Anaerobic Digester Design MCP Server")
    logger.info("="*60)
    logger.info("")
    logger.info("Registered tools (14 total):")
    logger.info("  Design Workflow:")
    logger.info("    1. elicit_basis_of_design - Collect design parameters")
    logger.info("    2. load_adm1_state - Load ADM1 state from JSON file")
    logger.info("    3. validate_adm1_state - Validate ADM1 state against composites")
    logger.info("    4. compute_bulk_composites - Compute COD/TSS/VSS/TKN/TP from ADM1")
    logger.info("    5. check_strong_ion_balance - Check cation/anion electroneutrality")
    logger.info("    6. heuristic_sizing_ad - Size digester and auxiliary equipment")
    logger.info("    7. simulate_ad_system_tool - Run QSDsan ADM1+sulfur simulation")
    logger.info("    8. estimate_chemical_dosing - Estimate FeCl3/NaOH/Na2CO3 dosing")
    logger.info("    9. get_design_state - View current design state and next steps")
    logger.info("   10. reset_design - Reset design state for new project")
    logger.info("  Background Job Management:")
    logger.info("   11. get_job_status - Check status of background job")
    logger.info("   12. get_job_results - Retrieve results from completed job")
    logger.info("   13. list_jobs - List all background jobs")
    logger.info("   14. terminate_job - Stop a running background job")
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