"""Heuristic sizing tool for anaerobic digesters."""

import logging
from typing import Dict, Any, Optional, Union
from core.state import design_state
from core.utils import coerce_to_dict, to_float
from utils.heuristic_sizing import perform_heuristic_sizing

logger = logging.getLogger(__name__)


async def heuristic_sizing_ad(
    biomass_yield: Optional[Union[float, int, str]] = None,
    target_srt_days: Optional[Union[float, int, str]] = None,
    use_current_basis: bool = True,
    custom_basis: Optional[Dict[str, Any]] = None,
    # Tank material and geometry
    tank_material: str = "concrete",
    height_to_diameter_ratio: float = 1.2,
    # Mixing configuration
    mixing_type: str = "mechanical",
    mixing_power_target_w_m3: Optional[float] = None,
    impeller_type: str = "pitched_blade_turbine",
    pumped_recirculation_turnovers_per_hour: float = 3.0,
    # Biogas handling
    biogas_application: str = "storage",
    biogas_discharge_pressure_kpa: Optional[float] = None,
    # Thermal analysis
    calculate_thermal_load: bool = True,
    feedstock_inlet_temp_c: float = 10.0,
    insulation_R_value_si: float = 1.76
) -> Dict[str, Any]:
    """
    Perform heuristic sizing for anaerobic digester with integrated mixing, biogas, and thermal analysis.

    This tool calculates digester volume, tank dimensions, mixing power requirements, biogas blower sizing,
    and thermal load estimates. Determines flowsheet configuration (high TSS with dewatering vs. low TSS with MBR)
    based on expected biomass concentration.

    Args:
        biomass_yield: Biomass yield in kg TSS/kg COD (default 0.1)
        target_srt_days: Target solids retention time in days (default 30)
        use_current_basis: Use parameters from current design state (default True)
        custom_basis: Optional custom basis of design parameters

        # Tank material and geometry
        tank_material: "concrete" or "steel_bolted" (default "concrete")
        height_to_diameter_ratio: H/D ratio for cylindrical tank (default 1.2)

        # Mixing configuration
        mixing_type: "pumped", "mechanical", or "hybrid" (default "mechanical")
        mixing_power_target_w_m3: Target power intensity [W/m³] (default: auto-select from preset)
        impeller_type: For mechanical mixing - "pitched_blade_turbine", "rushton_turbine", "marine_propeller" (default "pitched_blade_turbine")
        pumped_recirculation_turnovers_per_hour: For pumped mixing (default 3.0)

        # Biogas handling
        biogas_application: "storage", "direct_utilization", or "upgrading" (default "storage")
        biogas_discharge_pressure_kpa: Blower discharge pressure (default: auto-select from application)

        # Thermal analysis
        calculate_thermal_load: Enable thermal budget calculation (default True)
        feedstock_inlet_temp_c: Feed temperature [°C] (default 10.0)
        insulation_R_value_si: Tank insulation R-value [m²·K/W] (default 1.76)

    Returns:
        Dictionary containing:
        - flowsheet_type: "high_tss" or "low_tss_mbr"
        - digester: Sizing details (volume, HRT, SRT, diameter, height, material)
        - mixing: Mixing system details (type, power, impeller specs)
        - biogas_blower: Biogas blower sizing (pressure, flow)
        - thermal_analysis_request: Thermal load parameters for heat-transfer-mcp integration
        - mbr: MBR requirements if applicable
        - dewatering: Dewatering configuration
        - sizing_basis: Summary of inputs and calculations
        - flowsheet_decision: Reasoning for configuration selection
    """
    try:
        # Get basis of design
        if use_current_basis:
            if not design_state.basis_of_design:
                return {
                    "status": "error",
                    "message": "No basis of design found. Run elicit_basis_of_design first.",
                    "next_step": "Use elicit_basis_of_design to collect parameters"
                }
            basis = design_state.basis_of_design
        else:
            basis = coerce_to_dict(custom_basis) or {}
            if not basis:
                return {
                    "status": "error",
                    "message": "No basis provided. Set use_current_basis=True or provide custom_basis"
                }
        
        # Extract required parameters
        feed_flow_m3d = basis.get("feed_flow_m3d", 1000.0)
        cod_mg_l = basis.get("cod_mg_l", 50000.0)
        temperature_c = basis.get("temperature_c", 35.0)
        
        # Set defaults for optional parameters
        biomass_yield = to_float(biomass_yield) if biomass_yield is not None else 0.1
        target_srt_days = to_float(target_srt_days) if target_srt_days is not None else 30.0
        
        # Perform sizing calculation with all new parameters
        sizing_result = perform_heuristic_sizing(
            basis_of_design=basis,
            biomass_yield=biomass_yield,
            target_srt_days=target_srt_days,
            # Tank material and geometry
            tank_material=tank_material,
            height_to_diameter_ratio=height_to_diameter_ratio,
            # Mixing configuration
            mixing_type=mixing_type,
            mixing_power_target_w_m3=mixing_power_target_w_m3,
            impeller_type=impeller_type,
            pumped_recirculation_turnovers_per_hour=pumped_recirculation_turnovers_per_hour,
            # Biogas handling
            biogas_application=biogas_application,
            biogas_discharge_pressure_kpa=biogas_discharge_pressure_kpa,
            # Thermal analysis
            calculate_thermal_load=calculate_thermal_load,
            feedstock_inlet_temp_c=feedstock_inlet_temp_c,
            insulation_R_value_si=insulation_R_value_si
        )
        
        # Store in design state
        design_state.heuristic_config = sizing_result
        
        # Add summary message
        if sizing_result["flowsheet_type"] == "high_tss":
            summary = f"High TSS configuration selected. Digester volume: {sizing_result['digester']['total_volume_m3']:.0f} m³, "
            summary += f"HRT: {sizing_result['digester']['hrt_days']:.1f} days, SRT: {sizing_result['digester']['srt_days']} days"
        else:
            summary = f"Low TSS with MBR configuration selected. Digester volume: {sizing_result['digester']['liquid_volume_m3']:.0f} m³, "
            summary += f"HRT: {sizing_result['digester']['hrt_days']:.1f} days, SRT: {sizing_result['digester']['srt_days']} days, "
            summary += f"MBR area: {sizing_result['mbr']['total_area_m2']:.0f} m²"
        
        sizing_result["summary"] = summary
        
        return sizing_result
        
    except Exception as e:
        logger.error(f"Error in heuristic_sizing_ad: {str(e)}")
        return {
            "status": "error",
            "message": f"Heuristic sizing failed: {str(e)}"
        }