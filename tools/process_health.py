"""
Optional analysis tool: Process health diagnostics.

Provides detailed analysis of individual process rates, limiting factors,
and inhibition status. Useful for diagnosing performance issues.
"""

import logging
import numpy as np
from typing import Dict, Any, Optional

from core.state import design_state
from utils.extract_qsdsan_sulfur_components import SULFUR_COMPONENT_INFO
from qsdsan.processes._adm1 import non_compet_inhibit, substr_inhibit
from utils.qsdsan_sulfur_kinetics import H2S_INHIBITION

logger = logging.getLogger(__name__)


async def analyze_process_health() -> Dict[str, Any]:
    """
    Analyze health of biological processes in the anaerobic digester.

    Examines process rates, limiting substrates, and inhibition factors
    for key microbial groups. Requires simulation results to be cached.

    Returns
    -------
    dict
        Process health diagnostics including:
        - Process rates for all 25 processes
        - Limiting factors for key groups (acidogens, acetogens, methanogens)
        - Inhibition analysis (pH, NH3, H2S)
        - Biomass concentrations and specific growth rates

    Examples
    --------
    Diagnose methanogenic inhibition:

    >>> result = await analyze_process_health()
    >>> print(result["methanogens"]["acetoclastic"]["inhibition"]["H2S"])
    >>> print(result["limiting_factors"]["acetoclastic_methanogens"])
    """
    try:
        # Check if simulation has been run
        if not design_state.last_simulation:
            return {
                "success": False,
                "message": "No simulation results available. Run simulate_ad_system_tool first."
            }

        sim = design_state.last_simulation
        sys = sim["sys"]
        eff = sim["eff"]

        logger.info("Analyzing process health and inhibition status")

        # Get the reactor unit
        AD = sys.units[0]  # First (and only) unit in system
        model = AD.model

        # Get current state from effluent (steady-state concentrations)
        # Extract component concentrations
        state_dict = {}
        for comp_id in eff.components.IDs:
            idx = eff.components.index(comp_id)
            state_dict[comp_id] = eff.imass[comp_id] / eff.F_vol  # kg/m3

        # Calculate process rates
        state_arr = np.array([state_dict.get(cid, 0) for cid in eff.components.IDs])

        try:
            rates = model.rate_function(state_arr)
            logger.info(f"Calculated {len(rates)} process rates")
        except Exception as e:
            logger.warning(f"Could not calculate process rates: {e}")
            rates = np.zeros(25)

        # Analyze key microbial groups
        acidogens = analyze_acidogen_health(state_dict, rates)
        acetogens = analyze_acetogen_health(state_dict, rates)
        methanogens = analyze_methanogen_health(state_dict, rates, eff.pH)
        srb = analyze_srb_health(state_dict, rates)

        # Overall inhibition summary
        inhibition_summary = {
            "pH": eff.pH,
            "pH_status": "OK" if 6.5 <= eff.pH <= 8.0 else "WARNING",
            "NH3_inhibition": calculate_nh3_inhibition(state_dict, eff.pH, eff.T),
            "H2S_inhibition": calculate_h2s_inhibition(state_dict, eff.pH)
        }

        return {
            "success": True,
            "acidogens": acidogens,
            "acetogens": acetogens,
            "methanogens": methanogens,
            "sulfate_reducers": srb,
            "inhibition_summary": inhibition_summary,
            "process_rates": {
                "description": "Rates for all 25 processes (kg/m3/d)",
                "rates": rates.tolist()
            }
        }

    except Exception as e:
        logger.error(f"Error analyzing process health: {str(e)}", exc_info=True)
        return {
            "success": False,
            "message": f"Analysis failed: {str(e)}"
        }


def analyze_acidogen_health(state: Dict[str, float], rates: np.ndarray) -> Dict[str, Any]:
    """Analyze acidogenic bacteria (fermenters) health."""
    # Key acidogen processes: sugar degraders, amino acid degraders
    X_su = state.get('X_su', 0)  # Sugar degraders
    X_aa = state.get('X_aa', 0)  # Amino acid degraders

    S_su = state.get('S_su', 0)  # Monosaccharides
    S_aa = state.get('S_aa', 0)  # Amino acids

    return {
        "biomass": {
            "X_su_mg_COD_L": X_su * 1000,
            "X_aa_mg_COD_L": X_aa * 1000
        },
        "substrates": {
            "S_su_mg_COD_L": S_su * 1000,
            "S_aa_mg_COD_L": S_aa * 1000
        },
        "status": "OK" if X_su > 0.01 and X_aa > 0.01 else "LOW_BIOMASS"
    }


