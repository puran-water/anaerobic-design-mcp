#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Synchronous QSDsan validation functions for subprocess isolation.

These are synchronous (non-async) versions of the validation functions,
designed to be called from subprocess CLI scripts.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def _load_qsdsan_components():
    """Load QSDsan components synchronously (no async)."""
    from utils.extract_qsdsan_sulfur_components import create_adm1_sulfur_cmps
    return create_adm1_sulfur_cmps()


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


def check_charge_balance_sync(adm1_state: Dict[str, Any], ph: float, temperature_k: float) -> Dict[str, Any]:
    """
    Check strong-ion charge balance consistency vs pH.

    SYNCHRONOUS version for subprocess isolation.

    Args:
        adm1_state: ADM1 state dict (kg/m³)
        ph: pH for speciation
        temperature_k: Temperature in Kelvin

    Returns:
        Dictionary with balance status and residuals
    """
    from qsdsan import WasteStream, set_thermo

    # Load components
    ADM1_SULFUR_CMPS = _load_qsdsan_components()
    set_thermo(ADM1_SULFUR_CMPS)

    # Create WasteStream using set_flow_by_concentration
    ws = WasteStream(ID='temp_balance', T=temperature_k, pH=ph)

    # Filter to only valid component IDs
    valid_ids = {c.ID for c in ADM1_SULFUR_CMPS}
    filtered_state = {k: v for k, v in adm1_state.items() if k in valid_ids}

    # Set concentrations using the proper QSDsan method
    ws.set_flow_by_concentration(
        flow_tot=1.0,  # 1 m³/d for unit concentration calculations
        concentrations=filtered_state,
        units=('m3/d', 'kg/m3')
    )

    # Get charge composite (automatically includes all charged species)
    net_charge_mmol_l = ws.charge * 1000  # mol/m³ → mmol/L
    residual_meq_l = abs(net_charge_mmol_l)  # meq/L

    # Calculate imbalance percentage
    # Use total ionic strength as reference
    total_cations = sum([
        ws.imass[comp.ID] / comp.MW * comp.charge * 1000
        for comp in ws.components
        if comp.charge > 0
    ])

    if total_cations > 0:
        imbalance_percent = (residual_meq_l / total_cations) * 100
    else:
        imbalance_percent = 0.0

    balanced = imbalance_percent <= 5.0

    return {
        "residual_meq_l": round(residual_meq_l, 4),
        "net_charge_mmol_l": round(net_charge_mmol_l, 4),
        "imbalance_percent": round(imbalance_percent, 2),
        "balanced": balanced,
        "calculated_ph": round(ws.pH, 2),
        "target_ph": round(ph, 2),
        "message": "Charge balance OK" if balanced else f"Charge imbalance: {imbalance_percent:.1f}%"
    }
