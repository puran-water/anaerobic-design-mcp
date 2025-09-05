#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Feedstock characterization using Codex MCP for ADM1 state variable estimation.

This module interfaces with the Codex MCP server to convert natural language
feedstock descriptions into ADM1 component concentrations required for WaterTAP.
"""

import logging
from typing import Dict, Any, Optional, List
import json

logger = logging.getLogger(__name__)


# ADM1 component definitions for reference
ADM1_COMPONENTS = {
    "soluble": {
        "S_su": "Monosaccharides (kg/m³)",
        "S_aa": "Amino acids (kg/m³)",
        "S_fa": "Long chain fatty acids (kg/m³)",
        "S_va": "Total valerate (kg/m³)",
        "S_bu": "Total butyrate (kg/m³)",
        "S_pro": "Total propionate (kg/m³)",
        "S_ac": "Total acetate (kg/m³)",
        "S_h2": "Hydrogen gas (kg/m³)",
        "S_ch4": "Methane gas (kg/m³)",
        "S_IC": "Inorganic carbon (kg/m³)",
        "S_IN": "Inorganic nitrogen (kg/m³)",
        "S_I": "Soluble inerts (kg/m³)",
        "S_cat": "Total cation equivalents (kmol/m³)",
        "S_an": "Total anion equivalents (kmol/m³)",
        "S_co2": "Carbon dioxide (kg/m³)",
        # Modified ADM1 additions
        "S_IP": "Inorganic phosphorus (kg/m³)",
        "S_K": "Potassium (kg/m³)",
        "S_Mg": "Magnesium (kg/m³)"
    },
    "particulate": {
        "X_c": "Composites (kg/m³)",
        "X_ch": "Carbohydrates (kg/m³)",
        "X_pr": "Proteins (kg/m³)",
        "X_li": "Lipids (kg/m³)",
        "X_su": "Sugar degraders (kg/m³)",
        "X_aa": "Amino acid degraders (kg/m³)",
        "X_fa": "LCFA degraders (kg/m³)",
        "X_c4": "Valerate and butyrate degraders (kg/m³)",
        "X_pro": "Propionate degraders (kg/m³)",
        "X_ac": "Acetate degraders (kg/m³)",
        "X_h2": "Hydrogen degraders (kg/m³)",
        "X_I": "Particulate inerts (kg/m³)",
        # Modified ADM1 additions
        "X_PAO": "Phosphorus accumulating organisms (kg/m³)",
        "X_PHA": "Polyhydroxyalkanoates (kg/m³)",
        "X_PP": "Polyphosphates (kg/m³)"
    }
}


def validate_adm1_state(adm1_state: Dict[str, float]) -> Dict[str, Any]:
    """
    Validate ADM1 state variables for completeness and reasonable ranges.
    
    Args:
        adm1_state: Dictionary of ADM1 component concentrations
        
    Returns:
        Dictionary with validation results and any warnings
    """
    validation_result = {
        "valid": True,
        "warnings": [],
        "missing_components": [],
        "negative_values": []
    }
    
    # Check for required components
    all_components = list(ADM1_COMPONENTS["soluble"].keys()) + list(ADM1_COMPONENTS["particulate"].keys())
    
    for component in all_components:
        if component not in adm1_state:
            validation_result["missing_components"].append(component)
        elif adm1_state[component] < 0:
            validation_result["negative_values"].append(component)
            
    # Check mass balance reasonability
    total_cod = sum([
        adm1_state.get("S_su", 0) * 1.067,  # COD factor for sugars
        adm1_state.get("S_aa", 0) * 1.5,    # COD factor for amino acids
        adm1_state.get("S_fa", 0) * 2.88,   # COD factor for fatty acids
        adm1_state.get("X_ch", 0) * 1.067,  # COD factor for carbohydrates
        adm1_state.get("X_pr", 0) * 1.5,    # COD factor for proteins
        adm1_state.get("X_li", 0) * 2.88,   # COD factor for lipids
        adm1_state.get("X_c", 0) * 1.2,     # Approximate COD factor for composites
    ])
    
    if total_cod > 0:
        validation_result["estimated_cod_mg_l"] = total_cod * 1000  # Convert kg/m³ to mg/L
    
    # Check charge balance
    cation_charge = adm1_state.get("S_cat", 0)
    anion_charge = adm1_state.get("S_an", 0)
    charge_imbalance = abs(cation_charge - anion_charge)
    
    if charge_imbalance > 0.01:  # kmol/m³
        validation_result["warnings"].append(
            f"Charge imbalance: {charge_imbalance:.3f} kmol/m³"
        )
    
    # Set validity
    if validation_result["missing_components"] or validation_result["negative_values"]:
        validation_result["valid"] = False
        
    return validation_result


def prepare_codex_prompt(
    feedstock_description: str,
    cod_mg_l: Optional[float] = None,
    tss_mg_l: Optional[float] = None,
    vss_mg_l: Optional[float] = None,
    ph: Optional[float] = None,
    alkalinity_meq_l: Optional[float] = None
) -> str:
    """
    Prepare a detailed prompt for Codex to estimate ADM1 state variables.
    
    Args:
        feedstock_description: Natural language description of feedstock
        cod_mg_l: Optional measured COD concentration
        tss_mg_l: Optional measured TSS concentration
        vss_mg_l: Optional measured VSS concentration
        ph: Optional measured pH
        alkalinity_meq_l: Optional measured alkalinity
        
    Returns:
        Formatted prompt string for Codex
    """
    prompt = f"""You are an expert in anaerobic digestion and the ADM1 (Anaerobic Digestion Model No. 1) framework.

