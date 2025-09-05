#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Anaerobic Digester Design MCP Server

An MCP server for anaerobic digester design following the RO-design-mcp architecture.
Provides tools for parameter elicitation, heuristic sizing, WaterTAP simulation, and economic analysis.
"""

import os
import sys
import json
import re
import logging
import subprocess
import tempfile
import datetime
import copy
import anyio
from typing import Dict, Any, Optional, List, Union
from pathlib import Path

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Set required environment variables
if 'LOCALAPPDATA' not in os.environ:
    if sys.platform == 'win32':
        os.environ['LOCALAPPDATA'] = os.path.join(os.path.expanduser('~'), 'AppData', 'Local')
    else:
        os.environ['LOCALAPPDATA'] = os.path.join(os.path.expanduser('~'), '.local')

# Set Jupyter platform dirs to avoid warnings
if 'JUPYTER_PLATFORM_DIRS' not in os.environ:
    os.environ['JUPYTER_PLATFORM_DIRS'] = '1'

from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field
try:
    # Pydantic v2 RootModel for free-form dicts
    from pydantic import RootModel
except Exception:  # pragma: no cover - fallback if v1 is present
    RootModel = None  # type: ignore
import subprocess
import tempfile

# Configure logging FIRST before any logger usage
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import utility modules
from utils.heuristic_sizing import perform_heuristic_sizing
from utils.adm1_validation import (
    validate_adm1_state as validate_adm1_composite,
    compute_bulk_composites as _compute_bulk_composites,
    calculate_strong_ion_residual as _calculate_strong_ion_residual,
)
from utils.feedstock_characterization import (
    create_default_adm1_state
)

# Import simulation availability marker lazily; use subprocess for actual runs
try:
    # Only to inform tool availability; the simulation itself runs in a child process
    from utils.watertap_simulation_modified import simulate_ad_system  # type: ignore
    SIMULATION_AVAILABLE = True
except ImportError as e:
    logger.warning(f"WaterTAP simulation not available in parent process: {e}")
    SIMULATION_AVAILABLE = False

# Create FastMCP instance
mcp = FastMCP("Anaerobic Digester Design Server")

# Project root
PROJECT_ROOT = Path(__file__).parent


def _to_float(value: Union[float, int, str, None]) -> Optional[float]:
    """
    Coerce a value to float, handling strings and None.
    Used to fix parameter validation issues with numeric strings.
    """
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _filter_simulation_response(
    results: Dict[str, Any],
    detail_level: str = "summary"
) -> Dict[str, Any]:
    """
    Filter simulation results to reduce response size.
    
    Args:
        results: Full simulation results
        detail_level: "summary" for KPIs only, "full" for all details
        
    Returns:
        Filtered results dictionary
    """
    if detail_level == "summary":
        # Return only essential KPIs
        filtered = {
            "status": results.get("status"),
            "flowsheet_type": results.get("flowsheet_type"),
        }
        
        # Add operational results if present
        if "operational_results" in results:
            op = results["operational_results"]
            filtered["operational_results"] = {
                "biogas_production_m3d": op.get("biogas_production_m3d"),
                "methane_fraction": op.get("methane_fraction"),
                "methane_production_m3d": op.get("methane_production_m3d"),
                "sludge_production_m3d": op.get("sludge_production_m3d"),
                "centrate_flow_m3d": op.get("centrate_flow_m3d"),
            }
            # Add MBR-specific if present
            if "mbr_permeate_flow_m3d" in op:
                filtered["operational_results"]["mbr_permeate_flow_m3d"] = op["mbr_permeate_flow_m3d"]
        
        # Add economic results if present
        if "economic_results" in results:
            ec = results["economic_results"]
            filtered["economic_results"] = {
                "total_capital_cost": ec.get("total_capital_cost"),
                "total_operating_cost": ec.get("total_operating_cost"),
                "LCOW": ec.get("LCOW"),
            }
        
        # Add convergence info
        if "convergence_info" in results:
            conv = results["convergence_info"]
            filtered["convergence_info"] = {
                "solver_status": conv.get("solver_status"),
                "degrees_of_freedom": conv.get("degrees_of_freedom"),
            }
        
        # Add summary if present
        if "summary" in results:
            filtered["summary"] = results["summary"]
        
        # Add error info if failed
        if results.get("status") == "error":
            filtered["message"] = results.get("message")
            filtered["error"] = results.get("error")
        
        return filtered
    
    else:
        # Return full results but remove very large objects
        filtered = copy.deepcopy(results)
        
        # Remove solver logs and raw model objects if present
        keys_to_remove = ["raw_stdout", "stderr", "model_str", "solver_log"]
        for key in keys_to_remove:
            filtered.pop(key, None)
        
        return filtered


def _save_full_logs(results: Dict[str, Any]) -> Optional[str]:
    """
    Save full simulation logs to a temporary file.
    
    Returns path to the log file if saved, None otherwise.
    """
    try:
        import tempfile
        import json
        
        # Create temp file in project directory
        log_dir = PROJECT_ROOT / "simulation_logs"
        log_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"simulation_{timestamp}.json"
        
        with open(log_file, "w") as f:
            json.dump(results, f, indent=2, default=str)
        
        return str(log_file)
    except Exception as e:
        logger.warning(f"Failed to save simulation logs: {e}")
        return None


def _extract_json_from_output(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract the last valid JSON object from potentially corrupted output.
    Used as fallback when direct JSON parsing fails due to warnings in stdout.
    """
    if not text:
        return None
    
    # Try to find the last complete JSON object in the output
    # Look for pattern starting with { and ending with }
    try:
        # Find all potential JSON objects
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.findall(json_pattern, text)
        
        if matches:
            # Try parsing from the last match (most likely to be our result)
            for match in reversed(matches):
                try:
                    return json.loads(match)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.debug(f"Failed to extract JSON via regex: {e}")
    
    return None


