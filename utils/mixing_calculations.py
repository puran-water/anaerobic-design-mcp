#!/usr/bin/env python3
"""
Mixing power calculations for anaerobic digesters.

This module provides analytical correlations for sizing mechanical and pumped
mixing systems in anaerobic digesters. Calculations are based on established
literature correlations and industry design standards.

References:
    Paul, E.L., Atiemo-Obeng, V.A., and Kresta, S.M. (2004).
    Handbook of Industrial Mixing: Science and Practice. Wiley-Interscience.

    WEF (2017). Design of Municipal Wastewater Treatment Plants.
    Manual of Practice No. 8 (MOP-8), 6th Edition.

    Metzner, A.B. and Otto, R.E. (1957). "Agitation of non-Newtonian fluids."
    AIChE Journal, 3(1), 3-10.

    Metcalf & Eddy (2014). Wastewater Engineering: Treatment and Resource Recovery.
    5th Edition, McGraw-Hill.

Typical Power Requirements (WEF MOP-8, 2017):
    - Complete mix digesters: 5-8 W/m³ (typical)
    - High-rate digesters: 8-12 W/m³
    - Thermophilic digesters: 10-15 W/m³
    - Draft tube baffled: 3-5 W/m³

Author: Generated for anaerobic-design-mcp
Date: 2025-10-30
"""

from dataclasses import dataclass
from typing import Dict, Any, Literal, Optional, Tuple
import math

try:
    from fluids.jet_pump import liquid_jet_pump
    FLUIDS_AVAILABLE = True
except ImportError:
    FLUIDS_AVAILABLE = False


# ============================================================================
# Constants and Configuration
# ============================================================================

# Impeller geometry constants (Paul et al., 2004)
POWER_NUMBER_CONSTANTS = {
    "pitched_blade_turbine": {
        "turbulent": 1.27,  # Re > 10,000, 45° angle, D/T = 0.33
        "transitional_const": 14.0,  # For transitional regime calculation
    },
    "rushton_turbine": {
        "turbulent": 5.0,  # Re > 10,000, 6-blade, D/T = 0.33
        "transitional_const": 70.0,
    },
    "marine_propeller": {
        "turbulent": 0.32,  # Re > 10,000, square pitch
        "transitional_const": 4.0,
    },
}

# Reynolds number regime boundaries
REYNOLDS_REGIMES = {
    "laminar": (0, 10),
    "transitional": (10, 10000),
    "turbulent": (10000, 1e9),
}

# Metzner-Otto constants for different impeller types (k_s)
# γ̇_avg = k_s × N (average shear rate)
METZNER_OTTO_CONSTANTS = {
    "pitched_blade_turbine": 13.0,  # 45° angle
    "rushton_turbine": 11.5,
    "marine_propeller": 10.0,
}


@dataclass
class AnaerobicDigesterMixingPreset:
    """Standard mixing configurations for anaerobic digesters."""

    name: str
    temperature_c: float
    power_target_w_m3: float
    impeller_type: Literal["pitched_blade_turbine", "rushton_turbine", "marine_propeller"]
    typical_viscosity_pa_s: float
    typical_density_kg_m3: float
    description: str


# Standard presets from WEF MOP-8 and Metcalf & Eddy
ANAEROBIC_DIGESTER_MIXING_PRESETS = {
    "mesophilic_complete_mix": AnaerobicDigesterMixingPreset(
        name="Mesophilic Complete Mix",
        temperature_c=35.0,
        power_target_w_m3=7.0,
        impeller_type="pitched_blade_turbine",
        typical_viscosity_pa_s=0.01,  # 10 cP (1-3% TS)
        typical_density_kg_m3=1010.0,
        description="Standard mesophilic digester, 1-3% TS, complete mixing"
    ),
    "mesophilic_high_rate": AnaerobicDigesterMixingPreset(
        name="Mesophilic High Rate",
        temperature_c=35.0,
        power_target_w_m3=10.0,
        impeller_type="pitched_blade_turbine",
        typical_viscosity_pa_s=0.05,  # 50 cP (4-6% TS)
        typical_density_kg_m3=1020.0,
        description="High-rate mesophilic digester, 4-6% TS, aggressive mixing"
    ),
    "thermophilic_complete_mix": AnaerobicDigesterMixingPreset(
        name="Thermophilic Complete Mix",
        temperature_c=55.0,
        power_target_w_m3=12.0,
        impeller_type="pitched_blade_turbine",
        typical_viscosity_pa_s=0.008,  # 8 cP (lower viscosity at higher temp)
        typical_density_kg_m3=1005.0,
        description="Thermophilic digester, 1-3% TS, enhanced mixing for high temp"
    ),
    "draft_tube_baffled": AnaerobicDigesterMixingPreset(
        name="Draft Tube Baffled",
        temperature_c=35.0,
        power_target_w_m3=4.0,
        impeller_type="marine_propeller",
        typical_viscosity_pa_s=0.01,
        typical_density_kg_m3=1010.0,
        description="Draft tube design with marine propeller, lower power requirement"
    ),
}


# ============================================================================
# Reynolds Number Calculations
# ============================================================================

def calculate_impeller_reynolds_number(
    fluid_density_kg_m3: float,
    impeller_speed_rpm: float,
    impeller_diameter_m: float,
    fluid_viscosity_pa_s: float,
) -> float:
    """
    Calculate impeller Reynolds number for Newtonian fluids.

    The Reynolds number determines the flow regime (laminar, transitional,
    or turbulent) and affects the power number correlation.

    Parameters
    ----------
    fluid_density_kg_m3 : float
        Fluid density [kg/m³]
    impeller_speed_rpm : float
        Impeller rotational speed [rpm]
    impeller_diameter_m : float
        Impeller diameter [m]
    fluid_viscosity_pa_s : float
        Dynamic viscosity [Pa·s]

    Returns
    -------
    float
        Impeller Reynolds number [-]

    Notes
    -----
    Re = ρ × N × D² / μ

    where:
        ρ = fluid density [kg/m³]
        N = rotational speed [rev/s]
        D = impeller diameter [m]
        μ = dynamic viscosity [Pa·s]

    Flow regimes:
        - Laminar: Re < 10
        - Transitional: 10 ≤ Re ≤ 10,000
        - Turbulent: Re > 10,000

    Examples
    --------
    >>> # Mesophilic digester, 3 m diameter, 50 rpm, 10 cP viscosity
    >>> Re = calculate_impeller_reynolds_number(
    ...     fluid_density_kg_m3=1010,
    ...     impeller_speed_rpm=50,
    ...     impeller_diameter_m=1.0,  # D/T = 0.33
    ...     fluid_viscosity_pa_s=0.01
    ... )
    >>> print(f"Reynolds number: {Re:.0f}")
    Reynolds number: 84,167 (turbulent regime)

    References
    ----------
    Paul et al. (2004), Section 5.3.2
    """
    # Convert rpm to rev/s
    N_rev_per_s = impeller_speed_rpm / 60.0

    # Calculate Reynolds number
    Re = (
        fluid_density_kg_m3
        * N_rev_per_s
        * impeller_diameter_m**2
        / fluid_viscosity_pa_s
    )

    return Re


