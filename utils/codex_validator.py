#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Codex ADM1 State Validation using QSDsan's Production pH Solver.

This module provides validation tools for Codex-generated ADM1 states,
ensuring they produce the correct equilibrium pH when loaded into QSDsan.

Key insight from Codex analysis (via QSD-Group/QSDsan):
- WasteStream.pH is just a stored attribute (defaults to 7.0)
- True pH is calculated by ADM1's PCM solver during simulation
- Validation must use the SAME solver to prevent false passes

References:
- qsdsan/_waste_stream.py:647 - WasteStream.pH is not auto-calculated
- qsdsan/processes/_adm1.py:152,179 - Production acid_base_rxn + solve_pH
- qsdsan/sanunits/_anaerobic_reactor.py:410 - pH pushed to effluent
"""

import numpy as np
from typing import Dict, Any


def qsdsan_equilibrium_ph(
    state_dict: Dict[str, float],
    temperature_k: float = 308.15
) -> float:
    """
    Calculate equilibrium pH using QSDsan's production PCM solver.

    This wraps our existing pcm() function in utils/qsdsan_madm1.py,
    which implements the same acid_base_rxn + Brent's method approach
    used by QSDsan during reactor simulation.

    Args:
        state_dict: ADM1 state variables with component IDs as keys,
                   concentrations in kg/m³ as values
        temperature_k: Temperature in Kelvin (default 35°C = 308.15 K)

    Returns:
        pH: Equilibrium pH from charge balance with Henderson-Hasselbalch
            speciation for all weak acids (NH3/NH4+, CO2/HCO3-, VFAs, H2S/HS-)

    Example:
        >>> state = {
        ...     'S_IN': 1.9,  # kg-N/m³
        ...     'S_IC': 1.5,  # kg-C/m³
        ...     'S_Na': 0.5,  # kg/m³
        ...     'S_ac': 0.2,  # kg/m³
        ...     # ... other components
        ... }
        >>> pH = qsdsan_equilibrium_ph(state, temperature_k=308.15)
        >>> print(f"Equilibrium pH: {pH:.2f}")
        Equilibrium pH: 7.15

    Notes:
        - Uses the SAME pcm() solver as reactor simulation
        - Accounts for temperature-corrected Ka values
        - Includes all explicit ions (Na+, K+, Mg²+, Ca²+, Fe²+/³+, Cl-, SO4²-)
        - Much more accurate than simple electroneutrality checks
    """
    # Import here to avoid circular dependencies
    from qsdsan.processes import mass2mol_conversion
    from utils.qsdsan_madm1 import create_madm1_cmps, ModifiedADM1, pcm
    from qsdsan import set_thermo

    # Load mADM1 components (63 components including H2O)
    cmps = create_madm1_cmps(set_thermo=True)
    set_thermo(cmps)

    # Build params dict with temperature correction
    model = ModifiedADM1()
    params = model.rate_function.params.copy()
    params['components'] = cmps
    params['unit_conv'] = mass2mol_conversion(cmps)
    params['T_op'] = temperature_k

    # Convert state_dict to array (fill missing components with zeros)
    state_arr = np.zeros(len(cmps))
    for ID, conc in state_dict.items():
        if ID in cmps.IDs:
            idx = cmps.index(ID)
            state_arr[idx] = conc

    # Call production PCM solver (same as reactor uses)
    # Returns: (pH, nh3, co2, activities)
    pH, nh3, co2, acts = pcm(state_arr, params)

    return pH


def validate_adm1_ion_balance(
    adm1_state: Dict[str, float],
    target_ph: float,
    target_alkalinity_meq_l: float = None,
    temperature_c: float = 35.0,
    ph_tolerance: float = 0.5
) -> Dict[str, Any]:
    """
    Validate ADM1 state charge balance using QSDsan's equilibrium pH solver.

    This is the CRITICAL validation that prevents "false pass" scenarios where
    simple electroneutrality checks claim pH 6.5 but QSDsan calculates pH 4.0.

    Args:
        adm1_state: Dictionary of ADM1 component concentrations (kg/m³)
        target_ph: Desired equilibrium pH (typically 7.0 for mesophilic digesters)
        target_alkalinity_meq_l: Target alkalinity in meq/L (optional)
        temperature_c: Operating temperature in Celsius (default 35°C)
        ph_tolerance: Acceptable pH deviation (default ±0.5 pH units)

    Returns:
        Dictionary with validation results:
        {
            'equilibrium_ph': float,        # Actual pH from PCM solver
            'target_ph': float,             # User-specified target
            'ph_deviation': float,          # abs(equilibrium - target)
            'ph_deviation_percent': float,  # Deviation as % of target
            'cations_meq_l': float,         # Total cations in meq/L
            'anions_meq_l': float,          # Total anions in meq/L
            'imbalance_meq_l': float,       # abs(cations - anions)
            'imbalance_percent': float,     # Imbalance as % of total
            'pass': bool,                   # True if within tolerances
            'warnings': list[str]           # Actionable warning messages
        }

    Example:
        >>> result = validate_adm1_ion_balance(
        ...     adm1_state={'S_IN': 0.0, 'S_IC': 0.6, 'S_Na': 1.2, ...},
        ...     target_ph=7.0,
        ...     temperature_c=35.0
        ... )
        >>> print(f"Pass: {result['pass']}")
        Pass: False
        >>> print(f"Equilibrium pH: {result['equilibrium_ph']:.2f}")
        Equilibrium pH: 4.05
        >>> print(result['warnings'])
        ['pH deviation: 2.95 units (target: 7.0, calculated: 4.05)',
         'S_IN = 0.0 kg-N/m³ - no ammonia buffer!',
         'Consider increasing S_Na or S_IC to raise pH']

    Notes:
        - Uses qsdsan_equilibrium_ph() for accurate pH calculation
        - Validates pH tolerance (default ±0.5 pH units)
        - Checks charge balance (should be <5% imbalance)
        - Provides actionable warnings for common mistakes
        - This is the validation Codex MUST use in .codex/AGENTS.md
    """
    temperature_k = temperature_c + 273.15

    # Calculate equilibrium pH using production solver
    equilibrium_ph = qsdsan_equilibrium_ph(adm1_state, temperature_k)

    # Calculate pH deviation
    ph_deviation = abs(equilibrium_ph - target_ph)
    ph_deviation_percent = (ph_deviation / target_ph) * 100

    # Calculate charge balance (cations vs anions)
    cations_meq_l, anions_meq_l = _calculate_charge_balance(adm1_state, equilibrium_ph)
    imbalance_meq_l = abs(cations_meq_l - anions_meq_l)
    total_charge = (cations_meq_l + anions_meq_l) / 2
    imbalance_percent = (imbalance_meq_l / total_charge * 100) if total_charge > 0 else 0.0

    # Determine pass/fail
    ph_pass = ph_deviation <= ph_tolerance
    charge_pass = imbalance_percent <= 5.0  # Within 5% is acceptable
    overall_pass = ph_pass and charge_pass

    # Generate warnings
    warnings = []

    if not ph_pass:
        warnings.append(
            f"pH deviation: {ph_deviation:.2f} units (target: {target_ph:.1f}, "
            f"calculated: {equilibrium_ph:.2f})"
        )

        # Diagnose common issues
        S_IN = adm1_state.get('S_IN', 0.0)
        S_IC = adm1_state.get('S_IC', 0.0)
        S_Na = adm1_state.get('S_Na', 0.0)

        if S_IN < 0.5:
            warnings.append(
                f"S_IN = {S_IN:.3f} kg-N/m³ - insufficient ammonia buffer! "
                f"Should be ~70-80% of TKN."
            )

        if S_IC < 1.0:
            warnings.append(
                f"S_IC = {S_IC:.3f} kg-C/m³ - low inorganic carbon. "
                f"Should be ~1.5-2.0 kg-C/m³ for 50 meq/L alkalinity."
            )

        if equilibrium_ph < target_ph:
            warnings.append(
                "pH too low: Increase S_Na (cations) or S_IC (alkalinity) "
                "to raise pH."
            )
        else:
            warnings.append(
                "pH too high: Decrease S_Na or increase VFAs (S_ac, S_pro) "
                "to lower pH."
            )

    if not charge_pass:
        warnings.append(
            f"Charge imbalance: {imbalance_percent:.1f}% "
            f"(cations: {cations_meq_l:.1f} meq/L, anions: {anions_meq_l:.1f} meq/L)"
        )

    # Add alkalinity check if target provided
    if target_alkalinity_meq_l is not None:
        calculated_alk = _estimate_alkalinity(adm1_state, equilibrium_ph)
        alk_deviation = abs(calculated_alk - target_alkalinity_meq_l)
        if alk_deviation > target_alkalinity_meq_l * 0.2:  # >20% deviation
            warnings.append(
                f"Alkalinity deviation: {alk_deviation:.1f} meq/L "
                f"(target: {target_alkalinity_meq_l:.1f}, calculated: {calculated_alk:.1f})"
            )

    return {
        'equilibrium_ph': round(equilibrium_ph, 2),
        'target_ph': round(target_ph, 2),
        'ph_deviation': round(ph_deviation, 2),
        'ph_deviation_percent': round(ph_deviation_percent, 1),
        'cations_meq_l': round(cations_meq_l, 1),
        'anions_meq_l': round(anions_meq_l, 1),
        'imbalance_meq_l': round(imbalance_meq_l, 1),
        'imbalance_percent': round(imbalance_percent, 1),
        'pass': overall_pass,
        'warnings': warnings
    }


def _calculate_charge_balance(
    state_dict: Dict[str, float],
    pH: float
) -> tuple:
    """
    Calculate total cations and anions in meq/L.

    Uses Henderson-Hasselbalch to determine speciation of weak acids
    at the given pH.

    Returns:
        (cations_meq_l, anions_meq_l)
    """
    # Molecular weights (g/mol)
    MW = {
        'Na': 22.99, 'K': 39.10, 'Mg': 24.31, 'Ca': 40.08,
        'Fe': 55.845, 'Al': 26.98, 'Cl': 35.45, 'S': 32.06,
        'N': 14.01, 'C': 12.01, 'P': 30.97
    }

    # Cations (meq/L = mmol/L × charge)
    cations = 0.0
    cations += state_dict.get('S_Na', 0.0) / MW['Na'] * 1000 * 1  # Na+ (1+)
    cations += state_dict.get('S_K', 0.0) / MW['K'] * 1000 * 1    # K+ (1+)
    cations += state_dict.get('S_Mg', 0.0) / MW['Mg'] * 1000 * 2  # Mg²+ (2+)
    cations += state_dict.get('S_Ca', 0.0) / MW['Ca'] * 1000 * 2  # Ca²+ (2+)
    cations += state_dict.get('S_Fe2', 0.0) / MW['Fe'] * 1000 * 2  # Fe²+ (2+)
    cations += state_dict.get('S_Fe3', 0.0) / MW['Fe'] * 1000 * 3  # Fe³+ (3+)
    cations += state_dict.get('S_Al', 0.0) / MW['Al'] * 1000 * 3   # Al³+ (3+)

    # NH4+ (from S_IN at given pH, pKa ~ 9.25)
    S_IN = state_dict.get('S_IN', 0.0)
    h_ion = 10**(-pH)
    Ka_nh = 10**(-9.25)
    nh4_fraction = h_ion / (Ka_nh + h_ion)
    cations += S_IN / MW['N'] * 1000 * nh4_fraction * 1  # NH4+ (1+)

    # Anions (meq/L = mmol/L × charge)
    anions = 0.0
    anions += state_dict.get('S_Cl', 0.0) / MW['Cl'] * 1000 * 1  # Cl- (1-)

    # SO4²- (2-)
    anions += state_dict.get('S_SO4', 0.0) / MW['S'] * 1000 * 2  # SO4²- (2-)

    # HCO3- (from S_IC at given pH, pKa1 ~ 6.35)
    S_IC = state_dict.get('S_IC', 0.0)
    Ka_co2 = 10**(-6.35)
    hco3_fraction = Ka_co2 / (Ka_co2 + h_ion)
    anions += S_IC / MW['C'] * 1000 * hco3_fraction * 1  # HCO3- (1-)

    # VFAs (assume fully ionized at pH > 4)
    anions += state_dict.get('S_ac', 0.0) / 59.0 * 1000 * 1   # Acetate (1-)
    anions += state_dict.get('S_pro', 0.0) / 73.0 * 1000 * 1  # Propionate (1-)
    anions += state_dict.get('S_bu', 0.0) / 87.0 * 1000 * 1   # Butyrate (1-)
    anions += state_dict.get('S_va', 0.0) / 101.0 * 1000 * 1  # Valerate (1-)

    # HPO4²- (from S_IP, assume fully deprotonated, 2-)
    anions += state_dict.get('S_IP', 0.0) / MW['P'] * 1000 * 2  # HPO4²- (2-)

    # HS- (from S_IS at given pH, pKa ~ 7.0)
    S_IS = state_dict.get('S_IS', 0.0)
    Ka_h2s = 10**(-7.0)
    hs_fraction = Ka_h2s / (Ka_h2s + h_ion)
    anions += S_IS / MW['S'] * 1000 * hs_fraction * 1  # HS- (1-)

    return cations, anions


def _estimate_alkalinity(state_dict: Dict[str, float], pH: float) -> float:
    """
    Estimate alkalinity (meq/L) from S_IC and pH.

    Alkalinity ≈ HCO3- + 2×CO3-- + OH- - H+ (simplified)

    Returns:
        alkalinity_meq_l: Estimated alkalinity in meq/L
    """
    S_IC = state_dict.get('S_IC', 0.0)  # kg-C/m³
    MW_C = 12.01

    # Convert to mmol-C/L
    IC_mmol_l = S_IC / MW_C * 1000

    # Henderson-Hasselbalch for carbonate system
    h_ion = 10**(-pH)
    Ka1 = 10**(-6.35)  # CO2 <-> HCO3-
    Ka2 = 10**(-10.33)  # HCO3- <-> CO3--

    # Fractions
    hco3_frac = Ka1 / (Ka1 + h_ion)
    co3_frac = Ka1 * Ka2 / (Ka1 * h_ion + h_ion**2 + Ka1 * Ka2)

    # Alkalinity from carbonate system (meq/L)
    alkalinity = IC_mmol_l * (hco3_frac + 2 * co3_frac)

    return alkalinity
