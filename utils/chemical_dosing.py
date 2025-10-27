"""
Chemical dosing estimation functions for anaerobic digester design.

Provides stoichiometric calculations for:
- FeCl3 (ferric chloride) for sulfide and phosphate removal
- NaOH (sodium hydroxide) for pH control
- Na2CO3 (sodium carbonate) for alkalinity adjustment

These are DESIGN FUNCTIONS, not dynamic simulation units.
They return recommended doses based on stoichiometry and safety factors.

For dynamic simulation validation, pass the recommended doses to
simulate_cli.py with --fecl3-dose, --naoh-dose, --na2co3-dose flags.
"""

from typing import Dict, Any

__all__ = (
    'estimate_fecl3_for_sulfide_removal',
    'estimate_fecl3_for_phosphate_removal',
    'estimate_naoh_for_ph_adjustment',
    'estimate_na2co3_for_alkalinity'
)


def estimate_fecl3_for_sulfide_removal(
    sulfide_mg_L: float,
    target_removal: float = 0.90,
    safety_factor: float = 1.2
) -> Dict[str, Any]:
    """
    Estimate FeCl3 dose for sulfide precipitation.

    Reaction: 2Fe³⁺ + 3S²⁻ → Fe2S3 (simplified, actual pathway: 2FeS + S⁰)
    Stoichiometry: 2 mol Fe³⁺ per 3 mol S²⁻ = 0.667 mol ratio

    Parameters
    ----------
    sulfide_mg_L : float
        Total sulfide concentration (H2S + HS⁻ + S²⁻) in mg-S/L
    target_removal : float, optional
        Fraction of sulfide to precipitate (default 0.90 = 90%)
    safety_factor : float, optional
        Overdose factor for kinetics and competing reactions (default 1.2)

    Returns
    -------
    dict
        - fecl3_dose_mg_L: FeCl3 dose in mg/L
        - fe3_added_mg_L: Fe³⁺ added in mg/L
        - cl_added_mg_L: Cl⁻ added in mg/L
        - molar_ratio_fe_to_s: Actual Fe:S molar ratio applied
        - sulfide_removed_mg_L: Expected sulfide removal in mg-S/L
        - stoichiometry: Reaction equation

    Notes
    -----
    - Assumes all Fe³⁺ is available for sulfide precipitation
    - Does not account for competing reactions (phosphate, organics)
    - Safety factor accounts for kinetics and side reactions
    - At pH < 7, Fe³⁺ may hydrolyze to Fe(OH)3 instead

    Examples
    --------
    >>> result = estimate_fecl3_for_sulfide_removal(sulfide_mg_L=100, target_removal=0.90)
    >>> print(f"Dose {result['fecl3_dose_mg_L']:.1f} mg/L FeCl3")
    """
    # Target sulfide to remove (mg-S/L)
    s_to_remove_mg_L = sulfide_mg_L * target_removal
    s_to_remove_mol_L = s_to_remove_mg_L / 32.06  # S MW = 32.06 g/mol

    # Stoichiometry: 2Fe³⁺ / 3S²⁻ = 0.667
    fe_required_mol_L = s_to_remove_mol_L * (2.0 / 3.0) * safety_factor
    fe_required_mg_L = fe_required_mol_L * 55.845  # Fe MW = 55.845 g/mol

    # FeCl3 dissociation: FeCl3 → Fe³⁺ + 3Cl⁻
    # MW_FeCl3 = 162.2, MW_Fe = 55.845, MW_Cl = 35.453
    fecl3_mg_L = fe_required_mg_L * (162.2 / 55.845)
    cl_added_mg_L = fe_required_mg_L * (3 * 35.453 / 55.845)

    return {
        'fecl3_dose_mg_L': fecl3_mg_L,
        'fe3_added_mg_L': fe_required_mg_L,
        'cl_added_mg_L': cl_added_mg_L,
        'molar_ratio_fe_to_s': (2.0 / 3.0) * safety_factor,
        'sulfide_removed_mg_L': s_to_remove_mg_L,
        'stoichiometry': '2Fe3+ + 3S2- -> Fe2S3'
    }


def estimate_fecl3_for_phosphate_removal(
    phosphate_mg_P_L: float,
    target_removal: float = 0.80,
    safety_factor: float = 1.5
) -> Dict[str, Any]:
    """
    Estimate FeCl3 dose for phosphate precipitation.

    Reaction: Fe³⁺ + PO4³⁻ → FePO4
    Stoichiometry: 1:1 molar ratio

    Parameters
    ----------
    phosphate_mg_P_L : float
        Orthophosphate concentration in mg-P/L
    target_removal : float, optional
        Fraction of phosphate to precipitate (default 0.80 = 80%)
    safety_factor : float, optional
        Overdose factor (default 1.5, higher than sulfide due to organics)

    Returns
    -------
    dict
        - fecl3_dose_mg_L: FeCl3 dose in mg/L
        - fe3_added_mg_L: Fe³⁺ added in mg/L
        - cl_added_mg_L: Cl⁻ added in mg/L
        - molar_ratio_fe_to_p: Actual Fe:P molar ratio applied
        - phosphate_removed_mg_P_L: Expected phosphate removal in mg-P/L
        - stoichiometry: Reaction equation

    Notes
    -----
    - Higher safety factor than sulfide due to organic matter competition
    - Fe³⁺ binds to organics in high-COD systems
    - May form mixed Fe-P-organics precipitates
    """
    # Target phosphate to remove (mg-P/L)
    p_to_remove_mg_L = phosphate_mg_P_L * target_removal
    p_to_remove_mol_L = p_to_remove_mg_L / 30.974  # P MW = 30.974 g/mol

    # Stoichiometry: 1Fe³⁺ / 1PO4³⁻ = 1.0
    fe_required_mol_L = p_to_remove_mol_L * 1.0 * safety_factor
    fe_required_mg_L = fe_required_mol_L * 55.845

    # FeCl3 dose
    fecl3_mg_L = fe_required_mg_L * (162.2 / 55.845)
    cl_added_mg_L = fe_required_mg_L * (3 * 35.453 / 55.845)

    return {
        'fecl3_dose_mg_L': fecl3_mg_L,
        'fe3_added_mg_L': fe_required_mg_L,
        'cl_added_mg_L': cl_added_mg_L,
        'molar_ratio_fe_to_p': 1.0 * safety_factor,
        'phosphate_removed_mg_P_L': p_to_remove_mg_L,
        'stoichiometry': 'Fe3+ + PO43- -> FePO4'
    }