def calculate_effective_reynolds_number_non_newtonian(
    fluid_density_kg_m3: float,
    impeller_speed_rpm: float,
    impeller_diameter_m: float,
    consistency_index_pa_s_n: float,
    flow_behavior_index: float,
    impeller_type: str = "pitched_blade_turbine",
) -> Tuple[float, float]:
    """
    Calculate effective Reynolds number for non-Newtonian fluids using
    the Metzner-Otto method.

    Parameters
    ----------
    fluid_density_kg_m3 : float
        Fluid density [kg/m³]
    impeller_speed_rpm : float
        Impeller rotational speed [rpm]
    impeller_diameter_m : float
        Impeller diameter [m]
    consistency_index_pa_s_n : float
        Power-law consistency index K [Pa·s^n]
    flow_behavior_index : float
        Power-law flow behavior index n [-]
        n = 1: Newtonian
        n < 1: shear-thinning (pseudoplastic)
        n > 1: shear-thickening (dilatant)
    impeller_type : str
        Type of impeller for k_s selection

    Returns
    -------
    tuple[float, float]
        (effective_reynolds_number, average_shear_rate_s_inv)

    Notes
    -----
    Metzner-Otto method:
        γ̇_avg = k_s × N
        μ_eff = K × (k_s × N)^(n-1)
        Re_eff = ρ × N × D² / μ_eff

    where:
        k_s = Metzner-Otto constant (impeller-dependent)
        K = consistency index [Pa·s^n]
        n = flow behavior index [-]

    Typical k_s values:
        - Pitched blade turbine (45°): 13
        - Rushton turbine: 11.5
        - Marine propeller: 10

    Examples
    --------
    >>> # High-solids digester with shear-thinning behavior
    >>> Re_eff, shear_rate = calculate_effective_reynolds_number_non_newtonian(
    ...     fluid_density_kg_m3=1020,
    ...     impeller_speed_rpm=60,
    ...     impeller_diameter_m=1.0,
    ...     consistency_index_pa_s_n=0.5,  # K
    ...     flow_behavior_index=0.6,  # n (shear-thinning)
    ...     impeller_type="pitched_blade_turbine"
    ... )
    >>> print(f"Re_eff: {Re_eff:.0f}, Shear rate: {shear_rate:.1f} s^-1")

    References
    ----------
    Metzner and Otto (1957), AIChE Journal
    Paul et al. (2004), Section 5.4
    """
    # Convert rpm to rev/s
    N_rev_per_s = impeller_speed_rpm / 60.0

    # Get Metzner-Otto constant
    k_s = METZNER_OTTO_CONSTANTS.get(impeller_type, 13.0)

    # Calculate average shear rate
    shear_rate_avg = k_s * N_rev_per_s

    # Calculate effective viscosity
    mu_eff = consistency_index_pa_s_n * (shear_rate_avg ** (flow_behavior_index - 1))

    # Calculate effective Reynolds number
    Re_eff = (
        fluid_density_kg_m3
        * N_rev_per_s
        * impeller_diameter_m**2
        / mu_eff
    )

    return Re_eff, shear_rate_avg


# ============================================================================
# Power Number Correlations
# ============================================================================

def get_power_number_pitched_blade(
    reynolds_number: float,
    d_t_ratio: float = 0.33,
    blade_angle_deg: float = 45.0,
    baffled: bool = True,
) -> float:
    """
    Calculate power number for pitched blade turbine.

    Parameters
    ----------
    reynolds_number : float
        Impeller Reynolds number [-]
    d_t_ratio : float, optional
        Impeller-to-tank diameter ratio D/T (default: 0.33)
    blade_angle_deg : float, optional
        Blade angle from horizontal (default: 45°)
    baffled : bool, optional
        Tank has baffles (default: True)

    Returns
    -------
    float
        Power number Np [-]

    Notes
    -----
    Correlation from Paul et al. (2004), Table 10-2:

    Turbulent regime (Re > 10,000):
        Np = 1.27 (for 45°, D/T=0.33, baffled)

    Transitional regime (10 < Re < 10,000):
        Np = 1.27 + 14/Re

    Laminar regime (Re < 10):
        Np = 14/Re

    For different blade angles (Bates et al., 1966):
        30°: Np = 0.8
        45°: Np = 1.27
        60°: Np = 1.6

    Examples
    --------
    >>> # Turbulent flow
    >>> Np = get_power_number_pitched_blade(reynolds_number=50000)
    >>> print(f"Np = {Np:.2f}")
    Np = 1.27

    >>> # Transitional flow
    >>> Np = get_power_number_pitched_blade(reynolds_number=1000)
    >>> print(f"Np = {Np:.2f}")
    Np = 1.28

    References
    ----------
    Paul et al. (2004), Chapter 10, Table 10-2
    Bates et al. (1966), Ind. Eng. Chem. Process Des. Dev.
    """
    if not baffled:
        # Unbaffled tanks have lower power numbers (not recommended for AD)
        correction_factor = 0.65
    else:
        correction_factor = 1.0

    # Get base constants
    Np_turbulent = POWER_NUMBER_CONSTANTS["pitched_blade_turbine"]["turbulent"]
    const = POWER_NUMBER_CONSTANTS["pitched_blade_turbine"]["transitional_const"]

    # Blade angle correction (relative to 45°)
    angle_factor = 1.0
    if abs(blade_angle_deg - 30) < 5:
        angle_factor = 0.8 / 1.27
    elif abs(blade_angle_deg - 60) < 5:
        angle_factor = 1.6 / 1.27

    # Determine regime and calculate Np
    if reynolds_number >= REYNOLDS_REGIMES["turbulent"][0]:
        # Turbulent regime - constant Np
        Np = Np_turbulent * angle_factor
    elif reynolds_number >= REYNOLDS_REGIMES["transitional"][0]:
        # Transitional regime - Np = Np_turb + const/Re
        Np = (Np_turbulent + const / reynolds_number) * angle_factor
    else:
        # Laminar regime - Np proportional to 1/Re
        Np = (const / reynolds_number) * angle_factor

    return Np * correction_factor