Given the following feedstock description, estimate the ADM1 state variable concentrations.
Use kg/m³ for all conc_mass_comp components (S_*, X_*), and kmol/m³ only for S_cat and S_an (cations/anions).

FEEDSTOCK DESCRIPTION:
{feedstock_description}

"""
    
    if cod_mg_l:
        prompt += f"Measured COD: {cod_mg_l} mg/L\n"
    if tss_mg_l:
        prompt += f"Measured TSS: {tss_mg_l} mg/L\n"
    if vss_mg_l:
        prompt += f"Measured VSS: {vss_mg_l} mg/L\n"
    if ph:
        prompt += f"pH: {ph}\n"
    if alkalinity_meq_l:
        prompt += f"Alkalinity: {alkalinity_meq_l} meq/L\n"
    
    prompt += """
Please provide estimates for ALL of the following ADM1 components in the specified units.
Return your response as a valid JSON object with the component names as keys and concentrations as values.

SOLUBLE COMPONENTS (kg/m³ unless specified):
- S_su: Monosaccharides
- S_aa: Amino acids
- S_fa: Long chain fatty acids
- S_va: Total valerate
- S_bu: Total butyrate
- S_pro: Total propionate
- S_ac: Total acetate
- S_h2: Hydrogen gas
- S_ch4: Methane gas
- S_IC: Inorganic carbon (kg/m³)
- S_IN: Inorganic nitrogen (kg/m³)
- S_I: Soluble inerts
- S_cat: Total cation equivalents (kmol/m³)
- S_an: Total anion equivalents (kmol/m³)
- S_co2: Carbon dioxide

PARTICULATE COMPONENTS (kg/m³):
- X_c: Composites
- X_ch: Carbohydrates
- X_pr: Proteins
- X_li: Lipids
- X_su: Sugar degraders
- X_aa: Amino acid degraders
- X_fa: LCFA degraders
- X_c4: Valerate and butyrate degraders
- X_pro: Propionate degraders
- X_ac: Acetate degraders
- X_h2: Hydrogen degraders
- X_I: Particulate inerts

Guidelines:
1. For inlet streams, biomass concentrations (X_su through X_h2) are typically very low or zero
2. Ensure charge balance between S_cat and S_an
3. Use typical COD fractionation for the feedstock type
4. VFAs (S_va, S_bu, S_pro, S_ac) depend on pre-acidification level
5. For raw feedstocks, most organics are in particulate form (X_ch, X_pr, X_li, X_c)

Return ONLY the JSON object with all component concentrations."""
    
    return prompt


def parse_codex_response(response: str) -> Dict[str, float]:
    """
    Parse Codex response to extract ADM1 state variables.
    
    Args:
        response: Raw response from Codex
        
    Returns:
        Dictionary of ADM1 component concentrations
    """
    try:
        # Try to extract JSON from the response
        # Look for JSON-like structure in the response
        import re
        
        # Try to find JSON object in the response
        json_pattern = r'\{[^{}]*\}'
        matches = re.findall(json_pattern, response, re.DOTALL)
        
        if matches:
            # Try the last match (usually the most complete)
            for match in reversed(matches):
                try:
                    data = json.loads(match)
                    # Ensure all values are floats
                    return {k: float(v) for k, v in data.items()}
                except (json.JSONDecodeError, ValueError):
                    continue
        
        # If no valid JSON found, try to parse line by line
        adm1_state = {}
        lines = response.split('\n')
        for line in lines:
            # Look for pattern like "S_su: 0.5" or "S_su = 0.5"
            match = re.match(r'^\s*([SX]_\w+)\s*[:=]\s*([\d.]+)', line)
            if match:
                component = match.group(1)
                value = float(match.group(2))
                adm1_state[component] = value
        
        if adm1_state:
            return adm1_state
            
        # If still no data, raise error
        raise ValueError("Could not parse ADM1 state from Codex response")
        
    except Exception as e:
        logger.error(f"Error parsing Codex response: {e}")
        logger.debug(f"Response was: {response}")
        raise


async def estimate_adm1_state_with_codex(
    feedstock_description: str,
    measured_parameters: Optional[Dict[str, float]] = None,
    codex_session_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Use Codex to estimate ADM1 state variables from feedstock description.
    
    This is a placeholder that will be called by the server tool.
    The actual Codex integration happens at the server level.
    
    Args:
        feedstock_description: Natural language description
        measured_parameters: Optional measured values (cod_mg_l, tss_mg_l, etc.)
        codex_session_id: Optional session ID for continued conversation
        
    Returns:
        Dictionary with ADM1 state and validation results
    """
    # This function would be called by the server tool
    # The actual Codex call happens at the server level
    raise NotImplementedError(
        "This function should be called through the MCP server tool"
    )


