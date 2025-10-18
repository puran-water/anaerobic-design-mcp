"""Validation tools for ADM1 state variables - CLI Instruction Mode."""

import logging
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from core.state import design_state
from core.utils import coerce_to_dict, to_float

logger = logging.getLogger(__name__)
logger.info("Using QSDsan validation via CLI instructions (FastMCP-compatible)")


async def validate_adm1_state(
    adm1_state: Dict[str, Any],
    user_parameters: Dict[str, float],
    tolerance: float = 0.10
) -> Dict[str, Any]:
    """
    Validate ADM1 state variables against composite parameters using QSDsan.

    Returns CLI instructions for manual execution (bypasses FastMCP execution issues).

    Args:
        adm1_state: Dictionary of ADM1 component concentrations (30 components)
        user_parameters: Dictionary with measured values (cod_mg_l, tss_mg_l, etc.)
        tolerance: Relative tolerance for validation (default 10%)

    Returns:
        Dictionary containing CLI execution instructions
    """
    try:
        # Normalize inputs
        adm1_state = coerce_to_dict(adm1_state) or {}
        user_parameters = coerce_to_dict(user_parameters) or {}

        # Clean ADM1 state - handle [value, unit, description] format
        clean_state = {}
        for key, value in adm1_state.items():
            if isinstance(value, list) and len(value) > 0:
                clean_state[key] = to_float(value[0])
            elif isinstance(value, dict) and 'value' in value:
                clean_state[key] = to_float(value['value'])
            else:
                clean_state[key] = to_float(value)

        # Get temperature
        temp_c = user_parameters.get('temperature_c', 35.0)

        # Save cleaned ADM1 state to persistent file
        adm1_file = Path('./adm1_state_cleaned.json')
        with open(adm1_file, 'w') as f:
            json.dump(clean_state, f, indent=2)

        # Build CLI command (convert Windows paths to WSL format for bash compatibility)
        user_params_json = json.dumps(user_parameters).replace('"', '\\"')

        # Convert sys.executable to WSL path if it's a Windows path
        python_exe = sys.executable
        if python_exe.startswith('C:\\'):
            # Convert C:\Users\... to /mnt/c/Users/...
            python_exe = python_exe.replace('C:\\', '/mnt/c/').replace('\\', '/')

        command = (
            f"{python_exe} utils/validate_cli.py validate "
            f"--adm1-state adm1_state_cleaned.json "
            f"--user-params '{user_params_json}' "
            f"--tolerance {tolerance} "
            f"--temperature-c {temp_c}"
        )

        # Store cleaned state in design_state for future use
        design_state.adm1_state = clean_state

        return {
            "status": "manual_execution_required",
            "command": command,
            "instructions": [
                "FastMCP cannot execute heavy QSDsan operations reliably.",
                "Please run the command below in your terminal to validate the ADM1 state:",
                "",
                f"  {command}",
                "",
                "The command will:",
                "  1. Load QSDsan components (~18s one-time cost)",
                "  2. Validate ADM1 state against target composites",
                "  3. Output JSON with validation results",
                "",
                f"ADM1 state saved to: {adm1_file.absolute()}",
                f"Components: {len(clean_state)} ADM1+sulfur variables"
            ],
            "expected_output": {
                "valid": "boolean - true if all parameters within tolerance",
                "calculated_parameters": "COD, TSS, VSS, TKN, TP from ADM1 state",
                "deviations": "Percent deviation for each parameter",
                "pass_fail": "PASS/FAIL status for each parameter",
                "warnings": "List of any validation warnings"
            },
            "adm1_state_file": str(adm1_file.absolute()),
            "user_parameters": user_parameters,
            "tolerance": tolerance
        }

    except Exception as e:
        logger.error(f"Error preparing validation instructions: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": f"Failed to prepare validation instructions: {str(e)}"
        }