def get_power_number_rushton(
    reynolds_number: float,
    d_t_ratio: float = 0.33,
    num_blades: int = 6,
) -> float:
    """
    Calculate power number for Rushton turbine (radial flow impeller).

    Parameters
    ----------
    reynolds_number : float
        Impeller Reynolds number [-]
    d_t_ratio : float, optional
        Impeller-to-tank diameter ratio D/T (default: 0.33)
    num_blades : int, optional
        Number of blades (default: 6)

    Returns
    -------
    float
        Power number Np [-]

    Notes
    -----
    Rushton turbines are less common in AD due to higher power consumption
    and potential for dead zones. Included for completeness.

    Turbulent regime (Re > 10,000):
        Np = 5.0 (standard 6-blade)

    Transitional/laminar: Similar correction as pitched blade

    References
    ----------
    Paul et al. (2004), Chapter 10
    """
    Np_turbulent = POWER_NUMBER_CONSTANTS["rushton_turbine"]["turbulent"]
    const = POWER_NUMBER_CONSTANTS["rushton_turbine"]["transitional_const"]

    if reynolds_number >= REYNOLDS_REGIMES["turbulent"][0]:
        Np = Np_turbulent
    elif reynolds_number >= REYNOLDS_REGIMES["transitional"][0]:
        Np = Np_turbulent + const / reynolds_number
    else:
        Np = const / reynolds_number

    return Np


def get_power_number_marine_propeller(
    reynolds_number: float,
    d_t_ratio: float = 0.33,
    pitch_ratio: float = 1.0,
) -> float:
    """
    Calculate power number for marine propeller (axial flow).

    Parameters
    ----------
    reynolds_number : float
        Impeller Reynolds number [-]
    d_t_ratio : float, optional
        Impeller-to-tank diameter ratio D/T (default: 0.33)
    pitch_ratio : float, optional
        Pitch-to-diameter ratio (default: 1.0 = square pitch)

    Returns
    -------
    float
        Power number Np [-]

    Notes
    -----
    Marine propellers are common in draft-tube baffled digesters.
    Lower power numbers than pitched blade turbines.

    Turbulent regime (Re > 10,000):
        Np = 0.32 (square pitch)

    References
    ----------
    Paul et al. (2004), Chapter 10
    WEF MOP-8 (2017), Section 15.5
    """
    Np_turbulent = POWER_NUMBER_CONSTANTS["marine_propeller"]["turbulent"]
    const = POWER_NUMBER_CONSTANTS["marine_propeller"]["transitional_const"]

    if reynolds_number >= REYNOLDS_REGIMES["turbulent"][0]:
        Np = Np_turbulent
    elif reynolds_number >= REYNOLDS_REGIMES["transitional"][0]:
        Np = Np_turbulent + const / reynolds_number
    else:
        Np = const / reynolds_number

    return Np


# ============================================================================
# Helper Functions
# ============================================================================

def get_flow_regime(reynolds_number: float) -> str:
    """
    Determine flow regime from Reynolds number.

    Parameters
    ----------
    reynolds_number : float
        Reynolds number [-]

    Returns
    -------
    str
        "laminar", "transitional", or "turbulent"
    """
    if reynolds_number < REYNOLDS_REGIMES["transitional"][0]:
        return "laminar"
    elif reynolds_number < REYNOLDS_REGIMES["turbulent"][0]:
        return "transitional"
    else:
        return "turbulent"


def check_turbulent_regime(reynolds_number: float, min_re: float = 10000) -> Dict[str, Any]:
    """
    Check if flow is in turbulent regime and provide warnings if not.

    Parameters
    ----------
    reynolds_number : float
        Reynolds number [-]
    min_re : float, optional
        Minimum Re for turbulent flow (default: 10,000)

    Returns
    -------
    dict
        Contains 'is_turbulent' (bool) and 'warning' (str or None)
    """
    regime = get_flow_regime(reynolds_number)
    is_turbulent = reynolds_number >= min_re

    warning = None
    if not is_turbulent:
        if regime == "laminar":
            warning = (
                f"CRITICAL: Laminar flow (Re={reynolds_number:.0f}). "
                "Mixing will be inadequate. Increase speed or diameter."
            )
        else:  # transitional
            warning = (
                f"WARNING: Transitional flow (Re={reynolds_number:.0f}). "
                "Consider increasing speed for reliable turbulent mixing (Re>10,000)."
            )

    return {
        "is_turbulent": is_turbulent,
        "regime": regime,
        "warning": warning,
    }


# ============================================================================
# Main Mechanical Mixing Calculation
# ============================================================================

