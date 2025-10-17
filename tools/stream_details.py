"""
Optional analysis tool: Detailed stream composition analysis.

Provides deep dive into stream properties with full component breakdown,
useful for debugging and understanding simulation behavior.
"""

import logging
from typing import Dict, Any, Optional

from core.state import design_state
from utils.stream_analysis_sulfur import (
    analyze_liquid_stream,
    analyze_gas_stream
)

logger = logging.getLogger(__name__)


async def analyze_stream_details(
    stream_type: str = "effluent",
    include_all_components: bool = True
) -> Dict[str, Any]:
    """
    Get detailed composition analysis of a specific stream.

    Requires a simulation to have been run first (uses cached results).

    Parameters
    ----------
    stream_type : str, optional
        Which stream to analyze: "influent", "effluent", or "biogas" (default "effluent")
    include_all_components : bool, optional
        Include all 30 component concentrations (default True)

    Returns
    -------
    dict
        Detailed stream properties including:
        - All component concentrations (if include_all_components=True)
        - Composite parameters (COD, TSS, VSS, TKN, TP, alkalinity)
        - pH and temperature
        - Sulfur species breakdown
        - For biogas: composition, H2S content, energy value

    Examples
    --------
    Get effluent details after simulation:

    >>> result = await analyze_stream_details(stream_type="effluent")
    >>> print(result["composites"]["COD"])
    >>> print(result["sulfur"]["S_SO4_mg_L"])

    Get biogas composition:

    >>> result = await analyze_stream_details(stream_type="biogas")
    >>> print(result["composition"]["methane_percent"])
    >>> print(result["h2s_ppm"])
    """
    try:
        # Check if simulation has been run
        if not design_state.last_simulation:
            return {
                "success": False,
                "message": "No simulation results available. Run simulate_ad_system_tool first."
            }

        sim = design_state.last_simulation

        # Validate stream type
        valid_types = ["influent", "effluent", "biogas"]
        if stream_type not in valid_types:
            return {
                "success": False,
                "message": f"Invalid stream_type '{stream_type}'. Must be one of: {valid_types}"
            }

        # Get the requested stream
        stream_map = {
            "influent": sim["inf"],
            "effluent": sim["eff"],
            "biogas": sim["gas"]
        }

        stream = stream_map[stream_type]

        logger.info(f"Analyzing {stream_type} stream details (include_all_components={include_all_components})")

        # Analyze based on stream type
        if stream_type == "biogas":
            analysis = analyze_gas_stream(stream)

            return {
                "success": True,
                "stream_type": stream_type,
                "composition": {
                    "methane_percent": analysis["methane_percent"],
                    "co2_percent": analysis["co2_percent"],
                    "h2s_ppm": analysis["h2s_ppm"],
                    "h2_percent": analysis.get("h2_percent", 0)
                },
                "flow": {
                    "total_m3_d": analysis["flow_total"],
                    "methane_m3_d": analysis["methane_flow"],
                    "co2_m3_d": analysis["co2_flow"]
                },
                "energy": {
                    "lhv_mj_m3": analysis.get("LHV_MJ_m3", 35.8),  # Standard LHV for CH4
                    "energy_mj_d": analysis["methane_flow"] * 35.8
                },
                "sulfur": {
                    "h2s_ppm": analysis["h2s_ppm"],
                    "h2s_kg_d": analysis.get("h2s_mass_flow", 0)
                }
            }

        else:  # influent or effluent (liquid streams)
            analysis = analyze_liquid_stream(stream, include_components=include_all_components)

            result = {
                "success": True,
                "stream_type": stream_type,
                "basic_properties": {
                    "flow_m3_d": analysis["flow"],
                    "temperature_K": analysis["temperature"],
                    "pH": analysis["pH"]
                },
                "composites": {
                    "COD_mg_L": analysis["COD"],
                    "TSS_mg_L": analysis["TSS"],
                    "VSS_mg_L": analysis["VSS"],
                    "TKN_mg_N_L": analysis["TKN"],
                    "TP_mg_P_L": analysis["TP"],
                    "alkalinity_mg_CaCO3_L": analysis["alkalinity"]
                },
                "sulfur": {
                    "S_SO4_mg_S_L": analysis.get("sulfur", {}).get("sulfate", 0),
                    "S_IS_total_mg_S_L": analysis.get("sulfur", {}).get("total_sulfide", 0),
                    "X_SRB_mg_COD_L": analysis.get("sulfur", {}).get("srb_biomass", 0)
                }
            }

            # Add full component breakdown if requested
            if include_all_components and "components" in analysis:
                result["components"] = analysis["components"]

            return result

    except Exception as e:
        logger.error(f"Error analyzing stream details: {str(e)}", exc_info=True)
        return {
            "success": False,
            "message": f"Analysis failed: {str(e)}"
        }


async def compare_streams(
    stream1: str = "influent",
    stream2: str = "effluent"
) -> Dict[str, Any]:
    """
    Compare two streams side-by-side.

    Useful for understanding treatment performance by comparing influent vs effluent.

    Parameters
    ----------
    stream1 : str, optional
        First stream to compare (default "influent")
    stream2 : str, optional
        Second stream to compare (default "effluent")

    Returns
    -------
    dict
        Side-by-side comparison with removal efficiencies and changes

    Examples
    --------
    Compare influent to effluent:

    >>> result = await compare_streams("influent", "effluent")
    >>> print(result["removal_efficiencies"]["COD_percent"])
    >>> print(result["mass_changes"]["TSS_kg_d"])
    """
    try:
        # Get details for both streams
        details1 = await analyze_stream_details(stream1, include_all_components=False)
        details2 = await analyze_stream_details(stream2, include_all_components=False)

        if not details1["success"] or not details2["success"]:
            return {
                "success": False,
                "message": "Failed to retrieve stream details for comparison"
            }

        # Skip if one is biogas (can't compare liquid to gas)
        if details1["stream_type"] == "biogas" or details2["stream_type"] == "biogas":
            return {
                "success": False,
                "message": "Cannot compare liquid streams with biogas streams"
            }

        # Calculate removal efficiencies
        comp1 = details1["composites"]
        comp2 = details2["composites"]
        flow1 = details1["basic_properties"]["flow_m3_d"]
        flow2 = details2["basic_properties"]["flow_m3_d"]

        removal_efficiencies = {}
        mass_changes = {}

        for param in ["COD", "TSS", "VSS", "TKN", "TP"]:
            key1 = f"{param}_mg_L"
            val1 = comp1[key1]
            val2 = comp2[key1]

            # Removal efficiency (%)
            if val1 > 1e-6:
                removal_efficiencies[f"{param}_percent"] = (1 - val2/val1) * 100
            else:
                removal_efficiencies[f"{param}_percent"] = 0

            # Mass change (kg/d)
            mass1 = val1 * flow1 / 1000  # mg/L * m3/d / 1000 = kg/d
            mass2 = val2 * flow2 / 1000
            mass_changes[f"{param}_kg_d"] = mass2 - mass1

        return {
            "success": True,
            "stream1": stream1,
            "stream2": stream2,
            "removal_efficiencies": removal_efficiencies,
            "mass_changes": mass_changes,
            "stream1_details": details1,
            "stream2_details": details2
        }

    except Exception as e:
        logger.error(f"Error comparing streams: {str(e)}", exc_info=True)
        return {
            "success": False,
            "message": f"Comparison failed: {str(e)}"
        }
