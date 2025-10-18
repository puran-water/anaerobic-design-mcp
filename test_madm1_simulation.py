#!/usr/bin/env python
"""
Quick test script for mADM1 simulation.

Tests the complete mADM1 workflow without MCP server overhead.
"""

import sys
import json
import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Run mADM1 simulation test."""
    from utils.qsdsan_simulation_madm1 import run_madm1_simulation

    # Load input files
    with open('simulation_basis.json', 'r') as f:
        basis = json.load(f)
    with open('simulation_adm1_state.json', 'r') as f:
        adm1_state = json.load(f)
    with open('simulation_heuristic_config.json', 'r') as f:
        heuristic_config = json.load(f)

    logger.info("="*80)
    logger.info("Testing mADM1 Simulation")
    logger.info("="*80)
    logger.info(f"Basis: Q={basis.get('Q')} m3/d, T={basis.get('Temp')} K")
    logger.info(f"HRT: {heuristic_config['digester']['HRT_days']} days")
    logger.info(f"ADM1 state: {len(adm1_state)} components")

    try:
        sys, inf, eff, gas, converged_at, status = await run_madm1_simulation(
            basis, adm1_state, heuristic_config
        )

        logger.info("="*80)
        logger.info("SUCCESS - mADM1 Simulation Completed!")
        logger.info("="*80)
        logger.info(f"Status: {status}")
        logger.info(f"Converged at: {converged_at} days")
        logger.info(f"Influent: Q={inf.F_vol:.1f} m3/d, pH={inf.pH:.2f}")

        # Check if effluent is liquid or gas phase
        if eff.phase == 'l':
            logger.info(f"Effluent: Q={eff.F_vol:.1f} m3/d, pH={eff.pH:.2f}")
        else:
            logger.info(f"Effluent: Q={eff.F_vol:.1f} m3/d, phase={eff.phase}")

        logger.info(f"Biogas: Q={gas.F_vol:.1f} m3/d")

        # Check biogas composition
        logger.info(f"Biogas composition:")
        if 'S_ch4' in gas.components.IDs:
            logger.info(f"  CH4: {gas.imass['S_ch4']:.4f} kg/d")
        if 'S_IS' in gas.components.IDs:
            logger.info(f"  H2S: {gas.imass['S_IS']:.4f} kg/d")
        if 'S_IC' in gas.components.IDs:
            logger.info(f"  CO2: {gas.imass['S_IC']:.4f} kg/d")
        if 'S_h2' in gas.components.IDs:
            logger.info(f"  H2:  {gas.imass['S_h2']:.6f} kg/d")

        return 0

    except Exception as e:
        logger.error(f"FAILED: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
