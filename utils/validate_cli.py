#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Standalone validation CLI - Called via subprocess for process isolation.

This script runs QSDsan validation operations synchronously in a separate
process to avoid FastMCP event loop / executor contention issues.

Usage:
    python validate_cli.py validate --adm1-state STATE.json --user-params PARAMS.json
    python validate_cli.py composites --adm1-state STATE.json --temperature 35
    python validate_cli.py ion-balance --adm1-state STATE.json --ph 7.0
"""

import json
import sys
import argparse
import logging
import asyncio
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configure logging to stderr (stdout is for JSON output)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)


def validate_adm1_state_sync(adm1_state: dict, user_parameters: dict, tolerance: float, temperature_k: float) -> dict:
    """
    Synchronous wrapper for validate_adm1_state from tools.validation.

    Imports QSDsan and runs validation synchronously (no async).
    """
    logger.info("Loading validation module...")
    from tools.validation import validate_adm1_state

    logger.info("Running validation...")
    result = asyncio.run(validate_adm1_state(
        adm1_state=adm1_state,
        user_parameters=user_parameters,
        tolerance=tolerance
    ))

    logger.info("Validation complete")
    return result


def compute_bulk_composites_sync(adm1_state: dict, temperature_k: float) -> dict:
    """
    Compute bulk composites (COD, TSS, VSS, TKN, TP) directly from ADM1 state.

    This function creates a QSDsan WasteStream with ADM1 concentrations and
    reads the composite properties.
    """
    logger.info("Loading QSDsan components...")
    from utils.extract_qsdsan_sulfur_components import create_adm1_sulfur_cmps, set_global_components
    from qsdsan import WasteStream

    # Set global components
    cmps = create_adm1_sulfur_cmps()
    set_global_components(cmps)

    logger.info("Creating WasteStream from ADM1 state...")
    # Build concentrations dict
    conc_dict = {}
    for key, value in adm1_state.items():
        if key.startswith('S_') or key.startswith('X_'):
            cmp_id = key[2:]  # Remove S_ or X_ prefix
            if cmp_id in [c.ID for c in cmps]:
                conc_dict[cmp_id] = value  # Already in kg/m3

    # Create waste stream
    ws = WasteStream('influent', T=temperature_k, units='kg/hr')
    ws.set_flow_by_concentration(
        flow_tot=1.0,  # 1 m3/hr for concentration basis
        concentrations=conc_dict,
        units='kg/m3'
    )

    logger.info("Computing composites...")
    # QSDsan automatically computes .COD, .TSS, .VSS, .TN, .TP
    result = {
        "status": "success",
        "composites": {
            "COD_mg_L": ws.COD,  # Already in mg/L
            "TSS_mg_L": ws.TSS,
            "VSS_mg_L": ws.VSS,
            "TKN_mg_L": ws.TN,  # Total nitrogen ≈ TKN for anaerobic
            "TP_mg_L": ws.TP
        },
        "temperature_K": temperature_k
    }

    logger.info("Composites computed successfully")
    return result


def check_ion_balance_sync(adm1_state: dict, target_ph: float, max_imbalance: float, temperature_k: float) -> dict:
    """
    Check strong ion balance for electroneutrality.

    Args:
        adm1_state: ADM1 state dict (kg/m³)
        target_ph: Target pH from basis of design
        max_imbalance: Maximum acceptable imbalance percent (default: 5%)
        temperature_k: Temperature in Kelvin

    Returns:
        Dictionary with balance check results
    """
    logger.info("Checking strong ion balance...")
    from tools.validation import check_strong_ion_balance

    result = asyncio.run(check_strong_ion_balance(
        adm1_state=adm1_state,
        ph=target_ph,
        max_imbalance_percent=max_imbalance
    ))

    logger.info("Ion balance check complete")
    return result


def main():
    parser = argparse.ArgumentParser(description='QSDsan validation CLI (subprocess isolation)')

    # Global output directory option (for job isolation)
    parser.add_argument('--output-dir', default='.', help='Directory for output files (default: current directory)')

    subparsers = parser.add_subparsers(dest='command', required=True)

    # validate_adm1_state command
    validate_parser = subparsers.add_parser('validate', help='Validate ADM1 state against composites')
    validate_parser.add_argument('--adm1-state', required=True, help='Path to ADM1 state JSON file')
    validate_parser.add_argument('--user-params', required=True, help='User parameters as JSON string')
    validate_parser.add_argument('--tolerance', type=float, default=0.1, help='Validation tolerance')
    validate_parser.add_argument('--temperature-c', type=float, default=35.0, help='Temperature in Celsius')

    # compute_bulk_composites command
    composites_parser = subparsers.add_parser('composites', help='Compute bulk composites from ADM1 state')
    composites_parser.add_argument('--adm1-state', required=True, help='Path to ADM1 state JSON file')
    composites_parser.add_argument('--temperature-c', type=float, default=35.0, help='Temperature in Celsius')

    # check_ion_balance command
    balance_parser = subparsers.add_parser('ion-balance', help='Check strong ion balance')
    balance_parser.add_argument('--adm1-state', required=True, help='Path to ADM1 state JSON file')
    balance_parser.add_argument('--ph', type=float, default=7.0, help='pH for speciation')
    balance_parser.add_argument('--max-imbalance', type=float, default=5.0, help='Max imbalance percent (default: 5%%)')
    balance_parser.add_argument('--temperature-c', type=float, default=35.0, help='Temperature in Celsius')

    args = parser.parse_args()

    try:
        # Create output directory
        output_path = Path(args.output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Load ADM1 state from file
        with open(args.adm1_state, 'r') as f:
            adm1_state_raw = json.load(f)

        # Extract numeric values from annotated format [value, unit, explanation]
        adm1_state = {}
        for k, v in adm1_state_raw.items():
            if isinstance(v, (list, tuple)) and len(v) > 0:
                adm1_state[k] = float(v[0])
            else:
                adm1_state[k] = float(v)

        temperature_k = 273.15 + args.temperature_c

        # Execute the requested command
        if args.command == 'validate':
            user_params = json.loads(args.user_params)
            result = validate_adm1_state_sync(adm1_state, user_params, args.tolerance, temperature_k)
            output_file = output_path / 'validation_results.json'

        elif args.command == 'composites':
            result = compute_bulk_composites_sync(adm1_state, temperature_k)
            output_file = output_path / 'composites_results.json'

        elif args.command == 'ion-balance':
            result = check_ion_balance_sync(adm1_state, args.ph, args.max_imbalance, temperature_k)
            output_file = output_path / 'ion_balance_results.json'

        else:
            raise ValueError(f"Unknown command: {args.command}")

        # Write result to job-specific output file
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)

        logger.info(f"Results written to: {output_file}")

        # Output result as JSON to stdout (for backward compatibility)
        print(json.dumps(result))
        sys.exit(0)

    except Exception as e:
        logger.error(f"Validation failed: {e}", exc_info=True)
        error_result = {
            "status": "error",
            "message": str(e)
        }
        print(json.dumps(error_result))
        sys.exit(1)


if __name__ == "__main__":
    main()
