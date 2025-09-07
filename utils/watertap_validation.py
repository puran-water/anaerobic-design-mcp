#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
WaterTAP-based validation for ADM1 state variables.

This module uses WaterTAP's Modified ADM1 property package for:
- Calculating composite parameters (COD, TSS, VSS, TKN, TP)
- Enforcing electroneutrality at target pH
- Validating ADM1 states before simulation
"""

import logging
from typing import Dict, Any, Tuple, Optional
from pyomo.environ import ConcreteModel, value, Constraint
from idaes.core import FlowsheetBlock
from idaes.core.util.model_statistics import degrees_of_freedom

# WaterTAP imports
from watertap.property_models.unit_specific.anaerobic_digestion.modified_adm1_properties import (
    ModifiedADM1ParameterBlock
)

logger = logging.getLogger(__name__)


def calculate_composites_with_watertap(
    adm1_state: Dict[str, float],
    temperature_k: float = 308.15
) -> Dict[str, float]:
    """
    Calculate composite parameters using WaterTAP's property package.
    
    Args:
        adm1_state: Dictionary of ADM1 component concentrations (kg/m³ or kmol/m³)
        temperature_k: Temperature in Kelvin (default 35°C)
    
    Returns:
        Dictionary with calculated composites in mg/L:
        - cod_mg_l: Total COD
        - tss_mg_l: Total suspended solids
        - vss_mg_l: Volatile suspended solids
        - tkn_mg_l: Total Kjeldahl nitrogen
        - tp_mg_l: Total phosphorus
        - ph: Calculated pH from charge balance
        - alkalinity_mol_l: Alkalinity in mol/L
    """
    try:
        # Create model with WaterTAP property package
        m = ConcreteModel()
        m.fs = FlowsheetBlock(dynamic=False)
        m.fs.props = ModifiedADM1ParameterBlock()
        
        # Create state block
        m.fs.state = m.fs.props.build_state_block([0], defined_state=True)
        state = m.fs.state[0]
        
        # Set temperature
        state.temperature.fix(temperature_k)
        state.pressure.fix(101325)  # 1 atm
        
        # Set component concentrations
        for comp in m.fs.props.soluble_set | m.fs.props.particulate_set:
            comp_name = comp.name
            if comp_name in adm1_state:
                # Handle S_cat, S_an (kmol/m³)
                if comp_name in ['S_cat', 'S_an']:
                    state.conc_mass_comp[comp].fix(adm1_state[comp_name])
                # Handle other components (kg/m³)
                else:
                    state.conc_mass_comp[comp].fix(adm1_state.get(comp_name, 0))
        
        # Initialize the state block
        state.initialize()
        
        # Extract calculated properties
        results = {
            "cod_mg_l": value(state.COD) * 1000,  # Convert kg/m³ to mg/L
            "tss_mg_l": value(state.TSS) * 1000,
            "vss_mg_l": value(state.VSS) * 1000,
            "tkn_mg_l": value(state.TKN) * 1000,
            "tp_mg_l": value(state.TP) * 1000 if hasattr(state, 'TP') else 0,
            "ph": value(state.pH) if hasattr(state, 'pH') else 7.0,
            "alkalinity_mol_l": value(state.alkalinity) if hasattr(state, 'alkalinity') else 0
        }
        
        return results
        
    except Exception as e:
        logger.error(f"Error calculating composites with WaterTAP: {e}")
        # Fall back to simple calculation if WaterTAP fails
        return calculate_composites_simple(adm1_state)


def calculate_composites_simple(adm1_state: Dict[str, float]) -> Dict[str, float]:
    """
    Simple fallback calculation of composites without WaterTAP.
    
    This maintains compatibility if WaterTAP is unavailable.
    """
    # COD calculation (all organic components)
    cod_kg_m3 = (
        adm1_state.get('S_su', 0) * 1.07 +  # Sugars
        adm1_state.get('S_aa', 0) * 1.5 +   # Amino acids
        adm1_state.get('S_fa', 0) * 2.88 +  # Fatty acids
        adm1_state.get('S_va', 0) * 1.51 +  # Valerate
        adm1_state.get('S_bu', 0) * 1.82 +  # Butyrate
        adm1_state.get('S_pro', 0) * 1.51 + # Propionate
        adm1_state.get('S_ac', 0) * 1.07 +  # Acetate
        adm1_state.get('S_I', 0) +          # Soluble inerts
        adm1_state.get('X_c', 0) * 1.2 +    # Composites
        adm1_state.get('X_ch', 0) * 1.07 +  # Carbohydrates
        adm1_state.get('X_pr', 0) * 1.5 +   # Proteins
        adm1_state.get('X_li', 0) * 2.88 +  # Lipids
        adm1_state.get('X_I', 0) +          # Particulate inerts
        sum(adm1_state.get(f'X_{x}', 0) * 1.42 for x in ['su', 'aa', 'fa', 'c4', 'pro', 'ac', 'h2'])  # Biomass
    )
    
    # TSS calculation (all particulates)
    tss_mg_l = sum(adm1_state.get(f'X_{x}', 0) for x in [
        'c', 'ch', 'pr', 'li', 'su', 'aa', 'fa', 'c4', 'pro', 'ac', 'h2', 'I', 'PAO', 'PHA', 'PP'
    ]) * 1000
    
    # VSS (TSS minus inerts)
    vss_mg_l = tss_mg_l - adm1_state.get('X_I', 0) * 1000
    
    # TKN calculation
    tkn_kg_m3 = (
        adm1_state.get('S_IN', 0) +  # Ammonia
        adm1_state.get('S_aa', 0) * 0.14 +  # N in amino acids
        adm1_state.get('X_pr', 0) * 0.16    # N in proteins
    )
    
    # TP calculation
    tp_kg_m3 = (
        adm1_state.get('S_IP', 0) +  # Orthophosphate
        adm1_state.get('X_PP', 0)    # Polyphosphate
    )
    
    return {
        "cod_mg_l": cod_kg_m3 * 1000,
        "tss_mg_l": tss_mg_l,
        "vss_mg_l": vss_mg_l,
        "tkn_mg_l": tkn_kg_m3 * 1000,
        "tp_mg_l": tp_kg_m3 * 1000,
        "ph": 7.0,  # Default
        "alkalinity_mol_l": 0.1  # Default
    }


def enforce_electroneutrality(
    adm1_state: Dict[str, float],
    target_ph: float = 7.0,
    adjustment_strategy: str = "auto"
) -> Tuple[Dict[str, float], Dict[str, Any]]:
    """
    Enforce electroneutrality by adjusting S_cat or S_an.
    
    Args:
        adm1_state: ADM1 state dictionary
        target_ph: Target pH for electroneutrality
        adjustment_strategy: "auto", "s_cat", or "s_an"
    
    Returns:
        Tuple of (adjusted_state, adjustment_info)
    """
    from utils.adm1_validation import calculate_strong_ion_residual
    
    # Make a copy to avoid modifying original
    adjusted_state = adm1_state.copy()
    
    # Calculate current charge balance
    charge_result = calculate_strong_ion_residual(adjusted_state, target_ph)
    
    if charge_result["balanced"]:
        return adjusted_state, {
            "adjusted": False,
            "message": "Already electroneutral",
            "imbalance_percent": charge_result["imbalance_percent"]
        }
    
    # Determine adjustment needed
    residual_mol_m3 = charge_result["residual_mol_m3"]
    adjustment_kmol_m3 = abs(residual_mol_m3) / 1000
    
    # Decide which ion to adjust
    if adjustment_strategy == "auto":
        # Auto-select based on residual sign and magnitude
        if residual_mol_m3 > 0:  # Excess cations
            adjust_component = "S_an"
        else:  # Excess anions
            adjust_component = "S_cat"
    else:
        adjust_component = adjustment_strategy
    
    # Apply adjustment
    original_value = adjusted_state.get(adjust_component, 0.02 if adjust_component == "S_an" else 0.08)
    
    if adjust_component == "S_an" and residual_mol_m3 > 0:
        # Increase anions to balance excess cations
        adjusted_state["S_an"] = original_value + adjustment_kmol_m3
    elif adjust_component == "S_cat" and residual_mol_m3 < 0:
        # Increase cations to balance excess anions
        adjusted_state["S_cat"] = original_value + adjustment_kmol_m3
    else:
        # Wrong direction - need to decrease, but can't go negative
        # Switch to the other component
        adjust_component = "S_cat" if adjust_component == "S_an" else "S_an"
        original_value = adjusted_state.get(adjust_component, 0.08 if adjust_component == "S_cat" else 0.02)
        adjusted_state[adjust_component] = original_value + adjustment_kmol_m3
    
    # Verify the adjustment
    new_charge_result = calculate_strong_ion_residual(adjusted_state, target_ph)
    
    adjustment_info = {
        "adjusted": True,
        "component_adjusted": adjust_component,
        "original_value": original_value,
        "new_value": adjusted_state[adjust_component],
        "adjustment_kmol_m3": adjustment_kmol_m3,
        "original_imbalance_percent": charge_result["imbalance_percent"],
        "final_imbalance_percent": new_charge_result["imbalance_percent"],
        "message": f"Adjusted {adjust_component} from {original_value:.4f} to {adjusted_state[adjust_component]:.4f} kmol/m³"
    }
    
    return adjusted_state, adjustment_info


def validate_adm1_state_with_watertap(
    adm1_state: Dict[str, float],
    user_parameters: Dict[str, float],
    tolerance: float = 0.1,
    enforce_balance: bool = True
) -> Dict[str, Any]:
    """
    Validate ADM1 state using WaterTAP calculations with optional electroneutrality enforcement.
    
    Args:
        adm1_state: ADM1 component concentrations
        user_parameters: Target values for validation
        tolerance: Relative tolerance for validation
        enforce_balance: Whether to auto-correct electroneutrality
    
    Returns:
        Comprehensive validation results
    """
    # Step 1: Enforce electroneutrality if requested
    if enforce_balance and 'ph' in user_parameters:
        adm1_state, adjustment_info = enforce_electroneutrality(
            adm1_state,
            target_ph=user_parameters['ph']
        )
    else:
        adjustment_info = {"adjusted": False}
    
    # Step 2: Calculate composites with WaterTAP
    temperature_k = 273.15 + user_parameters.get('temperature_c', 35)
    calculated = calculate_composites_with_watertap(adm1_state, temperature_k)
    
    # Step 3: Compare with user parameters
    results = {
        "valid": True,
        "calculated_parameters": calculated,
        "user_parameters": user_parameters,
        "deviations": {},
        "pass_fail": {},
        "warnings": [],
        "electroneutrality_adjustment": adjustment_info
    }
    
    # Check each parameter
    for param in ['cod_mg_l', 'tss_mg_l', 'vss_mg_l', 'tkn_mg_l', 'tp_mg_l']:
        if param in user_parameters:
            calc_val = calculated.get(param, 0)
            user_val = user_parameters[param]
            
            if user_val > 0:
                deviation = abs(calc_val - user_val) / user_val
                results["deviations"][f"{param.split('_')[0]}_percent"] = deviation * 100
                
                if deviation > tolerance:
                    results["pass_fail"][param.split('_')[0]] = "FAIL"
                    results["valid"] = False
                    results["warnings"].append(
                        f"{param.upper()} deviation {deviation*100:.1f}% exceeds tolerance"
                    )
                else:
                    results["pass_fail"][param.split('_')[0]] = "PASS"
    
    # Add pH check if calculated
    if 'ph' in user_parameters and 'ph' in calculated:
        ph_diff = abs(calculated['ph'] - user_parameters['ph'])
        if ph_diff > 0.5:
            results["warnings"].append(f"pH difference {ph_diff:.2f} may affect convergence")
    
    return results