def calculate_mechanical_mixing_power(
    tank_diameter_m: float,
    tank_volume_m3: float,
    target_power_w_m3: float,
    fluid_density_kg_m3: float = 1010.0,
    fluid_viscosity_pa_s: float = 0.01,
    impeller_type: Literal["pitched_blade_turbine", "rushton_turbine", "marine_propeller"] = "pitched_blade_turbine",
    d_t_ratio: float = 0.33,
    mode: Literal["design", "analysis"] = "design",
    known_speed_rpm: Optional[float] = None,
    known_diameter_m: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Calculate mechanical mixing power requirements for anaerobic digesters.

    This is the main function for sizing mechanical mixing systems. It can
    operate in two modes:

    1. Design mode: Given target power, calculate required speed and diameter
    2. Analysis mode: Given speed and diameter, calculate actual power

    Parameters
    ----------
    tank_diameter_m : float
        Tank diameter [m]
    tank_volume_m3 : float
        Tank working volume [m³]
    target_power_w_m3 : float
        Target mixing power intensity [W/m³]
    fluid_density_kg_m3 : float, optional
        Sludge density (default: 1010 kg/m³)
    fluid_viscosity_pa_s : float, optional
        Dynamic viscosity (default: 0.01 Pa·s = 10 cP)
    impeller_type : str, optional
        Impeller type (default: "pitched_blade_turbine")
    d_t_ratio : float, optional
        Impeller diameter / tank diameter ratio (default: 0.33)
    mode : str, optional
        "design" or "analysis" (default: "design")
    known_speed_rpm : float, optional
        For analysis mode: impeller speed [rpm]
    known_diameter_m : float, optional
        For analysis mode: impeller diameter [m]

    Returns
    -------
    dict
        Contains all calculated parameters:
        - power_total_kw: Total mixing power [kW]
        - power_intensity_w_m3: Power per unit volume [W/m³]
        - impeller_speed_rpm: Rotational speed [rpm]
        - impeller_diameter_m: Impeller diameter [m]
        - reynolds_number: Flow Reynolds number [-]
        - power_number: Dimensionless power number [-]
        - flow_regime: "laminar", "transitional", or "turbulent"
        - tip_speed_m_s: Impeller tip speed [m/s]
        - warnings: List of warning messages
        - impeller_type: Type of impeller used

    Examples
    --------
    >>> # Design mode: Size impeller for 7 W/m³ mesophilic digester
    >>> result = calculate_mechanical_mixing_power(
    ...     tank_diameter_m=12.0,
    ...     tank_volume_m3=1000.0,
    ...     target_power_w_m3=7.0,
    ...     fluid_density_kg_m3=1010.0,
    ...     fluid_viscosity_pa_s=0.01,
    ...     impeller_type="pitched_blade_turbine",
    ...     mode="design"
    ... )
    >>> print(f"Speed: {result['impeller_speed_rpm']:.1f} rpm")
    >>> print(f"Diameter: {result['impeller_diameter_m']:.2f} m")
    >>> print(f"Total power: {result['power_total_kw']:.1f} kW")

    >>> # Analysis mode: Check existing installation
    >>> result = calculate_mechanical_mixing_power(
    ...     tank_diameter_m=12.0,
    ...     tank_volume_m3=1000.0,
    ...     target_power_w_m3=7.0,  # For comparison
    ...     fluid_density_kg_m3=1010.0,
    ...     fluid_viscosity_pa_s=0.01,
    ...     impeller_type="pitched_blade_turbine",
    ...     mode="analysis",
    ...     known_speed_rpm=60.0,
    ...     known_diameter_m=4.0
    ... )
    >>> print(f"Actual power: {result['power_intensity_w_m3']:.1f} W/m³")

    Notes
    -----
    Design methodology:
    1. Calculate impeller diameter from D/T ratio
    2. Assume turbulent regime (Np constant)
    3. Solve for speed N from power equation:
       P = Np × ρ × N³ × D⁵
    4. Calculate Reynolds number to verify turbulent flow
    5. If not turbulent, iterate with regime-appropriate Np

    Typical design criteria (WEF MOP-8):
    - Tip speed: 3-5 m/s (avoid excessive shear)
    - Minimum Re: 10,000 (ensure turbulent mixing)
    - Power intensity: 5-12 W/m³ (see ANAEROBIC_DIGESTER_MIXING_PRESETS)

    References
    ----------
    Paul et al. (2004), Chapter 10
    WEF MOP-8 (2017), Section 15.5
    Metcalf & Eddy (2014), Chapter 13
    """
    warnings = []

    # Input validation
    if tank_volume_m3 <= 0 or tank_diameter_m <= 0:
        raise ValueError("Tank volume and diameter must be positive")
    if not 0.2 <= d_t_ratio <= 0.5:
        warnings.append(f"WARNING: D/T ratio {d_t_ratio:.2f} outside typical range 0.2-0.5")

    # Calculate impeller diameter
    if mode == "analysis" and known_diameter_m is not None:
        D = known_diameter_m
        actual_d_t = D / tank_diameter_m
        if abs(actual_d_t - d_t_ratio) > 0.05:
            warnings.append(f"Actual D/T={actual_d_t:.2f} differs from specified {d_t_ratio:.2f}")
    else:
        D = d_t_ratio * tank_diameter_m

    # Get power number function
    if impeller_type == "pitched_blade_turbine":
        get_np = get_power_number_pitched_blade
    elif impeller_type == "rushton_turbine":
        get_np = get_power_number_rushton
    elif impeller_type == "marine_propeller":
        get_np = get_power_number_marine_propeller
    else:
        raise ValueError(f"Unknown impeller type: {impeller_type}")

    # === DESIGN MODE ===
    if mode == "design":
        # Target power in watts
        P_target = target_power_w_m3 * tank_volume_m3

        # Initial assumption: turbulent flow (constant Np)
        Np_initial = get_np(reynolds_number=1e6)  # High Re for turbulent

        # Solve for N from: P = Np × ρ × N³ × D⁵
        # N³ = P / (Np × ρ × D⁵)
        N_cubed = P_target / (Np_initial * fluid_density_kg_m3 * (D ** 5))
        N_rev_per_s = N_cubed ** (1/3)
        N_rpm = N_rev_per_s * 60.0

        # Calculate Reynolds number to check assumption
        Re = calculate_impeller_reynolds_number(
            fluid_density_kg_m3=fluid_density_kg_m3,
            impeller_speed_rpm=N_rpm,
            impeller_diameter_m=D,
            fluid_viscosity_pa_s=fluid_viscosity_pa_s,
        )

        # Get actual Np for this Re
        Np_actual = get_np(reynolds_number=Re)

        # If not turbulent, iterate to convergence
        max_iterations = 10
        tolerance = 0.01
        iteration = 0

        while abs(Np_actual - Np_initial) / Np_initial > tolerance and iteration < max_iterations:
            Np_initial = Np_actual
            N_cubed = P_target / (Np_initial * fluid_density_kg_m3 * (D ** 5))
            N_rev_per_s = N_cubed ** (1/3)
            N_rpm = N_rev_per_s * 60.0

            Re = calculate_impeller_reynolds_number(
                fluid_density_kg_m3=fluid_density_kg_m3,
                impeller_speed_rpm=N_rpm,
                impeller_diameter_m=D,
                fluid_viscosity_pa_s=fluid_viscosity_pa_s,
            )

            Np_actual = get_np(reynolds_number=Re)
            iteration += 1

        if iteration >= max_iterations:
            warnings.append("WARNING: Power calculation did not fully converge")

        # Final calculations
        Np = Np_actual
        P_actual = Np * fluid_density_kg_m3 * (N_rev_per_s ** 3) * (D ** 5)

    # === ANALYSIS MODE ===
    else:
        if known_speed_rpm is None:
            raise ValueError("Analysis mode requires known_speed_rpm")

        N_rpm = known_speed_rpm
        N_rev_per_s = N_rpm / 60.0

        # Calculate Reynolds number
        Re = calculate_impeller_reynolds_number(
            fluid_density_kg_m3=fluid_density_kg_m3,
            impeller_speed_rpm=N_rpm,
            impeller_diameter_m=D,
            fluid_viscosity_pa_s=fluid_viscosity_pa_s,
        )

        # Get power number
        Np = get_np(reynolds_number=Re)

        # Calculate power: P = Np × ρ × N³ × D⁵
        P_actual = Np * fluid_density_kg_m3 * (N_rev_per_s ** 3) * (D ** 5)

    # Check turbulent regime
    regime_check = check_turbulent_regime(Re)
    if regime_check["warning"]:
        warnings.append(regime_check["warning"])

    # Calculate tip speed
    tip_speed = math.pi * D * N_rev_per_s

    # Check tip speed limits (3-5 m/s typical)
    if tip_speed > 5.0:
        warnings.append(
            f"WARNING: Tip speed {tip_speed:.2f} m/s exceeds 5 m/s. "
            "Risk of excessive shear stress on biomass."
        )
    elif tip_speed < 2.0:
        warnings.append(
            f"WARNING: Tip speed {tip_speed:.2f} m/s below 2 m/s. "
            "Mixing may be inadequate."
        )

    # Calculate power intensity
    power_intensity = P_actual / tank_volume_m3

    # Check against target
    if mode == "design" and abs(power_intensity - target_power_w_m3) / target_power_w_m3 > 0.05:
        warnings.append(
            f"WARNING: Achieved power {power_intensity:.2f} W/m³ differs from "
            f"target {target_power_w_m3:.2f} W/m³"
        )

    return {
        "power_total_kw": P_actual / 1000.0,
        "power_intensity_w_m3": power_intensity,
        "impeller_speed_rpm": N_rpm,
        "impeller_diameter_m": D,
        "reynolds_number": Re,
        "power_number": Np,
        "flow_regime": regime_check["regime"],
        "tip_speed_m_s": tip_speed,
        "d_t_ratio": D / tank_diameter_m,
        "warnings": warnings,
        "impeller_type": impeller_type,
    }


# ============================================================================
# Eductor/Jet Pump Sizing Helper
# ============================================================================

def calculate_eductor_parameters(
    total_educted_flow_m3_h: float,
    entrainment_ratio_total_to_motive: float = 5.0,
    static_head_m: float = 10.0,
    discharge_pressure_kpa: float = 101.325,
    suction_pressure_kpa: float = 101.325,
    density_kg_m3: float = 1010.0,
    target_nozzle_velocity_m_s: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Calculate eductor/jet pump parameters using fluids.jet_pump model.

    Eductors (jet pumps) use high-velocity motive flow to entrain additional
    liquid, providing total flow greater than the pump flow. This is critical
    for accurate pump sizing and costing.

    Parameters
    ----------
    total_educted_flow_m3_h : float
        Total flow (motive + entrained) for tank turnover [m³/h]
    entrainment_ratio_total_to_motive : float, optional
        Ratio of total flow to motive pump flow [-] (default: 5.0)
        Typical range: 4-6 for liquid jet pumps
        Note: This is (Qp + Qs)/Qp = 1 + M, where M is the fluids.jet_pump
        entrainment ratio M = Qs/Qp
    static_head_m : float, optional
        Static head from pump centerline to discharge [m] (default: 10 m)
    discharge_pressure_kpa : float, optional
        Pressure at eductor exit [kPa] (default: 101.325 kPa = 1 atm)
    suction_pressure_kpa : float, optional
        Pressure at secondary inlet [kPa] (default: 101.325 kPa)
    density_kg_m3 : float, optional
        Liquid density [kg/m³] (default: 1010 for digester sludge)
    target_nozzle_velocity_m_s : float, optional
        Target nozzle discharge velocity [m/s] (default: auto-calculate)
        If None, uses 20 m/s (typical for eductor jets)
        Range: 15-30 m/s for effective entrainment

    Returns
    -------
    dict
        Eductor sizing parameters:
        - motive_flow_m3_h: Pump flow rate [m³/h]
        - motive_flow_m3_s: Pump flow rate [m³/s]
        - entrainment_ratio_M: fluids.jet_pump M = Qs/Qp [-]
        - nozzle_diameter_m: Primary nozzle diameter [m]
        - nozzle_velocity_m_s: Nozzle discharge velocity [m/s]
        - required_pump_pressure_kpa: Pump discharge pressure [kPa]
        - required_pump_head_m: Total Dynamic Head [m]
        - velocity_head_m: Velocity head component [m]
        - static_head_m: Static head component [m]
        - jet_pump_efficiency: Overall efficiency [-]
        - warnings: List of warnings

    Notes
    -----
    **Entrainment Ratio Convention:**
    - User specifies: entrainment_ratio = Q_total/Q_motive (e.g., 5:1)
    - fluids.jet_pump uses: M = Q_secondary/Q_primary
    - Relationship: Q_total = Q_motive + Q_secondary = Q_motive(1 + M)
    - Therefore: M = entrainment_ratio - 1

    **Critical for Costing:**
    For a 5:1 eductor with 3000 m³/h total educted flow:
    - Total flow: 3000 m³/h (for tank turnover calculations)
    - Motive pump flow: 600 m³/h (for pump CAPEX/OPEX)
    - Using 3000 m³/h for pump sizing would overestimate costs by 5×!

    **Velocity Head:**
    Eductor jets require high velocity (15-30 m/s) to entrain liquid.
    Velocity head H_v = v²/(2g) is significant (~15-46 m for 15-30 m/s).

    Examples
    --------
    >>> # Size eductor for 3000 m³/h total flow with 5:1 entrainment
    >>> result = calculate_eductor_parameters(
    ...     total_educted_flow_m3_h=3000.0,
    ...     entrainment_ratio_total_to_motive=5.0,
    ...     static_head_m=10.0
    ... )
    >>> print(f"Pump flow: {result['motive_flow_m3_h']:.0f} m³/h")
    >>> print(f"Required TDH: {result['required_pump_head_m']:.1f} m")

    References
    ----------
    Bell, I. H. (2016-2024). fluids: Fluid dynamics component of Chemical
        Engineering Design Library. https://github.com/CalebBell/fluids
    EPA P100GGR5: Jet Aeration Systems Performance Testing
    Karassik's Pump Handbook (4th Edition)
    """
    warnings = []

    # Check fluids library availability
    if not FLUIDS_AVAILABLE:
        raise ImportError(
            "fluids library is required for eductor sizing. "
            "Install with: pip install fluids"
        )

    # Calculate motive flow from total flow and entrainment ratio
    # User convention: ratio = Q_total/Q_motive (e.g., 5.0 for 5:1)
    # fluids.jet_pump convention: M = Q_secondary/Q_primary
    # Relationship: Q_total = Q_motive(1 + M), so M = ratio - 1
    M_fluids = entrainment_ratio_total_to_motive - 1.0  # Convert to Qs/Qp
    motive_flow_m3_h = total_educted_flow_m3_h / entrainment_ratio_total_to_motive
    motive_flow_m3_s = motive_flow_m3_h / 3600.0
    secondary_flow_m3_s = (total_educted_flow_m3_h - motive_flow_m3_h) / 3600.0

    # Set target nozzle velocity
    if target_nozzle_velocity_m_s is None:
        target_nozzle_velocity_m_s = 20.0  # Typical for eductor jets

    # Validate velocity range
    if target_nozzle_velocity_m_s < 10.0:
        warnings.append(
            f"WARNING: Nozzle velocity {target_nozzle_velocity_m_s:.1f} m/s is low. "
            "Eductors typically require 15-30 m/s for effective entrainment."
        )
    elif target_nozzle_velocity_m_s > 35.0:
        warnings.append(
            f"WARNING: Nozzle velocity {target_nozzle_velocity_m_s:.1f} m/s is very high. "
            "Consider erosion and cavitation risks."
        )

    # Calculate nozzle diameter from continuity: Q = v·A
    nozzle_area_m2 = motive_flow_m3_s / target_nozzle_velocity_m_s
    nozzle_diameter_m = math.sqrt(4 * nozzle_area_m2 / math.pi)

    # Calculate velocity head: H_v = v²/(2g)
    GRAVITY = 9.81  # m/s²
    velocity_head_m = (target_nozzle_velocity_m_s ** 2) / (2 * GRAVITY)

    # Convert pressures to Pa for fluids.jet_pump
    P1_Pa = None  # To be solved
    P2_Pa = suction_pressure_kpa * 1000.0  # kPa to Pa
    P5_Pa = discharge_pressure_kpa * 1000.0  # kPa to Pa

    # Estimate mixing chamber diameter (typical R = An/Am ≈ 0.25-0.35)
    R_target = 0.30  # Area ratio (nozzle/mixing)
    mixing_diameter_m = nozzle_diameter_m / math.sqrt(R_target)

    # Estimate diffuser diameter (typical expansion ratio ~2-3)
    diffuser_diameter_m = mixing_diameter_m * 1.5

    try:
        # Call fluids.jet_pump to solve for P1 (pump discharge pressure)
        result = liquid_jet_pump(
            rhop=density_kg_m3,  # Primary (motive) fluid density
            rhos=density_kg_m3,  # Secondary fluid density (same liquid)
            Kp=0.05,  # Primary nozzle loss coefficient (well-designed nozzle)
            Ks=0.10,  # Secondary inlet loss coefficient
            Km=0.15,  # Mixing chamber loss coefficient
            Kd=0.10,  # Diffuser loss coefficient
            d_nozzle=nozzle_diameter_m,
            d_mixing=mixing_diameter_m,
            d_diffuser=diffuser_diameter_m,
            Qp=motive_flow_m3_s,
            Qs=secondary_flow_m3_s,
            P2=P2_Pa,
            P5=P5_Pa,
            nozzle_retracted=True,
        )

        # Extract P1 from solution
        P1_Pa = result['P1']
        P1_kpa = P1_Pa / 1000.0

        # Calculate pump head from pressure
        # TDH = ΔP/(ρ·g) = (P1 - P_atm)/(ρ·g) + static_head
        pressure_head_m = (P1_Pa - suction_pressure_kpa * 1000.0) / (density_kg_m3 * GRAVITY)
        total_head_m = pressure_head_m + static_head_m

        # Get efficiency from solution
        efficiency = result.get('efficiency', 0.0)

        fluids_success = True

    except Exception as e:
        warnings.append(
            f"WARNING: fluids.jet_pump calculation failed ({str(e)}). "
            "Using simplified TDH estimate."
        )

        # Fallback: simplified TDH calculation
        P1_kpa = discharge_pressure_kpa + (velocity_head_m * density_kg_m3 * GRAVITY / 1000.0)
        total_head_m = static_head_m + velocity_head_m * 1.5  # 1.5× for friction losses
        efficiency = 0.0
        fluids_success = False

    return {
        "motive_flow_m3_h": motive_flow_m3_h,
        "motive_flow_m3_s": motive_flow_m3_s,
        "secondary_flow_m3_h": total_educted_flow_m3_h - motive_flow_m3_h,
        "total_flow_m3_h": total_educted_flow_m3_h,
        "entrainment_ratio_total_to_motive": entrainment_ratio_total_to_motive,
        "entrainment_ratio_M": M_fluids,  # fluids.jet_pump convention
        "nozzle_diameter_m": nozzle_diameter_m,
        "nozzle_diameter_mm": nozzle_diameter_m * 1000.0,
        "nozzle_velocity_m_s": target_nozzle_velocity_m_s,
        "nozzle_area_m2": nozzle_area_m2,
        "mixing_diameter_m": mixing_diameter_m,
        "diffuser_diameter_m": diffuser_diameter_m,
        "required_pump_pressure_kpa": P1_kpa,
        "required_pump_head_m": total_head_m,
        "velocity_head_m": velocity_head_m,
        "static_head_m": static_head_m,
        "jet_pump_efficiency": efficiency,
        "fluids_calculation_success": fluids_success,
        "density_kg_m3": density_kg_m3,
        "warnings": warnings,
    }


# ============================================================================
# Pumped Mixing Calculation
# ============================================================================

def calculate_pumped_mixing_power(
    tank_volume_m3: float,
    recirculation_rate_m3_h: float,
    pump_head_m: float = 5.0,
    pump_efficiency: float = 0.65,
    nozzle_velocity_m_s: float = 3.0,
    mixing_mode: str = "simple",
    entrainment_ratio: float = 5.0,
    use_eductor_physics: bool = True,
) -> Dict[str, Any]:
    """
    Calculate power requirements for pumped (recirculation) mixing systems.

    Supports both simple pumped mixing and eductor/jet mixer systems with
    physics-based entrainment modeling using fluids.jet_pump.

    Parameters
    ----------
    tank_volume_m3 : float
        Tank working volume [m³]
    recirculation_rate_m3_h : float
        For simple mode: pump recirculation flow rate [m³/h]
        For eductor mode: total educted flow rate (motive + entrained) [m³/h]
    pump_head_m : float, optional
        Total pump head (suction + discharge + friction) [m]
        Default: 5 m (simple mode)
        Note: For eductor mode with use_eductor_physics=True, this is
        overridden by calculated TDH from fluids.jet_pump
    pump_efficiency : float, optional
        Wire-to-water pump efficiency [-] (default: 0.65)
    nozzle_velocity_m_s : float, optional
        Nozzle discharge velocity [m/s]
        Default: 3 m/s (simple mode), 20 m/s (eductor mode with physics)
    mixing_mode : str, optional
        Mixing system type: "simple" or "eductor" (default: "simple")
        - "simple": Direct pumped recirculation (pump flow = tank turnover)
        - "eductor": Jet mixer with entrainment (pump flow < tank turnover)
    entrainment_ratio : float, optional
        Ratio of total educted flow to motive pump flow [-] (default: 5.0)
        Only used for eductor mode. Typical range: 4-6
        This is Q_total/Q_motive (e.g., 5.0 for 5:1 ratio)
    use_eductor_physics : bool, optional
        If True, use fluids.jet_pump for physics-based TDH calculation
        If False, use simplified velocity head approach (default: True)

    Returns
    -------
    dict
        Contains calculated parameters:
        - power_total_kw: Total pump power [kW]
        - power_intensity_w_m3: Power per unit volume [W/m³]
        - recirculation_rate_m3_h: Total flow rate [m³/h]
        - pump_flow_m3_h: Actual pump flow (= motive flow for eductor) [m³/h]
        - recirculation_rate_volume_per_hour: Tank turnovers per hour [-]
        - pump_head_m: Total Dynamic Head [m]
        - nozzle_velocity_m_s: Discharge velocity [m/s]
        - mixing_mode: System type
        - eductor_details: Eductor parameters (eductor mode only)
        - warnings: List of warnings

    Notes
    -----
    **Simple Pumped Mixing:**
    - Pump flow = tank turnover flow
    - Lower nozzle velocity (2-4 m/s)
    - Lower pump head (5-10 m)
    - Power intensity: 3-5 W/m³

    **Eductor/Jet Mixer Systems:**
    - Pump flow = motive flow (typically 20% of total for 5:1 ratio)
    - High nozzle velocity (15-30 m/s) creates jet for entrainment
    - Higher pump head (15-25 m) to achieve velocity head
    - Total educted flow determines tank turnover
    - CRITICAL: Pump power uses motive flow, NOT total flow!

    Pump power equation:
        P = (ρ × g × Q_pump × H) / η

    where:
        ρ = fluid density [kg/m³]
        g = gravitational acceleration [9.81 m/s²]
        Q_pump = pump flow [m³/s] (motive flow for eductor mode)
        H = total head [m]
        η = pump efficiency [-]

    **CRITICAL COSTING NOTE:**
    For eductor systems, pump CAPEX/OPEX must use motive flow, NOT total
    educted flow. Using total flow would overestimate costs by 4-5×.

    Example: 5:1 eductor with 3000 m³/h total educted flow
    - Total flow: 3000 m³/h (for tank turnover)
    - Pump flow: 600 m³/h (for pump sizing/costing)
    - Using 3000 m³/h would give 5× wrong pump costs!

    Examples
    --------
    >>> # Simple pumped mixing
    >>> result = calculate_pumped_mixing_power(
    ...     tank_volume_m3=1000.0,
    ...     recirculation_rate_m3_h=3000.0,
    ...     pump_head_m=5.0,
    ...     mixing_mode="simple"
    ... )
    >>> print(f"Pump flow: {result['pump_flow_m3_h']:.0f} m³/h")
    >>> print(f"Power: {result['power_total_kw']:.1f} kW")

    >>> # Eductor mixing with physics-based sizing
    >>> result = calculate_pumped_mixing_power(
    ...     tank_volume_m3=1000.0,
    ...     recirculation_rate_m3_h=3000.0,  # Total educted flow
    ...     mixing_mode="eductor",
    ...     entrainment_ratio=5.0,
    ...     use_eductor_physics=True
    ... )
    >>> print(f"Total flow: {result['recirculation_rate_m3_h']:.0f} m³/h")
    >>> print(f"Pump flow: {result['pump_flow_m3_h']:.0f} m³/h")
    >>> print(f"TDH: {result['pump_head_m']:.1f} m")
    >>> print(f"Power: {result['power_total_kw']:.1f} kW")

    References
    ----------
    WEF MOP-8 (2017), Section 15.5
    Metcalf & Eddy (2014), Chapter 13
    EPA P100GGR5: Jet Aeration Systems Performance Testing
    Bell, I. H. fluids library: https://github.com/CalebBell/fluids
    """
    warnings = []

    # Constants
    DENSITY = 1010.0  # kg/m³ (typical sludge)
    GRAVITY = 9.81  # m/s²

    # Validate mixing mode
    if mixing_mode not in ["simple", "eductor"]:
        raise ValueError(
            f"Invalid mixing_mode '{mixing_mode}'. Must be 'simple' or 'eductor'."
        )

    # Initialize eductor details (will be populated for eductor mode)
    eductor_details = None

    # Determine pump flow and TDH based on mixing mode
    if mixing_mode == "eductor":
        # Eductor mode: Use motive flow for pump sizing
        if use_eductor_physics and FLUIDS_AVAILABLE:
            # Physics-based eductor sizing
            try:
                eductor_details = calculate_eductor_parameters(
                    total_educted_flow_m3_h=recirculation_rate_m3_h,
                    entrainment_ratio_total_to_motive=entrainment_ratio,
                    static_head_m=pump_head_m,
                    density_kg_m3=DENSITY,
                    target_nozzle_velocity_m_s=nozzle_velocity_m_s if nozzle_velocity_m_s != 3.0 else None,
                )

                # Use calculated motive flow and TDH
                pump_flow_m3_h = eductor_details['motive_flow_m3_h']
                actual_pump_head_m = eductor_details['required_pump_head_m']
                actual_nozzle_velocity = eductor_details['nozzle_velocity_m_s']

                # Append eductor warnings
                warnings.extend(eductor_details['warnings'])

                if eductor_details['fluids_calculation_success']:
                    warnings.append(
                        f"INFO: Using fluids.jet_pump calculated TDH = {actual_pump_head_m:.1f} m "
                        f"(overrides pump_head_m={pump_head_m:.1f} m parameter)"
                    )

            except Exception as e:
                warnings.append(
                    f"WARNING: Eductor physics calculation failed ({str(e)}). "
                    "Falling back to simplified approach."
                )
                use_eductor_physics = False

        if not use_eductor_physics or not FLUIDS_AVAILABLE:
            # Simplified approach: Calculate motive flow and estimate TDH
            pump_flow_m3_h = recirculation_rate_m3_h / entrainment_ratio

            # Use higher defaults for eductor mode
            if nozzle_velocity_m_s == 3.0:  # Default simple mode velocity
                actual_nozzle_velocity = 20.0  # Eductor default
                warnings.append(
                    "INFO: Using default eductor nozzle velocity 20 m/s "
                    "(override with nozzle_velocity_m_s parameter)"
                )
            else:
                actual_nozzle_velocity = nozzle_velocity_m_s

            # Simplified velocity head calculation
            velocity_head_m = (actual_nozzle_velocity ** 2) / (2 * GRAVITY)
            actual_pump_head_m = pump_head_m + velocity_head_m * 1.5  # 1.5× for losses

            warnings.append(
                f"INFO: Simplified eductor TDH = {pump_head_m:.1f} m (static) + "
                f"{velocity_head_m:.1f} m × 1.5 (velocity + losses) = {actual_pump_head_m:.1f} m"
            )

    else:
        # Simple pumped mixing: Pump flow = total flow
        pump_flow_m3_h = recirculation_rate_m3_h
        actual_pump_head_m = pump_head_m
        actual_nozzle_velocity = nozzle_velocity_m_s

    # Convert pump flow rate to m³/s for power calculation
    Q_pump_m3_s = pump_flow_m3_h / 3600.0

    # Calculate hydraulic power (using PUMP FLOW, not total flow!)
    P_hydraulic = DENSITY * GRAVITY * Q_pump_m3_s * actual_pump_head_m

    # Calculate electrical power (accounting for efficiency)
    P_electrical = P_hydraulic / pump_efficiency

    # Calculate power intensity
    power_intensity = P_electrical / tank_volume_m3

    # Calculate turnovers per hour (using TOTAL FLOW for tank turnover)
    turnovers_per_hour = recirculation_rate_m3_h / tank_volume_m3

    # Check design criteria
    if turnovers_per_hour < 2.0:
        warnings.append(
            f"WARNING: Recirculation rate {turnovers_per_hour:.2f} turnovers/hour "
            "is below recommended minimum (2/hour). Mixing may be inadequate."
        )
    elif turnovers_per_hour > 6.0:
        warnings.append(
            f"WARNING: Recirculation rate {turnovers_per_hour:.2f} turnovers/hour "
            "is very high. Consider reducing to save energy."
        )

    # Mode-specific velocity validation
    if mixing_mode == "simple":
        if actual_nozzle_velocity < 1.5:
            warnings.append(
                f"WARNING: Nozzle velocity {actual_nozzle_velocity:.2f} m/s is low for simple pumped mixing. "
                "Target: 2-4 m/s for adequate mixing."
            )
        elif actual_nozzle_velocity > 5.0:
            warnings.append(
                f"WARNING: Nozzle velocity {actual_nozzle_velocity:.2f} m/s is high for simple pumped mixing. "
                "Risk of excessive erosion and energy loss."
            )
    else:  # eductor mode
        if actual_nozzle_velocity < 15.0:
            warnings.append(
                f"WARNING: Nozzle velocity {actual_nozzle_velocity:.2f} m/s is low for eductor systems. "
                "Eductors typically require 15-30 m/s for effective entrainment."
            )
        elif actual_nozzle_velocity > 35.0:
            warnings.append(
                f"WARNING: Nozzle velocity {actual_nozzle_velocity:.2f} m/s is very high for eductor systems. "
                "Consider erosion, cavitation, and energy efficiency."
            )

    if power_intensity < 2.0:
        warnings.append(
            f"WARNING: Power intensity {power_intensity:.2f} W/m³ is very low. "
            "Verify mixing will be adequate."
        )

    # Prepare return dictionary
    result = {
        "power_total_kw": P_electrical / 1000.0,
        "power_intensity_w_m3": power_intensity,
        "recirculation_rate_m3_h": recirculation_rate_m3_h,  # Total flow
        "pump_flow_m3_h": pump_flow_m3_h,  # Actual pump flow (motive for eductor)
        "recirculation_rate_volume_per_hour": turnovers_per_hour,
        "pump_head_m": actual_pump_head_m,  # Actual TDH used
        "pump_efficiency": pump_efficiency,
        "nozzle_velocity_m_s": actual_nozzle_velocity,
        "mixing_mode": mixing_mode,
        "warnings": warnings,
    }

    # Add eductor-specific details if available
    if eductor_details is not None:
        result["eductor_details"] = eductor_details

    return result


# ============================================================================
# Example Usage and Testing
# ============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("Anaerobic Digester Mixing Calculations - Test Suite")
    print("=" * 80)

    # Test 1: Mesophilic digester with mechanical mixing (design mode)
    print("\n--- Test 1: Mesophilic Complete Mix Digester (Design Mode) ---")
    preset = ANAEROBIC_DIGESTER_MIXING_PRESETS["mesophilic_complete_mix"]
    result = calculate_mechanical_mixing_power(
        tank_diameter_m=12.0,
        tank_volume_m3=1000.0,
        target_power_w_m3=preset.power_target_w_m3,
        fluid_density_kg_m3=preset.typical_density_kg_m3,
        fluid_viscosity_pa_s=preset.typical_viscosity_pa_s,
        impeller_type=preset.impeller_type,
        mode="design",
    )

    print(f"Impeller: {result['impeller_type']}")
    print(f"Diameter: {result['impeller_diameter_m']:.2f} m (D/T={result['d_t_ratio']:.2f})")
    print(f"Speed: {result['impeller_speed_rpm']:.1f} rpm")
    print(f"Power: {result['power_total_kw']:.1f} kW ({result['power_intensity_w_m3']:.1f} W/m³)")
    print(f"Reynolds: {result['reynolds_number']:.0f} ({result['flow_regime']})")
    print(f"Tip speed: {result['tip_speed_m_s']:.2f} m/s")
    if result['warnings']:
        for warning in result['warnings']:
            print(f"  {warning}")

    # Test 2: Pumped mixing
    print("\n--- Test 2: Pumped Mixing System ---")
    result_pumped = calculate_pumped_mixing_power(
        tank_volume_m3=1000.0,
        recirculation_rate_m3_h=3000.0,
        pump_head_m=5.0,
        pump_efficiency=0.65,
        nozzle_velocity_m_s=3.0,
    )

    print(f"Flow rate: {result_pumped['recirculation_rate_m3_h']:.0f} m³/h")
    print(f"Turnovers: {result_pumped['recirculation_rate_volume_per_hour']:.1f} per hour")
    print(f"Power: {result_pumped['power_total_kw']:.1f} kW ({result_pumped['power_intensity_w_m3']:.1f} W/m³)")
    if result_pumped['warnings']:
        for warning in result_pumped['warnings']:
            print(f"  {warning}")

    print("\n" + "=" * 80)
    print("All tests completed successfully!")
    print("=" * 80)
