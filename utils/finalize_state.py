#!/usr/bin/env python3
"""
Finalize ADM1 state with mandatory validation checks.

This script enforces BOTH bulk composite validation AND ionic balance checking
before allowing an ADM1 state to be finalized. Exit codes provide unambiguous
pass/fail signals for automation.

Exit codes:
    0 - All validations passed
    1 - Bulk composite validation failed (COD/TSS/VSS/TKN/TP out of tolerance)
    2 - Ionic balance validation failed (charge imbalance > 5%)
    3 - Both validations failed
    4 - File not found or JSON parsing error
    5 - Missing required parameters
"""

import sys
import json
import subprocess
import argparse
from pathlib import Path

def run_bulk_validation(adm1_state_file: str, user_params: dict, tolerance: float, temperature_c: float) -> tuple[bool, dict]:
    """Run bulk composite validation (COD, TSS, VSS, TKN, TP)."""
    cmd = [
        sys.executable,  # Use same interpreter as this script
        "utils/validate_cli.py",
        "validate",
        "--adm1-state", adm1_state_file,
        "--user-params", json.dumps(user_params),
        "--tolerance", str(tolerance),
        "--temperature-c", str(temperature_c)
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        validation_result = json.loads(result.stdout)
        return validation_result.get("valid", False), validation_result
    except Exception as e:
        print(f"ERROR: Bulk validation failed to run: {e}", file=sys.stderr)
        return False, {"error": str(e)}

def run_ion_balance(adm1_state_file: str, ph: float, max_imbalance_percent: float, temperature_c: float) -> tuple[bool, dict]:
    """Run ionic balance validation (cation/anion electroneutrality)."""
    cmd = [
        sys.executable,
        "utils/validate_cli.py",
        "ion-balance",
        "--adm1-state", adm1_state_file,
        "--ph", str(ph),
        "--max-imbalance", str(max_imbalance_percent),
        "--temperature-c", str(temperature_c)
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        balance_result = json.loads(result.stdout)
        return balance_result.get("balanced", False), balance_result
    except Exception as e:
        print(f"ERROR: Ion balance validation failed to run: {e}", file=sys.stderr)
        return False, {"error": str(e)}

def main():
    parser = argparse.ArgumentParser(
        description="Finalize ADM1 state with mandatory validation checks"
    )
    parser.add_argument("--adm1-state", required=True, help="Path to ADM1 state JSON file")
    parser.add_argument("--cod", type=float, required=True, help="Target COD (mg/L)")
    parser.add_argument("--tss", type=float, help="Target TSS (mg/L)")
    parser.add_argument("--vss", type=float, help="Target VSS (mg/L)")
    parser.add_argument("--tkn", type=float, help="Target TKN (mg N/L)")
    parser.add_argument("--tp", type=float, help="Target TP (mg P/L)")
    parser.add_argument("--ph", type=float, default=7.0, help="Target pH (default: 7.0)")
    parser.add_argument("--tolerance", type=float, default=0.10, help="Bulk validation tolerance (default: 0.10 = 10%%)")
    parser.add_argument("--max-ph-deviation", type=float, default=0.5, help="Max pH deviation from target (default: 0.5 units)")
    parser.add_argument("--temperature-c", type=float, default=35.0, help="Temperature in °C (default: 35)")
    parser.add_argument("--output", help="Write combined validation results to JSON file")

    args = parser.parse_args()

    # Check if file exists
    if not Path(args.adm1_state).exists():
        print(f"ERROR: ADM1 state file not found: {args.adm1_state}", file=sys.stderr)
        sys.exit(4)

    # Build user_params for bulk validation
    user_params = {"cod_mg_l": args.cod}
    if args.tss is not None:
        user_params["tss_mg_l"] = args.tss
    if args.vss is not None:
        user_params["vss_mg_l"] = args.vss
    if args.tkn is not None:
        user_params["tkn_mg_l"] = args.tkn
    if args.tp is not None:
        user_params["tp_mg_l"] = args.tp
    user_params["ph"] = args.ph

    print("="*80)
    print("ADM1 STATE FINALIZATION - MANDATORY VALIDATION")
    print("="*80)
    print(f"ADM1 State: {args.adm1_state}")
    print(f"Target parameters: COD={args.cod} mg/L, pH={args.ph}")
    print()

    # Run bulk composite validation
    print("[1/2] Running bulk composite validation (COD, TSS, VSS, TKN, TP)...")
    bulk_valid, bulk_result = run_bulk_validation(
        args.adm1_state, user_params, args.tolerance, args.temperature_c
    )

    if bulk_valid:
        print("[PASS] Bulk composites within tolerance")
    else:
        print("[FAIL] Bulk composites out of tolerance")
        if "warnings" in bulk_result:
            for warning in bulk_result["warnings"]:
                print(f"  - {warning}")
    print()

    # Run ionic balance validation
    print("[2/2] Running ionic balance validation (electroneutrality)...")
    ion_valid, ion_result = run_ion_balance(
        args.adm1_state, args.ph, args.max_ph_deviation, args.temperature_c
    )

    if ion_valid:
        print("[PASS] Ionic balance within tolerance")
        if "equilibrium_ph" in ion_result:
            print(f"  Equilibrium pH: {ion_result['equilibrium_ph']:.2f}")
            print(f"  Target pH: {ion_result['target_ph']:.2f}")
            print(f"  pH deviation: {ion_result['ph_deviation']:.2f} units")
            print(f"  Cations: {ion_result['cation_meq_l']:.2f} meq/L")
            print(f"  Anions: {ion_result['anion_meq_l']:.2f} meq/L")
    else:
        print("[FAIL] Ionic balance out of tolerance")
        if "equilibrium_ph" in ion_result:
            print(f"  Equilibrium pH: {ion_result['equilibrium_ph']:.2f}")
            print(f"  Target pH: {ion_result['target_ph']:.2f}")
            print(f"  pH deviation: {ion_result['ph_deviation']:.2f} units (max allowed: {args.max_ph_deviation} units)")
            print(f"  Cations: {ion_result['cation_meq_l']:.2f} meq/L")
            print(f"  Anions: {ion_result['anion_meq_l']:.2f} meq/L")
        if "message" in ion_result:
            print(f"  {ion_result['message']}")
    print()

    # Combined results
    combined = {
        "bulk_validation": bulk_result,
        "ion_balance": ion_result,
        "all_valid": bulk_valid and ion_valid
    }

    # Save to output file if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(combined, f, indent=2)
        print(f"Validation results saved to: {args.output}")
        print()

    # Print final verdict
    print("="*80)
    if bulk_valid and ion_valid:
        print(">> VALIDATION PASSED - State is ready for simulation")
        print("="*80)
        sys.exit(0)
    elif not bulk_valid and not ion_valid:
        print(">> VALIDATION FAILED - Both bulk and ionic checks failed")
        print("="*80)
        print("\nACTION REQUIRED:")
        print("1. Adjust substrate fractions (X_ch, X_pr, X_li) for COD/TSS/VSS")
        print("2. Add cations (S_Na, S_K, S_Mg, S_Ca) to balance anions")
        print("3. Re-run this validation until both checks pass")
        sys.exit(3)
    elif not bulk_valid:
        print(">> VALIDATION FAILED - Bulk composites out of tolerance")
        print("="*80)
        print("\nACTION REQUIRED:")
        print("1. Adjust substrate fractions to match target COD/TSS/VSS/TKN/TP")
        print("2. Re-run validation")
        sys.exit(1)
    else:  # not ion_valid
        print(">> VALIDATION FAILED - Ionic balance out of tolerance")
        print("="*80)
        print("\nACTION REQUIRED:")
        print("1. Add cations (S_Na, S_K, S_Mg, S_Ca) to balance charge")
        print("2. Ensure cation equivalents = anion equivalents")
        print("3. Re-run validation")
        sys.exit(2)

if __name__ == "__main__":
    main()