def create_default_adm1_state(
    cod_mg_l: float,
    tss_mg_l: Optional[float] = None,
    vss_mg_l: Optional[float] = None,
    use_modified_adm1: bool = True
) -> Dict[str, float]:
    """
    Create a default ADM1 state based on typical wastewater composition.
    
    This is a fallback when Codex is not available or for testing.
    
    Args:
        cod_mg_l: COD concentration in mg/L
        tss_mg_l: TSS concentration in mg/L
        vss_mg_l: VSS concentration in mg/L
        use_modified_adm1: If True, include P-species for Modified ADM1
        
    Returns:
        Dictionary of ADM1 component concentrations
    """
    # Convert mg/L to kg/m³
    cod_kg_m3 = cod_mg_l / 1000.0
    
    # Default VSS/TSS ratio if not provided
    if tss_mg_l and not vss_mg_l:
        vss_mg_l = tss_mg_l * 0.8
    
    # Typical COD fractionation for municipal wastewater
    adm1_state = {
        # Soluble components (25% of COD)
        "S_su": cod_kg_m3 * 0.02,    # 2% as sugars
        "S_aa": cod_kg_m3 * 0.03,    # 3% as amino acids
        "S_fa": cod_kg_m3 * 0.05,    # 5% as fatty acids
        "S_va": 0.001,                # Trace VFAs
        "S_bu": 0.001,
        "S_pro": 0.002,
        "S_ac": cod_kg_m3 * 0.05,    # 5% as acetate
        "S_h2": 0.0001,
        "S_ch4": 0.0001,
        "S_IC": 0.05,                 # kg/m³ (mass concentration in Modified ADM1)
        "S_IN": 0.003,                # kg/m³ (3000 mg/L as N - more realistic)
        "S_I": cod_kg_m3 * 0.05,     # 5% as soluble inerts
        "S_cat": 0.04,                # kmol/m³ (balanced)
        "S_an": 0.04,                 # kmol/m³ (balanced)
        "S_co2": 0.01,
        
        # Particulate components (75% of COD)
        "X_c": cod_kg_m3 * 0.15,     # 15% as composites
        "X_ch": cod_kg_m3 * 0.25,    # 25% as carbohydrates
        "X_pr": cod_kg_m3 * 0.20,    # 20% as proteins
        "X_li": cod_kg_m3 * 0.10,    # 10% as lipids
        "X_su": 0.01,                 # Minimal biomass in raw feed
        "X_aa": 0.01,
        "X_fa": 0.005,
        "X_c4": 0.005,
        "X_pro": 0.005,
        "X_ac": 0.01,
        "X_h2": 0.005,
        "X_I": cod_kg_m3 * 0.05,     # 5% as particulate inerts
    }
    
    # Add Modified ADM1 P-species if requested
    if use_modified_adm1:
        # Typical P content ~1% of COD (all as mass concentrations in kg/m³)
        p_fraction = 0.01
        adm1_state.update({
            # Soluble P-species (kg/m³ - NOT kmol/m³)
            "S_IP": 0.0005,           # kg/m³ - Inorganic phosphorus (500 mg/L as P)
            "S_K": 0.001,             # kg/m³ - Potassium (1000 mg/L as K)
            "S_Mg": 0.0005,           # kg/m³ - Magnesium (500 mg/L as Mg)
            
            # Particulate P-species (minimal in raw feed)
            "X_PAO": 0.01,            # kg/m³ - PAOs minimal in raw feed
            "X_PHA": 0.001,           # kg/m³ - PHA storage minimal
            "X_PP": cod_kg_m3 * p_fraction * 0.2,  # kg/m³ - Some P as polyphosphates
        })
    
    return adm1_state
