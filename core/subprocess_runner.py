"""Subprocess handling for WaterTAP simulations."""

import os
import sys
import json
import logging
import subprocess
import tempfile
import datetime
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


def filter_simulation_response(
    sim_results: Dict[str, Any], 
    detail_level: str = "summary"
) -> Dict[str, Any]:
    """
    Filter simulation response based on requested detail level.
    
    Args:
        sim_results: Full simulation results
        detail_level: "summary" for KPIs only, "full" for everything
        
    Returns:
        Filtered results dictionary
    """
    if detail_level == "summary" and sim_results.get("status") == "success":
        # Extract only key performance indicators
        filtered = {
            "status": sim_results["status"],
            "flowsheet_type": sim_results.get("flowsheet_type"),
            "operational_results": {},
            "economic_results": {}
        }
        
        # Key operational metrics
        if "operational_results" in sim_results:
            ops = sim_results["operational_results"]
            filtered["operational_results"] = {
                "biogas_production_m3d": ops.get("biogas_production_m3d"),
                "methane_fraction": ops.get("methane_fraction"),
                "methane_production_m3d": ops.get("methane_production_m3d"),
                "sludge_production_m3d": ops.get("sludge_production_m3d"),
                "centrate_flow_m3d": ops.get("centrate_flow_m3d"),
                "mbr_permeate_flow_m3d": ops.get("mbr_permeate_flow_m3d")
            }
            
        # Key economic metrics  
        if "economic_results" in sim_results:
            econ = sim_results["economic_results"]
            filtered["economic_results"] = {
                "total_capital_cost": econ.get("total_capital_cost"),
                "total_operating_cost": econ.get("total_operating_cost"),
                "LCOW": econ.get("LCOW")
            }
            
        # Include convergence info if available
        if "convergence_info" in sim_results:
            filtered["convergence_info"] = sim_results["convergence_info"]
        
        # ALWAYS include digester performance metrics for diagnosis
        if "digester_performance" in sim_results:
            filtered["digester_performance"] = sim_results["digester_performance"]
            
        return filtered
    else:
        # Return full results for errors or when requested
        return sim_results


def save_full_logs(results: Dict[str, Any]) -> Optional[str]:
    """
    Save full simulation logs to a timestamped file.
    
    Args:
        results: Full simulation results to save
        
    Returns:
        Path to saved log file or None if save failed
    """
    try:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_dir = Path("simulation_logs")
        log_dir.mkdir(exist_ok=True)
        
        log_file = log_dir / f"sim_log_{timestamp}.json"
        with open(log_file, "w") as f:
            json.dump(results, f, indent=2, default=str)
            
        return str(log_file)
    except Exception as e:
        logger.error(f"Failed to save simulation logs: {e}")
        return None


def extract_json_from_output(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract JSON from mixed text output (stdout with potential warnings).
    
    Handles cases where warnings or other text may be mixed with JSON output.
    """
    if not text:
        return None
        
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
        
    # Try to find JSON boundaries
    import re
    json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
    matches = re.findall(json_pattern, text, re.DOTALL)
    
    for match in reversed(matches):  # Try from end (most likely complete)
        try:
            return json.loads(match)
        except json.JSONDecodeError:
            continue
            
    return None


def run_simulation_in_subprocess(sim_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run WaterTAP AD simulation in a child Python process to isolate stdout/stderr.
    
    This prevents IDAES/Pyomo warnings from corrupting the MCP JSON protocol.
    """
    timeout_s = float(os.environ.get("AD_SIM_TIMEOUT_SEC", "240"))
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "utils.simulate_ad_cli"],
            input=json.dumps(sim_input),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=Path(__file__).parent.parent  # Run from project root
        )
        
        if proc.returncode != 0:
            logger.error(f"Child process failed with code {proc.returncode}")
            logger.error(f"Stderr: {proc.stderr[:1000]}")
            
            # Try to extract JSON error from stdout
            result = extract_json_from_output(proc.stdout)
            if result:
                return result
            else:
                return {
                    "status": "error",
                    "message": f"Child process failed with code {proc.returncode}",
                    "stderr": proc.stderr[:1000],
                }
        
        # Parse JSON from stdout
        try:
            result = json.loads(proc.stdout)
            if proc.stderr:
                logger.debug(f"Child stderr (warnings): {proc.stderr[:500]}")
            return result
        except json.JSONDecodeError as e:
            # Try extraction with fallback
            result = extract_json_from_output(proc.stdout)
            if result:
                logger.warning(f"Extracted JSON from mixed output")
                return result
            
            logger.error(f"Failed to parse JSON from child: {e}")
            logger.error(f"Raw stdout: {proc.stdout[:500]}")
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