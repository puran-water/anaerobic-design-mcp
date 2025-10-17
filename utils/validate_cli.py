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
    Synchronous wrapper for validate_adm1_state_qsdsan.

    Imports QSDsan and runs validation synchronously (no async).
    """
    logger.info("Loading QSDsan components...")
    from utils.qsdsan_validation_sync import validate_adm1_state_sync as validate_impl

    logger.info("Running validation...")
    result = validate_impl(
        adm1_state=adm1_state,
        user_parameters=user_parameters,
        tolerance=tolerance,
        temperature_k=temperature_k
    )

    logger.info("Validation complete")
    return result


def compute_bulk_composites_sync(adm1_state: dict, temperature_k: float) -> dict:
    """Synchronous wrapper for calculate_composites_qsdsan."""
    logger.info("Loading QSDsan components...")
    from utils.qsdsan_validation_sync import calculate_composites_sync

    logger.info("Computing bulk composites...")
    result = calculate_composites_sync(adm1_state, temperature_k)

    logger.info("Composites computed")
    return result


def check_ion_balance_sync(adm1_state: dict, ph: float, temperature_k: float) -> dict:
    """Synchronous wrapper for check_charge_balance_qsdsan."""
    logger.info("Loading QSDsan components...")
    from utils.qsdsan_validation_sync import check_charge_balance_sync

    logger.info("Checking ion balance...")
    result = check_charge_balance_sync(adm1_state, ph, temperature_k)

    logger.info("Ion balance check complete")
    return result


def main():
    parser = argparse.ArgumentParser(description='QSDsan validation CLI (subprocess isolation)')
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
    balance_parser.add_argument('--temperature-c', type=float, default=35.0, help='Temperature in Celsius')

    args = parser.parse_args()

    try:
        # Load ADM1 state from file
        with open(args.adm1_state, 'r') as f:
            adm1_state = json.load(f)

        temperature_k = 273.15 + args.temperature_c

        # Execute the requested command
        if args.command == 'validate':
            user_params = json.loads(args.user_params)
            result = validate_adm1_state_sync(adm1_state, user_params, args.tolerance, temperature_k)

        elif args.command == 'composites':
            result = compute_bulk_composites_sync(adm1_state, temperature_k)

        elif args.command == 'ion-balance':
            result = check_ion_balance_sync(adm1_state, args.ph, temperature_k)

        else:
            raise ValueError(f"Unknown command: {args.command}")

        # Output result as JSON to stdout
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
