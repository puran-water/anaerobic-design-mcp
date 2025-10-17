#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ADM1 state validation utilities.

NOTE: This module is being superseded by watertap_validation.py which uses
WaterTAP's property package directly for more accurate calculations. 
These functions remain as a fallback when WaterTAP is not available.

Validates ADM1 state variables against composite parameters (COD, TSS, TKN, TP, pH, Alkalinity)
using simplified calculations.
"""

import logging
from typing import Dict, Any, List, Tuple, Optional
import copy
import pyomo.environ as pyo
from pyomo.environ import units as pyunits

logger = logging.getLogger(__name__)


def calculate_total_cod(adm1_state: Dict[str, float]) -> float:
    """
    Calculate total COD from ADM1 components.
    
    All components in kg COD/m³ except S_IC, S_IN which are elemental.
    """
    cod_components = [
        'S_su', 'S_aa', 'S_fa', 'S_va', 'S_bu', 'S_pro', 'S_ac', 
        'S_h2', 'S_ch4', 'S_I',  # Soluble COD
        'X_c', 'X_ch', 'X_pr', 'X_li',  # Particulate substrates
        'X_su', 'X_aa', 'X_fa', 'X_c4', 'X_pro', 'X_ac', 'X_h2',  # Biomass
        'X_I',  # Particulate inerts
        'X_PAO', 'X_PHA'  # P-species with COD
    ]
    
    total_cod = sum(adm1_state.get(comp, 0.0) for comp in cod_components)
    return total_cod


def calculate_tss(adm1_state: Dict[str, float]) -> float:
    """
    Calculate Total Suspended Solids from ADM1 components.
    
    Uses WaterTAP Modified ADM1 approach: TSS = VSS + ISS
    """
    # COD to VSS conversion factors (typical values)
    CODtoVSS_XI = 1.42    # Particulate inerts
    CODtoVSS_XCH = 1.42   # Carbohydrates  
    CODtoVSS_XPR = 1.42   # Proteins
    CODtoVSS_XLI = 1.42   # Lipids
    CODtoVSS_XBM = 1.42   # Biomass
    CODtoVSS_XPHA = 1.42  # PHA
    
    # ISS factors
    f_ISS_BM = 0.1  # ISS fraction of biomass (10% ash content)
    ISS_P = 3.23    # Mass ISS per mass P for polyphosphates
    
    # Calculate VSS (volatile suspended solids - excludes X_I which is inert)
    vss = (
        # X_I is INERT - not included in VSS
        adm1_state.get('X_ch', 0) / CODtoVSS_XCH +
        adm1_state.get('X_pr', 0) / CODtoVSS_XPR +
        adm1_state.get('X_li', 0) / CODtoVSS_XLI +
        (adm1_state.get('X_su', 0) + adm1_state.get('X_aa', 0) + 
         adm1_state.get('X_fa', 0) + adm1_state.get('X_c4', 0) +
         adm1_state.get('X_pro', 0) + adm1_state.get('X_ac', 0) +
         adm1_state.get('X_h2', 0) + adm1_state.get('X_PAO', 0)) / CODtoVSS_XBM +
        adm1_state.get('X_PHA', 0) / CODtoVSS_XPHA
    )
    
    # Calculate ISS (inorganic suspended solids)
    biomass_total = (
        adm1_state.get('X_su', 0) + adm1_state.get('X_aa', 0) + 
        adm1_state.get('X_fa', 0) + adm1_state.get('X_c4', 0) +
        adm1_state.get('X_pro', 0) + adm1_state.get('X_ac', 0) +
        adm1_state.get('X_h2', 0) + adm1_state.get('X_PAO', 0)
    )
    
    iss = (
        adm1_state.get('X_I', 0) +  # X_I is all inert/inorganic
        f_ISS_BM * biomass_total / CODtoVSS_XBM +
        ISS_P * adm1_state.get('X_PP', 0)
    )
    
    tss = vss + iss
    return tss * 1000  # Convert kg/m³ to mg/L


def calculate_vss(adm1_state: Dict[str, float]) -> float:
    """Calculate Volatile Suspended Solids (excludes X_I which is inert)."""
    CODtoVSS_XCH = 1.42
    CODtoVSS_XPR = 1.42
    CODtoVSS_XLI = 1.42
    CODtoVSS_XBM = 1.42
    CODtoVSS_XPHA = 1.42
    
    vss = (
        # X_I is INERT - not included in VSS
        adm1_state.get('X_ch', 0) / CODtoVSS_XCH +
        adm1_state.get('X_pr', 0) / CODtoVSS_XPR +
        adm1_state.get('X_li', 0) / CODtoVSS_XLI +
        (adm1_state.get('X_su', 0) + adm1_state.get('X_aa', 0) + 
         adm1_state.get('X_fa', 0) + adm1_state.get('X_c4', 0) +
         adm1_state.get('X_pro', 0) + adm1_state.get('X_ac', 0) +
         adm1_state.get('X_h2', 0) + adm1_state.get('X_PAO', 0)) / CODtoVSS_XBM +
        adm1_state.get('X_PHA', 0) / CODtoVSS_XPHA
    )
    
    return vss * 1000  # Convert kg/m³ to mg/L


def calculate_tkn(adm1_state: Dict[str, float]) -> float:
    """
    Calculate Total Kjeldahl Nitrogen from ADM1 components.
    
    TKN = Organic N + Ammonia N
    """
    # Nitrogen content factors
    N_aa = 0.11  # N content in amino acids/proteins (kg N/kg COD)
    N_bm = 0.086  # N content in biomass (kg N/kg COD)
    
    # Inorganic nitrogen (S_IN is already in kg N/m³)
    inorganic_n = adm1_state.get('S_IN', 0)
    
    # Organic nitrogen from proteins and biomass
    organic_n = (
        adm1_state.get('S_aa', 0) * N_aa +
        adm1_state.get('X_pr', 0) * N_aa +
        (adm1_state.get('X_su', 0) + adm1_state.get('X_aa', 0) + 
         adm1_state.get('X_fa', 0) + adm1_state.get('X_c4', 0) +
         adm1_state.get('X_pro', 0) + adm1_state.get('X_ac', 0) +
         adm1_state.get('X_h2', 0) + adm1_state.get('X_PAO', 0)) * N_bm
    )
    
    tkn = inorganic_n + organic_n
    return tkn * 1000  # Convert kg N/m³ to mg N/L


def calculate_tp(adm1_state: Dict[str, float]) -> float:
    """
    Calculate Total Phosphorus from ADM1 components.
    
    TP = S_IP + X_PP + P in biomass
    """
    # Phosphorus content in biomass (typical)
    P_bm = 0.02  # kg P/kg COD for biomass
    
    # Inorganic phosphorus (S_IP is in kg P/m³)
    inorganic_p = adm1_state.get('S_IP', 0)
    
    # Polyphosphate (X_PP is in kg P/m³)
    poly_p = adm1_state.get('X_PP', 0)
    
    # Organic phosphorus in biomass
    biomass_p = (
        adm1_state.get('X_PAO', 0) * P_bm * 2 +  # PAOs have higher P content
        (adm1_state.get('X_su', 0) + adm1_state.get('X_aa', 0) + 
         adm1_state.get('X_fa', 0) + adm1_state.get('X_c4', 0) +
         adm1_state.get('X_pro', 0) + adm1_state.get('X_ac', 0) +
         adm1_state.get('X_h2', 0)) * P_bm
    )
    
    tp = inorganic_p + poly_p + biomass_p
    return tp * 1000  # Convert kg P/m³ to mg P/L


def estimate_alkalinity(adm1_state: Dict[str, float], ph: float = 7.0) -> float:
    """
    Estimate alkalinity from ADM1 components.
    
    Alkalinity = HCO3- + 2*CO3-- + OH- - H+ + organic acid anions
    """
    # Inorganic carbon (S_IC in kg C/m³)
    s_ic = adm1_state.get('S_IC', 0.05)
    s_ic_mol = s_ic / 0.012  # Convert to mol C/m³
    
    # Calculate carbonate species based on pH
    # pKa1 = 6.35, pKa2 = 10.33 for carbonate system
    h_conc = 10**(-ph)
    ka1 = 10**(-6.35)
    ka2 = 10**(-10.33)
    
    ct = s_ic_mol  # Total carbonate
    alpha0 = h_conc**2 / (h_conc**2 + h_conc*ka1 + ka1*ka2)
    alpha1 = h_conc*ka1 / (h_conc**2 + h_conc*ka1 + ka1*ka2)
    alpha2 = ka1*ka2 / (h_conc**2 + h_conc*ka1 + ka1*ka2)
    
    hco3 = ct * alpha1  # mol/m³
    co3 = ct * alpha2   # mol/m³
    
    # Organic acid contributions (simplified - acetate, propionate, butyrate)
    # Convert from kg COD/m³ to mol/m³
    acetate_mol = adm1_state.get('S_ac', 0) / 0.064  # 64 g COD/mol acetate
    propionate_mol = adm1_state.get('S_pro', 0) / 0.112  # 112 g COD/mol propionate
    butyrate_mol = adm1_state.get('S_bu', 0) / 0.160  # 160 g COD/mol butyrate
    
    # Total alkalinity in meq/L
    alkalinity = (
        hco3 + 2*co3 +  # Carbonate alkalinity
        acetate_mol + propionate_mol + butyrate_mol  # Organic acid alkalinity
    ) / 1000 * 1000  # Convert mol/m³ to meq/L
    
    return alkalinity


def calculate_strong_ion_residual(
    adm1_state: Dict[str, float],
    ph: float = 7.0,
    pkw: float = 14.0,
    mode: str = "watertap"  # "watertap" or "general"
) -> Dict[str, Any]:
    """
    Calculate electroneutrality with S_cat/S_an as OTHER ions only.
    Matches WaterTAP's S_H_cons constraint logic.
    
    Args:
        adm1_state: ADM1 component concentrations
        ph: pH value
        pkw: pKw value (default 14.0)
        mode: "watertap" (match S_H_cons, no CO3--) or "general" (include CO3--)
    
    Returns:
        Detailed charge balance with suggestions for correction
    """
    # Helper to get values
    def _gv(k: str, d: float = 0.0) -> float:
        v = adm1_state.get(k, d)
        try:
            return float(v)
        except Exception:
            return d
    
    # === EXPLICIT CATIONS (mol/m³) ===
    
    # NH4+ with speciation (pKa = 9.25)
    s_in_kg_m3 = _gv("S_IN", 0.0)
    nh_total_mol_m3 = s_in_kg_m3 / 0.014 if s_in_kg_m3 > 0 else 0.0
    alpha_nh4 = 1.0 / (1.0 + 10**(ph - 9.25))
    nh4_mol_m3 = nh_total_mol_m3 * alpha_nh4
    
    # K+ and Mg2+ handling depends on mode
    if mode == "watertap":
        # WaterTAP derives K/Mg from polyphosphate (X_PP) in S_H_cons
        # This matches the Modified ADM1 property model behavior
        x_pp_kg_m3 = _gv("X_PP", 0.0)
        # Stoichiometric factors from WaterTAP (approximate)
        # X_PP releases K and Mg during hydrolysis
        k_mol_m3 = x_pp_kg_m3 / 0.30041 if x_pp_kg_m3 > 0 else 0.0
        mg_mol_m3 = x_pp_kg_m3 / 0.30041 if x_pp_kg_m3 > 0 else 0.0
    else:
        # General mode: use explicit S_K and S_Mg values
        k_mol_m3 = _gv("S_K", 0.0) / 0.0391 if _gv("S_K", 0.0) > 0 else 0.0
        mg_mol_m3 = _gv("S_Mg", 0.0) / 0.0243 if _gv("S_Mg", 0.0) > 0 else 0.0
    
    # H+ (mol/m³)
    h_mol_m3 = 10**(-ph) * 1000.0
    
    # S_cat as OTHER cations (kmol/m³ -> mol/m³)
    s_cat_other_mol_m3 = _gv("S_cat", 0.0) * 1000.0
    
    # === EXPLICIT ANIONS (mol/m³) ===
    
    # Carbonate system
    s_ic_kg_m3 = _gv("S_IC", 0.0)
    ct_mol_m3 = s_ic_kg_m3 / 0.012 if s_ic_kg_m3 > 0 else 0.0
    
    # Carbonate speciation (pKa1=6.35, pKa2=10.33)
    h = 10**(-ph)
    ka1 = 10**(-6.35)
    ka2 = 10**(-10.33)
    denom = h**2 + h*ka1 + ka1*ka2
    
    if denom > 0:
        alpha1 = (h * ka1) / denom  # HCO3- fraction
        alpha2 = (ka1 * ka2) / denom  # CO3-- fraction
    else:
        alpha1, alpha2 = 0.0, 0.0
    
    hco3_mol_m3 = ct_mol_m3 * alpha1
    co3_mol_m3 = ct_mol_m3 * alpha2 if mode == "general" else 0.0
    
    # VFA anions (fully deprotonated at pH > 5)
    # Using WaterTAP's COD conversions
    ac_mol_m3 = _gv("S_ac", 0.0) / 0.064
    pro_mol_m3 = _gv("S_pro", 0.0) / 0.112
    bu_mol_m3 = _gv("S_bu", 0.0) / 0.160
    va_mol_m3 = _gv("S_va", 0.0) / 0.208
    vfa_mol_m3 = ac_mol_m3 + pro_mol_m3 + bu_mol_m3 + va_mol_m3
    
    # OH- (mol/m³)
    oh_mol_m3 = 10**(ph - pkw) * 1000.0
    
    # S_an as OTHER anions (kmol/m³ -> mol/m³)
    s_an_other_mol_m3 = _gv("S_an", 0.0) * 1000.0
    
    # === TOTALS ===
    
    # Total cations (charge equivalents)
    cations_total = (s_cat_other_mol_m3 + nh4_mol_m3 + 
                     k_mol_m3 + 2.0*mg_mol_m3 + h_mol_m3)
    
    # Total anions (charge equivalents)
    if mode == "watertap":
        # Match WaterTAP S_H_cons exactly (no CO3--)
        anions_total = (s_an_other_mol_m3 + hco3_mol_m3 + 
                       vfa_mol_m3 + oh_mol_m3)
    else:
        # General chemistry mode (include CO3--)
        anions_total = (s_an_other_mol_m3 + hco3_mol_m3 + 
                       2.0*co3_mol_m3 + vfa_mol_m3 + oh_mol_m3)
    
    # Residual and imbalance
    residual_mol_m3 = cations_total - anions_total
    scale = max(abs(cations_total), abs(anions_total), 1e-9)
    imbalance_pct = 100.0 * abs(residual_mol_m3) / scale
    
    # Suggestion for balancing
    if abs(residual_mol_m3) > 1.0:  # > 1 meq/L imbalance
        if residual_mol_m3 > 0:
            # Need more anions
            required_s_an = s_an_other_mol_m3 + residual_mol_m3
            suggestion = f"Increase S_an to {required_s_an/1000:.4f} kmol/m³"
        else:
            # Need more cations
            required_s_cat = s_cat_other_mol_m3 - residual_mol_m3
            suggestion = f"Increase S_cat to {required_s_cat/1000:.4f} kmol/m³"
    else:
        suggestion = "Balance OK"
    
    return {
        "cations": {
            "S_cat_OTHER": s_cat_other_mol_m3,
            "NH4+": nh4_mol_m3,
            "K+": k_mol_m3,
            "Mg2+": mg_mol_m3 * 2.0,  # charge equivalents
            "H+": h_mol_m3,
            "total": cations_total
        },
        "anions": {
            "S_an_OTHER": s_an_other_mol_m3,
            "HCO3-": hco3_mol_m3,
            "CO3--": co3_mol_m3 * 2.0 if mode == "general" else 0.0,
            "VFA_anions": vfa_mol_m3,
            "OH-": oh_mol_m3,
            "total": anions_total
        },
        "residual_mol_m3": residual_mol_m3,
        "residual_meq_l": residual_mol_m3,  # mol/m³ = meq/L for monovalent
        "imbalance_percent": imbalance_pct,
        "balanced": imbalance_pct < 5.0,
        "suggestion": suggestion,
        "mode": mode
    }


def compute_bulk_composites(adm1_state: Dict[str, float]) -> Dict[str, float]:
    """
    Convenience: compute composite bulk parameters from an ADM1 state.
    Returns mg/L for COD, TSS, VSS, TKN, TP.
    """
    cod_mg_l = calculate_total_cod(adm1_state) * 1000.0
    tss_mg_l = calculate_tss(adm1_state)
    vss_mg_l = calculate_vss(adm1_state)
    tkn_mg_l = calculate_tkn(adm1_state)
    tp_mg_l = calculate_tp(adm1_state)
    return {
        "cod_mg_l": cod_mg_l,
        "tss_mg_l": tss_mg_l,
        "vss_mg_l": vss_mg_l,
        "tkn_mg_l": tkn_mg_l,
        "tp_mg_l": tp_mg_l,
    }


def validate_adm1_state(
    adm1_state: Dict[str, Any],
    user_parameters: Dict[str, float],
    tolerance: float = 0.1
) -> Dict[str, Any]:
    """
    Validate ADM1 state against user-provided composite parameters.
    
    Args:
        adm1_state: Dictionary of ADM1 component concentrations
                   Can be in format {"S_su": value} or {"S_su": [value, unit, explanation]}
        user_parameters: Dictionary with measured values:
                        - cod_mg_l: COD concentration in mg/L
                        - tss_mg_l: TSS concentration in mg/L
                        - vss_mg_l: VSS concentration in mg/L
                        - tkn_mg_l: TKN concentration in mg/L
                        - tp_mg_l: TP concentration in mg/L
                        - ph: pH value
                        - alkalinity_meq_l: Alkalinity in meq/L
        tolerance: Relative tolerance for validation (default 10%)
    
    Returns:
        Dictionary with validation results
    """
    # Extract values if in [value, unit, explanation] format
    clean_state = {}
    for key, val in adm1_state.items():
        if isinstance(val, list):
            clean_state[key] = val[0]
        else:
            clean_state[key] = val
    
    # Normalize user parameter keys for unit-conversion conveniences
    # Support alkalinity reported as mg/L as CaCO3
    norm = {k.lower(): k for k in user_parameters.keys()}
    for key in ("alkalinity_mg_l_as_caco3", "alkalinity_caco3_mg_l", "alkalinity_mg_l_caco3"):
        if key in norm and "alkalinity_meq_l" not in user_parameters:
            try:
                original_key = norm[key]
                mgL = float(user_parameters[original_key])
                user_parameters["alkalinity_meq_l"] = mgL / 50.0
            except Exception:
                logger.warning("Failed to convert alkalinity from mg/L as CaCO3 to meq/L")

    results = {
        "valid": True,
        "calculated_parameters": {},
        "user_parameters": user_parameters,
        "deviations": {},
        "warnings": [],
        "pass_fail": {}
    }
    
    # Calculate composite parameters
    if 'cod_mg_l' in user_parameters:
        calc_cod = calculate_total_cod(clean_state) * 1000  # kg/m³ to mg/L
        results["calculated_parameters"]["cod_mg_l"] = calc_cod
        
        deviation = abs(calc_cod - user_parameters['cod_mg_l']) / user_parameters['cod_mg_l']
        results["deviations"]["cod_percent"] = deviation * 100
        
        if deviation > tolerance:
            results["warnings"].append(
                f"COD deviation {deviation*100:.1f}% exceeds tolerance"
            )
            results["pass_fail"]["cod"] = "FAIL"
            results["valid"] = False
        else:
            results["pass_fail"]["cod"] = "PASS"
    
    if 'tss_mg_l' in user_parameters:
        calc_tss = calculate_tss(clean_state)
        results["calculated_parameters"]["tss_mg_l"] = calc_tss
        
        deviation = abs(calc_tss - user_parameters['tss_mg_l']) / user_parameters['tss_mg_l']
        results["deviations"]["tss_percent"] = deviation * 100
        
        if deviation > tolerance:
            results["warnings"].append(
                f"TSS deviation {deviation*100:.1f}% exceeds tolerance"
            )
            results["pass_fail"]["tss"] = "FAIL"
            results["valid"] = False
        else:
            results["pass_fail"]["tss"] = "PASS"
    
    if 'vss_mg_l' in user_parameters:
        calc_vss = calculate_vss(clean_state)
        results["calculated_parameters"]["vss_mg_l"] = calc_vss
        
        deviation = abs(calc_vss - user_parameters['vss_mg_l']) / user_parameters['vss_mg_l']
        results["deviations"]["vss_percent"] = deviation * 100
        
        if deviation > tolerance:
            results["warnings"].append(
                f"VSS deviation {deviation*100:.1f}% exceeds tolerance"
            )
            results["pass_fail"]["vss"] = "FAIL"
            results["valid"] = False
        else:
            results["pass_fail"]["vss"] = "PASS"
    
    if 'tkn_mg_l' in user_parameters:
        calc_tkn = calculate_tkn(clean_state)
        results["calculated_parameters"]["tkn_mg_l"] = calc_tkn
        
        deviation = abs(calc_tkn - user_parameters['tkn_mg_l']) / user_parameters['tkn_mg_l']
        results["deviations"]["tkn_percent"] = deviation * 100
        
        if deviation > tolerance:
            results["warnings"].append(
                f"TKN deviation {deviation*100:.1f}% exceeds tolerance"
            )
            results["pass_fail"]["tkn"] = "FAIL"
            results["valid"] = False
        else:
            results["pass_fail"]["tkn"] = "PASS"
    
    if 'tp_mg_l' in user_parameters:
        calc_tp = calculate_tp(clean_state)
        results["calculated_parameters"]["tp_mg_l"] = calc_tp
        
        deviation = abs(calc_tp - user_parameters['tp_mg_l']) / user_parameters['tp_mg_l']
        results["deviations"]["tp_percent"] = deviation * 100
        
        if deviation > tolerance:
            results["warnings"].append(
                f"TP deviation {deviation*100:.1f}% exceeds tolerance"
            )
            results["pass_fail"]["tp"] = "FAIL"
            results["valid"] = False
        else:
            results["pass_fail"]["tp"] = "PASS"
    
    if 'alkalinity_meq_l' in user_parameters:
        ph = user_parameters.get('ph', 7.0)
        calc_alk = estimate_alkalinity(clean_state, ph)
        results["calculated_parameters"]["alkalinity_meq_l"] = calc_alk
        
        deviation = abs(calc_alk - user_parameters['alkalinity_meq_l']) / user_parameters['alkalinity_meq_l']
        results["deviations"]["alkalinity_percent"] = deviation * 100
        
        if deviation > tolerance * 2:  # More tolerance for alkalinity
            results["warnings"].append(
                f"Alkalinity deviation {deviation*100:.1f}% exceeds tolerance"
            )
            results["pass_fail"]["alkalinity"] = "FAIL"
            results["valid"] = False
        else:
            results["pass_fail"]["alkalinity"] = "PASS"
    
    # Check charge balance
    s_cat = clean_state.get('S_cat', 0) * 1000  # kmol/m³ to mol/m³
    s_an = clean_state.get('S_an', 0) * 1000   # kmol/m³ to mol/m³
    
    charge_imbalance = abs(s_cat - s_an) / max(s_cat, s_an, 0.001)
    if charge_imbalance > 0.05:  # 5% imbalance
        results["warnings"].append(
            f"Charge imbalance: {charge_imbalance*100:.1f}%"
        )
    
    return results


def reconcile_composites(
    adm1_state: Dict[str, Any],
    user_parameters: Dict[str, float],
    tolerance: float = 0.1
) -> Tuple[Dict[str, float], Dict[str, str]]:
    """
    Reconcile ADM1 state to match measured composite parameters.
    
    Adjusts ADM1 component concentrations to better match user-provided
    COD, TSS/VSS, TKN, TP while maintaining reasonable mass balances.
    
    Args:
        adm1_state: Initial ADM1 state (may have triplet format)
        user_parameters: Target composite values (cod_mg_l, tss_mg_l, etc.)
        tolerance: Acceptable deviation fraction
        
    Returns:
        Tuple of (reconciled_state, adjustments_made)
    """
    # Extract numeric values from ADM1 state
    from utils.state_utils import clean_adm1_state
    clean_state, _ = clean_adm1_state(adm1_state)
    reconciled = copy.deepcopy(clean_state)
    adjustments = {}
    
    # 1. Reconcile COD if provided
    if 'cod_mg_l' in user_parameters:
        calc_cod = calculate_total_cod(reconciled)
        target_cod = user_parameters['cod_mg_l']
        
        if abs(calc_cod - target_cod) / target_cod > tolerance:
            # Scale all organic components proportionally
            scale_factor = target_cod / calc_cod
            organics = ['S_su', 'S_aa', 'S_fa', 'S_va', 'S_bu', 'S_pro', 'S_ac',
                       'X_ch', 'X_pr', 'X_li', 'X_c']
            
            for comp in organics:
                if comp in reconciled:
                    reconciled[comp] *= scale_factor
            
            adjustments["COD"] = f"Scaled organics by {scale_factor:.2f}"
    
    # 2. Reconcile TSS/VSS if provided
    if 'tss_mg_l' in user_parameters and 'vss_mg_l' in user_parameters:
        target_tss = user_parameters['tss_mg_l'] / 1000  # Convert to kg/m³
        target_vss = user_parameters['vss_mg_l'] / 1000
        target_iss = target_tss - target_vss
        
        # Adjust X_I to meet ISS target
        # ISS = X_I + biomass_ash + polyphosphate_minerals
        biomass_total = sum([reconciled.get(c, 0) for c in 
                           ['X_su', 'X_aa', 'X_fa', 'X_c4', 'X_pro', 'X_ac', 'X_h2', 'X_PAO']])
        biomass_ash = 0.1 * biomass_total / 1.42  # 10% ash content
        pp_minerals = 3.23 * reconciled.get('X_PP', 0)
        
        required_xi = max(0, target_iss - biomass_ash - pp_minerals)
        reconciled['X_I'] = required_xi
        adjustments["TSS"] = f"Set X_I to {required_xi:.3f} kg/m³ for ISS target"
    
    # 3. Reconcile TP if provided
    if 'tp_mg_l' in user_parameters:
        target_tp = user_parameters['tp_mg_l'] / 1000  # Convert to kg P/m³
        
        # Current P content
        current_p = reconciled.get('S_IP', 0) + reconciled.get('X_PP', 0)
        
        if abs(current_p - target_tp) / target_tp > tolerance:
            # Distribute P between S_IP (30%) and X_PP (70%) for raw wastewater
            reconciled['S_IP'] = target_tp * 0.3
            reconciled['X_PP'] = target_tp * 0.7
            adjustments["TP"] = f"Redistributed P: S_IP={reconciled['S_IP']:.4f}, X_PP={reconciled['X_PP']:.4f}"
    
    # 4. Reconcile TKN if provided
    if 'tkn_mg_l' in user_parameters:
        target_tkn = user_parameters['tkn_mg_l'] / 1000  # Convert to kg N/m³
        
        # Organic N is mostly in proteins
        protein_n = reconciled.get('X_pr', 0) * 0.16  # Proteins are ~16% N
        aa_n = reconciled.get('S_aa', 0) * 0.16
        
        # Adjust S_IN to meet target
        required_sin = max(0, target_tkn - protein_n - aa_n)
        reconciled['S_IN'] = required_sin
        adjustments["TKN"] = f"Set S_IN to {required_sin:.4f} kg/m³ for TKN target"
    
    # 5. Maintain charge balance
    cation_charge = reconciled.get('S_cat', 0.04)
    anion_charge = reconciled.get('S_an', 0.04)
    
    # Simple electroneutrality adjustment
    avg_charge = (cation_charge + anion_charge) / 2
    reconciled['S_cat'] = avg_charge
    reconciled['S_an'] = avg_charge
    
    if abs(cation_charge - anion_charge) > 0.001:
        adjustments["Charge"] = f"Balanced S_cat=S_an={avg_charge:.4f} kmol/m³"
    
    return reconciled, adjustments
