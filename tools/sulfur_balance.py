"""
Optional analysis tool: Sulfur mass balance verification.

Provides comprehensive sulfur accounting across all streams,
validates mass balance closure, and identifies sulfur fate.
"""

import logging
from typing import Dict, Any, Optional

from core.state import design_state
from utils.stream_analysis_sulfur import calculate_sulfur_metrics

logger = logging.getLogger(__name__)


async def verify_sulfur_balance(
    tolerance_percent: float = 5.0
) -> Dict[str, Any]:
    """
    Perform sulfur mass balance verification.

    Tracks sulfur through all streams (influent, effluent, biogas) and
    validates that mass balance closes within tolerance.

    Parameters
    ----------
    tolerance_percent : float, optional
        Acceptable imbalance as percentage of input (default 5.0%)

    Returns
    -------
    dict
        Sulfur mass balance including:
        - Input sulfur (influent sulfate + sulfide)
        - Output sulfur (effluent sulfate + sulfide, biogas H2S)
        - Accumulation (biomass sulfur)
        - Balance closure (% error)
        - Detailed breakdown by stream and species

    Examples
    --------
    Check sulfur balance after simulation:

    >>> result = await verify_sulfur_balance(tolerance_percent=5.0)
    >>> print(result["balance"]["closure_percent"])
    >>> print(result["fate"]["to_biogas_percent"])
    """
    try:
        # Check if simulation has been run
        if not design_state.last_simulation:
            return {
                "success": False,
                "message": "No simulation results available. Run simulate_ad_system_tool first."
            }

        sim = design_state.last_simulation
        inf = sim["inf"]
        eff = sim["eff"]
        gas = sim["gas"]

        logger.info("Verifying sulfur mass balance")

        # Use existing sulfur metrics calculation
        sulfur_metrics = calculate_sulfur_metrics(inf, eff, gas)

        # Extract key values (now flat structure)
        input_kg_d = sulfur_metrics["sulfate_in_kg_S_d"]
        output_sulfate_kg_d = sulfur_metrics["sulfate_out_kg_S_d"]
        output_sulfide_dissolved_kg_d = sulfur_metrics["sulfide_out_kg_S_d"]
        output_h2s_biogas_kg_d = sulfur_metrics["h2s_biogas_kg_S_d"]

        # Calculate totals
        total_output = output_sulfate_kg_d + output_sulfide_dissolved_kg_d + output_h2s_biogas_kg_d

        # Calculate accumulation (difference = accumulation in biomass/particulates)
        accumulation_kg_d = input_kg_d - total_output

        # Calculate balance closure
        if input_kg_d > 1e-6:
            closure_percent = (total_output / input_kg_d) * 100
            imbalance_percent = abs(100 - closure_percent)
        else:
            closure_percent = 0
            imbalance_percent = 0

        # Determine balance status
        balance_ok = imbalance_percent <= tolerance_percent

        # Calculate sulfur fate distribution
        if input_kg_d > 1e-6:
            fate = {
                "to_biogas_percent": (output_h2s_biogas_kg_d / input_kg_d) * 100,
                "dissolved_effluent_percent": (output_sulfide_dissolved_kg_d / input_kg_d) * 100,
                "remains_sulfate_percent": (output_sulfate_kg_d / input_kg_d) * 100,
                "accumulated_percent": (accumulation_kg_d / input_kg_d) * 100
            }
        else:
            fate = {
                "to_biogas_percent": 0,
                "dissolved_effluent_percent": 0,
                "remains_sulfate_percent": 0,
                "accumulated_percent": 0
            }

        # Build detailed breakdown
        breakdown = {
            "input": {
                "sulfate_influent_kg_S_d": input_kg_d,
                "sulfide_influent_kg_S_d": 0,  # Typically zero for influent
                "total_kg_S_d": input_kg_d
            },
            "output": {
                "sulfate_effluent_kg_S_d": output_sulfate_kg_d,
                "sulfide_dissolved_effluent_kg_S_d": output_sulfide_dissolved_kg_d,
                "h2s_biogas_kg_S_d": output_h2s_biogas_kg_d,
                "total_kg_S_d": total_output
            },
            "accumulation": {
                "biomass_particulates_kg_S_d": accumulation_kg_d,
                "description": "Sulfur incorporated into SRB biomass or precipitated"
            }
        }

        # SRB activity analysis
        srb_analysis = analyze_srb_activity(inf, eff, gas, sulfur_metrics)

        return {
            "success": True,
            "balance": {
                "input_kg_S_d": input_kg_d,
                "output_kg_S_d": total_output,
                "accumulation_kg_S_d": accumulation_kg_d,
                "closure_percent": closure_percent,
                "imbalance_percent": imbalance_percent,
                "status": "BALANCED" if balance_ok else "IMBALANCED",
                "tolerance_percent": tolerance_percent
            },
            "fate": fate,
            "breakdown": breakdown,
            "srb_activity": srb_analysis,
            "speciation": {
                "effluent": {
                    "H2S_dissolved_mg_S_L": sulfur_metrics["H2S_dissolved_mg_L"],
                    "HS_dissolved_mg_S_L": sulfur_metrics["HS_dissolved_mg_L"],
                    "fraction_H2S": sulfur_metrics["fraction_H2S"]
                },
                "biogas": {
                    "H2S_ppm": sulfur_metrics["h2s_biogas_ppm"],
                    "H2S_percent": sulfur_metrics["h2s_biogas_percent"]
                }
            }
        }

    except Exception as e:
        logger.error(f"Error verifying sulfur balance: {str(e)}", exc_info=True)
        return {
            "success": False,
            "message": f"Sulfur balance verification failed: {str(e)}"
        }


