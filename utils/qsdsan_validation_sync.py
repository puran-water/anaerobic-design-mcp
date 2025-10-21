#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Synchronous QSDsan validation functions for subprocess isolation.

These are synchronous (non-async) versions of the validation functions,
designed to be called from subprocess CLI scripts.
"""

# CRITICAL FIX: Patch fluids.numerics BEFORE any QSDsan imports
# thermo package (dependency of thermosteam → biosteam → qsdsan) expects
# numerics.PY37 which was removed in fluids 1.2.0
# Since we're on Python 3.12, PY37 should always be True
import fluids.numerics
if not hasattr(fluids.numerics, 'PY37'):
    fluids.numerics.PY37 = True  # Python 3.12 > 3.7

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def _load_qsdsan_components():
    """Load QSDsan mADM1 components synchronously (no async)."""
    # CRITICAL FIX: Patch fluids.numerics for compatibility with thermo package
    # thermo package expects numerics.PY37 which was removed in fluids 1.2.0
    # Since we're on Python 3.12, PY37 should always be True
    import fluids.numerics
    if not hasattr(fluids.numerics, 'PY37'):
        fluids.numerics.PY37 = True  # Python 3.12 > 3.7

    # CRITICAL: Must use mADM1 (62 components) to match simulation
    # Using ADM1+sulfur (30 components) would miss cations/precipitates
    from utils.qsdsan_madm1 import create_madm1_cmps
    return create_madm1_cmps(set_thermo=True)


def validate_adm1_state_sync(
    adm1_state: Dict[str, Any],
    user_parameters: Dict[str, float],
    tolerance: float,
    temperature_k: float
) -> Dict[str, Any]:
    """
    Validate ADM1 state against composite parameters using QSDsan.

    SYNCHRONOUS version for subprocess isolation.

    Args:
        adm1_state: Dictionary of ADM1 component concentrations (kg/m3)
        user_parameters: Dictionary with measured values (cod_mg_l, tss_mg_l, etc.)
        tolerance: Relative tolerance for validation (default 10%)
        temperature_k: Temperature in Kelvin

    Returns:
        Dictionary containing validation results
    """
    from qsdsan import WasteStream, set_thermo

    # Load components
    ADM1_SULFUR_CMPS = _load_qsdsan_components()
    set_thermo(ADM1_SULFUR_CMPS)

    # Create WasteStream with ADM1 state using set_flow_by_concentration
    ws = WasteStream(ID='temp_validation', T=temperature_k)

    # Filter to only valid component IDs
    valid_ids = {c.ID for c in ADM1_SULFUR_CMPS}
    filtered_state = {k: v for k, v in adm1_state.items() if k in valid_ids}

    # Set concentrations (kg/m³) using the proper QSDsan method
    ws.set_flow_by_concentration(
        flow_tot=1.0,  # 1 m³/d for unit concentration calculations
        concentrations=filtered_state,
        units=('m3/d', 'kg/m3')
    )

    # Calculate composites using QSDsan methods and properties
    calculated = {
        "cod_mg_l": ws.composite('COD', unit='g/m3'),  # g/m³ = mg/L
        "tss_mg_l": ws.get_TSS(),  # Returns mg/L
        "vss_mg_l": ws.get_VSS(),  # Returns mg/L
        "tkn_mg_l": ws.TKN,  # Property, returns mg/L
        "tp_mg_l": ws.TP  # Property, returns mg/L
    }

    # Calculate deviations
    deviations = {}
    pass_fail = {}
    warnings = []
    all_valid = True

    for param in ["cod_mg_l", "tss_mg_l", "vss_mg_l", "tkn_mg_l", "tp_mg_l"]:
        if param in user_parameters and user_parameters[param] is not None:
            target = user_parameters[param]
            calc = calculated[param]

            if target > 0:
                deviation = abs(calc - target) / target
                deviations[param] = {
                    "calculated": round(calc, 2),
                    "target": round(target, 2),
                    "deviation_percent": round(deviation * 100, 2)
                }

                passed = deviation <= tolerance
                pass_fail[param] = "PASS" if passed else "FAIL"

                if not passed:
                    all_valid = False
                    warnings.append(
                        f"{param.upper()}: {calc:.1f} mg/L (target: {target:.1f} mg/L, "
                        f"deviation: {deviation*100:.1f}%)"
                    )

    return {
        "valid": all_valid,
        "calculated_parameters": calculated,
        "deviations": deviations,
        "pass_fail": pass_fail,
        "warnings": warnings
    }


def calculate_composites_sync(adm1_state: Dict[str, Any], temperature_k: float) -> Dict[str, float]:
    """
    Compute COD, TSS, VSS, TKN, TP (mg/L) from an ADM1 state.

    SYNCHRONOUS version for subprocess isolation.

    Args:
        adm1_state: ADM1 state dict (kg/m³ concentrations)
        temperature_k: Temperature in Kelvin

    Returns:
        Dictionary with cod_mg_l, tss_mg_l, vss_mg_l, tkn_mg_l, tp_mg_l
    """
    from qsdsan import WasteStream, set_thermo

    # Load components
    ADM1_SULFUR_CMPS = _load_qsdsan_components()
    set_thermo(ADM1_SULFUR_CMPS)

    # Create WasteStream using set_flow_by_concentration
    ws = WasteStream(ID='temp_composites', T=temperature_k)

    # Filter to only valid component IDs
    valid_ids = {c.ID for c in ADM1_SULFUR_CMPS}
    filtered_state = {k: v for k, v in adm1_state.items() if k in valid_ids}

    # Set concentrations using the proper QSDsan method
    ws.set_flow_by_concentration(
        flow_tot=1.0,  # 1 m³/d for unit concentration calculations
        concentrations=filtered_state,
        units=('m3/d', 'kg/m3')
    )

    # Calculate composites using QSDsan methods and properties
    return {
        "cod_mg_l": round(ws.composite('COD', unit='g/m3'), 2),
        "tss_mg_l": round(ws.get_TSS(), 2),
        "vss_mg_l": round(ws.get_VSS(), 2),
        "tkn_mg_l": round(ws.TKN, 2),
        "tp_mg_l": round(ws.TP, 2)
    }


def check_charge_balance_sync(adm1_state: Dict[str, Any], target_ph: float, temperature_k: float) -> Dict[str, Any]:
    """
    Solve for equilibrium pH that satisfies electroneutrality, then compare to target.

    This is the CORRECT approach: the ionic imbalance drives pH to an equilibrium value
    that may differ from the target. We solve for that equilibrium pH, then report the
    deviation so Codex can adjust cations to achieve the target pH.

    Args:
        adm1_state: ADM1 state dict (kg/m³)
        target_ph: Target pH from basis of design
        temperature_k: Temperature in Kelvin

    Returns:
        Dictionary with equilibrium pH, target pH, deviation, and charge balance details
    """
    from scipy.optimize import brentq

    def charge_residual(ph_trial):
        """
        Calculate net charge (cations - anions) at a trial pH.
        Electroneutrality is satisfied when this returns 0.
        """
        result = check_charge_balance_sync_lightweight(adm1_state, ph_trial, temperature_k)
        return result['net_charge_meq_l']

    # Solve for pH where charge residual = 0
    # pH range: 4.0 to 10.0 (typical for anaerobic digestion)
    try:
        equilibrium_ph = brentq(charge_residual, 4.0, 10.0, xtol=0.01)
    except ValueError:
        # If no root found in range, check endpoints to determine direction
        residual_low = charge_residual(4.0)
        residual_high = charge_residual(10.0)

        if abs(residual_low) < abs(residual_high):
            equilibrium_ph = 4.0  # Severe anion excess
        else:
            equilibrium_ph = 10.0  # Severe cation excess

    # Get full charge balance at equilibrium pH
    balance_at_eq = check_charge_balance_sync_lightweight(adm1_state, equilibrium_ph, temperature_k)

    # Calculate deviation from target
    ph_deviation = abs(equilibrium_ph - target_ph)
    balanced = ph_deviation <= 0.5  # ±0.5 pH units tolerance

    if balanced:
        message = f"Charge balance OK - equilibrium pH {equilibrium_ph:.2f} matches target {target_ph:.2f}"
    else:
        message = (
            f"Equilibrium pH ({equilibrium_ph:.2f}) differs from target ({target_ph:.2f}) "
            f"by {ph_deviation:.2f} units. Add cations to raise pH or add anions to lower pH."
        )

    return {
        "equilibrium_ph": round(equilibrium_ph, 2),
        "target_ph": round(target_ph, 2),
        "ph_deviation": round(ph_deviation, 2),
        "cation_meq_l": balance_at_eq['cation_meq_l'],
        "anion_meq_l": balance_at_eq['anion_meq_l'],
        "residual_meq_l": balance_at_eq['residual_meq_l'],
        "balanced": balanced,
        "message": message
    }


def check_charge_balance_sync_lightweight(adm1_state: Dict[str, Any], ph: float, temperature_k: float) -> Dict[str, Any]:
    """
    Mass-conserving charge balance check using Henderson-Hasselbalch equilibria.

    Following Codex recommendation: uses continuous weak-acid fractions instead of
    step functions, and includes S_fa (fatty acids) as identified missing species.

    Args:
        adm1_state: ADM1 state dict (kg/m³)
        ph: pH for speciation
        temperature_k: Temperature in Kelvin

    Returns:
        Dictionary with balance status and residuals
    """
    import math

    # Molecular weights (g/mol)
    MW = {
        'Na': 23.0, 'K': 39.1, 'Mg': 24.3, 'Ca': 40.1,
        'Fe': 55.8, 'Al': 27.0, 'N': 14.0, 'S': 32.1,
        'C': 12.0, 'P': 31.0, 'Cl': 35.5
    }

    # Temperature-corrected pKa values (simplified - could use van't Hoff)
    # For 35°C (308K), rough corrections from 25°C values
    temp_C = temperature_k - 273.15
    pKa_NH4 = 9.25 + 0.02 * (temp_C - 25)  # NH3/NH4+
    pKa_CO2_1 = 6.35 + 0.01 * (temp_C - 25)  # CO2/HCO3-
    pKa_CO2_2 = 10.33 + 0.01 * (temp_C - 25)  # HCO3-/CO3 2-
    pKa_H2S_1 = 7.0 + 0.01 * (temp_C - 25)  # H2S/HS-
    pKa_H2S_2 = 12.9  # HS-/S2- (rarely matters)
    pKa_PO4_1 = 2.1  # H3PO4/H2PO4-
    pKa_PO4_2 = 7.2  # H2PO4-/HPO4 2-
    pKa_PO4_3 = 12.4  # HPO4 2-/PO4 3-
    pKa_VFA = 4.75  # Typical for VFAs (acetate ~4.75, propionate ~4.87, butyrate ~4.82)
    pKa_fa = 4.8  # Long-chain fatty acids

    # Helper: Henderson-Hasselbalch fraction of deprotonated form
    def frac_deprotonated(pKa):
        """Fraction in deprotonated (anionic) form: A-/(HA + A-)"""
        return 1.0 / (1.0 + 10**(pKa - ph))

    def frac_protonated(pKa):
        """Fraction in protonated (cationic/neutral) form: HA/(HA + A-)"""
        return 1.0 / (1.0 + 10**(ph - pKa))

    # Calculate cation equivalents (meq/L = mmol/L × charge)
    cations_meq = 0.0

    # Monovalent cations (1+ charge): kg/m³ → mmol/L × charge
    cations_meq += adm1_state.get('S_Na', 0) / MW['Na'] * 1000 * 1
    cations_meq += adm1_state.get('S_K', 0) / MW['K'] * 1000 * 1

    # Divalent cations (2+ charge)
    cations_meq += adm1_state.get('S_Mg', 0) / MW['Mg'] * 1000 * 2
    cations_meq += adm1_state.get('S_Ca', 0) / MW['Ca'] * 1000 * 2
    cations_meq += adm1_state.get('S_Fe2', 0) / MW['Fe'] * 1000 * 2

    # Trivalent cations (3+ charge)
    cations_meq += adm1_state.get('S_Fe3', 0) / MW['Fe'] * 1000 * 3
    cations_meq += adm1_state.get('S_Al', 0) / MW['Al'] * 1000 * 3

    # Ammonium (NH4+) - pH dependent via Henderson-Hasselbalch
    S_IN = adm1_state.get('S_IN', 0)
    frac_nh4 = frac_protonated(pKa_NH4)  # NH4+ is protonated form
    cations_meq += S_IN / MW['N'] * 1000 * 1 * frac_nh4

    # Calculate anion equivalents (meq/L)
    anions_meq = 0.0

    # Chloride (Cl-, 1- charge, always fully dissociated)
    anions_meq += adm1_state.get('S_Cl', 0) / MW['Cl'] * 1000 * 1

    # VFAs (weak acids, pKa ~4.75) - Henderson-Hasselbalch
    frac_vfa_ion = frac_deprotonated(pKa_VFA)
    anions_meq += adm1_state.get('S_ac', 0) / 59 * 1000 * 1 * frac_vfa_ion   # Acetate
    anions_meq += adm1_state.get('S_pro', 0) / 73 * 1000 * 1 * frac_vfa_ion  # Propionate
    anions_meq += adm1_state.get('S_bu', 0) / 87 * 1000 * 1 * frac_vfa_ion   # Butyrate
    anions_meq += adm1_state.get('S_va', 0) / 101 * 1000 * 1 * frac_vfa_ion  # Valerate

    # Long-chain fatty acids (S_fa) - MISSING in original validator (Codex finding)
    frac_fa_ion = frac_deprotonated(pKa_fa)
    anions_meq += adm1_state.get('S_fa', 0) / 280 * 1000 * 1 * frac_fa_ion  # MW~280 for oleic acid

    # Inorganic carbon (CO2/HCO3-/CO3 2-) - diprotic acid
    S_IC = adm1_state.get('S_IC', 0)
    S_IC_mmol = S_IC / MW['C'] * 1000
    # Fraction of each species using exact diprotic equilibrium
    denom_ic = 1 + 10**(pKa_CO2_1 - ph) + 10**(ph - pKa_CO2_2)
    frac_hco3 = 1.0 / denom_ic  # HCO3- (charge -1)
    frac_co3 = 10**(ph - pKa_CO2_2) / denom_ic  # CO3 2- (charge -2)
    anions_meq += S_IC_mmol * (frac_hco3 * 1 + frac_co3 * 2)

    # Sulfate (SO4 2-, always fully dissociated)
    anions_meq += adm1_state.get('S_SO4', 0) / MW['S'] * 1000 * 2

    # Sulfide (H2S/HS-/S 2-) - diprotic acid
    S_IS = adm1_state.get('S_IS', 0)
    S_IS_mmol = S_IS / MW['S'] * 1000
    denom_is = 1 + 10**(pKa_H2S_1 - ph) + 10**(ph - pKa_H2S_2)
    frac_hs = 1.0 / denom_is  # HS- (charge -1)
    frac_s2 = 10**(ph - pKa_H2S_2) / denom_is  # S 2- (charge -2)
    anions_meq += S_IS_mmol * (frac_hs * 1 + frac_s2 * 2)

    # Phosphate (H3PO4/H2PO4-/HPO4 2-/PO4 3-) - triprotic acid
    S_IP = adm1_state.get('S_IP', 0)
    S_IP_mmol = S_IP / MW['P'] * 1000
    denom_ip = (1 + 10**(pKa_PO4_1 - ph) +
                10**(ph - pKa_PO4_2) +
                10**(2*ph - pKa_PO4_2 - pKa_PO4_3))
    frac_h2po4 = 1.0 / denom_ip  # H2PO4- (charge -1)
    frac_hpo4 = 10**(ph - pKa_PO4_2) / denom_ip  # HPO4 2- (charge -2)
    frac_po4 = 10**(2*ph - pKa_PO4_2 - pKa_PO4_3) / denom_ip  # PO4 3- (charge -3)
    anions_meq += S_IP_mmol * (frac_h2po4 * 1 + frac_hpo4 * 2 + frac_po4 * 3)

    # Calculate imbalance
    residual_meq_l = abs(cations_meq - anions_meq)
    net_charge = cations_meq - anions_meq

    # Imbalance percentage (relative to total cations)
    if cations_meq > 0:
        imbalance_percent = (residual_meq_l / cations_meq) * 100
    else:
        imbalance_percent = 100.0  # No cations = complete imbalance

    balanced = imbalance_percent <= 5.0

    return {
        "cation_meq_l": round(cations_meq, 4),
        "anion_meq_l": round(anions_meq, 4),
        "residual_meq_l": round(residual_meq_l, 4),
        "net_charge_meq_l": round(net_charge, 4),
        "imbalance_percent": round(imbalance_percent, 2),
        "balanced": balanced,
        "target_ph": round(ph, 2),
        "message": "Charge balance OK" if balanced else f"Charge imbalance: {imbalance_percent:.1f}% (excess {'cations' if net_charge > 0 else 'anions'})"
    }