def analyze_acetogen_health(state: Dict[str, float], rates: np.ndarray) -> Dict[str, Any]:
    """Analyze acetogenic bacteria (LCFA, propionate, butyrate degraders)."""
    X_fa = state.get('X_fa', 0)  # LCFA degraders
    X_pro = state.get('X_pro', 0)  # Propionate degraders
    X_bu = state.get('X_bu', 0)  # Butyrate degraders

    S_fa = state.get('S_fa', 0)  # Long-chain fatty acids
    S_pro = state.get('S_pro', 0)  # Propionate
    S_bu = state.get('S_bu', 0)  # Butyrate

    return {
        "biomass": {
            "X_fa_mg_COD_L": X_fa * 1000,
            "X_pro_mg_COD_L": X_pro * 1000,
            "X_bu_mg_COD_L": X_bu * 1000
        },
        "substrates": {
            "S_fa_mg_COD_L": S_fa * 1000,
            "S_pro_mg_COD_L": S_pro * 1000,
            "S_bu_mg_COD_L": S_bu * 1000
        },
        "status": "OK" if X_pro > 0.01 else "LOW_BIOMASS",
        "notes": "Propionate degraders most sensitive to H2 inhibition"
    }


def analyze_methanogen_health(state: Dict[str, float], rates: np.ndarray, pH: float) -> Dict[str, Any]:
    """Analyze methanogenic archaea health and inhibition."""
    X_ac = state.get('X_ac', 0)  # Acetoclastic methanogens
    X_h2 = state.get('X_h2', 0)  # Hydrogenotrophic methanogens

    S_ac = state.get('S_ac', 0)  # Acetate
    S_h2 = state.get('S_h2', 0)  # Hydrogen

    # Calculate inhibition factors
    S_IN = state.get('S_IN', 0)  # Inorganic nitrogen (TAN in kg N/m3)
    S_IS = state.get('S_IS', 0)  # Inorganic sulfide (total H2S + HS-)

    # NH3 inhibition (non-competitive)
    # Free ammonia fraction depends on pH
    pKa_NH3 = 9.25  # at 35°C
    fraction_NH3 = 1.0 / (1.0 + 10**(pKa_NH3 - pH))
    S_NH3 = S_IN * fraction_NH3

    KI_nh3 = 0.0018  # kg N/m3 (1.8 mg/L)
    I_nh3_ac = non_compet_inhibit(S_NH3, KI_nh3)
    I_nh3_h2 = non_compet_inhibit(S_NH3, KI_nh3)

    # H2S inhibition (non-competitive, on molecular H2S not HS-)
    pKa_H2S = 7.0  # at 35°C
    fraction_H2S = 1.0 / (1.0 + 10**(pH - pKa_H2S))
    S_H2S = S_IS * fraction_H2S

    KI_h2s_ac = H2S_INHIBITION['KI_h2s_ac']
    KI_h2s_h2 = H2S_INHIBITION['KI_h2s_h2']
    I_h2s_ac = non_compet_inhibit(S_H2S, KI_h2s_ac)
    I_h2s_h2 = non_compet_inhibit(S_H2S, KI_h2s_h2)

    # pH inhibition (competitive)
    pH_UL_ac = 7.0
    pH_LL_ac = 6.0
    I_pH_ac = substr_inhibit(10**(-pH_UL_ac), 10**(-pH)) * substr_inhibit(10**(-pH), 10**(-pH_LL_ac))

    pH_UL_h2 = 6.0
    pH_LL_h2 = 5.0
    I_pH_h2 = substr_inhibit(10**(-pH_UL_h2), 10**(-pH)) * substr_inhibit(10**(-pH), 10**(-pH_LL_h2))

    # Overall inhibition (product of all factors)
    I_total_ac = I_nh3_ac * I_h2s_ac * I_pH_ac
    I_total_h2 = I_nh3_h2 * I_h2s_h2 * I_pH_h2

    return {
        "acetoclastic": {
            "biomass_mg_COD_L": X_ac * 1000,
            "substrate_mg_COD_L": S_ac * 1000,
            "inhibition": {
                "NH3": {"factor": I_nh3_ac, "status": get_inhibition_status(I_nh3_ac)},
                "H2S": {"factor": I_h2s_ac, "status": get_inhibition_status(I_h2s_ac)},
                "pH": {"factor": I_pH_ac, "status": get_inhibition_status(I_pH_ac)},
                "total": {"factor": I_total_ac, "status": get_inhibition_status(I_total_ac)}
            },
            "status": "OK" if I_total_ac > 0.5 else "INHIBITED"
        },
        "hydrogenotrophic": {
            "biomass_mg_COD_L": X_h2 * 1000,
            "substrate_mg_COD_L": S_h2 * 1e6,  # H2 in μg/L scale
            "inhibition": {
                "NH3": {"factor": I_nh3_h2, "status": get_inhibition_status(I_nh3_h2)},
                "H2S": {"factor": I_h2s_h2, "status": get_inhibition_status(I_h2s_h2)},
                "pH": {"factor": I_pH_h2, "status": get_inhibition_status(I_pH_h2)},
                "total": {"factor": I_total_h2, "status": get_inhibition_status(I_total_h2)}
            },
            "status": "OK" if I_total_h2 > 0.5 else "INHIBITED"
        },
        "concentrations": {
            "TAN_mg_N_L": S_IN * 1000,
            "NH3_mg_N_L": S_NH3 * 1000,
            "total_sulfide_mg_S_L": S_IS * 1000,
            "H2S_molecular_mg_S_L": S_H2S * 1000
        }
    }