def estimate_naoh_for_ph_adjustment(
    alkalinity_meq_L: float,
    pH_current: float,
    pH_target: float,
    temperature_c: float = 35.0
) -> Dict[str, Any]:
    """
    Estimate NaOH dose for pH adjustment.

    Uses simplified buffer capacity for carbonate-dominated systems.
    Assumes bicarbonate (HCO3⁻) is the dominant buffer.

    Parameters
    ----------
    alkalinity_meq_L : float
        Total alkalinity in meq/L (typically 30-80 for AD)
    pH_current : float
        Current pH (typically 6.5-7.5)
    pH_target : float
        Target pH (typically 7.0-7.5)
    temperature_c : float, optional
        Temperature in °C (default 35, affects pKa)

    Returns
    -------
    dict
        - naoh_dose_mg_L: NaOH dose in mg/L
        - na_added_mg_L: Na⁺ added in mg/L
        - alkalinity_increase_meq_L: Alkalinity increase in meq/L
        - ph_change: Expected pH change
        - stoichiometry: Reaction equation

    Notes
    -----
    - Simplified model: assumes carbonate buffer dominates
    - Does not account for VFA buffers or protein hydrolysis
    - For large pH changes (>1 unit), use iterative approach
    """
    if pH_target <= pH_current:
        return {
            'naoh_dose_mg_L': 0,
            'na_added_mg_L': 0,
            'alkalinity_increase_meq_L': 0,
            'ph_change': 0,
            'stoichiometry': 'No base needed'
        }

    # Buffer capacity estimation (meq/L per pH unit)
    # For carbonate system: β ≈ 2.3 × C_T × α_HCO3 × α_CO3
    # Simplified: β ≈ 0.4 × alkalinity for pH 6.5-7.5 range
    buffer_capacity = 0.4 * alkalinity_meq_L

    # Required base (meq/L) = buffer capacity × ΔpH
    delta_ph = pH_target - pH_current
    base_required_meq_L = buffer_capacity * delta_ph

    # NaOH provides 1 meq/mmol (MW = 40 g/mol)
    naoh_mmol_L = base_required_meq_L
    naoh_mg_L = naoh_mmol_L * 40.0

    # Na⁺ added
    na_mg_L = naoh_mmol_L * 22.99  # Na MW = 22.99 g/mol

    return {
        'naoh_dose_mg_L': naoh_mg_L,
        'na_added_mg_L': na_mg_L,
        'alkalinity_increase_meq_L': base_required_meq_L,
        'ph_change': delta_ph,
        'stoichiometry': 'NaOH -> Na+ + OH-; OH- + HCO3- -> CO32- + H2O'
    }


def estimate_na2co3_for_alkalinity(
    alkalinity_current_meq_L: float,
    alkalinity_target_meq_L: float
) -> Dict[str, Any]:
    """
    Estimate Na2CO3 dose for alkalinity increase.

    Preferred over NaOH when you want to increase buffering capacity
    without excessively raising pH.

    Reaction: Na2CO3 → 2Na⁺ + CO3²⁻
    Alkalinity contribution: 2 meq per mmol Na2CO3

    Parameters
    ----------
    alkalinity_current_meq_L : float
        Current alkalinity in meq/L
    alkalinity_target_meq_L : float
        Target alkalinity in meq/L (typically 50-100 for AD)

    Returns
    -------
    dict
        - na2co3_dose_mg_L: Na2CO3 dose in mg/L
        - na_added_mg_L: Na⁺ added in mg/L
        - alkalinity_increase_meq_L: Alkalinity increase in meq/L
        - stoichiometry: Reaction equation

    Notes
    -----
    - Na2CO3 is a weaker base than NaOH (pKa2 = 10.33)
    - Increases buffering capacity more than NaOH per mole
    - Preferred for systems with adequate pH but low alkalinity
    """
    if alkalinity_target_meq_L <= alkalinity_current_meq_L:
        return {
            'na2co3_dose_mg_L': 0,
            'na_added_mg_L': 0,
            'alkalinity_increase_meq_L': 0,
            'stoichiometry': 'No base needed'
        }

    # Required alkalinity increase
    delta_alk_meq_L = alkalinity_target_meq_L - alkalinity_current_meq_L

    # Na2CO3 provides 2 meq/mmol (each CO3²⁻ can accept 2 H⁺)
    # MW_Na2CO3 = 105.99 g/mol
    na2co3_mmol_L = delta_alk_meq_L / 2.0
    na2co3_mg_L = na2co3_mmol_L * 105.99

    # Na⁺ added: 2 mol Na per mol Na2CO3
    na_mg_L = na2co3_mmol_L * 2.0 * 22.99

    return {
        'na2co3_dose_mg_L': na2co3_mg_L,
        'na_added_mg_L': na_mg_L,
        'alkalinity_increase_meq_L': delta_alk_meq_L,
        'stoichiometry': 'Na2CO3 -> 2Na+ + CO32-'
    }
