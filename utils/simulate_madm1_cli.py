#!/usr/bin/env python
"""
CLI script for running QSDsan mADM1 (Modified ADM1) simulations.

This script handles the complete mADM1 simulation with 62 components.
"""

import sys
import json
import argparse
import logging
import anyio
from pathlib import Path
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def run_simulation(
    basis_file: str,
    adm1_state_file: str,
    heuristic_config_file: str,
    output_file: str = 'simulation_results.json'
):
    """
    Run QSDsan mADM1 simulation from JSON input files.

    Args:
        basis_file: Path to basis of design JSON
        adm1_state_file: Path to ADM1 state JSON (62 components)
        heuristic_config_file: Path to heuristic config JSON
        output_file: Path to save results JSON
    """
    try:
        start_time = datetime.now()

        # Load input files
        logger.info("Loading input files...")
        with open(basis_file, 'r') as f:
            basis = json.load(f)
        with open(adm1_state_file, 'r') as f:
            adm1_state = json.load(f)
        with open(heuristic_config_file, 'r') as f:
            heuristic_config = json.load(f)

        logger.info(f"Basis: Q={basis.get('Q', 'N/A')} m3/d, T={basis.get('Temp', 'N/A')} K")
        logger.info(f"ADM1 state: {len(adm1_state)} components")
        logger.info(f"HRT: {heuristic_config['digester']['HRT_days']} days")

        # Import simulation modules
        logger.info("Loading mADM1 simulation module...")
        from utils.qsdsan_simulation_madm1 import run_madm1_simulation

        # Run simulation
        logger.info("Running mADM1 simulation...")
        sys_d, inf_d, eff_d, gas_d, converged_at_d, status_d = await run_madm1_simulation(
            basis, adm1_state, heuristic_config
        )
        logger.info(f"Simulation: {status_d} at t={converged_at_d} days")

        # Analyze results
        logger.info("Analyzing simulation results...")

        # Extract inhibition factors from the mADM1 model
        def analyze_inhibition(sys_d):
            """Extract inhibition factors from mADM1 simulation."""
            try:
                root_data = sys_d._path[0].model.rate_function._params.get('root', {})
                if hasattr(root_data, 'data'):
                    root_data = root_data.data

                if not root_data:
                    return None

                # Extract inhibition factors from nested structure
                # (as populated by diagnostic hooks in qsdsan_madm1.py:887-940)
                pH_inhibition = root_data.get('I_pH', {})
                h2_inhibition = root_data.get('I_h2', {})
                h2s_inhibition = root_data.get('I_h2s', {})
                nutrients = root_data.get('I_nutrients', {})

                # Extract key inhibition factors
                inhibition = {
                    "pH": root_data.get('pH', 7.0),
                    "I_pH_ac": pH_inhibition.get('acetoclastic', 1.0),  # pH inhibition on acetoclastic methanogens
                    "I_pH_h2": pH_inhibition.get('hydrogenotrophic', 1.0),  # pH inhibition on hydrogenotrophic methanogens
                    "I_IN_lim": nutrients.get('I_IN_lim', 1.0),  # Nitrogen limitation
                    "I_h2_fa": h2_inhibition.get('LCFA', 1.0),  # H2 inhibition on LCFA uptake
                    "I_h2_c4": min(h2_inhibition.get('C4_valerate', 1.0), h2_inhibition.get('C4_butyrate', 1.0)),  # H2 inhibition on C4
                    "I_h2_pro": h2_inhibition.get('propionate', 1.0),  # H2 inhibition on propionate
                    "I_nh3": nutrients.get('I_nh3', 1.0),  # Free ammonia inhibition
                    "I_h2s_c4": min(h2s_inhibition.get('C4_valerate', 1.0), h2s_inhibition.get('C4_butyrate', 1.0)),  # H2S inhibition on C4
                    "I_h2s_pro": h2s_inhibition.get('propionate', 1.0),  # H2S inhibition on propionate
                    "I_h2s_ac": h2s_inhibition.get('acetate', 1.0),  # H2S inhibition on acetate
                    "I_h2s_h2": h2s_inhibition.get('hydrogen', 1.0)  # H2S inhibition on H2
                }

                # Calculate overall methanogen health
                # Acetoclastic: affected by pH, NH3, H2S
                acetoclastic_health = inhibition["I_pH_ac"] * inhibition["I_nh3"] * inhibition["I_h2s_ac"]
                # Hydrogenotrophic: affected by pH, H2S
                hydrogenotrophic_health = inhibition["I_pH_h2"] * inhibition["I_h2s_h2"]

                # Convert to inhibition percentages (0 = no inhibition, 100 = complete inhibition)
                def to_percent_inhibited(factor):
                    return (1.0 - factor) * 100

                return {
                    "pH": float(inhibition["pH"]),
                    "pH_inhibition_ac_pct": float(to_percent_inhibited(inhibition["I_pH_ac"])),
                    "pH_inhibition_h2_pct": float(to_percent_inhibited(inhibition["I_pH_h2"])),
                    "nitrogen_limitation_pct": float(to_percent_inhibited(inhibition["I_IN_lim"])),
                    "ammonia_inhibition_pct": float(to_percent_inhibited(inhibition["I_nh3"])),
                    "h2_inhibition_fa_pct": float(to_percent_inhibited(inhibition["I_h2_fa"])),
                    "h2_inhibition_c4_pct": float(to_percent_inhibited(inhibition["I_h2_c4"])),
                    "h2_inhibition_pro_pct": float(to_percent_inhibited(inhibition["I_h2_pro"])),
                    "h2s_inhibition_ac_pct": float(to_percent_inhibited(inhibition["I_h2s_ac"])),
                    "h2s_inhibition_h2_pct": float(to_percent_inhibited(inhibition["I_h2s_h2"])),
                    "acetoclastic_methanogen_health_pct": float(acetoclastic_health * 100),
                    "hydrogenotrophic_methanogen_health_pct": float(hydrogenotrophic_health * 100),
                    "overall_methanogen_health_pct": float(min(acetoclastic_health, hydrogenotrophic_health) * 100)
                }
            except Exception as e:
                logger.warning(f"Could not extract inhibition factors: {e}")
                return None

        # Simple stream analysis
        def analyze_stream(stream, name):
            """Extract basic metrics from a stream following ADM1 MCP server conventions."""
            # Convert F_vol from m3/hr to m3/d (matching ADM1 MCP server approach)
            flow_m3_d = float(stream.F_vol) * 24  # m3/hr → m3/d

            result = {
                "name": name,
                "F_vol_m3_d": flow_m3_d,
                "T_C": float(stream.T - 273.15),
                # Note: COD/TSS/TKN properties trigger component compilation errors due to duplicate CAS numbers
                # We'll calculate these manually in the performance section
                "total_mass_kg_d": float(stream.F_mass) * 24  # kg/hr → kg/d
            }
            # Only add pH for liquid streams (gas phase doesn't have pH)
            if stream.phase == 'l':
                result["pH"] = float(stream.pH)
            return result

        def analyze_biogas(stream):
            """Extract biogas metrics following QSDsan conventions."""
            # Total volumetric flow (m3/hr → m3/d)
            total_flow_m3_hr = float(stream.F_vol)
            total_flow_m3_d = total_flow_m3_hr * 24

            # Volumetric flows of individual components (m3/hr → m3/d)
            # Note: In mADM1, H2S is tracked as S_IS (inorganic sulfide), not S_h2s
            ch4_vol_m3_d = float(stream.ivol['S_ch4']) * 24 if 'S_ch4' in stream.components.IDs else 0
            co2_vol_m3_d = float(stream.ivol['S_IC']) * 24 if 'S_IC' in stream.components.IDs else 0
            h2_vol_m3_d = float(stream.ivol['S_h2']) * 24 if 'S_h2' in stream.components.IDs else 0
            h2s_vol_m3_d = float(stream.ivol['S_IS']) * 24 if 'S_IS' in stream.components.IDs else 0

            # Percentages by volume
            ch4_percent = (ch4_vol_m3_d / total_flow_m3_d * 100) if total_flow_m3_d > 0 else 0
            co2_percent = (co2_vol_m3_d / total_flow_m3_d * 100) if total_flow_m3_d > 0 else 0
            h2_percent = (h2_vol_m3_d / total_flow_m3_d * 100) if total_flow_m3_d > 0 else 0

            # H2S in ppm (parts per million by volume)
            h2s_ppm = (h2s_vol_m3_d / total_flow_m3_d * 1e6) if total_flow_m3_d > 0 else 0

            result = {
                "flow_total_m3_d": float(total_flow_m3_d),
                "flow_ch4_m3_d": float(ch4_vol_m3_d),
                "flow_co2_m3_d": float(co2_vol_m3_d),
                "flow_h2_m3_d": float(h2_vol_m3_d),
                "methane_percent": float(ch4_percent),
                "co2_percent": float(co2_percent),
                "h2_percent": float(h2_percent),
                "h2s_ppm": float(h2s_ppm)
            }
            return result

        influent = analyze_stream(inf_d, "influent")
        effluent = analyze_stream(eff_d, "effluent")
        biogas = analyze_biogas(gas_d)
        inhibition_analysis = analyze_inhibition(sys_d)

        # Calculate performance metrics from component masses
        # COD removal based on total organic mass change
        organic_in = influent['total_mass_kg_d']
        organic_out = effluent['total_mass_kg_d']
        mass_removal = (organic_in - organic_out) / organic_in * 100 if organic_in > 0 else 0

        logger.info(f"Organic mass removal: {mass_removal:.1f}%")
        logger.info(f"Biogas: {biogas['flow_total_m3_d']:.1f} m3/d, CH4: {biogas['methane_percent']:.1f}%")
        logger.info(f"H2S: {biogas['h2s_ppm']:.1f} ppm")

        if inhibition_analysis:
            logger.info(f"pH: {inhibition_analysis['pH']:.2f}")
            logger.info(f"Methanogen health: {inhibition_analysis['overall_methanogen_health_pct']:.1f}%")
            logger.info(f"NH3 inhibition: {inhibition_analysis['ammonia_inhibition_pct']:.1f}%")
            logger.info(f"H2 inhibition (pro): {inhibition_analysis['h2_inhibition_pro_pct']:.1f}%")

        # Calculate runtime
        end_time = datetime.now()
        runtime_seconds = (end_time - start_time).total_seconds()

        logger.info(f"Simulation completed in {runtime_seconds:.1f} seconds")

        # Build result structure
        result = {
            "success": True,
            "message": f"mADM1 simulation completed: {status_d} at t={converged_at_d} days",
            "model": "mADM1",
            "components": len(adm1_state),
            "streams": {
                "influent": influent,
                "effluent": effluent,
                "biogas": biogas
            },
            "performance": {
                "organic_mass_removal_percent": float(mass_removal),
                "biogas_yield_m3_per_m3_influent": float(biogas['flow_total_m3_d'] / influent['F_vol_m3_d']) if influent['F_vol_m3_d'] > 0 else 0
            },
            "inhibition": inhibition_analysis,
            "convergence": {
                "converged_at_days": float(converged_at_d),
                "status": status_d,
                "runtime_seconds": float(runtime_seconds)
            }
        }

        # Save results
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)

        logger.info(f"Results saved to {output_file}")
        logger.info("=== mADM1 Simulation Complete ===")

        return result

    except Exception as e:
        logger.error(f"Error in simulation: {str(e)}", exc_info=True)
        result = {
            "success": False,
            "message": f"mADM1 simulation failed: {str(e)}"
        }
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        return result


def main():
    parser = argparse.ArgumentParser(
        description='Run QSDsan mADM1 simulation from CLI'
    )
    parser.add_argument(
        '--basis',
        required=True,
        help='Path to basis of design JSON file'
    )
    parser.add_argument(
        '--adm1-state',
        required=True,
        help='Path to ADM1 state JSON file (62 components)'
    )
    parser.add_argument(
        '--heuristic-config',
        required=True,
        help='Path to heuristic config JSON file'
    )
    parser.add_argument(
        '--output',
        default='simulation_results.json',
        help='Path to save results JSON (default: simulation_results.json)'
    )

    args = parser.parse_args()

    # Run async simulation
    result = anyio.run(
        run_simulation,
        args.basis,
        args.adm1_state,
        args.heuristic_config,
        args.output
    )

    # Exit with appropriate code
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
