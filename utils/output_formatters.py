#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Output formatting functions for QSDsan mADM1 simulation results.

Converts nested simulation results into clean, parseable JSON files:
1. simulation_performance.json - Performance metrics, yields, stability
2. simulation_inhibition.json - Complete inhibition analysis
3. simulation_precipitation.json - Precipitation rates and mineral data
4. simulation_timeseries.json - Time series data with derived metrics
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def calculate_vfa_alkalinity(stream_data: Dict[str, Any], pH: float) -> Dict[str, float]:
    """
    Calculate VFA totals and alkalinity from stream composition.

    Args:
        stream_data: Stream components dict with S_ac, S_pro, S_bu, S_va, S_IC (mg/L)
        pH: Stream pH

    Returns:
        dict with total_VFA_mg_L, alkalinity_meq_L, VFA_Alk_ratio
    """
    components = stream_data.get('components', {})

    # Calculate total VFA (mg/L)
    vfas = ['S_ac', 'S_pro', 'S_bu', 'S_va']
    total_vfa = sum(components.get(vfa, 0) for vfa in vfas)

    # Calculate alkalinity from S_IC and pH (Henderson-Hasselbalch)
    s_ic_mg_l = components.get('S_IC', 0)  # mg-C/L
    s_ic_kg_m3 = s_ic_mg_l / 1000  # Convert to kg-C/m³

    # Convert to mmol-C/L
    MW_C = 12.01
    ic_mmol_l = s_ic_kg_m3 / MW_C * 1000

    # Carbonate equilibrium
    h_ion = 10**(-pH)
    Ka1 = 10**(-6.35)  # CO2 <-> HCO3-
    Ka2 = 10**(-10.33)  # HCO3- <-> CO3--

    hco3_frac = Ka1 / (Ka1 + h_ion)
    co3_frac = Ka1 * Ka2 / (Ka1 * h_ion + h_ion**2 + Ka1 * Ka2)

    # Alkalinity (meq/L)
    alkalinity = ic_mmol_l * (hco3_frac + 2 * co3_frac)

    # VFA/Alkalinity ratio
    vfa_alk_ratio = total_vfa / alkalinity if alkalinity > 0 else 999999

    return {
        'total_VFA_mg_L': round(total_vfa, 1),
        'alkalinity_meq_L': round(alkalinity, 2),
        'VFA_Alk_ratio': round(vfa_alk_ratio, 1)
    }


def classify_stability(vfa_alk_ratio: float, ph_drop: float) -> str:
    """
    Classify digester stability based on VFA/Alk ratio and pH drop.

    Args:
        vfa_alk_ratio: VFA/Alkalinity ratio (mg-VFA/meq-alk)
        ph_drop: pH drop from influent to effluent

    Returns:
        Status string: HEALTHY | UNSTABLE | FAILURE | CATASTROPHIC_FAILURE
    """
    if vfa_alk_ratio < 300 and ph_drop < 0.5:
        return "HEALTHY"
    elif vfa_alk_ratio < 400 and ph_drop < 1.0:
        return "UNSTABLE"
    elif vfa_alk_ratio < 5000 or ph_drop < 2.0:
        return "FAILURE"
    else:
        return "CATASTROPHIC_FAILURE"