def _run_simulation_in_subprocess(sim_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run WaterTAP AD simulation in a child Python process to isolate stdout/stderr.

    Prevents solver/native output from corrupting MCP STDIO.
    """
    timeout_s = float(os.environ.get("AD_SIM_TIMEOUT_SEC", "240"))
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "utils.simulate_ad_cli"],
            input=json.dumps(sim_input),
            text=True,
            capture_output=True,
            cwd=str(PROJECT_ROOT),
            check=False,
            timeout=timeout_s,
        )

        if proc.returncode != 0:
            logger.error(
                f"Child simulation failed (code {proc.returncode}). Stderr: {proc.stderr[:2000]}"
            )
            try:
                return json.loads(proc.stdout) if proc.stdout else {
                    "status": "error",
                    "message": f"Child process failed with code {proc.returncode}",
                    "stderr": proc.stderr,
                }
            except json.JSONDecodeError:
                return {
                    "status": "error",
                    "message": "Child process failed and returned non-JSON stdout",
                    "stderr": proc.stderr,
                    "raw_stdout": proc.stdout,
                }

        try:
            return json.loads(proc.stdout) if proc.stdout else {
                "status": "error",
                "message": "No output from child process",
            }
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse child JSON directly: {e}. Attempting fallback extraction...")
            
            # Try fallback JSON extraction
            extracted = _extract_json_from_output(proc.stdout)
            if extracted:
                logger.info("Successfully extracted JSON using fallback method")
                return extracted
            
            logger.error(f"Failed to extract JSON even with fallback. Raw: {proc.stdout[:500]}")
            return {"status": "error", "message": f"Invalid JSON from child process: {e}", "raw_stdout": proc.stdout}
    except subprocess.TimeoutExpired as e:
        logger.error(f"Child simulation timed out after {timeout_s}s")
        return {
            "status": "error",
            "message": f"Simulation timed out after {timeout_s} seconds",
            "timeout_seconds": timeout_s,
            "stderr": getattr(e, "stderr", None),
        }
    except Exception as e:
        logger.error(f"Exception launching child process: {e}")
        return {"status": "error", "message": f"Failed to launch child process: {e}"}

# State management for parameter collection
class ADDesignState:
    """Manages state across tools for anaerobic digester design."""
    
    def __init__(self):
        self.basis_of_design = {}
        self.adm1_state = {}
        self.heuristic_config = {}
        self.simulation_results = {}
        self.economic_results = {}
        
    def reset(self):
        """Reset all state."""
        self.__init__()
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary."""
        return {
            "basis_of_design": self.basis_of_design,
            "adm1_state": self.adm1_state,
            "heuristic_config": self.heuristic_config,
            "simulation_results": self.simulation_results,
            "economic_results": self.economic_results
        }

# Global state instance
design_state = ADDesignState()


# Pydantic models for structured inputs
class BasisOfDesign(BaseModel):
    """Basic design parameters for anaerobic digester."""
    feed_flow_m3d: float = Field(description="Feed flow rate in m³/day")
    cod_mg_l: float = Field(description="COD concentration in mg/L")
    tss_mg_l: Optional[float] = Field(None, description="TSS concentration in mg/L")
    vss_mg_l: Optional[float] = Field(None, description="VSS concentration in mg/L")
    temperature_c: float = Field(35.0, description="Operating temperature in °C")
    tkn_mg_l: Optional[float] = Field(None, description="TKN concentration in mg/L")
    tp_mg_l: Optional[float] = Field(None, description="TP concentration in mg/L")
    alkalinity_meq_l: Optional[float] = Field(None, description="Alkalinity in meq/L")
    ph: Optional[float] = Field(None, description="pH value")


# Free-form dictionary type for FastMCP tool parameters
if RootModel is not None:
    class AnyDict(RootModel[Dict[str, Any]]):
        pass
else:
    # Fallback for environments without Pydantic v2
    class AnyDict(BaseModel):  # type: ignore
        data: Dict[str, Any] = Field(default_factory=dict)


def _coerce_to_dict(value: Optional[Any]) -> Optional[Dict[str, Any]]:
    """Coerce tool inputs to a plain dict.

    Supports:
    - dict
    - JSON string
    - Pydantic RootModel with `.root`
    - Fallback BaseModel with `.data`
    """
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return None
    # Pydantic v2 RootModel
    if hasattr(value, "root") and isinstance(getattr(value, "root"), dict):  # type: ignore
        return getattr(value, "root")  # type: ignore
    # Fallback BaseModel with `data`
    if hasattr(value, "data") and isinstance(getattr(value, "data"), dict):  # type: ignore
        return getattr(value, "data")  # type: ignore
    return None


@mcp.tool()
async def elicit_basis_of_design(
    parameter_group: str = "essential",
    current_values: Optional[AnyDict] = None
) -> Dict[str, Any]:
    """
    Elicit basis of design parameters for anaerobic digester design.
    
    This tool collects essential and optional parameters through structured prompts,
    validates inputs, and stores them in the design state for use by other tools.
    
    Args:
        parameter_group: Parameter group to elicit. Options:
                        - "essential": Flow, COD, temperature (required)
                        - "solids": TSS, VSS concentrations
                        - "nutrients": TKN, TP concentrations  
                        - "alkalinity": pH, alkalinity values
                        - "all": Complete parameter set
        current_values: Optional dictionary of already known values (any JSON object). Strings containing JSON are accepted.
    
    Returns:
        Dictionary containing:
        - status: "success" or "error"
        - parameters: Collected parameter values
        - validation: Validation results and warnings
        - message: Status message
    
    Example:
        ```python
        # Elicit essential parameters
        result = await elicit_basis_of_design(
            parameter_group="essential"
        )
        
        # Elicit with some known values
        result = await elicit_basis_of_design(
            parameter_group="all",
            current_values={"feed_flow_m3d": 1000, "cod_mg_l": 50000}
        )
        ```
        Note: If alkalinity is provided as `alkalinity_mg_l_as_caco3` (or similar),
        it is converted to `alkalinity_meq_l` using mg/L ÷ 50.
    """
    try:
        # Normalize dict-like inputs that may arrive as JSON strings or RootModel
        current_values = _coerce_to_dict(current_values) or {}
        
        # Define parameter groups with prompts and defaults
        parameter_definitions = {
            "essential": [
                ("feed_flow_m3d", "Feed flow rate (m³/day)", 1000.0, True),
                ("cod_mg_l", "COD concentration (mg/L)", 50000.0, True),
                ("temperature_c", "Operating temperature (°C)", 35.0, True)
            ],
            "solids": [
                ("tss_mg_l", "TSS concentration (mg/L)", 35000.0, False),
                ("vss_mg_l", "VSS concentration (mg/L)", 28000.0, False)
            ],
            "nutrients": [
                ("tkn_mg_l", "TKN concentration (mg/L)", 2500.0, False),
                ("tp_mg_l", "TP concentration (mg/L)", 500.0, False)
            ],
            "alkalinity": [
                ("alkalinity_meq_l", "Alkalinity (meq/L)", 100.0, False),
                ("ph", "pH value", 7.0, False)
            ]
        }
        
        # Handle "all" parameter group
        if parameter_group == "all":
            params_to_elicit = []
            for group_params in parameter_definitions.values():
                params_to_elicit.extend(group_params)
        elif parameter_group in parameter_definitions:
            params_to_elicit = parameter_definitions[parameter_group]
        else:
            return {
                "status": "error",
                "message": f"Invalid parameter group: {parameter_group}",
                "valid_groups": list(parameter_definitions.keys()) + ["all"]
            }
        
        # Collect parameters
        collected_params = current_values.copy() if current_values else {}
        validation_warnings = []

        # Convenience: convert alkalinity reported as mg/L as CaCO3 to meq/L
        # Accept several common key variants
        for key in list(collected_params.keys()):
            k = key.lower()
            if k in {"alkalinity_mg_l_as_caco3", "alkalinity_caco3_mg_l", "alkalinity_mg_l_caco3"}:
                try:
                    mgL = float(collected_params[key])
                    collected_params["alkalinity_meq_l"] = mgL / 50.0
                except Exception:
                    validation_warnings.append("Could not convert alkalinity from mg/L as CaCO3 to meq/L")
                # Keep original key for traceability
        
        for param_name, description, default, required in params_to_elicit:
            # Skip if already provided
            if param_name in collected_params:
                continue
            
            # For this basic version, use the default value
            # In production, this would prompt the user
            value = default
            
            # Validate value ranges
            if param_name == "feed_flow_m3d" and value <= 0:
                validation_warnings.append(f"Feed flow must be positive")
            elif param_name == "cod_mg_l" and value <= 0:
                validation_warnings.append(f"COD must be positive")
            elif param_name == "temperature_c":
                if value < 20 or value > 60:
                    validation_warnings.append(f"Temperature {value}°C is outside typical range (20-60°C)")
            elif param_name == "ph":
                if value < 6 or value > 8:
                    validation_warnings.append(f"pH {value} is outside optimal range (6-8)")
            
            collected_params[param_name] = value
        
        # Update global state
        design_state.basis_of_design.update(collected_params)
        
        # Calculate derived parameters
        derived_params = {}
        if "tss_mg_l" in collected_params and "vss_mg_l" in collected_params:
            vss_tss_ratio = collected_params["vss_mg_l"] / collected_params["tss_mg_l"]
            derived_params["vss_tss_ratio"] = vss_tss_ratio
            if vss_tss_ratio < 0.6 or vss_tss_ratio > 0.95:
                validation_warnings.append(f"VSS/TSS ratio {vss_tss_ratio:.2f} is unusual")
        
        if "cod_mg_l" in collected_params and "vss_mg_l" in collected_params:
            cod_vss_ratio = collected_params["cod_mg_l"] / collected_params.get("vss_mg_l", 1)
            derived_params["cod_vss_ratio"] = cod_vss_ratio
        
        # Determine digester type
        if collected_params.get("temperature_c", 35) < 40:
            derived_params["digester_type"] = "mesophilic"
        else:
            derived_params["digester_type"] = "thermophilic"
        
        return {
            "status": "success",
            "parameters": collected_params,
            "derived_parameters": derived_params,
            "validation": {
                "warnings": validation_warnings,
                "valid": len(validation_warnings) == 0
            },
            "message": f"Collected {len(collected_params)} parameters for {parameter_group} group",
            "state_summary": {
                "total_parameters": len(design_state.basis_of_design),
                "groups_completed": [parameter_group]
            }
        }
        
    except Exception as e:
        logger.error(f"Error in elicit_basis_of_design: {str(e)}")
        return {
            "status": "error",
            "error": str(type(e).__name__),
            "message": str(e)
        }


@mcp.tool()
async def validate_adm1_state(
    adm1_state: Dict[str, Any],
    user_parameters: Dict[str, float],
    tolerance: float = 0.1,
    force_store: bool = False
) -> Dict[str, Any]:
    """
    Validate ADM1 state variables against composite parameters (COD, TSS, TKN, TP, pH, alkalinity).
    
    This tool validates ADM1 state variables (from ADM1-State-Variable-Estimator MCP server)
    against user-provided composite parameters using WaterTAP calculation methods.
    
    Args:
        adm1_state: Dictionary of ADM1 component concentrations
                   Can be in format {"S_su": value} or {"S_su": [value, unit, explanation]}
        user_parameters: Dictionary with measured values:
                        - cod_mg_l: COD concentration in mg/L
                        - tss_mg_l: TSS concentration in mg/L
                        - vss_mg_l: VSS concentration in mg/L
                        - tkn_mg_l: TKN concentration in mg/L
                        - tp_mg_l: TP concentration in mg/L
                        - ph: pH value
                        - alkalinity_meq_l: Alkalinity in meq/L
        tolerance: Relative tolerance for validation (default 10%)
        force_store: If True, store ADM1 state even if validation fails (testing/development)
    
    Returns:
        Dictionary containing:
        - status: "success" or "error"
        - valid: Boolean indicating if validation passed
        - calculated_parameters: Calculated composite values from ADM1 state
        - user_parameters: User-provided values for comparison
        - deviations: Percentage deviations for each parameter
        - pass_fail: Pass/fail status for each parameter
        - warnings: List of validation warnings
        - stored: Whether ADM1 state was stored in server state
        - message: Summary message
    
    Example:
        ```python
        # First get ADM1 state from ADM1-State-Variable-Estimator
        # Then validate against measured parameters
        result = await validate_adm1_state(
            adm1_state=adm1_state_from_codex,
            user_parameters={"cod_mg_l": 50000, "tss_mg_l": 5000, "ph": 7.2}
        )
        ```
    """
    try:
        # Normalize inputs if provided as JSON strings
        if isinstance(adm1_state, str):
            try:
                import json as _json
                adm1_state = _json.loads(adm1_state)
            except Exception:
                return {
                    "status": "error",
                    "message": "adm1_state must be a dict or JSON string",
                }
        
        if isinstance(user_parameters, str):
            try:
                import json as _json
                user_parameters = _json.loads(user_parameters)
            except Exception:
                return {
                    "status": "error",
                    "message": "user_parameters must be a dict or JSON string",
                }
        
        # Perform validation using WaterTAP-based calculations
        validation_result = validate_adm1_composite(
            adm1_state=adm1_state,
            user_parameters=user_parameters,
            tolerance=tolerance
        )
        
        # Store ADM1 state if validation passed or force_store is True
        stored = False
        if validation_result.get("valid") or force_store:
            design_state.adm1_state = adm1_state
            stored = True
            
        # Generate summary message
        if validation_result["valid"]:
            message = "ADM1 state validation PASSED - all parameters within tolerance"
        else:
            failed_params = [k for k, v in validation_result["pass_fail"].items() if v == "FAIL"]
            message = f"ADM1 state validation FAILED - parameters out of tolerance: {', '.join(failed_params)}"
        
        return {
            "status": "success" if validation_result["valid"] else "warning",
            **validation_result,
            "stored": stored,
            "message": message
        }
        
    except Exception as e:
        logger.error(f"Error in validate_adm1_state: {str(e)}")
        return {
            "status": "error",
            "error": str(type(e).__name__),
            "message": str(e)
        }


@mcp.tool()
async def compute_bulk_composites(
    adm1_state: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Compute COD, TSS, VSS, TKN, TP (mg/L) from an ADM1 state.

    Accepts plain dict or JSON string. Returns calculated values only.
    """
    try:
        # Normalize inputs if provided as JSON strings
        if isinstance(adm1_state, str):
            import json as _json
            adm1_state = _json.loads(adm1_state)

        # If values are [value, unit, note], take value
        clean_state = {k: (v[0] if isinstance(v, list) else v) for k, v in adm1_state.items()}
        comps = _compute_bulk_composites(clean_state)
        return {"status": "success", "composites_mg_l": comps}
    except Exception as e:
        logger.error(f"Error in compute_bulk_composites: {e}")
        return {"status": "error", "message": str(e)}


@mcp.tool()
async def check_strong_ion_balance(
    adm1_state: Dict[str, Any],
    ph: float = 7.0,
    max_imbalance_percent: float = 5.0,
) -> Dict[str, Any]:
    """
    Check strong-ion charge balance consistency vs pH using a Modified ADM1-style residual.

    Args:
        adm1_state: ADM1 state dict (accepts [value, unit, note] entries)
        ph: pH to use for acid-base speciation terms
        max_imbalance_percent: Threshold for pass/fail

    Returns:
        status, residual metrics, pass/fail recommendation
    """
    try:
        if isinstance(adm1_state, str):
            import json as _json
            adm1_state = _json.loads(adm1_state)

        clean_state = {k: (v[0] if isinstance(v, list) else v) for k, v in adm1_state.items()}
        res = _calculate_strong_ion_residual(clean_state, ph=ph)
        ok = res.get("imbalance_percent", 1e9) <= max_imbalance_percent

        # Guidance: S_cat/S_an should capture OTHER ions, exclude explicit K/Mg
        guidance = (
            "S_cat/S_an should exclude explicit K+ and Mg2+ when bio_P=True to avoid double counting. "
            "If imbalance is high, consider rebalancing S_cat/S_an after setting S_K/S_Mg and S_IC at the target pH."
        )
        return {
            "status": "success",
            "ph": ph,
            **res,
            "pass": ok,
            "threshold_percent": max_imbalance_percent,
            "guidance": guidance,
        }
    except Exception as e:
        logger.error(f"Error in check_strong_ion_balance: {e}")
        return {"status": "error", "message": str(e)}

@mcp.tool()
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
    
    Example:
        ```python
        state = await get_design_state()
        print(f"Design progress: {state['completion_status']}")
        ```
    """
    try:
        # Calculate completion status
        completion_status = {
            "basis_of_design": len(design_state.basis_of_design) > 0,
            "adm1_estimation": len(design_state.adm1_state) > 0,
            "heuristic_sizing": len(design_state.heuristic_config) > 0,
            "simulation": len(design_state.simulation_results) > 0,
            "economic_analysis": len(design_state.economic_results) > 0
        }
        
        # Calculate overall progress
        completed_stages = sum(1 for v in completion_status.values() if v)
        total_stages = len(completion_status)
        progress_percent = (completed_stages / total_stages) * 100
        
        return {
            "status": "success",
            **design_state.to_dict(),
            "completion_status": completion_status,
            "overall_progress": f"{progress_percent:.0f}%",
            "next_steps": _get_next_steps(completion_status)
        }
        
    except Exception as e:
        logger.error(f"Error in get_design_state: {str(e)}")
        return {
            "status": "error",
            "error": str(type(e).__name__),
            "message": str(e)
        }


@mcp.tool()
async def reset_design() -> Dict[str, Any]:
    """
    Reset the anaerobic digester design state.
    
    Clears all stored parameters and results to start a new design session.
    
    Returns:
        Confirmation of reset operation
    
    Example:
        ```python
        result = await reset_design()
        # Start fresh with new design parameters
        ```
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
            "error": str(type(e).__name__),
            "message": str(e)
        }


@mcp.tool()
async def heuristic_sizing_ad(
    biomass_yield: Optional[Union[float, int, str]] = None,
    target_srt_days: Optional[Union[float, int, str]] = None,
    use_current_basis: bool = True,
    custom_basis: Optional[AnyDict] = None
) -> Dict[str, Any]:
    """
    Perform heuristic sizing for anaerobic digester based on COD load and biomass yield.
    
    This tool calculates digester volume and determines flowsheet configuration
    (high TSS with dewatering vs. low TSS with MBR) based on expected biomass concentration.
    
    Args:
        biomass_yield: Biomass yield in kg TSS/kg COD (default 0.1)
        target_srt_days: Target solids retention time in days (default 30)
        use_current_basis: Use parameters from current design state (default True)
        custom_basis: Optional custom basis of design parameters (any JSON object). Strings containing JSON are accepted.
    
    Returns:
        Dictionary containing:
        - flowsheet_type: "high_tss" or "low_tss_mbr"
        - digester: Sizing details (volume, HRT, SRT)
        - mbr: MBR requirements if applicable
        - dewatering: Dewatering configuration
        - sizing_basis: Summary of inputs and calculations
        - flowsheet_decision: Reasoning for configuration selection
    
    Example:
        ```python
        # Use default parameters from elicited basis
        result = await heuristic_sizing_ad()
        
        # Custom biomass yield
        result = await heuristic_sizing_ad(
            biomass_yield=0.15,  # Higher yield
            target_srt_days=25    # Shorter SRT
        )
        ```
    """
    try:
        # Get basis of design
        if use_current_basis:
            if not design_state.basis_of_design:
                return {
                    "status": "error",
                    "message": "No basis of design found. Run elicit_basis_of_design first.",
                    "next_step": "Use elicit_basis_of_design to collect parameters"
                }
            basis = design_state.basis_of_design
        elif custom_basis:
            basis = _coerce_to_dict(custom_basis)
            if basis is None:
                return {
                    "status": "error",
                    "message": "custom_basis must be a dict or JSON string",
                }
        else:
            return {
                "status": "error",
                "message": "Either use_current_basis must be True or custom_basis must be provided"
            }
        
        # Coerce numeric parameters from strings if needed
        biomass_yield = _to_float(biomass_yield)
        target_srt_days = _to_float(target_srt_days)
        
        # Perform heuristic sizing
        sizing_result = perform_heuristic_sizing(
            basis_of_design=basis,
            biomass_yield=biomass_yield,
            target_srt_days=target_srt_days
        )
        
        # Update design state
        design_state.heuristic_config = sizing_result
        
        # Add status and summary
        result = {
            "status": "success",
            **sizing_result,
            "summary": _generate_sizing_summary(sizing_result)
        }
        
        logger.info(f"Heuristic sizing complete: {sizing_result['flowsheet_type']}")
        
        return result
        
    except ValueError as ve:
        logger.error(f"Validation error in heuristic_sizing_ad: {str(ve)}")
        return {
            "status": "error",
            "error": "ValidationError",
            "message": str(ve)
        }
    except Exception as e:
        logger.error(f"Error in heuristic_sizing_ad: {str(e)}")
        return {
            "status": "error",
            "error": str(type(e).__name__),
            "message": str(e)
        }


@mcp.tool()
async def simulate_ad_system_tool(
    use_current_state: bool = True,
    costing_method: str = "WaterTAPCosting",
    initialize_only: bool = False,
    detail_level: str = "summary",
    custom_inputs: Optional[AnyDict] = None
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
        custom_inputs: Optional custom basis, ADM1 state, and config (any JSON object with keys `basis_of_design`, `adm1_state`, `heuristic_config`). Strings containing JSON are accepted.
    
    Returns:
        Dictionary containing:
        - status: Success/error status
        - flowsheet_type: Configuration simulated
        - operational_results: Biogas, methane, flows
        - economic_results: CAPEX, OPEX, LCOW (if costing enabled)
        - convergence_info: Solver statistics
        
    Example:
        ```python
        # Simulate using current design state
        result = await simulate_ad_system_tool()
        
        # Initialize only for testing
        result = await simulate_ad_system_tool(initialize_only=True)
        ```
    """
    if not SIMULATION_AVAILABLE:
        return {
            "status": "error",
            "message": "WaterTAP simulation module not available. Please install WaterTAP dependencies.",
            "next_step": "Install WaterTAP using: pip install watertap"
        }
    
    try:
        # Get inputs from current state or custom
        if use_current_state:
            if not design_state.basis_of_design:
                return {
                    "status": "error",
                    "message": "No basis of design found. Run elicit_basis_of_design first."
                }
            if not design_state.adm1_state:
                return {
                    "status": "error",
                    "message": "No ADM1 state found. Use ADM1-State-Variable-Estimator MCP server first."
                }
            if not design_state.heuristic_config:
                return {
                    "status": "error",
                    "message": "No heuristic configuration found. Run heuristic_sizing_ad first."
                }
            
            basis = design_state.basis_of_design
            adm1_state = design_state.adm1_state
            heuristic_config = design_state.heuristic_config
            
        elif custom_inputs:
            _inputs = _coerce_to_dict(custom_inputs)
            if _inputs is None:
                return {
                    "status": "error",
                    "message": "custom_inputs must be a dict or JSON string",
                }
            basis = _inputs.get("basis_of_design")
            adm1_state = _inputs.get("adm1_state")
            heuristic_config = _inputs.get("heuristic_config")
            
            if not all([basis, adm1_state, heuristic_config]):
                return {
                    "status": "error",
                    "message": "custom_inputs must include basis_of_design, adm1_state, and heuristic_config"
                }
        else:
            return {
                "status": "error",
                "message": "Either use_current_state must be True or custom_inputs must be provided"
            }
        
        # Validate P-species presence for Modified ADM1
        required_p_species = ['S_IP', 'S_K', 'S_Mg', 'X_PAO', 'X_PHA', 'X_PP']
        missing_species = []
        
        for species in required_p_species:
            if species not in adm1_state or adm1_state[species] is None:
                missing_species.append(species)
        
        if missing_species:
            return {
                "status": "error",
                "message": f"Missing required P-species for Modified ADM1: {missing_species}",
                "solution": "Use ADM1-State-Variable-Estimator MCP server to generate Modified ADM1 state with P-species",
                "required_species": required_p_species
            }
        
        # Run simulation in isolated child process
        logger.info(f"Starting WaterTAP simulation for {heuristic_config['flowsheet_type']} configuration (child process)")

        sim_input = {
            "basis_of_design": basis,
            "adm1_state": adm1_state,
            "heuristic_config": heuristic_config,
            "costing_method": costing_method,
            "initialize_only": initialize_only,
            "tee": False,
        }

        sim_results = await anyio.to_thread.run_sync(_run_simulation_in_subprocess, sim_input)
        
        # Store results in design state if successful
        if sim_results["status"] in ["success", "initialized"]:
            design_state.simulation_results = sim_results
            
            # Store economic results if available
            if "economic_results" in sim_results:
                design_state.economic_results = sim_results["economic_results"]
        
        # Add summary
        if sim_results["status"] == "success":
            sim_results["summary"] = _generate_simulation_summary(sim_results)
        
        # Save full logs if successful
        if sim_results["status"] in ["success", "initialized"]:
            log_path = _save_full_logs(sim_results)
            if log_path:
                sim_results["full_log_path"] = log_path
        
        # Filter response based on detail level
        filtered_results = _filter_simulation_response(sim_results, detail_level)
        
        return filtered_results
        
    except Exception as e:
        logger.error(f"Error in simulate_ad_system_tool: {str(e)}")
        return {
            "status": "error",
            "error": str(type(e).__name__),
            "message": str(e)
        }


def _generate_simulation_summary(sim_results: Dict[str, Any]) -> str:
    """Generate summary of simulation results."""
    op_results = sim_results.get("operational_results", {})
    econ_results = sim_results.get("economic_results", {})
    
    summary_parts = []
    
    # Operational results
    if op_results.get("biogas_production_m3d"):
        summary_parts.append(f"Biogas: {op_results['biogas_production_m3d']:.0f} m³/d")
    if op_results.get("methane_fraction"):
        summary_parts.append(f"CH4: {op_results['methane_fraction']*100:.1f}%")
    if op_results.get("sludge_production_m3d"):
        summary_parts.append(f"Sludge: {op_results['sludge_production_m3d']:.1f} m³/d")
    
    # Economic results
    if econ_results.get("total_capital_cost"):
        summary_parts.append(f"CAPEX: ${econ_results['total_capital_cost']/1e6:.1f}M")
    if econ_results.get("LCOW"):
        summary_parts.append(f"LCOW: ${econ_results['LCOW']:.2f}/m³")
    
    return "Simulation complete: " + ", ".join(summary_parts) if summary_parts else "Simulation complete"


def _generate_sizing_summary(sizing_result: Dict[str, Any]) -> str:
    """Generate human-readable summary of sizing results."""
    flowsheet = sizing_result['flowsheet_type']
    digester = sizing_result['digester']
    
    if flowsheet == "high_tss":
        summary = (
            f"High TSS configuration selected. "
            f"Digester volume: {digester['liquid_volume_m3']:.0f} m³, "
            f"HRT/SRT: {digester['hrt_days']:.0f} days, "
            f"Full dewatering required."
        )
    else:
        mbr = sizing_result['mbr']
        summary = (
            f"Low TSS with MBR configuration selected. "
            f"Digester volume: {digester['liquid_volume_m3']:.0f} m³, "
            f"HRT: {digester['hrt_days']:.1f} days, "
            f"SRT: {digester['srt_days']:.0f} days, "
            f"MBR area: {mbr['total_area_m2']:.0f} m²"
        )
    
    return summary


def _get_next_steps(completion_status: Dict[str, bool]) -> List[str]:
    """Determine next steps based on completion status."""
    next_steps = []
    
    if not completion_status["basis_of_design"]:
        next_steps.append("Use elicit_basis_of_design to collect design parameters")
    elif not completion_status["adm1_estimation"]:
        next_steps.append("Use ADM1-State-Variable-Estimator MCP server to generate ADM1 state, then validate_adm1_state")
    elif not completion_status["heuristic_sizing"]:
        next_steps.append("Use heuristic_sizing_ad to calculate digester configuration")
    elif not completion_status["simulation"]:
        next_steps.append("Use simulate_ad_system_tool to run WaterTAP simulation")
    elif not completion_status["economic_analysis"]:
        next_steps.append("Economic analysis is performed automatically during simulation")
    else:
        next_steps.append("Design complete! Review results with get_design_state")
    
    return next_steps


# Main entry point
def main():
    """Run the MCP server."""
    logger.info("Starting Anaerobic Digester Design MCP Server...")
    
    # Log available tools
    logger.info("Available tools:")
    logger.info("  - elicit_basis_of_design: Collect design parameters")
    logger.info("  - validate_adm1_state: Validate ADM1 state against composite parameters")
    logger.info("  - compute_bulk_composites: Compute COD/TSS/VSS/TKN/TP from ADM1 state")
    logger.info("  - check_strong_ion_balance: Check cation/anion balance consistency vs pH")
    logger.info("  - heuristic_sizing_ad: Calculate digester sizing and configuration")
    if SIMULATION_AVAILABLE:
        logger.info("  - simulate_ad_system_tool: Run WaterTAP simulation")
    else:
        logger.info("  - simulate_ad_system_tool: [NOT AVAILABLE - WaterTAP not installed]")
    logger.info("  - get_design_state: View current design state")
    logger.info("  - reset_design: Reset for new design")
    
    # Run the server
    mcp.run()


if __name__ == "__main__":
    main()
