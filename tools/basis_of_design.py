"""Tool for eliciting basis of design parameters."""

import logging
from typing import Dict, Any, Optional
from core.models import AnyDict
from core.state import design_state
from core.utils import coerce_to_dict, to_float

logger = logging.getLogger(__name__)


async def elicit_basis_of_design(
    parameter_group: str = "essential",
    current_values: Optional[AnyDict] = None
) -> Dict[str, Any]:
    """
    Elicit basis of design parameters for anaerobic digester design.
    
    This tool collects essential and optional parameters through structured prompts,
    validates inputs, and stores them in the design state for use by other tools.
    
    Args:
        parameter_group: Parameter group to elicit. Options:
                        - "essential": Flow, COD, temperature (required)
                        - "solids": TSS, VSS concentrations
                        - "nutrients": TKN, TP concentrations  
                        - "alkalinity": pH, alkalinity values
                        - "all": Complete parameter set
        current_values: Optional dictionary of already known values (any JSON object).
    
    Returns:
        Dictionary containing:
        - status: "success" or "error"
        - parameters: Collected parameter values
        - validation: Validation results and warnings
        - message: Status message
    """
    try:
        # Normalize dict-like inputs
        current_values = coerce_to_dict(current_values) or {}
        
        # Define parameter groups with prompts and defaults
        parameter_definitions = {
            "essential": [
                ("feed_flow_m3d", "Feed flow rate (m³/day)", 1000.0),
                ("cod_mg_l", "COD concentration (mg/L)", 50000.0),
                ("temperature_c", "Operating temperature (°C)", 35.0)
            ],
            "solids": [
                ("tss_mg_l", "TSS concentration (mg/L)", 35000.0),
                ("vss_mg_l", "VSS concentration (mg/L)", 28000.0)
            ],
            "nutrients": [
                ("tkn_mg_l", "TKN concentration (mg/L)", 2500.0),
                ("tp_mg_l", "TP concentration (mg/L)", 500.0)
            ],
            "alkalinity": [
                ("alkalinity_meq_l", "Alkalinity (meq/L)", 100.0),
                ("ph", "pH", 7.0)
            ]
        }
        
        # Handle 'all' parameter group
        if parameter_group == "all":
            groups_to_collect = ["essential", "solids", "nutrients", "alkalinity"]
        else:
            groups_to_collect = [parameter_group] if parameter_group in parameter_definitions else []
            
        if not groups_to_collect:
            return {
                "status": "error",
                "message": f"Invalid parameter group: {parameter_group}",
                "valid_groups": list(parameter_definitions.keys()) + ["all"]
            }
        
        # Collect parameters
        collected_params = {}
        for group in groups_to_collect:
            for param_name, prompt, default in parameter_definitions[group]:
                # Check if value provided in current_values
                if param_name in current_values:
                    value = current_values[param_name]
                else:
                    # Handle alkalinity conversion if provided in different units
                    if param_name == "alkalinity_meq_l":
                        # Check for various alkalinity formats
                        for alt_key in ["alkalinity_mg_l_as_caco3", "alkalinity_mg_l", "alkalinity_caco3"]:
                            if alt_key in current_values:
                                # Convert mg/L as CaCO3 to meq/L (divide by 50)
                                value = to_float(current_values[alt_key])
                                if value is not None:
                                    value = value / 50.0
                                break
                        else:
                            value = default
                    else:
                        value = default
                
                # Convert to float
                float_value = to_float(value)
                if float_value is not None:
                    collected_params[param_name] = float_value
                else:
                    logger.warning(f"Invalid value for {param_name}: {value}, using default {default}")
                    collected_params[param_name] = default
        
        # Validate parameters
        warnings = []
        
        # Basic validation
        if "feed_flow_m3d" in collected_params:
            if collected_params["feed_flow_m3d"] <= 0:
                warnings.append("Feed flow must be positive")
                
        if "cod_mg_l" in collected_params:
            if collected_params["cod_mg_l"] <= 0:
                warnings.append("COD must be positive")
                
        if "temperature_c" in collected_params:
            temp = collected_params["temperature_c"]
            if temp < 20 or temp > 60:
                warnings.append(f"Temperature {temp}°C outside typical range (20-60°C)")
                
        if "ph" in collected_params:
            ph = collected_params["ph"]
            if ph < 6.5 or ph > 8.5:
                warnings.append(f"pH {ph} outside typical range (6.5-8.5)")
        
        # VSS/TSS ratio check
        if "vss_mg_l" in collected_params and "tss_mg_l" in collected_params:
            vss = collected_params["vss_mg_l"]
            tss = collected_params["tss_mg_l"]
            if tss > 0:
                ratio = vss / tss
                if ratio > 1:
                    warnings.append("VSS cannot exceed TSS")
                elif ratio < 0.6:
                    warnings.append(f"VSS/TSS ratio {ratio:.2f} is unusually low")
        
        # Store in global state
        design_state.basis_of_design.update(collected_params)
        
        # Calculate derived parameters
        derived = {}
        
        if "vss_mg_l" in collected_params and "tss_mg_l" in collected_params:
            tss = collected_params["tss_mg_l"]
            if tss > 0:
                derived["vss_tss_ratio"] = collected_params["vss_mg_l"] / tss
                
        if "cod_mg_l" in collected_params and "vss_mg_l" in collected_params:
            vss = collected_params["vss_mg_l"]
            if vss > 0:
                derived["cod_vss_ratio"] = collected_params["cod_mg_l"] / vss
                
        if "temperature_c" in collected_params:
            temp = collected_params["temperature_c"]
            if temp < 25:
                derived["digester_type"] = "psychrophilic"
            elif temp < 45:
                derived["digester_type"] = "mesophilic"
            else:
                derived["digester_type"] = "thermophilic"
        
        return {
            "status": "success",
            "parameters": collected_params,
            "derived_parameters": derived,
            "validation": {
                "warnings": warnings,
                "valid": len(warnings) == 0
            },
            "message": f"Collected {len(collected_params)} parameters for {parameter_group} group",
            "state_summary": {
                "total_parameters": len(design_state.basis_of_design),
                "groups_completed": groups_to_collect
            }
        }
        
    except Exception as e:
        logger.error(f"Error in elicit_basis_of_design: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to elicit parameters: {str(e)}"
        }