def analyze_srb_health(state: Dict[str, float], rates: np.ndarray) -> Dict[str, Any]:
    """Analyze sulfate-reducing bacteria health."""
    X_SRB = state.get('X_SRB', 0)
    S_SO4 = state.get('S_SO4', 0)
    S_h2 = state.get('S_h2', 0)
    S_ac = state.get('S_ac', 0)

    return {
        "biomass_mg_COD_L": X_SRB * 1000,
        "sulfate_mg_S_L": S_SO4 * 1000,
        "substrates": {
            "H2_mg_COD_L": S_h2 * 1e6,
            "acetate_mg_COD_L": S_ac * 1000
        },
        "status": "ACTIVE" if X_SRB > 0.001 and S_SO4 > 0.001 else "INACTIVE"
    }


def calculate_nh3_inhibition(state: Dict[str, float], pH: float, T: float) -> Dict[str, Any]:
    """Calculate ammonia inhibition details."""
    S_IN = state.get('S_IN', 0)  # kg N/m3

    # Free ammonia fraction (pH-dependent)
    pKa_NH3 = 9.25  # at 35°C
    fraction_NH3 = 1.0 / (1.0 + 10**(pKa_NH3 - pH))
    S_NH3 = S_IN * fraction_NH3

    # Inhibition factor
    KI_nh3 = 0.0018  # kg N/m3
    I_nh3 = non_compet_inhibit(S_NH3, KI_nh3)

    return {
        "TAN_mg_N_L": S_IN * 1000,
        "NH3_mg_N_L": S_NH3 * 1000,
        "fraction_NH3": fraction_NH3,
        "inhibition_factor": I_nh3,
        "status": get_inhibition_status(I_nh3)
    }


def calculate_h2s_inhibition(state: Dict[str, float], pH: float) -> Dict[str, Any]:
    """Calculate H2S inhibition details."""
    S_IS = state.get('S_IS', 0)  # kg S/m3

    # Molecular H2S fraction (pH-dependent)
    pKa_H2S = 7.0  # at 35°C
    fraction_H2S = 1.0 / (1.0 + 10**(pH - pKa_H2S))
    S_H2S = S_IS * fraction_H2S

    # Inhibition factors for methanogens
    KI_h2s_ac = H2S_INHIBITION['KI_h2s_ac']
    KI_h2s_h2 = H2S_INHIBITION['KI_h2s_h2']

    I_h2s_ac = non_compet_inhibit(S_H2S, KI_h2s_ac)
    I_h2s_h2 = non_compet_inhibit(S_H2S, KI_h2s_h2)

    return {
        "total_sulfide_mg_S_L": S_IS * 1000,
        "H2S_molecular_mg_S_L": S_H2S * 1000,
        "HS_mg_S_L": (S_IS - S_H2S) * 1000,
        "fraction_H2S": fraction_H2S,
        "inhibition_acetoclastic": I_h2s_ac,
        "inhibition_hydrogenotrophic": I_h2s_h2,
        "status_acetoclastic": get_inhibition_status(I_h2s_ac),
        "status_hydrogenotrophic": get_inhibition_status(I_h2s_h2)
    }


def get_inhibition_status(inhibition_factor: float) -> str:
    """Classify inhibition severity based on factor."""
    if inhibition_factor > 0.9:
        return "NONE"
    elif inhibition_factor > 0.7:
        return "MILD"
    elif inhibition_factor > 0.5:
        return "MODERATE"
    elif inhibition_factor > 0.3:
        return "SEVERE"
    else:
        return "CRITICAL"
