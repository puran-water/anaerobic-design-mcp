#!/usr/bin/env python
"""
CLI script for running QSDsan ADM1+sulfur simulations.

This script handles the heavy QSDsan operations outside the MCP server
to avoid STDIO connection timeouts during the 18-second component loading.
"""

# CRITICAL FIX: Patch fluids.numerics BEFORE any QSDsan imports
# thermo package (dependency of thermosteam → biosteam → qsdsan) expects
# numerics.PY37 which was removed in fluids 1.2.0
# Since we're on Python 3.12, PY37 should always be True
import fluids.numerics
if not hasattr(fluids.numerics, 'PY37'):
    fluids.numerics.PY37 = True  # Python 3.12 > 3.7

import sys
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_simulation(
    basis_file: str,
    adm1_state_file: str,
    heuristic_config_file: str,
    validate_hrt: bool = True,
    hrt_variation: float = 0.2,
    check_interval: float = 2,
    tolerance: float = 1e-3,
    output_file: str = 'simulation_results.json',
    fecl3_dose_mg_L: float = 0,
    naoh_dose_mg_L: float = 0,
    na2co3_dose_mg_L: float = 0,
    pH_ctrl: float = None
):
    """
    Run QSDsan ADM1+sulfur simulation from JSON input files.

    Simulations run until TRUE steady state (no time limit).

    Args:
        basis_file: Path to basis of design JSON
        adm1_state_file: Path to ADM1 state JSON (62 mADM1 components)
        heuristic_config_file: Path to heuristic config JSON
        validate_hrt: Run dual-HRT validation (default True)
        hrt_variation: HRT variation for validation (default 0.2)
        check_interval: Days between convergence checks (default 2)
        tolerance: Convergence tolerance in kg/m3/d (default 1e-3)
        output_file: Path to save results JSON
        fecl3_dose_mg_L: FeCl3 dose in mg/L (default 0 = no dosing)
        naoh_dose_mg_L: NaOH dose in mg/L (default 0 = no dosing)
        na2co3_dose_mg_L: Na2CO3 dose in mg/L (default 0 = no dosing)
    """
    try:
        start_time = datetime.now()

        # Load input files
        logger.info("Loading input files...")
        with open(basis_file, 'r') as f:
            basis = json.load(f)
        with open(adm1_state_file, 'r') as f:
            adm1_state_raw = json.load(f)
        with open(heuristic_config_file, 'r') as f:
            heuristic_config = json.load(f)

        # Extract numeric values from annotated format [value, unit, explanation]
        adm1_state = {}
        for k, v in adm1_state_raw.items():
            if isinstance(v, (list, tuple)) and len(v) > 0:
                adm1_state[k] = float(v[0])
            else:
                adm1_state[k] = float(v)

        logger.info(f"Basis: Q={basis.get('Q', 'N/A')} m3/d, T={basis.get('Temp', 'N/A')} K")
        logger.info(f"ADM1 state: {len(adm1_state)} components")
        logger.info(f"Design SRT: {heuristic_config['digester']['srt_days']} days (HRT in heuristic: {heuristic_config['digester']['HRT_days']} days)")

        # Import simulation modules (this takes ~18 seconds on first run)
        logger.info("Loading QSDsan components (may take ~18 seconds)...")
        from utils.qsdsan_simulation_sulfur import (
            run_simulation_sulfur,
            run_dual_hrt_simulation
        )
        from utils.stream_analysis_sulfur import (
            analyze_liquid_stream,
            analyze_gas_stream,
            analyze_inhibition,
            calculate_sulfur_metrics,
            analyze_biomass_yields,
            extract_diagnostics
        )
        from utils.qsdsan_loader import get_qsdsan_components
        import anyio

        # Load components synchronously in CLI mode
        logger.info("Creating QSDsan component set...")
        async def _load():
            return await get_qsdsan_components()
        components = anyio.run(_load)
        logger.info(f"Components loaded: {len(components)} components available")

        # Convert dose concentrations (mg/L) to flow rates (m3/d)
        # Assumes dosing solutions with standard commercial concentrations:
        #   - NaOH: 431.25 kg/m³ S_Na (commercial 50% NaOH)
        #   - FeCl3: 400.0 kg/m³ S_Fe (commercial 35-42 wt% FeCl3·6H2O)
        #   - Na2CO3: 106.0 kg/m³ S_Na (soda ash solution)
        Q_influent = basis.get('Q', 1000)  # m3/d

        naoh_conc_kg_m3 = 431.25  # Commercial 50% NaOH
        fecl3_conc_kg_m3 = 400.0  # Commercial 35-42 wt% FeCl3·6H2O solution
        na2co3_conc_kg_m3 = 106.0  # Soda ash solution

        # Calculate flow rates from target concentrations
        naoh_flow_m3_d = (naoh_dose_mg_L * Q_influent) / (naoh_conc_kg_m3 * 1000) if naoh_dose_mg_L > 0 else 0
        fecl3_flow_m3_d = (fecl3_dose_mg_L * Q_influent) / (fecl3_conc_kg_m3 * 1000) if fecl3_dose_mg_L > 0 else 0
        na2co3_flow_m3_d = (na2co3_dose_mg_L * Q_influent) / (na2co3_conc_kg_m3 * 1000) if na2co3_dose_mg_L > 0 else 0

        # Log dosing configuration
        if any([fecl3_flow_m3_d, naoh_flow_m3_d, na2co3_flow_m3_d]):
            logger.info("Chemical dosing configuration:")
            if naoh_flow_m3_d > 0:
                logger.info(f"  NaOH: {naoh_dose_mg_L} mg/L target → {naoh_flow_m3_d:.4f} m³/d @ {naoh_conc_kg_m3:.2f} kg/m³")
            if fecl3_flow_m3_d > 0:
                logger.info(f"  FeCl3: {fecl3_dose_mg_L} mg/L target → {fecl3_flow_m3_d:.4f} m³/d @ {fecl3_conc_kg_m3:.2f} kg/m³")
            if na2co3_flow_m3_d > 0:
                logger.info(f"  Na2CO3: {na2co3_dose_mg_L} mg/L target → {na2co3_flow_m3_d:.4f} m³/d @ {na2co3_conc_kg_m3:.2f} kg/m³")

        # Run simulation(s)
        logger.info(f"Validate HRT: {validate_hrt}, Variation: ±{hrt_variation*100:.0f}%")

        if validate_hrt:
            # Dual-HRT simulation for robustness check (runs until convergence, no time limit)
            logger.info("Running dual-HRT validation...")
            results_design, results_check, warnings = run_dual_hrt_simulation(
                basis, adm1_state, heuristic_config, hrt_variation,
                check_interval=check_interval, tolerance=tolerance, pH_ctrl=pH_ctrl,
                fixed_naoh_dose_m3_d=naoh_flow_m3_d,
                fixed_fecl3_dose_m3_d=fecl3_flow_m3_d,
                fixed_na2co3_dose_m3_d=na2co3_flow_m3_d,
                naoh_conc_kg_m3=naoh_conc_kg_m3,
                fecl3_conc_kg_m3=fecl3_conc_kg_m3,
                na2co3_conc_kg_m3=na2co3_conc_kg_m3
            )

            # Unpack results
            sys_d, inf_d, eff_d, gas_d, converged_at_d, status_d, time_series_d = results_design
            sys_c, inf_c, eff_c, gas_c, converged_at_c, status_c, time_series_c = results_check

            logger.info(f"Design HRT: {status_d} at t={converged_at_d} days")
            logger.info(f"Check HRT: {status_c} at t={converged_at_c} days")

            if warnings:
                logger.warning(f"Robustness warnings: {len(warnings)}")
                for warning in warnings:
                    logger.warning(f"  - {warning}")
        else:
            # Single simulation at design SRT (for CSTR, SRT = HRT, runs until convergence)
            SRT_design = heuristic_config['digester']['srt_days']
            logger.info(f"Running single simulation at design SRT={SRT_design} days (no time limit)...")
            sys_d, inf_d, eff_d, gas_d, converged_at_d, status_d, time_series_d = run_simulation_sulfur(
                basis, adm1_state, SRT_design,
                check_interval=check_interval, tolerance=tolerance, pH_ctrl=pH_ctrl,
                fixed_naoh_dose_m3_d=naoh_flow_m3_d,
                fixed_fecl3_dose_m3_d=fecl3_flow_m3_d,
                fixed_na2co3_dose_m3_d=na2co3_flow_m3_d,
                naoh_conc_kg_m3=naoh_conc_kg_m3,
                fecl3_conc_kg_m3=fecl3_conc_kg_m3,
                na2co3_conc_kg_m3=na2co3_conc_kg_m3
            )
            logger.info(f"Simulation: {status_d} at t={converged_at_d} days")
            warnings = []
            time_series_c = None  # No check simulation in single mode

        # Analyze results
        logger.info("Analyzing simulation results...")
        influent = analyze_liquid_stream(inf_d, include_components=True)
        effluent = analyze_liquid_stream(eff_d, include_components=True)
        biogas = analyze_gas_stream(gas_d, inf_d, eff_d)

        # Extract comprehensive diagnostic data from mADM1 (needed for yields)
        logger.info("Extracting comprehensive diagnostic data...")
        diagnostics = extract_diagnostics(sys_d)

        # Calculate yields with detailed breakdown (pass system and diagnostics)
        yields = analyze_biomass_yields(inf_d, eff_d, system=sys_d, diagnostics=diagnostics)

        sulfur = calculate_sulfur_metrics(inf_d, eff_d, gas_d)
        inhibition = analyze_inhibition((sys_d, inf_d, eff_d, gas_d), speciation=sulfur.get("speciation"))

        if diagnostics.get('success'):
            logger.info(f"Diagnostic data extraction successful:")
            logger.info(f"  - {len(diagnostics.get('biomass_kg_m3', {}))} biomass functional groups")
            logger.info(f"  - {len(diagnostics.get('process_rates', []))} process rates")
            logger.info(f"  - {len(diagnostics.get('inhibition', {}))} inhibition categories")
        else:
            logger.warning(f"Diagnostic data extraction failed: {diagnostics.get('message', 'Unknown error')}")

        logger.info(f"COD removal: {yields.get('COD_removal_efficiency', 0):.1f}%")
        logger.info(f"Biogas: {biogas.get('flow_total', 0):.1f} m3/d, "
                   f"CH4: {biogas.get('methane_percent', 0):.1f}%")
        logger.info(f"H2S: {biogas.get('h2s_ppm', 0):.1f} ppm")

        # Build validation section if dual-HRT was run
        validation_results = None
        if validate_hrt:
            effluent_check = analyze_liquid_stream(eff_c)
            biogas_check = analyze_gas_stream(gas_c, inf_c, eff_c)
            yields_check = analyze_biomass_yields(inf_c, eff_c, system=sys_c)

            validation_results = {
                "hrt_design": heuristic_config['digester']['HRT_days'],
                "hrt_check": heuristic_config['digester']['HRT_days'] * (1 + hrt_variation),
                "converged_at_design": converged_at_d,
                "converged_at_check": converged_at_c,
                "status_design": status_d,
                "status_check": status_c,
                "performance_comparison": {
                    "cod_removal_design": yields.get('COD_removal_efficiency', 0),
                    "cod_removal_check": yields_check.get('COD_removal_efficiency', 0),
                    "biogas_design": biogas.get('flow_total', 0),
                    "biogas_check": biogas_check.get('flow_total', 0),
                    "methane_pct_design": biogas.get('methane_percent', 0),
                    "methane_pct_check": biogas_check.get('methane_percent', 0),
                    "h2s_ppm_design": biogas.get('h2s_ppm', 0),
                    "h2s_ppm_check": biogas_check.get('h2s_ppm', 0)
                },
                "warnings": warnings
            }

        # Calculate runtime
        end_time = datetime.now()
        runtime_seconds = (end_time - start_time).total_seconds()

        logger.info(f"Simulation completed in {runtime_seconds:.1f} seconds")

        # Build result structure
        result = {
            "success": True,
            "message": f"Simulation completed: {status_d} at t={converged_at_d} days",
            "streams": {
                "influent": influent,
                "effluent": effluent,
                "biogas": biogas
            },
            "performance": {
                "yields": yields,
                "inhibition": inhibition
            },
            "sulfur": sulfur,
            "diagnostics": diagnostics,  # Comprehensive diagnostic data from mADM1
            "validation": validation_results,
            "convergence": {
                "converged_at_days": converged_at_d,
                "status": status_d,
                "runtime_seconds": runtime_seconds
            },
            "time_series": {
                "design": time_series_d,
                "check": time_series_c if validate_hrt else None
            }
        }

        # Save legacy results file (for backward compatibility)
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        logger.info(f"Legacy results saved to {output_file} (deprecated)")

        # Generate formatted output files
        logger.info("Generating formatted output files...")
        from utils.output_formatters import (
            calculate_vfa_alkalinity,
            format_performance_output,
            format_inhibition_output,
            format_precipitation_output,
            format_timeseries_output
        )

        # Calculate VFA/Alkalinity metrics
        inf_vfa_alk = calculate_vfa_alkalinity(influent, influent['pH'])
        eff_vfa_alk = calculate_vfa_alkalinity(effluent, effluent['pH'])

        # Format and save performance output
        performance_output = format_performance_output(result, inf_vfa_alk, eff_vfa_alk)
        with open('simulation_performance.json', 'w') as f:
            json.dump(performance_output, f, indent=2)
        logger.info("  ✓ simulation_performance.json")

        # Format and save inhibition output
        inhibition_output = format_inhibition_output(diagnostics)
        with open('simulation_inhibition.json', 'w') as f:
            json.dump(inhibition_output, f, indent=2)
        logger.info("  ✓ simulation_inhibition.json")

        # Format and save precipitation output
        precipitation_output = format_precipitation_output(diagnostics, effluent)
        with open('simulation_precipitation.json', 'w') as f:
            json.dump(precipitation_output, f, indent=2)
        logger.info("  ✓ simulation_precipitation.json")

        # Format and save timeseries output
        timeseries_output = format_timeseries_output(result)
        with open('simulation_timeseries.json', 'w') as f:
            json.dump(timeseries_output, f, indent=2)
        logger.info("  ✓ simulation_timeseries.json")

        logger.info("=== Simulation Complete ===")

        return result

    except Exception as e:
        logger.error(f"Error in simulation: {str(e)}", exc_info=True)
        result = {
            "success": False,
            "message": f"Simulation failed: {str(e)}"
        }
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        return result