async def compute_bulk_composites(
    adm1_state: Dict[str, Any],
    temperature_c: float = 35.0
) -> Dict[str, Any]:
    """
    Compute COD, TSS, VSS, TKN, TP (mg/L) from an ADM1 state.

    Returns CLI instructions for manual execution.

    Args:
        adm1_state: ADM1 state dict (accepts [value, unit, note] entries)
        temperature_c: Temperature in Celsius (default 35°C)

    Returns:
        CLI execution instructions
    """
    try:
        adm1_state = coerce_to_dict(adm1_state) or {}

        # Clean state - handle multiple input formats
        clean_state = {}
        for key, value in adm1_state.items():
            if isinstance(value, list) and len(value) > 0:
                clean_state[key] = to_float(value[0])
            elif isinstance(value, dict) and 'value' in value:
                clean_state[key] = to_float(value['value'])
            else:
                clean_state[key] = to_float(value)

        # Save cleaned ADM1 state
        adm1_file = Path('./adm1_state_cleaned.json')
        with open(adm1_file, 'w') as f:
            json.dump(clean_state, f, indent=2)

        # Build CLI command (convert Windows paths to WSL format for bash compatibility)
        python_exe = sys.executable
        if python_exe.startswith('C:\\'):
            python_exe = python_exe.replace('C:\\', '/mnt/c/').replace('\\', '/')

        command = (
            f"{python_exe} utils/validate_cli.py composites "
            f"--adm1-state adm1_state_cleaned.json "
            f"--temperature-c {temperature_c}"
        )

        return {
            "status": "manual_execution_required",
            "command": command,
            "instructions": [
                "Please run the command below to compute bulk composites:",
                "",
                f"  {command}",
                "",
                "Output: JSON with COD, TSS, VSS, TKN, TP (mg/L)"
            ],
            "adm1_state_file": str(adm1_file.absolute()),
            "temperature_c": temperature_c
        }

    except Exception as e:
        logger.error(f"Error preparing composites instructions: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


async def check_strong_ion_balance(
    adm1_state: Dict[str, Any],
    ph: float = 7.0,
    max_imbalance_percent: float = 5.0,
    use_current_adm1: bool = True
) -> Dict[str, Any]:
    """
    Check strong-ion charge balance consistency vs pH.

    Returns CLI instructions for manual execution.
    Automatically includes all 30 ADM1+sulfur components including SO4²⁻, HS⁻, S²⁻

    Args:
        adm1_state: ADM1 state dict
        ph: pH to use for acid-base speciation
        max_imbalance_percent: Threshold for pass/fail
        use_current_adm1: Use ADM1 state from design_state (default True)

    Returns:
        CLI execution instructions
    """
    try:
        adm1_state = coerce_to_dict(adm1_state) or {}

        # Clean state - handle multiple input formats
        clean_state = {}
        for key, value in adm1_state.items():
            if isinstance(value, list) and len(value) > 0:
                clean_state[key] = to_float(value[0])
            elif isinstance(value, dict) and 'value' in value:
                clean_state[key] = to_float(value['value'])
            else:
                clean_state[key] = to_float(value)

        # Save cleaned ADM1 state
        adm1_file = Path('./adm1_state_cleaned.json')
        with open(adm1_file, 'w') as f:
            json.dump(clean_state, f, indent=2)

        # Build CLI command (convert Windows paths to WSL format for bash compatibility)
        python_exe = sys.executable
        if python_exe.startswith('C:\\'):
            python_exe = python_exe.replace('C:\\', '/mnt/c/').replace('\\', '/')

        command = (
            f"{python_exe} utils/validate_cli.py ion-balance "
            f"--adm1-state adm1_state_cleaned.json "
            f"--ph {ph} "
            f"--temperature-c 35.0"
        )

        return {
            "status": "manual_execution_required",
            "command": command,
            "instructions": [
                "Please run the command below to check ion balance:",
                "",
                f"  {command}",
                "",
                "Output: JSON with charge balance analysis (residual, imbalance %, balanced status)"
            ],
            "adm1_state_file": str(adm1_file.absolute()),
            "ph": ph,
            "max_imbalance_percent": max_imbalance_percent
        }

    except Exception as e:
        logger.error(f"Error preparing ion balance instructions: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