def format_performance_output(
    result: Dict[str, Any],
    inf_vfa_alk: Dict[str, float],
    eff_vfa_alk: Dict[str, float]
) -> Dict[str, Any]:
    """
    Format performance metrics output.

    Args:
        result: Full simulation result dict
        inf_vfa_alk: Influent VFA/alkalinity metrics
        eff_vfa_alk: Effluent VFA/alkalinity metrics

    Returns:
        Formatted performance dict for simulation_performance.json
    """
    inf = result['streams']['influent']
    eff = result['streams']['effluent']
    biogas = result['streams']['biogas']
    yields = result['performance']['yields']

    # Calculate pH drop
    ph_drop = inf['pH'] - eff['pH']

    # Classify stability
    status = classify_stability(eff_vfa_alk['VFA_Alk_ratio'], ph_drop)

    # Calculate alkalinity depletion
    alk_depletion = 0
    if inf_vfa_alk['alkalinity_meq_L'] > 0:
        alk_depletion = (1 - eff_vfa_alk['alkalinity_meq_L'] / inf_vfa_alk['alkalinity_meq_L']) * 100

    # Extract biomass yields by functional group
    detailed_yields = yields.get('detailed', {})
    biomass_by_group = {}

    # Acidogens
    acidogens = {}
    for key in ['X_su', 'X_aa', 'X_fa', 'X_c4', 'X_pro']:
        if key in detailed_yields.get('biomass_yields_kg_d', {}):
            name_map = {
                'X_su': 'X_su_sugar_degraders',
                'X_aa': 'X_aa_amino_acid_degraders',
                'X_fa': 'X_fa_LCFA_degraders',
                'X_c4': 'X_c4_C4_degraders',
                'X_pro': 'X_pro_propionate_degraders'
            }
            acidogens[name_map[key]] = round(detailed_yields['biomass_yields_kg_d'][key], 3)
    if acidogens:
        biomass_by_group['acidogens'] = acidogens

    # Methanogens
    methanogens = {}
    for key in ['X_ac', 'X_h2']:
        if key in detailed_yields.get('biomass_yields_kg_d', {}):
            name_map = {
                'X_ac': 'X_ac_acetoclastic',
                'X_h2': 'X_h2_hydrogenotrophic'
            }
            methanogens[name_map[key]] = round(detailed_yields['biomass_yields_kg_d'][key], 3)
    if methanogens:
        biomass_by_group['methanogens'] = methanogens

    # SRB
    srb = {}
    for key in ['X_hSRB', 'X_aSRB', 'X_pSRB', 'X_c4SRB']:
        if key in detailed_yields.get('biomass_yields_kg_d', {}):
            name_map = {
                'X_hSRB': 'X_hSRB_hydrogen_utilizing',
                'X_aSRB': 'X_aSRB_acetate_utilizing',
                'X_pSRB': 'X_pSRB_propionate_utilizing',
                'X_c4SRB': 'X_c4SRB_C4_utilizing'
            }
            srb[name_map[key]] = round(detailed_yields['biomass_yields_kg_d'][key], 3)
    if srb:
        biomass_by_group['SRB'] = srb

    # PAO
    if 'X_PAO' in detailed_yields.get('biomass_yields_kg_d', {}):
        biomass_by_group['PAO'] = {
            'X_PAO_polyphosphate_accumulators': round(detailed_yields['biomass_yields_kg_d']['X_PAO'], 3)
        }

    return {
        "streams": {
            "influent": {
                "pH": round(inf['pH'], 2),
                "COD_mg_L": round(inf.get('COD', 0), 1),
                "TSS_mg_L": round(inf.get('TSS', 0), 1),
                "VSS_mg_L": round(inf.get('VSS', 0), 1),
                "TKN_mg_N_L": round(inf.get('TKN', 0), 1),
                "TP_mg_P_L": round(inf.get('TP', 0), 1),
                "total_VFA_mg_L": inf_vfa_alk['total_VFA_mg_L'],
                "S_IC_mg_C_L": round(inf.get('components', {}).get('S_IC', 0), 1),
                "alkalinity_meq_L": inf_vfa_alk['alkalinity_meq_L'],
                "flow_m3_d": round(inf.get('flow', 0), 2)
            },
            "effluent": {
                "pH": round(eff['pH'], 2),
                "COD_mg_L": round(eff.get('COD', 0), 1),
                "TSS_mg_L": round(eff.get('TSS', 0), 1),
                "VSS_mg_L": round(eff.get('VSS', 0), 1),
                "TKN_mg_N_L": round(eff.get('TKN', 0), 1),
                "TP_mg_P_L": round(eff.get('TP', 0), 1),
                "total_VFA_mg_L": eff_vfa_alk['total_VFA_mg_L'],
                "S_IC_mg_C_L": round(eff.get('components', {}).get('S_IC', 0), 1),
                "alkalinity_meq_L": eff_vfa_alk['alkalinity_meq_L']
            },
            "biogas": {
                "flow_total_m3_d": round(biogas.get('flow_total', 0), 2),
                "methane_flow_m3_d": round(biogas.get('methane_flow', 0), 2),
                "methane_percent": round(biogas.get('methane_percent', 0), 2),
                "co2_percent": round(biogas.get('co2_percent', 0), 2),
                "h2_percent": round(biogas.get('h2_percent', 0), 2),
                "h2s_percent": round(biogas.get('h2s_percent', 0), 4),
                "h2s_ppm": round(biogas.get('h2s_ppm', 0), 1)
            }
        },
        "yields": {
            "COD_removal_efficiency_percent": round(yields.get('COD_removal_efficiency', 0), 2),
            "VSS_destruction_percent": round(yields.get('VSS_destruction_efficiency', 0), 2),
            "TSS_removal_percent": round(yields.get('TSS_removal_efficiency', 0), 2),

            "methane_yields": {
                "specific_methane_yield_m3_kg_COD_removed": round(yields.get('specific_methane_yield_m3_kg_COD', 0), 4),
                "theoretical_methane_yield_m3_kg_COD": 0.35,  # At STP
                "methane_yield_efficiency_percent": round(yields.get('specific_methane_yield_efficiency_percent', 0), 2),
                "total_methane_production_m3_d": round(biogas.get('methane_flow', 0), 2),
                "total_methane_production_kg_d": round(yields.get('methane_production_kg_d', 0), 3)
            },

            "biomass_yields": {
                "net_VSS_yield_kg_kg_COD_removed": round(yields.get('VSS_yield', 0), 3),
                "net_TSS_yield_kg_kg_COD_removed": round(yields.get('TSS_yield', 0), 3),
                "by_functional_group_kg_d": biomass_by_group,
                "total_biomass_production_kg_d": round(detailed_yields.get('total_biomass_production_kg_d', 0), 3),
                "total_precipitate_formation_kg_d": round(yields.get('total_precipitate_formation_kg_d', 0), 3)
            }
        },
        "stability": {
            "influent_VFA_Alk_ratio": inf_vfa_alk['VFA_Alk_ratio'],
            "effluent_VFA_Alk_ratio": eff_vfa_alk['VFA_Alk_ratio'],
            "VFA_accumulation_mg_L": round(eff_vfa_alk['total_VFA_mg_L'] - inf_vfa_alk['total_VFA_mg_L'], 1),
            "alkalinity_depletion_percent": round(alk_depletion, 1),
            "pH_drop": round(ph_drop, 2),
            "status": status
        },
        "convergence": {
            "converged_at_days": round(result['convergence'].get('converged_at_days', 0), 2),
            "runtime_seconds": round(result['convergence'].get('runtime_seconds', 0), 1),
            "status": result['convergence'].get('status', 'unknown')
        }
    }


