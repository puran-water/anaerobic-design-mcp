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
from typing import Dict, Any, Optional, Tuple, Literal
from dataclasses import dataclass
import math

logger = logging.getLogger(__name__)

# Import mixing calculations
try:
    from .mixing_calculations import (
        calculate_mechanical_mixing_power,
        calculate_pumped_mixing_power,
        ANAEROBIC_DIGESTER_MIXING_PRESETS
    )
except ImportError:
    from mixing_calculations import (
        calculate_mechanical_mixing_power,
        calculate_pumped_mixing_power,
        ANAEROBIC_DIGESTER_MIXING_PRESETS
    )


@dataclass
class SizingConfig:
    """Configuration parameters for heuristic sizing."""
    biomass_yield_default: float = 0.1  # kg TSS/kg COD
    target_srt_days: float = 30.0  # days
    max_tss_without_mbr: float = 10000.0  # mg/L
    target_mlss_with_mbr: float = 15000.0  # mg/L
    dewatering_hours_per_week: float = 40.0  # hours/week operation
    
    # Operating conditions
    pressure_atm_default: float = 1.0  # atm
    vapor_headspace_fraction: float = 0.10  # 10% of liquid volume
    
    # MBR configuration
    mbr_type_default: str = "submerged"  # or "external_crossflow"
    
    # Submerged MBR parameters
    submerged_flux_lmh: float = 5.0  # L/m²/h (conservative for AnMBR)
    submerged_module_m2: float = 12.0  # m² per module
    
    # External crossflow MBR parameters
    external_flux_lmh: float = 20.0  # L/m²/h
    external_module_m2: float = 35.8  # m² per module
    
    # MBR effluent quality
    permeate_tss_mg_l: float = 5.0  # mg/L
    
    # Dewatering configuration
    dewatering_type_default: str = "centrifuge"  # Default equipment type
    centrifuge_cake_solids_fraction: float = 0.22  # 22% dry solids
    centrifuge_capture_fraction: float = 0.95  # 95% solids capture


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


def convert_temperature_to_kelvin(temp_c: float) -> float:
    """Convert Celsius to Kelvin for WaterTAP."""
    return temp_c + 273.15


def calculate_tank_dimensions(
    liquid_volume_m3: float,
    height_to_diameter_ratio: float = 1.2
) -> Tuple[float, float]:
    """
    Calculate tank diameter and height from liquid volume.

    Assumes cylindrical tank with flat bottom.
    V = π × (D/2)² × H
    H = height_to_diameter_ratio × D

    Solving for D:
    V = π × (D/2)² × (ratio × D)
    V = π × ratio × D³ / 4
    D = (4V / (π × ratio))^(1/3)

    Args:
        liquid_volume_m3: Liquid working volume [m³]
        height_to_diameter_ratio: H/D ratio (default: 1.2)

    Returns:
        (diameter_m, height_m): Tank dimensions
    """
    # Solve for diameter
    diameter_m = ((4.0 * liquid_volume_m3) / (math.pi * height_to_diameter_ratio)) ** (1.0/3.0)
    height_m = height_to_diameter_ratio * diameter_m

    return diameter_m, height_m


def calculate_mbr_modules(total_area_m2: float, mbr_type: str, config: SizingConfig) -> int:
    """Calculate number of MBR modules needed."""
    import math
    
    if mbr_type == "submerged":
        module_size = config.submerged_module_m2
    else:  # external_crossflow
        module_size = config.external_module_m2
    
    return math.ceil(total_area_m2 / module_size)


