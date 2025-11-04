#!/usr/bin/env python3
"""
CLI Wrapper for Heuristic Sizing with Per-Job Output Isolation

This script wraps the heuristic_sizing module to support background job execution
via JobManager. It accepts command-line arguments and writes results to a
job-specific output directory to prevent file conflicts during concurrent execution.

Usage:
    python utils/heuristic_sizing_cli.py \\
        --output-dir jobs/abc123 \\
        --target-srt 20 \\
        --mixing-type mechanical \\
        --biogas-application storage

Output Files:
    - {output_dir}/results.json: Full sizing results
    - {output_dir}/stdout.log: Standard output (captured by JobManager)
    - {output_dir}/stderr.log: Standard error (captured by JobManager)
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Apply runtime patches BEFORE importing QSDsan/biosteam
from utils.runtime_patches import apply_all_patches
apply_all_patches()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Heuristic sizing for anaerobic digester with mixing and thermal analysis"
    )

    # Required arguments
    parser.add_argument(
        "--input-dir",
        type=str,
        required=True,
        help="Input directory containing basis.json (e.g., jobs/abc123)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        required=True,
        help="Output directory for results (e.g., jobs/abc123)"
    )

    # Sizing parameters
    parser.add_argument(
        "--target-srt",
        type=float,
        default=20.0,
        help="Target solids retention time in days (default: 20)"
    )
    parser.add_argument(
        "--mixing-type",
        type=str,
        default="mechanical",
        choices=["mechanical", "pumped", "hybrid"],
        help="Type of mixing system (default: mechanical)"
    )
    parser.add_argument(
        "--biogas-application",
        type=str,
        default="storage",
        choices=["storage", "direct_utilization", "upgrading"],
        help="Biogas application type (default: storage)"
    )
    parser.add_argument(
        "--height-to-diameter-ratio",
        type=float,
        default=1.2,
        help="Tank height to diameter ratio (default: 1.2)"
    )
    parser.add_argument(
        "--tank-material",
        type=str,
        default="concrete",
        choices=["concrete", "steel_bolted"],
        help="Tank construction material (default: concrete)"
    )

    # Mixing parameters
    parser.add_argument(
        "--mixing-power-target",
        type=float,
        default=7.0,
        help="Mixing power target in W/m³ (default: 7.0 for mesophilic)"
    )
    parser.add_argument(
        "--impeller-type",
        type=str,
        default="pitched_blade_turbine",
        choices=["pitched_blade_turbine", "rushton_turbine", "marine_propeller"],
        help="Impeller type for mechanical mixing (default: pitched_blade_turbine)"
    )

    # Thermal parameters
    parser.add_argument(
        "--calculate-thermal-load",
        action="store_true",
        default=True,
        help="Calculate thermal load requirements (default: True)"
    )
    parser.add_argument(
        "--feedstock-inlet-temp",
        type=float,
        default=10.0,
        help="Feedstock inlet temperature in °C (default: 10)"
    )
    parser.add_argument(
        "--insulation-r-value",
        type=float,
        default=1.76,
        help="Insulation R-value in SI units (m²K/W) (default: 1.76)"
    )

    # Biogas parameters
    parser.add_argument(
        "--biogas-discharge-pressure",
        type=float,
        default=25.0,
        help="Biogas discharge pressure in kPa (default: 25.0)"
    )

    args = parser.parse_args()

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("="*60)
    logger.info("Heuristic Sizing CLI")
    logger.info("="*60)
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"Target SRT: {args.target_srt} days")
    logger.info(f"Mixing type: {args.mixing_type}")
    logger.info(f"Biogas application: {args.biogas_application}")

    try:
        # Load data from JSON files (not design_state!)
        logger.info("Loading input data from JSON files...")
        input_dir = Path(args.input_dir)
        basis_file = input_dir / "basis.json"

        if not basis_file.exists():
            logger.error(f"Input file not found: {basis_file}")
            logger.error("The server should have created this file before launching subprocess.")
            sys.exit(1)

        with open(basis_file) as f:
            basis_of_design = json.load(f)

        # Validate basis has required keys
        required_keys = ['feed_flow_m3d', 'cod_mg_l']
        missing = [k for k in required_keys if k not in basis_of_design]
        if missing:
            logger.error(f"Missing required keys in basis: {missing}")
            sys.exit(1)

        logger.info(f"Loaded basis_of_design: Q={basis_of_design['feed_flow_m3d']} m³/d, COD={basis_of_design['cod_mg_l']} mg/L")

        # Import sizing function (heavy imports happen here)
        logger.info("Loading sizing modules (this may take 10-30 seconds)...")
        from utils.heuristic_sizing import perform_heuristic_sizing

        logger.info("Modules loaded successfully")

        # Perform sizing calculation
        logger.info("Starting heuristic sizing calculation...")

        results = perform_heuristic_sizing(
            basis_of_design=basis_of_design,  # CRITICAL: Pass loaded basis as first param
            target_srt_days=args.target_srt,
            mixing_type=args.mixing_type,
            biogas_application=args.biogas_application,
            height_to_diameter_ratio=args.height_to_diameter_ratio,
            tank_material=args.tank_material,
            mixing_power_target_w_m3=args.mixing_power_target,
            impeller_type=args.impeller_type,
            calculate_thermal_load=args.calculate_thermal_load,
            feedstock_inlet_temp_c=args.feedstock_inlet_temp,
            insulation_R_value_si=args.insulation_r_value,
            biogas_discharge_pressure_kpa=args.biogas_discharge_pressure
        )

        logger.info("Sizing calculation complete!")

        # Write results to output directory
        result_file = output_dir / "results.json"
        with open(result_file, "w") as f:
            json.dump(results, f, indent=2)

        logger.info(f"Results written to: {result_file}")

        # Print summary to stdout
        print("\n" + "="*60)
        print("SIZING RESULTS SUMMARY")
        print("="*60)

        if "flowsheet_type" in results:
            print(f"Flowsheet Type: {results['flowsheet_type']}")
            print(f"Description: {results.get('description', 'N/A')}")

        if "digester" in results:
            d = results["digester"]
            print(f"\nDigester:")
            print(f"  Liquid Volume: {d.get('liquid_volume_m3', 'N/A'):.1f} m³")
            print(f"  Total Volume: {d.get('total_volume_m3', 'N/A'):.1f} m³")
            print(f"  HRT: {d.get('hrt_days', 'N/A'):.2f} days")
            print(f"  SRT: {d.get('srt_days', 'N/A'):.1f} days")
            print(f"  Diameter: {d.get('diameter_m', 'N/A'):.2f} m")
            print(f"  Height: {d.get('height_m', 'N/A'):.2f} m")

        if "mixing" in results:
            m = results["mixing"]
            print(f"\nMixing:")
            print(f"  Type: {m.get('type', 'N/A')}")
            print(f"  Total Power: {m.get('total_power_kw', 'N/A'):.2f} kW")
            print(f"  Power Intensity: {m.get('target_power_w_m3', 'N/A'):.1f} W/m³")

        if "summary" in results:
            print(f"\n{results['summary']}")

        print("="*60)

        logger.info("CLI execution completed successfully")
        sys.exit(0)

    except Exception as e:
        logger.error(f"Sizing calculation failed: {e}", exc_info=True)

        # Write error to output directory
        error_file = output_dir / "error.json"
        with open(error_file, "w") as f:
            json.dump({
                "error": str(e),
                "error_type": type(e).__name__
            }, f, indent=2)

        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
