#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Heuristic sizing calculations for anaerobic digester design.

This module implements the sizing logic based on COD load, biomass yield,
and TSS concentration to determine digester volume and flowsheet configuration.
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
    
    Args:
        feed_flow_m3d: Feed flow rate in m³/day
        cod_mg_l: COD concentration in mg/L
        biomass_yield: Biomass yield in kg TSS/kg COD (default 0.1)
    
    Returns:
        Tuple of (cod_load_kg_d, biomass_production_kg_d)
    """
    config = SizingConfig()
    
    if biomass_yield is None:
        biomass_yield = config.biomass_yield_default
    
    # Calculate COD load
    cod_load_kg_d = feed_flow_m3d * cod_mg_l / 1000.0  # kg/day
    
    # Calculate biomass production
    biomass_production_kg_d = cod_load_kg_d * biomass_yield  # kg TSS/day
    
    return cod_load_kg_d, biomass_production_kg_d


def calculate_digester_tss_concentration(
    feed_flow_m3d: float,
    biomass_production_kg_d: float,
    existing_tss_mg_l: Optional[float] = None
) -> float:
    """
    Calculate expected TSS concentration in digester.
    
    Args:
        feed_flow_m3d: Feed flow rate in m³/day
        biomass_production_kg_d: Biomass production in kg TSS/day
        existing_tss_mg_l: Existing TSS in feed (mg/L)
    
    Returns:
        Expected TSS concentration in mg/L
    """
    # Calculate TSS from biomass production
    tss_from_biomass = (biomass_production_kg_d / feed_flow_m3d) * 1000.0  # mg/L
    
    # Add existing TSS if provided
    if existing_tss_mg_l:
        total_tss = existing_tss_mg_l + tss_from_biomass
    else:
        total_tss = tss_from_biomass
    
    return total_tss


def size_high_tss_configuration(
    feed_flow_m3d: float,
    target_srt_days: float,
    safety_factor: Optional[float] = None
) -> Dict[str, Any]:
    """
    Size digester for high TSS configuration (>10,000 mg/L).
    Simple digester with HRT = SRT, followed by full dewatering.
    
    Args:
        feed_flow_m3d: Feed flow rate in m³/day
        target_srt_days: Target SRT in days
        safety_factor: Safety factor for volume sizing
    
    Returns:
        Configuration dictionary
    """
    config = SizingConfig()
    
    if safety_factor is None:
        safety_factor = config.safety_factor
    
    # For high TSS, HRT = SRT
    hrt_days = target_srt_days
    
    # Calculate digester volume
    digester_volume_m3 = feed_flow_m3d * hrt_days * safety_factor
    
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
            "description": "Dewater all digestate",
            "expected_load_kg_d": None  # Will be calculated in simulation
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
    Size digester with anaerobic MBR for low TSS configuration (<10,000 mg/L).
    Maintains high MLSS using membrane retention.
    
    Args:
        feed_flow_m3d: Feed flow rate in m³/day
        cod_load_kg_d: COD load in kg/day
        biomass_yield: Biomass yield in kg TSS/kg COD
        target_mlss_mg_l: Target MLSS concentration in mg/L
        target_srt_days: Target SRT in days
        mbr_flux_lmh: MBR flux in L/m²/h
        safety_factor: Safety factor for volume sizing
    
    Returns:
        Configuration dictionary
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
    
    # Calculate digester volume to maintain target MLSS
    # Volume = (Biomass production * SRT) / MLSS concentration
    digester_volume_m3 = (biomass_production_kg_d * target_srt_days * 1000.0) / target_mlss_mg_l
    digester_volume_m3 *= safety_factor
    
    # Calculate HRT (will be less than SRT due to biomass retention)
    hrt_days = digester_volume_m3 / feed_flow_m3d
    
    # Calculate MBR membrane area
    permeate_flow_m3h = feed_flow_m3d / 24.0  # m³/h
    membrane_area_m2 = (permeate_flow_m3h * 1000.0) / mbr_flux_lmh  # m²
    
    # Calculate waste sludge flow for SRT control
    # Waste flow = Biomass production / MLSS concentration
    waste_sludge_m3d = (biomass_production_kg_d * 1000.0) / target_mlss_mg_l
    
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
            "expected_load_kg_d": round(biomass_production_kg_d, 2),
            "waste_sludge_flow_m3d": round(waste_sludge_m3d, 3)
        }
    }


def perform_heuristic_sizing(
    basis_of_design: Dict[str, Any],
    biomass_yield: Optional[float] = None,
    target_srt_days: Optional[float] = None
) -> Dict[str, Any]:
    """
    Main heuristic sizing function that determines configuration and sizes equipment.
    
    Args:
        basis_of_design: Dictionary with feed_flow_m3d, cod_mg_l, and optional tss_mg_l
        biomass_yield: Biomass yield in kg TSS/kg COD
        target_srt_days: Target SRT in days
    
    Returns:
        Complete sizing configuration with flowsheet selection
    """
    config = SizingConfig()
    
    # Extract required parameters
    feed_flow_m3d = basis_of_design.get("feed_flow_m3d")
    cod_mg_l = basis_of_design.get("cod_mg_l")
    existing_tss_mg_l = basis_of_design.get("tss_mg_l")
    
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
    
    # Calculate expected TSS concentration
    expected_tss_mg_l = calculate_digester_tss_concentration(
        feed_flow_m3d, biomass_production_kg_d, existing_tss_mg_l
    )
    
    # Determine flowsheet configuration based on TSS
    if expected_tss_mg_l > config.max_tss_without_mbr:
        # High TSS: Use simple digester with full dewatering
        configuration = size_high_tss_configuration(
            feed_flow_m3d, target_srt_days
        )
        flowsheet_decision = "high_tss"
        decision_reason = f"TSS concentration ({expected_tss_mg_l:.0f} mg/L) exceeds {config.max_tss_without_mbr:.0f} mg/L"
    else:
        # Low TSS: Use AnMBR to concentrate biomass
        configuration = size_low_tss_mbr_configuration(
            feed_flow_m3d, cod_load_kg_d, biomass_yield,
            target_srt_days=target_srt_days
        )
        flowsheet_decision = "low_tss_mbr"
        decision_reason = f"TSS concentration ({expected_tss_mg_l:.0f} mg/L) below {config.max_tss_without_mbr:.0f} mg/L, using MBR to maintain {config.target_mlss_with_mbr:.0f} mg/L MLSS"
    
    # Add summary information
    result = {
        **configuration,
        "sizing_basis": {
            "feed_flow_m3d": feed_flow_m3d,
            "cod_mg_l": cod_mg_l,
            "cod_load_kg_d": round(cod_load_kg_d, 1),
            "biomass_yield_kg_tss_kg_cod": biomass_yield,
            "biomass_production_kg_d": round(biomass_production_kg_d, 2),
            "expected_tss_mg_l": round(expected_tss_mg_l, 0),
            "target_srt_days": target_srt_days
        },
        "flowsheet_decision": {
            "selected": flowsheet_decision,
            "reason": decision_reason,
            "tss_threshold_mg_l": config.max_tss_without_mbr
        }
    }
    
    return result