def analyze_srb_activity(inf, eff, gas, sulfur_metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze sulfate-reducing bacteria activity based on sulfur transformations."""
    # Calculate sulfate reduction (flat structure)
    sulfate_in = sulfur_metrics["sulfate_in_kg_S_d"]
    sulfate_out = sulfur_metrics["sulfate_out_kg_S_d"]
    sulfate_reduced = sulfate_in - sulfate_out

    # Calculate sulfide production
    sulfide_produced = sulfur_metrics["sulfide_out_kg_S_d"]
    h2s_stripped = sulfur_metrics["h2s_biogas_kg_S_d"]
    total_sulfide_generated = sulfide_produced + h2s_stripped

    # SRB efficiency
    if sulfate_reduced > 1e-6:
        conversion_efficiency = (total_sulfide_generated / sulfate_reduced) * 100
    else:
        conversion_efficiency = 0

    # Estimate COD consumed by SRB
    # Stoichiometry: SO4^2- + 2 H+ + 4 H2 → H2S + 4 H2O
    # Or: SO4^2- + CH3COO- + H+ → H2S + 2 HCO3-
    # Roughly: 1 kg S reduced consumes ~2 kg COD
    cod_to_srb_kg_d = sulfate_reduced * 2.0

    # Activity status
    if sulfate_reduced > 0.01:  # >10 g S/d reduced
        activity_level = "HIGH"
    elif sulfate_reduced > 0.001:  # >1 g S/d reduced
        activity_level = "MODERATE"
    elif sulfate_reduced > 0:
        activity_level = "LOW"
    else:
        activity_level = "NEGLIGIBLE"

    return {
        "sulfate_reduced_kg_S_d": sulfate_reduced,
        "sulfide_generated_kg_S_d": total_sulfide_generated,
        "conversion_efficiency_percent": conversion_efficiency,
        "estimated_cod_to_srb_kg_d": cod_to_srb_kg_d,
        "activity_level": activity_level,
        "notes": "SRB compete with methanogens for acetate and H2"
    }


async def assess_h2s_removal_options(
    target_h2s_ppm: float = 100
) -> Dict[str, Any]:
    """
    Assess H2S removal requirements and options.

    Evaluates if biogas H2S exceeds target and suggests removal methods.

    Parameters
    ----------
    target_h2s_ppm : float, optional
        Target H2S concentration in biogas (default 100 ppm)

    Returns
    -------
    dict
        H2S removal assessment including:
        - Current H2S level vs target
        - Removal requirement (kg S/d)
        - Suggested removal methods
        - Iron dosing calculation (if applicable)

    Examples
    --------
    Check if H2S removal is needed:

    >>> result = await assess_h2s_removal_options(target_h2s_ppm=100)
    >>> print(result["removal_needed"])
    >>> print(result["methods"]["iron_dosing"]["FeCl3_kg_d"])
    """
    try:
        # Check if simulation has been run
        if not design_state.last_simulation:
            return {
                "success": False,
                "message": "No simulation results available. Run simulate_ad_system_tool first."
            }

        sim = design_state.last_simulation
        inf = sim["inf"]
        eff = sim["eff"]
        gas = sim["gas"]

        # Calculate current H2S (flat structure)
        sulfur_metrics = calculate_sulfur_metrics(inf, eff, gas)
        current_h2s_ppm = sulfur_metrics["h2s_biogas_ppm"]
        h2s_kg_S_d = sulfur_metrics["h2s_biogas_kg_S_d"]

        # Check if removal needed
        removal_needed = current_h2s_ppm > target_h2s_ppm

        if not removal_needed:
            return {
                "success": True,
                "removal_needed": False,
                "current_h2s_ppm": current_h2s_ppm,
                "target_h2s_ppm": target_h2s_ppm,
                "message": f"H2S level ({current_h2s_ppm:.1f} ppm) is below target ({target_h2s_ppm} ppm)"
            }

        # Calculate removal requirement
        excess_fraction = 1 - (target_h2s_ppm / current_h2s_ppm)
        h2s_to_remove_kg_S_d = h2s_kg_S_d * excess_fraction

        # Suggest removal methods
        methods = {
            "iron_dosing": calculate_iron_dosing(h2s_to_remove_kg_S_d),
            "biogas_scrubbing": {
                "type": "Water scrubbing or caustic scrubbing",
                "h2s_removal_kg_S_d": h2s_to_remove_kg_S_d,
                "efficiency_typical": "95-99%"
            },
            "biological_desulfurization": {
                "type": "Microaerobic desulfurization in digester headspace",
                "h2s_removal_kg_S_d": h2s_to_remove_kg_S_d,
                "oxygen_demand_kg_d": h2s_to_remove_kg_S_d * 0.5  # ~0.5 kg O2 per kg S
            }
        }

        return {
            "success": True,
            "removal_needed": True,
            "current_h2s_ppm": current_h2s_ppm,
            "target_h2s_ppm": target_h2s_ppm,
            "h2s_to_remove_kg_S_d": h2s_to_remove_kg_S_d,
            "methods": methods,
            "recommendation": get_removal_recommendation(current_h2s_ppm, h2s_to_remove_kg_S_d)
        }

    except Exception as e:
        logger.error(f"Error assessing H2S removal: {str(e)}", exc_info=True)
        return {
            "success": False,
            "message": f"H2S removal assessment failed: {str(e)}"
        }


def calculate_iron_dosing(h2s_to_remove_kg_S_d: float) -> Dict[str, Any]:
    """Calculate iron salt dosing for H2S removal."""
    # Stoichiometry: Fe3+ + H2S → FeS + 2 H+
    # 1 mol Fe (56 g) removes 1 mol S (32 g)
    # Ratio: 56/32 = 1.75 kg Fe per kg S

    Fe_kg_d = h2s_to_remove_kg_S_d * 1.75

    # FeCl3 dosing (typical coagulant)
    # FeCl3 MW = 162.2, Fe MW = 55.845
    # 1 kg Fe = 162.2/55.845 = 2.9 kg FeCl3
    FeCl3_kg_d = Fe_kg_d * 2.9

    # FeCl3 solution dosing (typical 40% solution)
    FeCl3_solution_kg_d = FeCl3_kg_d / 0.4

    return {
        "description": "Dosing FeCl3 to precipitate FeS",
        "Fe_required_kg_d": Fe_kg_d,
        "FeCl3_required_kg_d": FeCl3_kg_d,
        "FeCl3_solution_40pct_kg_d": FeCl3_solution_kg_d,
        "dosing_location": "Digester influent or recirculation line",
        "notes": "Produces FeS sludge that settles or is dewatered with biosolids"
    }


def get_removal_recommendation(current_ppm: float, h2s_kg_d: float) -> str:
    """Get removal method recommendation based on H2S level."""
    if current_ppm < 500:
        return "Iron dosing (FeCl3) most economical for low-moderate H2S"
    elif current_ppm < 2000:
        return "Consider biological desulfurization or biogas scrubbing"
    else:
        return "High H2S level - biogas scrubbing or two-stage treatment recommended"