def main():
    parser = argparse.ArgumentParser(
        description='Run QSDsan ADM1+sulfur simulation from CLI'
    )
    parser.add_argument(
        '--basis',
        required=True,
        help='Path to basis of design JSON file'
    )
    parser.add_argument(
        '--adm1-state',
        required=True,
        help='Path to ADM1 state JSON file (30 components)'
    )
    parser.add_argument(
        '--heuristic-config',
        required=True,
        help='Path to heuristic config JSON file'
    )
    parser.add_argument(
        '--validate-hrt',
        action='store_true',
        default=True,
        help='Run dual-HRT validation (default: True)'
    )
    parser.add_argument(
        '--no-validate-hrt',
        dest='validate_hrt',
        action='store_false',
        help='Skip dual-HRT validation'
    )
    parser.add_argument(
        '--hrt-variation',
        type=float,
        default=0.2,
        help='HRT variation for validation (default: 0.2 = ±20%%)'
    )
    parser.add_argument(
        '--check-interval',
        type=float,
        default=2,
        help='Days between convergence checks (default: 2, for faster detection)'
    )
    parser.add_argument(
        '--tolerance',
        type=float,
        default=1e-3,
        help='Convergence tolerance in kg/m3/d (default: 1e-3, relaxed from 5e-4 to avoid numerical noise)'
    )
    parser.add_argument(
        '--fecl3-dose',
        type=float,
        default=0,
        help='FeCl3 dose in mg/L for sulfide/phosphate precipitation (default: 0)'
    )
    parser.add_argument(
        '--naoh-dose',
        type=float,
        default=0,
        help='NaOH dose in mg/L for pH control (default: 0)'
    )
    parser.add_argument(
        '--na2co3-dose',
        type=float,
        default=0,
        help='Na2CO3 dose in mg/L for alkalinity adjustment (default: 0)'
    )
    parser.add_argument(
        '--pH-ctrl',
        type=float,
        default=None,
        help='Fix pH at this value (e.g., 7.0) to emulate perfect pH control for diagnostic testing'
    )
    parser.add_argument(
        '--output',
        default='simulation_results.json',
        help='Path to save results JSON (default: simulation_results.json)'
    )

    args = parser.parse_args()

    result = run_simulation(
        basis_file=args.basis,
        adm1_state_file=args.adm1_state,
        heuristic_config_file=args.heuristic_config,
        validate_hrt=args.validate_hrt,
        hrt_variation=args.hrt_variation,
        check_interval=args.check_interval,
        tolerance=args.tolerance,
        output_file=args.output,
        fecl3_dose_mg_L=args.fecl3_dose,
        naoh_dose_mg_L=args.naoh_dose,
        na2co3_dose_mg_L=args.na2co3_dose,
        pH_ctrl=args.pH_ctrl
    )

    # Exit with appropriate code
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
