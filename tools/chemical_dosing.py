"""
Chemical dosing estimation tool for anaerobic digester design.

Provides MCP interface for FeCl3, NaOH, and Na2CO3 dosing recommendations.
"""

import logging
from typing import Dict, Any, Optional

from core.state import design_state
from utils.chemical_dosing import (
    estimate_fecl3_for_sulfide_removal,
    estimate_fecl3_for_phosphate_removal,
    estimate_naoh_for_ph_adjustment,
    estimate_na2co3_for_alkalinity
)

logger = logging.getLogger(__name__)


async def estimate_chemical_dosing_tool(
    use_current_state: bool = True,
    custom_params: Optional[Dict[str, Any]] = None,
    objectives: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Estimate chemical dosing requirements for anaerobic digester operation.

    Provides stoichiometric estimates for:
    - FeCl3: Sulfide precipitation (H2S control) and phosphate removal
    - NaOH: pH adjustment
    - Na2CO3: Alkalinity supplementation

    Parameters
    ----------
    use_current_state : bool, optional
        Use feedstock parameters from current design state (default True)
    custom_params : dict, optional
        Custom feedstock parameters (if not using design state):
        - sulfide_mg_L: H2S concentration (mg-S/L)
        - phosphate_mg_P_L: Phosphate concentration (mg-P/L)
        - alkalinity_meq_L: Current alkalinity (meq/L)
        - pH_current: Current pH
    objectives : dict, optional
        Target treatment objectives:
        - sulfide_removal: Fraction of sulfide to remove (0-1, default 0.90)
        - phosphate_removal: Fraction of phosphate to remove (0-1, default 0.80)
        - pH_target: Target pH (default 7.5)
        - alkalinity_target_meq_L: Target alkalinity (meq/L, optional)

    Returns
    -------
    dict
        Dosing recommendations with:
        - fecl3_for_sulfide: FeCl3 dose for H2S control
        - fecl3_for_phosphate: FeCl3 dose for P removal
        - naoh_for_ph: NaOH dose for pH adjustment
        - na2co3_for_alkalinity: Na2CO3 dose for alkalinity
        - summary: Combined recommendations
        - rationale: Explanation of each recommendation

    Examples
    --------
    >>> # After running design workflow
    >>> result = await estimate_chemical_dosing_tool(
    ...     use_current_state=True,
    ...     objectives={'sulfide_removal': 0.95, 'pH_target': 7.5}
    ... )
    >>> print(result['summary']['total_fecl3_mg_L'])
    """
    try:
        # 1. Get feedstock parameters
        if use_current_state:
            if not design_state.basis_of_design:
                return {
                    "success": False,
                    "message": "No basis of design found. Run elicit_basis_of_design first."
                }
            if not design_state.adm1_state:
                return {
                    "success": False,
                    "message": "No ADM1 state found. Load or generate ADM1 state first."
                }

            # Extract parameters from ADM1 state
            basis = design_state.basis_of_design
            adm1_state = design_state.adm1_state

            # Get sulfide from ADM1 state (S_IS in kg/m³)
            sulfide_kg_m3 = adm1_state.get('S_IS', 0.0)
            sulfide_mg_L = sulfide_kg_m3 * 1000  # kg/m³ -> mg/L

            # Get phosphate from ADM1 state (S_IP in kg/m³, measured as P)
            phosphate_kg_m3 = adm1_state.get('S_IP', 0.0)
            phosphate_mg_P_L = phosphate_kg_m3 * 1000  # kg/m³ -> mg/L

            # Get alkalinity and pH from basis
            alkalinity_meq_L = basis.get('alkalinity_meq_l', 50.0)
            pH_current = basis.get('pH', 7.0)

        else:
            if not custom_params:
                return {
                    "success": False,
                    "message": "Must provide custom_params if not using design state"
                }

            sulfide_mg_L = custom_params.get('sulfide_mg_L', 0.0)
            phosphate_mg_P_L = custom_params.get('phosphate_mg_P_L', 0.0)
            alkalinity_meq_L = custom_params.get('alkalinity_meq_L', 50.0)
            pH_current = custom_params.get('pH_current', 7.0)

        # 2. Get treatment objectives
        objectives = objectives or {}
        sulfide_removal = objectives.get('sulfide_removal', 0.90)
        phosphate_removal = objectives.get('phosphate_removal', 0.80)
        pH_target = objectives.get('pH_target', 7.5)
        alkalinity_target_meq_L = objectives.get('alkalinity_target_meq_L', None)

        # 3. Calculate dosing for each chemical

        # FeCl3 for sulfide removal
        fecl3_sulfide = None
        if sulfide_mg_L > 0:
            fecl3_sulfide = estimate_fecl3_for_sulfide_removal(
                sulfide_mg_L=sulfide_mg_L,
                target_removal=sulfide_removal,
                safety_factor=1.2
            )

        # FeCl3 for phosphate removal
        fecl3_phosphate = None
        if phosphate_mg_P_L > 0:
            fecl3_phosphate = estimate_fecl3_for_phosphate_removal(
                phosphate_mg_P_L=phosphate_mg_P_L,
                target_removal=phosphate_removal,
                safety_factor=1.5
            )

        # NaOH for pH adjustment
        naoh_ph = None
        if pH_target > pH_current:
            naoh_ph = estimate_naoh_for_ph_adjustment(
                alkalinity_meq_L=alkalinity_meq_L,
                pH_current=pH_current,
                pH_target=pH_target
            )

        # Na2CO3 for alkalinity
        na2co3_alk = None
        if alkalinity_target_meq_L and alkalinity_target_meq_L > alkalinity_meq_L:
            na2co3_alk = estimate_na2co3_for_alkalinity(
                alkalinity_current_meq_L=alkalinity_meq_L,
                alkalinity_target_meq_L=alkalinity_target_meq_L
            )

        # 4. Build summary
        total_fecl3 = 0
        if fecl3_sulfide:
            total_fecl3 = max(total_fecl3, fecl3_sulfide['fecl3_dose_mg_L'])
        if fecl3_phosphate:
            total_fecl3 = max(total_fecl3, fecl3_phosphate['fecl3_dose_mg_L'])

        summary = {
            "total_fecl3_mg_L": total_fecl3,
            "naoh_mg_L": naoh_ph['naoh_dose_mg_L'] if naoh_ph else 0,
            "na2co3_mg_L": na2co3_alk['na2co3_dose_mg_L'] if na2co3_alk else 0,
            "fe3_added_mg_L": total_fecl3 * (55.845 / 162.2) if total_fecl3 > 0 else 0,
            "cl_added_mg_L": total_fecl3 * (3 * 35.453 / 162.2) if total_fecl3 > 0 else 0,
            "na_added_mg_L": (naoh_ph['na_added_mg_L'] if naoh_ph else 0) +
                            (na2co3_alk['na_added_mg_L'] if na2co3_alk else 0)
        }

        # 5. Build rationale
        rationale = []
        if fecl3_sulfide:
            rationale.append(
                f"FeCl3 for H2S control: {fecl3_sulfide['fecl3_dose_mg_L']:.0f} mg/L "
                f"to remove {sulfide_removal*100:.0f}% of {sulfide_mg_L:.0f} mg-S/L sulfide"
            )
        if fecl3_phosphate:
            rationale.append(
                f"FeCl3 for P removal: {fecl3_phosphate['fecl3_dose_mg_L']:.0f} mg/L "
                f"to remove {phosphate_removal*100:.0f}% of {phosphate_mg_P_L:.0f} mg-P/L phosphate"
            )
        if naoh_ph:
            rationale.append(
                f"NaOH for pH control: {naoh_ph['naoh_dose_mg_L']:.0f} mg/L "
                f"to raise pH from {pH_current:.1f} to {pH_target:.1f}"
            )
        if na2co3_alk:
            rationale.append(
                f"Na2CO3 for alkalinity: {na2co3_alk['na2co3_dose_mg_L']:.0f} mg/L "
                f"to increase from {alkalinity_meq_L:.0f} to {alkalinity_target_meq_L:.0f} meq/L"
            )

        if not rationale:
            rationale.append("No dosing required based on current parameters and objectives")

        return {
            "success": True,
            "message": "Chemical dosing estimates calculated successfully",
            "feedstock_parameters": {
                "sulfide_mg_L": sulfide_mg_L,
                "phosphate_mg_P_L": phosphate_mg_P_L,
                "alkalinity_meq_L": alkalinity_meq_L,
                "pH_current": pH_current
            },
            "treatment_objectives": {
                "sulfide_removal": sulfide_removal,
                "phosphate_removal": phosphate_removal,
                "pH_target": pH_target,
                "alkalinity_target_meq_L": alkalinity_target_meq_L
            },
            "detailed_calculations": {
                "fecl3_for_sulfide": fecl3_sulfide,
                "fecl3_for_phosphate": fecl3_phosphate,
                "naoh_for_ph": naoh_ph,
                "na2co3_for_alkalinity": na2co3_alk
            },
            "summary": summary,
            "rationale": rationale,
            "validation_note": (
                "These are stoichiometric estimates. For dynamic validation, "
                "pass doses to simulate_ad_system_tool with --fecl3-dose, "
                "--naoh-dose, --na2co3-dose flags."
            )
        }

    except Exception as e:
        logger.error(f"Error estimating chemical dosing: {str(e)}", exc_info=True)
        return {
            "success": False,
            "message": f"Failed to estimate chemical dosing: {str(e)}"
        }
