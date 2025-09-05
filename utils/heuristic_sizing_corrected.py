#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CORRECTED Heuristic sizing calculations for anaerobic digester design.

Key fixes:
1. TSS calculation based on biomass production rate only
2. Proper volume calculations for MBR configuration
3. Clear arithmetic documentation
"""

import logging
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SizingConfig:
    """Configuration parameters for heuristic sizing."""
    biomass_yield_default: float = 0.1  # kg TSS/kg COD
    target_srt_days: float = 30.0  # days
    max_tss_without_mbr: float = 10000.0  # mg/L
    target_mlss_with_mbr: float = 15000.0  # mg/L
    mbr_flux_lmh: float = 10.0  # L/m²/h (conservative for AnMBR)
    safety_factor: float = 1.1  # 10% safety margin on volume


def calculate_biomass_production(
    feed_flow_m3d: float,
    cod_mg_l: float,
    biomass_yield: Optional[float] = None
) -> Tuple[float, float]:
    """
    Calculate biomass production from COD load.
    
    Example:
        Feed: 500 m³/d at 30,000 mg/L COD
        COD load: 500 * 30,000 / 1000 = 15,000 kg COD/d
        Biomass: 15,000 * 0.1 = 1,500 kg TSS/d
    """
    config = SizingConfig()
    
    if biomass_yield is None:
        biomass_yield = config.biomass_yield_default
    
    # Calculate COD load
    cod_load_kg_d = feed_flow_m3d * cod_mg_l / 1000.0  # kg/day
    
    # Calculate biomass production
    biomass_production_kg_d = cod_load_kg_d * biomass_yield  # kg TSS/day
    
    logger.info(f"COD load: {cod_load_kg_d:.1f} kg/d, Biomass production: {biomass_production_kg_d:.1f} kg/d")
    
    return cod_load_kg_d, biomass_production_kg_d


def calculate_steady_state_tss(
    biomass_production_kg_d: float,
    feed_flow_m3d: float
) -> float:
    """
    Calculate steady-state TSS concentration based on biomass production.
    
    For a simple digester at steady state with SRT = HRT:
    TSS concentration = (Biomass production rate * SRT) / Volume
    Since Volume = Flow * HRT and HRT = SRT:
    TSS concentration = Biomass production rate / Flow
    
    Example:
        Biomass: 1,500 kg TSS/d
        Flow: 500 m³/d
        TSS: 1,500 / 500 = 3 kg/m³ = 3,000 mg/L
    """
    # TSS concentration from biomass production at steady state
    tss_kg_m3 = biomass_production_kg_d / feed_flow_m3d  # kg/m³
    tss_mg_l = tss_kg_m3 * 1000.0  # mg/L
    
    logger.info(f"Steady-state TSS: {tss_mg_l:.0f} mg/L")
    
    return tss_mg_l


def size_high_tss_configuration(
    feed_flow_m3d: float,
    target_srt_days: float,
    safety_factor: Optional[float] = None
) -> Dict[str, Any]:
    """
    Size digester for high TSS configuration (>10,000 mg/L).
    
    Example:
        Feed: 500 m³/d
        SRT: 30 days
        Volume: 500 * 30 * 1.1 = 16,500 m³
    """
    config = SizingConfig()
    
    if safety_factor is None:
        safety_factor = config.safety_factor
    
    # For high TSS, HRT = SRT
    hrt_days = target_srt_days
    
    # Calculate digester volume
    base_volume = feed_flow_m3d * hrt_days
    digester_volume_m3 = base_volume * safety_factor
    
    logger.info(f"High TSS config: Volume = {feed_flow_m3d} * {hrt_days} * {safety_factor} = {digester_volume_m3:.0f} m³")
    
    return {
        "flowsheet_type": "high_tss",
        "description": "Anaerobic digester with full dewatering",
        "digester": {
            "volume_m3": round(digester_volume_m3, 1),
            "hrt_days": hrt_days,
            "srt_days": target_srt_days,
            "type": "CSTR"
        },
        "mbr": {
            "required": False
        },
        "dewatering": {
            "type": "full",
            "description": "Dewater all digestate"
        }
    }


def size_low_tss_mbr_configuration(
    feed_flow_m3d: float,
    cod_load_kg_d: float,
    biomass_yield: float,
    target_mlss_mg_l: Optional[float] = None,
    target_srt_days: Optional[float] = None,
    mbr_flux_lmh: Optional[float] = None,
    safety_factor: Optional[float] = None
) -> Dict[str, Any]:
    """
    Size digester with anaerobic MBR for low TSS configuration.
    
    Volume calculation:
    At steady state: Biomass inventory = Production rate * SRT
    Volume = Biomass inventory / MLSS concentration
    
    Example:
        COD load: 12,000 kg/d
        Yield: 0.15 kg TSS/kg COD
        Biomass production: 1,800 kg/d
        SRT: 20 days
        Biomass inventory: 1,800 * 20 = 36,000 kg
        MLSS target: 15,000 mg/L = 15 kg/m³
        Volume: 36,000 / 15 = 2,400 m³
        With safety: 2,400 * 1.1 = 2,640 m³
    """
    config = SizingConfig()
    
    if target_mlss_mg_l is None:
        target_mlss_mg_l = config.target_mlss_with_mbr
    if target_srt_days is None:
        target_srt_days = config.target_srt_days
    if mbr_flux_lmh is None:
        mbr_flux_lmh = config.mbr_flux_lmh
    if safety_factor is None:
        safety_factor = config.safety_factor
    
    # Calculate biomass production
    biomass_production_kg_d = cod_load_kg_d * biomass_yield
    
    # Calculate biomass inventory at steady state
    biomass_inventory_kg = biomass_production_kg_d * target_srt_days
    
    # Calculate digester volume to maintain target MLSS
    # MLSS in kg/m³
    target_mlss_kg_m3 = target_mlss_mg_l / 1000.0
    
    # Volume = Biomass inventory / MLSS concentration
    base_volume = biomass_inventory_kg / target_mlss_kg_m3
    digester_volume_m3 = base_volume * safety_factor
    
    # Calculate HRT (will be less than SRT due to biomass retention)
    hrt_days = digester_volume_m3 / feed_flow_m3d
    
    logger.info(f"MBR config: Biomass inventory = {biomass_production_kg_d:.0f} * {target_srt_days} = {biomass_inventory_kg:.0f} kg")
    logger.info(f"MBR config: Volume = {biomass_inventory_kg:.0f} / {target_mlss_kg_m3:.1f} * {safety_factor} = {digester_volume_m3:.0f} m³")
    
    # Calculate MBR membrane area
    permeate_flow_m3h = feed_flow_m3d / 24.0  # m³/h
    membrane_area_m2 = (permeate_flow_m3h * 1000.0) / mbr_flux_lmh  # m²
    
    # Calculate waste sludge flow for SRT control
    # Waste flow = Biomass production / MLSS concentration
    waste_sludge_m3d = biomass_production_kg_d / target_mlss_kg_m3
    
    return {
        "flowsheet_type": "low_tss_mbr",
        "description": "Anaerobic digester with MBR for biomass retention",
        "digester": {
            "volume_m3": round(digester_volume_m3, 1),
            "hrt_days": round(hrt_days, 2),
            "srt_days": target_srt_days,
            "mlss_mg_l": target_mlss_mg_l,
            "type": "AnMBR"
        },
        "mbr": {
            "required": True,
            "membrane_area_m2": round(membrane_area_m2, 1),
            "flux_lmh": mbr_flux_lmh,
            "permeate_flow_m3d": feed_flow_m3d,
            "type": "submerged"
        },
        "dewatering": {
            "type": "excess_biomass_only",
            "description": "Dewater only excess biomass",
            "biomass_production_kg_d": round(biomass_production_kg_d, 2),
            "waste_sludge_flow_m3d": round(waste_sludge_m3d, 3)
        },
        "calculation_details": {
            "biomass_inventory_kg": round(biomass_inventory_kg, 0),
            "base_volume_m3": round(base_volume, 0),
            "safety_factor": safety_factor
        }
    }


def perform_heuristic_sizing(
    basis_of_design: Dict[str, Any],
    biomass_yield: Optional[float] = None,
    target_srt_days: Optional[float] = None
) -> Dict[str, Any]:
    """
    Main heuristic sizing function with corrected arithmetic.
    """
    config = SizingConfig()
    
    # Extract required parameters
    feed_flow_m3d = basis_of_design.get("feed_flow_m3d")
    cod_mg_l = basis_of_design.get("cod_mg_l")
    
    if not feed_flow_m3d or not cod_mg_l:
        raise ValueError("feed_flow_m3d and cod_mg_l are required in basis_of_design")
    
    if biomass_yield is None:
        biomass_yield = config.biomass_yield_default
    if target_srt_days is None:
        target_srt_days = config.target_srt_days
    
    # Calculate biomass production
    cod_load_kg_d, biomass_production_kg_d = calculate_biomass_production(
        feed_flow_m3d, cod_mg_l, biomass_yield
    )
    
    # Calculate steady-state TSS concentration
    steady_state_tss_mg_l = calculate_steady_state_tss(
        biomass_production_kg_d, feed_flow_m3d
    )
    
    # Determine flowsheet configuration based on TSS
    if steady_state_tss_mg_l > config.max_tss_without_mbr:
        # High TSS: Use simple digester with full dewatering
        configuration = size_high_tss_configuration(
            feed_flow_m3d, target_srt_days
        )
        flowsheet_decision = "high_tss"
        decision_reason = f"TSS concentration ({steady_state_tss_mg_l:.0f} mg/L) exceeds {config.max_tss_without_mbr:.0f} mg/L"
    else:
        # Low TSS: Use AnMBR to concentrate biomass
        configuration = size_low_tss_mbr_configuration(
            feed_flow_m3d, cod_load_kg_d, biomass_yield,
            target_srt_days=target_srt_days
        )
        flowsheet_decision = "low_tss_mbr"
        decision_reason = f"TSS concentration ({steady_state_tss_mg_l:.0f} mg/L) below {config.max_tss_without_mbr:.0f} mg/L, using MBR to maintain {config.target_mlss_with_mbr:.0f} mg/L MLSS"
    
    # Add summary information
    result = {
        **configuration,
        "sizing_basis": {
            "feed_flow_m3d": feed_flow_m3d,
            "cod_mg_l": cod_mg_l,
            "cod_load_kg_d": round(cod_load_kg_d, 1),
            "biomass_yield_kg_tss_kg_cod": biomass_yield,
            "biomass_production_kg_d": round(biomass_production_kg_d, 2),
            "steady_state_tss_mg_l": round(steady_state_tss_mg_l, 0),
            "target_srt_days": target_srt_days
        },
        "flowsheet_decision": {
            "selected": flowsheet_decision,
            "reason": decision_reason,
            "tss_threshold_mg_l": config.max_tss_without_mbr
        }
    }
    
    return result


# Test the arithmetic
if __name__ == "__main__":
    print("TEST CASE 1: 500 m³/d, 30,000 mg/L COD, yield 0.1")
    print("-" * 50)
    test1 = perform_heuristic_sizing(
        {"feed_flow_m3d": 500, "cod_mg_l": 30000},
        biomass_yield=0.1,
        target_srt_days=30
    )
    print(f"COD load: {test1['sizing_basis']['cod_load_kg_d']} kg/d")
    print(f"Biomass production: {test1['sizing_basis']['biomass_production_kg_d']} kg/d")
    print(f"Steady-state TSS: {test1['sizing_basis']['steady_state_tss_mg_l']} mg/L")
    print(f"Flowsheet: {test1['flowsheet_type']}")
    print(f"Volume: {test1['digester']['volume_m3']} m³")
    
    print("\nTEST CASE 2: 100 m³/d, 150,000 mg/L COD, yield 0.1")
    print("-" * 50)
    test2 = perform_heuristic_sizing(
        {"feed_flow_m3d": 100, "cod_mg_l": 150000},
        biomass_yield=0.1,
        target_srt_days=30
    )
    print(f"COD load: {test2['sizing_basis']['cod_load_kg_d']} kg/d")
    print(f"Biomass production: {test2['sizing_basis']['biomass_production_kg_d']} kg/d")
    print(f"Steady-state TSS: {test2['sizing_basis']['steady_state_tss_mg_l']} mg/L")
    print(f"Flowsheet: {test2['flowsheet_type']}")
    print(f"Volume: {test2['digester']['volume_m3']} m³")
    
    print("\nTEST CASE 3: 200 m³/d, 60,000 mg/L COD, yield 0.15, SRT 20")
    print("-" * 50)
    test3 = perform_heuristic_sizing(
        {"feed_flow_m3d": 200, "cod_mg_l": 60000},
        biomass_yield=0.15,
        target_srt_days=20
    )
    print(f"COD load: {test3['sizing_basis']['cod_load_kg_d']} kg/d")
    print(f"Biomass production: {test3['sizing_basis']['biomass_production_kg_d']} kg/d")
    print(f"Steady-state TSS: {test3['sizing_basis']['steady_state_tss_mg_l']} mg/L")
    print(f"Flowsheet: {test3['flowsheet_type']}")
    print(f"Volume: {test3['digester']['volume_m3']} m³")
    if test3['flowsheet_type'] == 'low_tss_mbr':
        print(f"Biomass inventory: {test3['calculation_details']['biomass_inventory_kg']} kg")
        print(f"Base volume (no safety): {test3['calculation_details']['base_volume_m3']} m³")