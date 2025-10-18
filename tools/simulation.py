"""
QSDsan simulation tool for anaerobic digesters with ADM1+sulfur model - CLI Instruction Mode.

Returns CLI execution instructions to avoid FastMCP STDIO connection timeout
during the 18-second QSDsan component loading.
"""

import logging
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional

from core.state import design_state
from core.utils import coerce_to_dict

logger = logging.getLogger(__name__)
logger.info("Using QSDsan simulation via CLI instructions (FastMCP-compatible)")


async def simulate_ad_system_tool(
    use_current_state: bool = True,
    validate_hrt: bool = True,
    hrt_variation: float = 0.2,
    costing_method: Optional[str] = None,
    custom_inputs: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Simulate anaerobic digester using QSDsan with ADM1+sulfur model.

    Returns CLI instructions for manual execution (bypasses FastMCP STDIO timeout issues).

    Parameters
    ----------
    use_current_state : bool, optional
        Use parameters from current design state (default True)
    validate_hrt : bool, optional
        Run dual-HRT validation for robustness check (default True)
    hrt_variation : float, optional
        HRT variation for validation as fraction (default 0.2 = ±20%)
    costing_method : str or None, optional
        Costing approach (not yet implemented)
    custom_inputs : dict or None, optional
        Custom basis, ADM1 state, and heuristic config

    Returns
    -------
    dict
        CLI execution instructions with:
        - status: "manual_execution_required"
        - command: CLI command to run
        - instructions: List of steps for the user

    Notes
    -----
    **CLI Instruction Mode**:
    - QSDsan component loading takes ~18 seconds
    - This causes FastMCP STDIO connection to timeout
    - CLI mode allows execution outside MCP server
    - Results are saved to simulation_results.json
    """
    try:
        # 1. Validate inputs and prepare simulation parameters
        if use_current_state:
            # Use design state
            if not design_state.basis_of_design:
                return {
                    "success": False,
                    "message": "No basis of design found. Run elicit_basis_of_design first."
                }
            if not design_state.adm1_state:
                return {
                    "success": False,
                    "message": "No ADM1 state found. Characterize feedstock first."
                }
            if not design_state.heuristic_config:
                return {
                    "success": False,
                    "message": "No heuristic sizing found. Run heuristic_sizing_ad first."
                }

            # Get state and normalize keys for simulation
            basis_raw = design_state.basis_of_design
            adm1_state = design_state.adm1_state
            heuristic_config_raw = design_state.heuristic_config

            # Normalize basis keys: feed_flow_m3d → Q, temperature_c → Temp (K)
            temp_c = basis_raw.get('temperature_c')
            temp_k = basis_raw.get('Temp')

            if temp_c is not None:
                temp_final = temp_c + 273.15
            elif temp_k is not None:
                temp_final = temp_k
            else:
                temp_final = 308.15

            basis = {
                'Q': basis_raw.get('feed_flow_m3d') or basis_raw.get('Q'),
                'Temp': temp_final,
                **{k: v for k, v in basis_raw.items() if k not in ['feed_flow_m3d', 'temperature_c']}
            }

            # Normalize heuristic_config keys: hrt_days → HRT_days
            heuristic_config = heuristic_config_raw.copy()
            if 'digester' in heuristic_config:
                digester = heuristic_config['digester'].copy()
                if 'hrt_days' in digester and 'HRT_days' not in digester:
                    digester['HRT_days'] = digester.pop('hrt_days')
                heuristic_config['digester'] = digester

        else:
            # Use custom inputs
            custom_inputs = coerce_to_dict(custom_inputs) or {}
            basis = custom_inputs.get("basis_of_design", {})
            adm1_state = custom_inputs.get("adm1_state", {})
            heuristic_config = custom_inputs.get("heuristic_config", {})

            if not all([basis, adm1_state, heuristic_config]):
                return {
                    "success": False,
                    "message": "Custom inputs must include basis_of_design, adm1_state, and heuristic_config"
                }

        # 2. Save input files for CLI execution
        basis_file = Path('./simulation_basis.json')
        adm1_file = Path('./simulation_adm1_state.json')
        config_file = Path('./simulation_heuristic_config.json')

        with open(basis_file, 'w') as f:
            json.dump(basis, f, indent=2)
        with open(adm1_file, 'w') as f:
            json.dump(adm1_state, f, indent=2)
        with open(config_file, 'w') as f:
            json.dump(heuristic_config, f, indent=2)

        # 3. Build CLI command (convert Windows paths to WSL format for bash compatibility)
        python_exe = sys.executable
        if python_exe.startswith('C:\\'):
            python_exe = python_exe.replace('C:\\', '/mnt/c/').replace('\\', '/')

        command_parts = [
            python_exe,
            "utils/simulate_cli.py",
            f"--basis {basis_file}",
            f"--adm1-state {adm1_file}",
            f"--heuristic-config {config_file}",
            f"--hrt-variation {hrt_variation}"
        ]

        if not validate_hrt:
            command_parts.append("--no-validate-hrt")

        command = " ".join(command_parts)

        return {
            "status": "manual_execution_required",
            "command": command,
            "instructions": [
                "FastMCP cannot execute QSDsan simulation reliably (STDIO timeout during 18s component loading).",
                "Run the command below in your terminal:",
                "",
                f"  {command}",
                "",
                "The simulation will:",
                "  1. Load QSDsan components (~18 seconds)",
                "  2. Run ADM1+sulfur simulation (~50-150 seconds)",
                "  3. Save results to simulation_results.json",
                "",
                "After completion, you can:",
                "  - View results: cat simulation_results.json | jq",
                "  - Load into workflow: Use the results file for next steps",
                "",
                f"Input files saved:",
                f"  - {basis_file}",
                f"  - {adm1_file}",
                f"  - {config_file}"
            ],
            "input_files": {
                "basis": str(basis_file),
                "adm1_state": str(adm1_file),
                "heuristic_config": str(config_file)
            },
            "output_file": "simulation_results.json"
        }

    except Exception as e:
        logger.error(f"Error preparing simulation CLI command: {str(e)}", exc_info=True)
        return {
            "success": False,
            "message": f"Failed to prepare simulation command: {str(e)}"
        }