def format_inhibition_output(diagnostics: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format complete inhibition analysis output.

    Args:
        diagnostics: Diagnostic data from extract_diagnostics()

    Returns:
        Formatted inhibition dict for simulation_inhibition.json
    """
    if not diagnostics.get('success'):
        return {"error": "Diagnostic data not available", "message": diagnostics.get('message', 'Unknown error')}

    inh = diagnostics.get('inhibition', {})
    pH_inh = inh.get('I_pH', {})
    h2_inh = inh.get('I_h2', {})
    h2s_inh = inh.get('I_h2s', {})
    nutrients = inh.get('I_nutrients', {})

    # Helper to convert factor to percent (0 = no inhibition, 100 = complete)
    def to_percent(factor):
        return round((1.0 - factor) * 100, 2)

    # Calculate overall methanogen health
    ac_health = pH_inh.get('acetoclastic', 1.0) * nutrients.get('I_nh3', 1.0) * h2s_inh.get('acetate', 1.0)
    h2_health = pH_inh.get('hydrogenotrophic', 1.0) * h2s_inh.get('hydrogen', 1.0)
    overall_health = min(ac_health, h2_health)

    # Identify primary limiting factor
    all_factors = {
        'pH_inhibition_acetoclastic': pH_inh.get('acetoclastic', 1.0),
        'pH_inhibition_hydrogenotrophic': pH_inh.get('hydrogenotrophic', 1.0),
        'ammonia_inhibition': nutrients.get('I_nh3', 1.0),
        'nitrogen_limitation': nutrients.get('I_IN_lim', 1.0),
        'h2_inhibition_propionate': h2_inh.get('propionate', 1.0),
        'h2_inhibition_C4': min(h2_inh.get('C4_valerate', 1.0), h2_inh.get('C4_butyrate', 1.0)),
        'h2s_inhibition_acetate': h2s_inh.get('acetate', 1.0),
        'h2s_inhibition_hydrogen': h2s_inh.get('hydrogen', 1.0)
    }
    sorted_factors = sorted(all_factors.items(), key=lambda x: x[1])
    primary_limiting = sorted_factors[0][0]
    secondary_limiting = sorted_factors[1][0] if len(sorted_factors) > 1 else "none"

    return {
        "summary": {
            "acetoclastic_methanogen_health_percent": round(ac_health * 100, 2),
            "hydrogenotrophic_methanogen_health_percent": round(h2_health * 100, 2),
            "overall_methanogen_health_percent": round(overall_health * 100, 2),
            "primary_limiting_factor": primary_limiting,
            "secondary_limiting_factor": secondary_limiting
        },
        "pH_inhibition": {
            "acetoclastic_methanogens": {
                "inhibition_percent": to_percent(pH_inh.get('acetoclastic', 1.0)),
                "inhibition_factor": round(pH_inh.get('acetoclastic', 1.0), 4),
                "pH_lower_limit": 6.5,
                "pH_upper_limit": 7.5,
                "actual_pH": round(diagnostics.get('speciation', {}).get('pH', 7.0), 2)
            },
            "hydrogenotrophic_methanogens": {
                "inhibition_percent": to_percent(pH_inh.get('hydrogenotrophic', 1.0)),
                "inhibition_factor": round(pH_inh.get('hydrogenotrophic', 1.0), 4)
            },
            "acidogens": {
                "inhibition_percent": to_percent(pH_inh.get('acidogens', 1.0)),
                "inhibition_factor": round(pH_inh.get('acidogens', 1.0), 4)
            },
            "SRB_h2": {
                "inhibition_percent": to_percent(pH_inh.get('SRB_h2', 1.0)),
                "inhibition_factor": round(pH_inh.get('SRB_h2', 1.0), 4)
            },
            "SRB_ac": {
                "inhibition_percent": to_percent(pH_inh.get('SRB_ac', 1.0)),
                "inhibition_factor": round(pH_inh.get('SRB_ac', 1.0), 4)
            }
        },
        "ammonia_inhibition": {
            "free_ammonia_inhibition": {
                "inhibition_percent": to_percent(nutrients.get('I_nh3', 1.0)),
                "inhibition_factor": round(nutrients.get('I_nh3', 1.0), 4),
                "KI_mg_N_L": 1800
            },
            "nitrogen_limitation": {
                "limitation_percent": to_percent(nutrients.get('I_IN_lim', 1.0)),
                "limitation_factor": round(nutrients.get('I_IN_lim', 1.0), 4)
            }
        },
        "h2_inhibition": {
            "LCFA_uptake": {
                "inhibition_percent": to_percent(h2_inh.get('LCFA', 1.0)),
                "inhibition_factor": round(h2_inh.get('LCFA', 1.0), 4)
            },
            "C4_valerate": {
                "inhibition_percent": to_percent(h2_inh.get('C4_valerate', 1.0)),
                "inhibition_factor": round(h2_inh.get('C4_valerate', 1.0), 4)
            },
            "C4_butyrate": {
                "inhibition_percent": to_percent(h2_inh.get('C4_butyrate', 1.0)),
                "inhibition_factor": round(h2_inh.get('C4_butyrate', 1.0), 4)
            },
            "propionate": {
                "inhibition_percent": to_percent(h2_inh.get('propionate', 1.0)),
                "inhibition_factor": round(h2_inh.get('propionate', 1.0), 4)
            }
        },
        "h2s_inhibition": {
            "acetate_uptake": {
                "inhibition_percent": to_percent(h2s_inh.get('acetate', 1.0)),
                "inhibition_factor": round(h2s_inh.get('acetate', 1.0), 4)
            },
            "hydrogen_uptake": {
                "inhibition_percent": to_percent(h2s_inh.get('hydrogen', 1.0)),
                "inhibition_factor": round(h2s_inh.get('hydrogen', 1.0), 4)
            },
            "propionate_uptake": {
                "inhibition_percent": to_percent(h2s_inh.get('propionate', 1.0)),
                "inhibition_factor": round(h2s_inh.get('propionate', 1.0), 4)
            },
            "C4_uptake": {
                "inhibition_percent": to_percent(min(h2s_inh.get('C4_valerate', 1.0), h2s_inh.get('C4_butyrate', 1.0))),
                "inhibition_factor": round(min(h2s_inh.get('C4_valerate', 1.0), h2s_inh.get('C4_butyrate', 1.0)), 4)
            }
        },
        "substrate_limitation": {
            "Monod_factors": diagnostics.get('substrate_limitation', {}).get('Monod', [])
        }
    }


def format_precipitation_output(
    diagnostics: Dict[str, Any],
    effluent: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Format precipitation analysis output.

    Args:
        diagnostics: Diagnostic data from extract_diagnostics()
        effluent: Effluent stream data

    Returns:
        Formatted precipitation dict for simulation_precipitation.json
    """
    if not diagnostics.get('success'):
        return {"error": "Diagnostic data not available"}

    # Process rates are in the diagnostics
    process_rates = diagnostics.get('process_rates', [])

    # Mineral names for precipitation processes (indices 50-62 in mADM1 process array)
    # These map to the last 13 processes in the 63-process mADM1 model
    mineral_map = [
        ("struvite_MgNH4PO4", "MgNH4PO4·6H2O"),
        ("HAP_Ca5PO43OH", "Ca5(PO4)3OH"),
        ("calcium_carbonate_CaCO3", "CaCO3"),
        ("amorphous_calcium_carbonate", "ACC"),
        ("amorphous_calcium_phosphate", "ACP"),
        ("dicalcium_phosphate", "DCPD"),
        ("octacalcium_phosphate", "OCP"),
        ("newberyite", "MgHPO4·3H2O"),
        ("magnesite", "MgCO3"),
        ("K_struvite", "KMgPO4·6H2O"),
        ("iron_sulfide_FeS", "FeS"),
        ("iron_phosphate", "Fe3(PO4)2"),
        ("aluminum_phosphate", "AlPO4")
    ]

    # Extract precipitation rates (last 13 processes)
    precip_start_idx = 50
    minerals = {}
    process_rates_dict = {}
    total_precip = 0

    for i, (name, formula) in enumerate(mineral_map):
        idx = precip_start_idx + i
        rate = process_rates[idx] if idx < len(process_rates) else 0.0
        minerals[name] = {
            "rate_kg_d": round(rate, 6),
            "concentration_mg_L": 0.0,  # Precipitates have concentration in effluent (extracted separately)
            "formula": formula
        }
        process_rates_dict[f"precipitation_{name.split('_')[0]}"] = round(rate, 6)
        total_precip += abs(rate)  # Absolute value in case of dissolution

    # Extract ion concentrations
    eff_comp = effluent.get('components', {})
    pH = effluent.get('pH', 7.0)

    # Determine if pH is limiting precipitation
    ph_limiting = pH < 6.5

    return {
        "summary": {
            "total_precipitation_kg_d": round(total_precip, 6),
            "total_phosphorus_precipitated_kg_P_d": 0.0,  # Would need stoichiometric calc
            "total_sulfur_precipitated_kg_S_d": 0.0,
            "precipitation_active": total_precip > 0.001
        },
        "minerals": minerals,
        "process_rates_kg_COD_m3_d": process_rates_dict,
        "effluent_ion_concentrations": {
            "S_IP_mg_P_L": round(eff_comp.get('S_IP', 0), 2),
            "S_Ca_mg_L": round(eff_comp.get('S_Ca', 0), 2),
            "S_Mg_mg_L": round(eff_comp.get('S_Mg', 0), 2),
            "S_Fe2_mg_L": round(eff_comp.get('S_Fe2', 0), 2),
            "S_Al_mg_L": round(eff_comp.get('S_Al', 0), 2),
            "pH": round(pH, 2),
            "S_IC_mg_C_L": round(eff_comp.get('S_IC', 0), 2)
        },
        "conditions_for_precipitation": {
            "pH_requirement": "Most minerals require pH > 6.5",
            "current_pH": round(pH, 2),
            "pH_limiting_precipitation": ph_limiting,
            "solubility_note": "Low pH makes all minerals highly soluble" if ph_limiting else "pH favorable for precipitation"
        }
    }


def format_timeseries_output(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format time series data output.

    Args:
        result: Full simulation result dict

    Returns:
        Formatted timeseries dict for simulation_timeseries.json
    """
    time_series = result.get('time_series', {})

    output = {}

    for hrt_type in ['design', 'check']:
        ts_data = time_series.get(hrt_type)
        if ts_data is None:
            continue

        output[f"{hrt_type}_HRT"] = {
            "time_days": ts_data.get('time_d', []),
            "pH": ts_data.get('pH', []),
            "total_VFA_mg_L": ts_data.get('total_VFA', []),
            "COD_mg_L": ts_data.get('COD', []),
            "TSS_mg_L": ts_data.get('TSS', []),
            "VSS_mg_L": ts_data.get('VSS', []),
            "methane_percent": ts_data.get('methane_percent', []),
            "biogas_flow_m3_d": ts_data.get('biogas_flow', []),
            "S_ac_mg_L": ts_data.get('S_ac', []),
            "S_pro_mg_L": ts_data.get('S_pro', []),
            "S_bu_mg_L": ts_data.get('S_bu', []),
            "S_va_mg_L": ts_data.get('S_va', []),
            "S_IC_mg_C_L": ts_data.get('S_IC', []),
            "biomass_X_ac_mg_L": ts_data.get('X_ac', []),
            "biomass_X_h2_mg_L": ts_data.get('X_h2', [])
        }

    return output
