"""
Output formatters for simulation results.
Generates token-efficient summary files from full simulation results.
"""

def calculate_vfa_alkalinity(stream_data, pH):
    """
    Calculate VFA/Alkalinity ratio from stream data.

    Args:
        stream_data: Dict with stream composition
        pH: Stream pH

    Returns:
        Dict with VFA and alkalinity metrics
    """
    # Extract VFA components (acetate, propionate, butyrate, valerate)
    # Components are nested in 'components' dict
    components = stream_data.get('components', {})
    vfa_mg_l = (
        components.get('S_ac', 0) * 1000 +  # Convert kg/m3 to mg/L
        components.get('S_pro', 0) * 1000 +
        components.get('S_bu', 0) * 1000 +
        components.get('S_va', 0) * 1000
    )

    # Extract alkalinity (already in meq/L from stream data)
    alkalinity_meq_l = stream_data.get('alkalinity', 0)

    # Calculate ratio
    vfa_alk_ratio = vfa_mg_l / alkalinity_meq_l if alkalinity_meq_l > 0 else 0

    return {
        'vfa_mg_l': vfa_mg_l,
        'alkalinity_meq_l': alkalinity_meq_l,
        'vfa_alk_ratio': vfa_alk_ratio,
        'pH': pH
    }


def format_performance_output(result, inf_vfa_alk, eff_vfa_alk):
    """
    Format performance metrics for token-efficient output.

    Args:
        result: Full simulation results dict
        inf_vfa_alk: Influent VFA/alkalinity dict
        eff_vfa_alk: Effluent VFA/alkalinity dict

    Returns:
        Dict with performance metrics
    """
    # Extract from nested structure (streams/performance)
    influent = result.get('streams', {}).get('influent', {})
    effluent = result.get('streams', {}).get('effluent', {})
    biogas = result.get('streams', {}).get('biogas', {})
    yields = result.get('performance', {}).get('yields', {})

    return {
        'influent': {
            'cod_mg_l': influent.get('COD', 0),
            'tss_mg_l': influent.get('TSS', 0),
            'vss_mg_l': influent.get('VSS', 0),
            'pH': influent.get('pH', 0),
            'vfa_mg_l': inf_vfa_alk.get('vfa_mg_l', 0),
            'alkalinity_meq_l': inf_vfa_alk.get('alkalinity_meq_l', 0)
        },
        'effluent': {
            'cod_mg_l': effluent.get('COD', 0),
            'tss_mg_l': effluent.get('TSS', 0),
            'vss_mg_l': effluent.get('VSS', 0),
            'pH': effluent.get('pH', 0),
            'vfa_mg_l': eff_vfa_alk.get('vfa_mg_l', 0),
            'alkalinity_meq_l': eff_vfa_alk.get('alkalinity_meq_l', 0),
            'vfa_alk_ratio': eff_vfa_alk.get('vfa_alk_ratio', 0)
        },
        'biogas': {
            'total_m3_d': biogas.get('flow_total', 0),
            'ch4_percent': biogas.get('methane_percent', 0),
            'co2_percent': biogas.get('co2_percent', 0),
            'h2s_ppm': biogas.get('h2s_ppm', 0)
        },
        'performance': {
            'cod_removal_percent': yields.get('COD_removal_efficiency', 0),  # Already in percent
            'specific_methane_yield_m3_kg_cod': biogas.get('methane_yield_m3_kg_cod', 0),
            'specific_methane_yield_L_kg_cod': biogas.get('methane_yield_m3_kg_cod', 0) * 1000,  # Convert m3 to L
            'net_biomass_yield_kg_vss_kg_cod': yields.get('VSS_yield', 0),
            'net_biomass_yield_kg_tss_kg_cod': yields.get('TSS_yield', 0)
        }
    }


def format_inhibition_output(diagnostics):
    """
    Format inhibition metrics for token-efficient output.

    Args:
        diagnostics: Dict with diagnostic data

    Returns:
        Dict with inhibition metrics
    """
    inhibition = diagnostics.get('inhibition', {})

    return {
        'overall_methanogen_health_percent': 100 - (inhibition.get('total_inhibition_percent', 0) or 0),
        'limiting_factors': inhibition.get('limiting_factors', []),
        'pH_inhibition': {
            'acetoclastic_percent': inhibition.get('pH_inhibition_ac_percent', 0),
            'hydrogenotrophic_percent': inhibition.get('pH_inhibition_h2_percent', 0)
        },
        'ammonia_inhibition': {
            'acetoclastic_percent': inhibition.get('NH3_inhibition_ac_percent', 0),
            'total_ammonia_mg_l': diagnostics.get('effluent', {}).get('TAN', 0) * 1000
        },
        'hydrogen_inhibition': {
            'propionate_percent': inhibition.get('H2_inhibition_pro_percent', 0),
            'lcfa_percent': inhibition.get('H2_inhibition_fa_percent', 0)
        },
        'h2s_inhibition': {
            'acetoclastic_percent': inhibition.get('H2S_inhibition_ac_percent', 0),
            'hydrogenotrophic_percent': inhibition.get('H2S_inhibition_h2_percent', 0),
            'h2s_concentration_mg_l': diagnostics.get('sulfur', {}).get('H2S_dissolved_mg_S_L', 0)
        }
    }


def format_precipitation_output(diagnostics, effluent):
    """
    Format precipitation metrics for token-efficient output.

    Args:
        diagnostics: Dict with diagnostic data
        effluent: Dict with effluent composition

    Returns:
        Dict with precipitation metrics
    """
    precipitation = diagnostics.get('precipitation', {})

    return {
        'total_precipitation_rate_kg_d': precipitation.get('total_rate_kg_d', 0),
        'phosphorus_precipitated_kg_d': precipitation.get('P_precipitated_kg_d', 0),
        'sulfur_precipitated_kg_d': precipitation.get('S_precipitated_kg_d', 0),
        'minerals': {
            'struvite_kg_d': precipitation.get('struvite_kg_d', 0),
            'k_struvite_kg_d': precipitation.get('k_struvite_kg_d', 0),
            'hydroxyapatite_kg_d': precipitation.get('HAP_kg_d', 0),
            'calcite_kg_d': precipitation.get('calcite_kg_d', 0),
            'fes_kg_d': precipitation.get('FeS_kg_d', 0)
        },
        'dissolved_concentrations': {
            'po4_mg_P_l': effluent.get('S_PO4', 0) * 1000 * 0.326,  # kg/m3 to mg-P/L
            'so4_mg_S_l': effluent.get('S_SO4', 0) * 1000,  # kg/m3 to mg-S/L
            'ca_mg_l': effluent.get('S_Ca', 0) * 1000,
            'fe_mg_l': effluent.get('S_Fe', 0) * 1000
        }
    }


def format_timeseries_output(result):
    """
    Format timeseries data for token-efficient output.

    Args:
        result: Full simulation results dict

    Returns:
        Dict with downsampled timeseries (every 2 days)
    """
    timeseries = result.get('timeseries', {})

    # Downsample to every 2 days to reduce file size
    t = timeseries.get('time_days', [])
    if not t:
        return {'time_days': [], 'data': {}}

    # Sample every 2 days (or every 10th point, whichever is less)
    step = min(10, max(1, len(t) // 100))
    sampled_indices = list(range(0, len(t), step))

    sampled_data = {
        'time_days': [t[i] for i in sampled_indices],
        'data': {}
    }

    # Sample key variables
    for key, values in timeseries.items():
        if key != 'time_days' and isinstance(values, list) and len(values) == len(t):
            sampled_data['data'][key] = [values[i] for i in sampled_indices]

    return sampled_data
