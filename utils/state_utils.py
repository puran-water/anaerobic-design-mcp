# -*- coding: utf-8 -*-
"""
State utilities for ADM1 state variable management.
"""

from typing import Dict, Any, Tuple, List

def clean_adm1_state(adm1_state: Dict[str, Any]) -> Tuple[Dict[str, float], List[str]]:
    """Clean and validate ADM1 state variables."""
    warnings = []
    cleaned = {}
    
    required_components = [
        "S_su", "S_aa", "S_fa", "S_va", "S_bu", "S_pro", "S_ac",
        "S_h2", "S_ch4", "S_IC", "S_IN", "S_I",
        "X_c", "X_ch", "X_pr", "X_li", "X_su", "X_aa", "X_fa",
        "X_c4", "X_pro", "X_ac", "X_h2", "X_I",
        "S_cat", "S_an", "S_co2", "S_nh4", "S_H"
    ]
    
    for comp in required_components:
        if comp in adm1_state:
            value = adm1_state[comp]
            if isinstance(value, (list, tuple)):
                value = float(value[0])
            else:
                value = float(value)
            
            if value < 0:
                warnings.append(f"{comp} was negative ({value}), setting to 0")
                value = 0
            elif comp == "S_H" and (value <= 0 or value > 1):
                warnings.append(f"{comp} out of range ({value}), setting to 1e-7")
                value = 1e-7
                
            cleaned[comp] = value
        else:
            if comp == "S_H":
                cleaned[comp] = 1e-7
            elif comp in ["S_h2", "S_ch4"]:
                cleaned[comp] = 1e-9
            elif comp.startswith("X_"):
                cleaned[comp] = 0.1
            else:
                cleaned[comp] = 0.01
            warnings.append(f"{comp} missing, using default {cleaned[comp]}")
    
    return cleaned, warnings

def regularize_adm1_state_for_initialization(
    adm1_state: Dict[str, float],
    basis_of_design: Dict[str, Any] = None
) -> Tuple[Dict[str, float], List[str]]:
    """Regularize ADM1 state for numerical stability."""
    warnings = []
    regularized = adm1_state.copy()
    
    min_thresholds = {
        "S_h2": 1e-9,
        "S_ch4": 1e-9,
        "S_H": 1e-14,
    }
    
    # Ensure adequate biomass for reactions to proceed
    biomass_minima = {
        "X_ac": 0.05,   # Acetoclastic methanogens - critical for CH4 production
        "X_h2": 0.02,   # Hydrogenotrophic methanogens  
        "X_su": 0.01,   # Sugar degraders
        "X_aa": 0.01,   # Amino acid degraders
        "X_fa": 0.01,   # Fatty acid degraders
        "X_c4": 0.01,   # C4 (butyrate/valerate) degraders
        "X_pro": 0.01,  # Propionate degraders
    }
    
    for comp, min_val in min_thresholds.items():
        if comp in regularized and regularized[comp] < min_val:
            warnings.append(f"{comp} below threshold, setting to {min_val}")
            regularized[comp] = min_val
    
    # Apply biomass minima
    for comp, min_val in biomass_minima.items():
        if comp in regularized and regularized[comp] < min_val:
            warnings.append(f"{comp} below minimum for kinetics ({regularized[comp]}), setting to {min_val}")
            regularized[comp] = min_val
    
    for comp, value in regularized.items():
        if value < 0:
            warnings.append(f"{comp} negative, setting to 1e-10")
            regularized[comp] = 1e-10
    
    S_cat = regularized.get("S_cat", 0.04)
    S_an = regularized.get("S_an", 0.02)
    
    if abs(S_cat - S_an) > 0.1:
        warnings.append(f"Ion imbalance: S_cat={S_cat}, S_an={S_an}")
        avg = (S_cat + S_an) / 2
        regularized["S_cat"] = avg + 0.01
        regularized["S_an"] = avg - 0.01
        warnings.append(f"Adjusted ions")
    
    return regularized, warnings