def size_high_tss_configuration(
    feed_flow_m3d: float,
    target_srt_days: float,
    biomass_production_kg_d: float,
    temperature_c: float = 35.0,
    pressure_atm: Optional[float] = None,
    vapor_headspace_fraction: Optional[float] = None,
    dewatering_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Size digester for high TSS configuration (>10,000 mg/L).
    
    Example:
        Feed: 500 m³/d
        SRT: 30 days
        Volume: 500 * 30 = 15,000 m³
    """
    config = SizingConfig()
    
    if pressure_atm is None:
        pressure_atm = config.pressure_atm_default
    if vapor_headspace_fraction is None:
        vapor_headspace_fraction = config.vapor_headspace_fraction
    if dewatering_type is None:
        dewatering_type = config.dewatering_type_default
    
    # For high TSS, HRT = SRT
    hrt_days = target_srt_days
    
    # Calculate digester volume (no safety factor - SRT already includes margin)
    liquid_volume_m3 = feed_flow_m3d * hrt_days
    vapor_volume_m3 = liquid_volume_m3 * vapor_headspace_fraction
    total_volume_m3 = liquid_volume_m3 + vapor_volume_m3
    
    logger.info(f"High TSS config: Liquid volume = {feed_flow_m3d} * {hrt_days} = {liquid_volume_m3:.0f} m³")
    logger.info(f"High TSS config: Vapor volume = {liquid_volume_m3:.0f} * {vapor_headspace_fraction} = {vapor_volume_m3:.0f} m³")
    
    # Convert temperature to Kelvin
    temperature_k = convert_temperature_to_kelvin(temperature_c)
    
    # Calculate dewatering equipment sizing (40 hours/week operation)
    # For non-MBR: dewater full feed flow
    weekly_flow_m3 = feed_flow_m3d * 7  # m³/week
    dewatering_flow_m3h = weekly_flow_m3 / config.dewatering_hours_per_week  # m³/h
    
    # Dry solids production
    weekly_solids_kg = biomass_production_kg_d * 7  # kg/week
    dewatering_solids_kg_h = weekly_solids_kg / config.dewatering_hours_per_week  # kg/h
    
    return {
        "flowsheet_type": "high_tss",
        "description": "Anaerobic digester with full dewatering",
        "digester": {
            "liquid_volume_m3": round(liquid_volume_m3, 1),
            "vapor_volume_m3": round(vapor_volume_m3, 1),
            "total_volume_m3": round(total_volume_m3, 1),
            "hrt_days": hrt_days,
            "srt_days": target_srt_days,
            "type": "CSTR"
        },
        "operating_conditions": {
            "temperature_c": temperature_c,
            "temperature_k": round(temperature_k, 2),
            "pressure_atm": pressure_atm,
            "vapor_headspace_fraction": vapor_headspace_fraction,
            "vapor_volume_m3": round(vapor_volume_m3, 1)
        },
        "mbr": {
            "required": False
        },
        "dewatering": {
            "equipment_type": dewatering_type,
            "type": "full",
            "description": "Dewater all digestate",
            "operating_hours_per_week": config.dewatering_hours_per_week,
            "flow_m3_h": round(dewatering_flow_m3h, 2),
            "dry_solids_kg_h": round(dewatering_solids_kg_h, 2),
            "cake_solids_fraction": config.centrifuge_cake_solids_fraction,
            "solids_capture_fraction": config.centrifuge_capture_fraction,
            "weekly_flow_m3": round(weekly_flow_m3, 1),
            "weekly_solids_kg": round(weekly_solids_kg, 1)
        }
    }


def size_low_tss_mbr_configuration(
    feed_flow_m3d: float,
    cod_load_kg_d: float,
    biomass_yield: float,
    target_mlss_mg_l: Optional[float] = None,
    target_srt_days: Optional[float] = None,
    mbr_type: Optional[str] = None,
    temperature_c: float = 35.0,
    pressure_atm: Optional[float] = None,
    vapor_headspace_fraction: Optional[float] = None,
    dewatering_type: Optional[str] = None
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
    """
    config = SizingConfig()
    
    if target_mlss_mg_l is None:
        target_mlss_mg_l = config.target_mlss_with_mbr
    if target_srt_days is None:
        target_srt_days = config.target_srt_days
    if mbr_type is None:
        mbr_type = config.mbr_type_default
    if pressure_atm is None:
        pressure_atm = config.pressure_atm_default
    if vapor_headspace_fraction is None:
        vapor_headspace_fraction = config.vapor_headspace_fraction
    if dewatering_type is None:
        dewatering_type = config.dewatering_type_default
    
    # Get flux and module size based on MBR type
    if mbr_type == "submerged":
        mbr_flux_lmh = config.submerged_flux_lmh
        module_size_m2 = config.submerged_module_m2
    else:  # external_crossflow
        mbr_flux_lmh = config.external_flux_lmh
        module_size_m2 = config.external_module_m2
    
    # Calculate biomass production
    biomass_production_kg_d = cod_load_kg_d * biomass_yield
    
    # Calculate biomass inventory at steady state
    biomass_inventory_kg = biomass_production_kg_d * target_srt_days
    
    # Calculate digester volume to maintain target MLSS
    # MLSS in kg/m³
    target_mlss_kg_m3 = target_mlss_mg_l / 1000.0
    
    # Volume = Biomass inventory / MLSS concentration (no safety factor)
    liquid_volume_m3 = biomass_inventory_kg / target_mlss_kg_m3
    vapor_volume_m3 = liquid_volume_m3 * vapor_headspace_fraction
    total_volume_m3 = liquid_volume_m3 + vapor_volume_m3
    
    # Calculate HRT (will be less than SRT due to biomass retention)
    hrt_days = liquid_volume_m3 / feed_flow_m3d
    
    logger.info(f"MBR config: Biomass inventory = {biomass_production_kg_d:.0f} * {target_srt_days} = {biomass_inventory_kg:.0f} kg")
    logger.info(f"MBR config: Liquid volume = {biomass_inventory_kg:.0f} / {target_mlss_kg_m3:.1f} = {liquid_volume_m3:.0f} m³")
    
    # Convert temperature to Kelvin
    temperature_k = convert_temperature_to_kelvin(temperature_c)
    
    # Calculate MBR membrane area
    permeate_flow_m3h = feed_flow_m3d / 24.0  # m³/h
    total_area_m2 = (permeate_flow_m3h * 1000.0) / mbr_flux_lmh  # m²
    
    # Calculate number of modules
    number_of_modules = calculate_mbr_modules(total_area_m2, mbr_type, config)
    
    # Calculate waste sludge flow for SRT control
    # Daily waste flow = Biomass production / MLSS concentration
    waste_sludge_m3d = biomass_production_kg_d / target_mlss_kg_m3
    
    # Calculate dewatering equipment sizing (40 hours/week operation)
    # For MBR: only dewater excess biomass at digester MLSS concentration
    weekly_solids_kg = biomass_production_kg_d * 7  # kg/week
    dewatering_solids_kg_h = weekly_solids_kg / config.dewatering_hours_per_week  # kg/h
    
    # Volume flow for dewatering = weekly solids / MLSS concentration / operating hours
    weekly_waste_volume_m3 = weekly_solids_kg / target_mlss_kg_m3  # m³/week
    dewatering_flow_m3h = weekly_waste_volume_m3 / config.dewatering_hours_per_week  # m³/h
    
    return {
        "flowsheet_type": "low_tss_mbr",
        "description": "Anaerobic digester with MBR for biomass retention",
        "digester": {
            "liquid_volume_m3": round(liquid_volume_m3, 1),
            "vapor_volume_m3": round(vapor_volume_m3, 1),
            "total_volume_m3": round(total_volume_m3, 1),
            "hrt_days": round(hrt_days, 2),
            "srt_days": target_srt_days,
            "mlss_mg_l": target_mlss_mg_l,
            "type": "AnMBR"
        },
        "operating_conditions": {
            "temperature_c": temperature_c,
            "temperature_k": round(temperature_k, 2),
            "pressure_atm": pressure_atm,
            "vapor_headspace_fraction": vapor_headspace_fraction,
            "vapor_volume_m3": round(vapor_volume_m3, 1)
        },
        "mbr": {
            "required": True,
            "type": mbr_type,
            "total_area_m2": round(total_area_m2, 1),
            "module_size_m2": module_size_m2,
            "number_of_modules": number_of_modules,
            "flux_lmh": mbr_flux_lmh,
            "permeate_flow_m3d": feed_flow_m3d,
            "permeate_tss_mg_l": config.permeate_tss_mg_l
        },
        "dewatering": {
            "equipment_type": dewatering_type,
            "type": "excess_biomass_only",
            "description": "Dewater only excess biomass at 15 kg/m³ TSS",
            "operating_hours_per_week": config.dewatering_hours_per_week,
            "flow_m3_h": round(dewatering_flow_m3h, 2),
            "dry_solids_kg_h": round(dewatering_solids_kg_h, 2),
            "cake_solids_fraction": config.centrifuge_cake_solids_fraction,
            "solids_capture_fraction": config.centrifuge_capture_fraction,
            "weekly_flow_m3": round(weekly_waste_volume_m3, 1),
            "weekly_solids_kg": round(weekly_solids_kg, 1),
            "daily_waste_sludge_m3d": round(waste_sludge_m3d, 3)
        },
        "calculation_details": {
            "biomass_inventory_kg": round(biomass_inventory_kg, 0),
            "biomass_production_kg_d": round(biomass_production_kg_d, 2)
        }
    }


def perform_heuristic_sizing(
    basis_of_design: Dict[str, Any],
    biomass_yield: Optional[float] = None,
    target_srt_days: Optional[float] = None,
    mbr_type: Optional[str] = None,
    dewatering_type: Optional[str] = None,
    pressure_atm: Optional[float] = None,
    vapor_headspace_fraction: Optional[float] = None,
    # NEW: Tank material parameters
    tank_material: Literal["concrete", "steel_bolted"] = "concrete",
    height_to_diameter_ratio: float = 1.2,
    # NEW: Mixing configuration
    mixing_type: Literal["pumped", "mechanical", "hybrid"] = "mechanical",
    mixing_power_target_w_m3: Optional[float] = None,
    impeller_type: Literal["pitched_blade_turbine", "rushton_turbine", "marine_propeller"] = "pitched_blade_turbine",
    pumped_recirculation_turnovers_per_hour: float = 3.0,
    # NEW: Biogas handling
    biogas_application: Literal["storage", "direct_utilization", "upgrading"] = "storage",
    biogas_discharge_pressure_kpa: Optional[float] = None,
    # NEW: Thermal analysis flags
    calculate_thermal_load: bool = True,
    feedstock_inlet_temp_c: float = 10.0,
    insulation_R_value_si: float = 1.76
) -> Dict[str, Any]:
    """
    Main heuristic sizing function with corrected arithmetic, WaterTAP-ready outputs,
    and integrated mixing/thermal/biogas calculations for economic costing.

    Args:
        basis_of_design: Dictionary with feed_flow_m3d, cod_mg_l, temperature_c
        biomass_yield: Biomass yield in kg TSS/kg COD (default 0.1)
        target_srt_days: Target SRT in days (default 30)
        mbr_type: "submerged" or "external_crossflow" (default "submerged")
        dewatering_type: Equipment type (default "centrifuge")
        pressure_atm: Operating pressure (default 1.0 atm)
        vapor_headspace_fraction: Vapor space fraction (default 0.10)

        # Tank material and geometry
        tank_material: "concrete" or "steel_bolted" (default "concrete")
        height_to_diameter_ratio: H/D ratio for cylindrical tank (default 1.2)

        # Mixing configuration
        mixing_type: "pumped", "mechanical", or "hybrid" (default "mechanical")
        mixing_power_target_w_m3: Target power intensity [W/m³] (default: auto-select from preset)
        impeller_type: For mechanical mixing (default "pitched_blade_turbine")
        pumped_recirculation_turnovers_per_hour: For pumped mixing (default 3.0)

        # Biogas handling
        biogas_application: "storage", "direct_utilization", or "upgrading" (default "storage")
        biogas_discharge_pressure_kpa: Blower discharge pressure (default: auto-select from application)

        # Thermal analysis
        calculate_thermal_load: Enable thermal budget calculation (default True)
        feedstock_inlet_temp_c: Feed temperature [°C] (default 10.0)
        insulation_R_value_si: Tank insulation R-value [m²·K/W] (default 1.76)
    """
    config = SizingConfig()
    
    # Extract required parameters
    feed_flow_m3d = basis_of_design.get("feed_flow_m3d")
    cod_mg_l = basis_of_design.get("cod_mg_l")
    temperature_c = basis_of_design.get("temperature_c", 35.0)
    
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
            feed_flow_m3d, target_srt_days, biomass_production_kg_d,
            temperature_c=temperature_c,
            pressure_atm=pressure_atm,
            vapor_headspace_fraction=vapor_headspace_fraction,
            dewatering_type=dewatering_type
        )
        flowsheet_decision = "high_tss"
        decision_reason = f"TSS concentration ({steady_state_tss_mg_l:.0f} mg/L) exceeds {config.max_tss_without_mbr:.0f} mg/L"
    else:
        # Low TSS: Use AnMBR to concentrate biomass
        configuration = size_low_tss_mbr_configuration(
            feed_flow_m3d, cod_load_kg_d, biomass_yield,
            target_srt_days=target_srt_days,
            mbr_type=mbr_type,
            temperature_c=temperature_c,
            pressure_atm=pressure_atm,
            vapor_headspace_fraction=vapor_headspace_fraction,
            dewatering_type=dewatering_type
        )
        flowsheet_decision = "low_tss_mbr"
        decision_reason = f"TSS concentration ({steady_state_tss_mg_l:.0f} mg/L) below {config.max_tss_without_mbr:.0f} mg/L, using MBR to maintain {config.target_mlss_with_mbr:.0f} mg/L MLSS"
    
    # ========================================================================
    # NEW: TANK GEOMETRY CALCULATIONS
    # ========================================================================
    liquid_volume = configuration["digester"]["liquid_volume_m3"]
    diameter_m, height_m = calculate_tank_dimensions(
        liquid_volume, height_to_diameter_ratio
    )

    # Add tank geometry to configuration
    configuration["digester"]["diameter_m"] = round(diameter_m, 2)
    configuration["digester"]["height_m"] = round(height_m, 2)
    configuration["digester"]["material"] = tank_material
    configuration["digester"]["height_to_diameter_ratio"] = height_to_diameter_ratio

    # ========================================================================
    # NEW: MIXING SYSTEM SIZING
    # ========================================================================
    # Auto-select mixing power target based on temperature if not specified
    if mixing_power_target_w_m3 is None:
        if temperature_c >= 50:  # Thermophilic
            preset_key = "thermophilic_complete_mix"
        else:  # Mesophilic
            preset_key = "mesophilic_complete_mix"

        mixing_power_target_w_m3 = ANAEROBIC_DIGESTER_MIXING_PRESETS[preset_key].power_target_w_m3

    # Get fluid properties from preset
    if temperature_c >= 50:
        preset = ANAEROBIC_DIGESTER_MIXING_PRESETS["thermophilic_complete_mix"]
    else:
        preset = ANAEROBIC_DIGESTER_MIXING_PRESETS["mesophilic_complete_mix"]

    mixing_result = {}

    if mixing_type in ["mechanical", "hybrid"]:
        # Calculate mechanical mixing
        mech_mixing = calculate_mechanical_mixing_power(
            tank_diameter_m=diameter_m,
            tank_volume_m3=liquid_volume,
            target_power_w_m3=mixing_power_target_w_m3,
            fluid_density_kg_m3=preset.typical_density_kg_m3,
            fluid_viscosity_pa_s=preset.typical_viscosity_pa_s,
            impeller_type=impeller_type,
            mode="design"
        )
        mixing_result["mechanical"] = mech_mixing

    if mixing_type in ["pumped", "hybrid"]:
        # Calculate pumped mixing
        recirculation_rate_m3h = pumped_recirculation_turnovers_per_hour * liquid_volume
        pumped_mixing = calculate_pumped_mixing_power(
            tank_volume_m3=liquid_volume,
            recirculation_rate_m3_h=recirculation_rate_m3h,
            pump_head_m=5.0,
            pump_efficiency=0.65,
            nozzle_velocity_m_s=3.0
        )
        mixing_result["pumped"] = pumped_mixing

    # Calculate total mixing power
    total_mixing_power_kw = 0.0
    if "mechanical" in mixing_result:
        total_mixing_power_kw += mixing_result["mechanical"]["power_total_kw"]
    if "pumped" in mixing_result:
        total_mixing_power_kw += mixing_result["pumped"]["power_total_kw"]

    configuration["mixing"] = {
        "type": mixing_type,
        "target_power_w_m3": mixing_power_target_w_m3,
        "total_power_kw": round(total_mixing_power_kw, 2),
        "details": mixing_result
    }

    # ========================================================================
    # NEW: BIOGAS BLOWER SIZING (placeholder for costing)
    # ========================================================================
    # Auto-select discharge pressure based on application
    if biogas_discharge_pressure_kpa is None:
        pressure_map = {
            "storage": 10.0,
            "direct_utilization": 25.0,
            "upgrading": 800.0
        }
        biogas_discharge_pressure_kpa = pressure_map[biogas_application]

    # Estimate biogas production from COD removal (placeholder - will be refined in simulation)
    # Typical: 0.35 m³ CH4 / kg COD removed at STP
    # Assuming 80% COD removal for preliminary estimate
    cod_removed_kg_d = cod_load_kg_d * 0.8
    methane_production_m3d = cod_removed_kg_d * 0.35
    total_biogas_m3d = methane_production_m3d / 0.60  # Assume 60% CH4 content

    biogas_flow_m3h = total_biogas_m3d / 24.0

    configuration["biogas_blower"] = {
        "application": biogas_application,
        "discharge_pressure_kpa": biogas_discharge_pressure_kpa,
        "estimated_biogas_flow_m3d": round(total_biogas_m3d, 1),
        "estimated_biogas_flow_m3h": round(biogas_flow_m3h, 2),
        "note": "Preliminary estimate. Refine with detailed simulation results."
    }

    # ========================================================================
    # NEW: THERMAL LOAD REQUEST (for heat-transfer-mcp integration)
    # ========================================================================
    if calculate_thermal_load:
        thermal_request = {
            "feedstock_heating": {
                "flow_m3_d": feed_flow_m3d,
                "inlet_temp_c": feedstock_inlet_temp_c,
                "outlet_temp_c": temperature_c,
                "solids_content_percent": steady_state_tss_mg_l / 10000.0  # Convert mg/L to %
            },
            "tank_heat_loss": {
                "diameter_m": diameter_m,
                "height_m": height_m,
                "contents_temp_c": temperature_c,
                "insulation_R_value_si": insulation_R_value_si
            },
            "note": "Use heat-transfer-mcp tools to calculate complete thermal budget"
        }
        configuration["thermal_analysis_request"] = thermal_request

    # ========================================================================
    # FINAL RESULT ASSEMBLY
    # ========================================================================
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