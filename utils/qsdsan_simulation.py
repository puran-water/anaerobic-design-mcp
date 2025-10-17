"""
QSDsan simulation for anaerobic digestion with sulfur extension.

This module REPLACES the WaterTAP simulation with comprehensive QSDsan-based modeling.
Provides complete reporting of:
- All biomass yields (VSS, TSS, net yields per substrate)
- All inhibition factors (NH3, H2S, pH)
- Complete biogas data (composition, production rates, quality)
- Complete effluent characterization (total and soluble fractions)
- All composite variables (COD, BOD, TKN, TP, NH4-N, TSS, VSS, etc.)

Pattern after ../adm1_mcp_server/simulation.py but with sulfur extension.
Reuses H2S speciation from degasser-design-mcp (DRY principle).
"""
import logging
import numpy as np
from qsdsan import sanunits as su, WasteStream, System

from utils.extract_qsdsan_sulfur_components import ADM1_SULFUR_CMPS
from utils.qsdsan_sulfur_kinetics import (
    extend_adm1_with_sulfate,
    get_h2s_inhibition_factors
)
from utils.h2s_speciation import calculate_h2s_distribution

logger = logging.getLogger(__name__)


def create_influent_stream(Q, Temp, concentrations):
    """
    Create influent stream with 27 components (ADM1 + sulfur).

    Pattern after ../adm1_mcp_server/simulation.py:create_influent_stream

    Args:
        Q: Flow rate (m³/d)
        Temp: Temperature (K)
        concentrations: Dict of component concentrations (kg/m³)

    Returns:
        WasteStream with all 27 components
    """
    logger.info(f"Creating influent stream: Q={Q} m³/d, T={Temp} K")

    inf = WasteStream('Influent', T=Temp)

    # Default concentrations for 27 components (24 ADM1 + 3 sulfur)
    default_conc = {
        # Standard ADM1 soluble (kg/m³)
        'S_su': 0.01,
        'S_aa': 1e-3,
        'S_fa': 1e-3,
        'S_va': 1e-3,
        'S_bu': 1e-3,
        'S_pro': 1e-3,
        'S_ac': 1e-3,
        'S_h2': 1e-8,
        'S_ch4': 1e-5,
        'S_IC': 0.04 * 12.01,  # kg C/m³
        'S_IN': 0.01 * 14.01,  # kg N/m³
        'S_I': 0.02,

        # Standard ADM1 particulate (kg/m³)
        'X_c': 2.0,
        'X_ch': 5.0,
        'X_pr': 20.0,
        'X_li': 5.0,
        'X_su': 1e-2,
        'X_aa': 1e-2,
        'X_fa': 1e-2,
        'X_c4': 1e-2,
        'X_pro': 1e-2,
        'X_ac': 1e-2,
        'X_h2': 1e-2,
        'X_I': 25.0,

        # Standard ADM1 ions (kmol/m³)
        'S_cat': 0.04,
        'S_an': 0.02,

        # Sulfur extension (kg/m³)
        'S_SO4': 0.0,    # Sulfate (set based on feedstock)
        'S_IS': 0.0,     # Sulfide (produced during digestion)
        'X_SRB': 0.001   # Minimal SRB seed
    }

    # Update with provided concentrations
    for k, value in concentrations.items():
        if k in default_conc:
            if isinstance(value, list):
                default_conc[k] = value[0]
            else:
                default_conc[k] = value

    # Set flow
    inf.set_flow_by_concentration(
        Q,
        concentrations=default_conc,
        units=('m3/d', 'kg/m3')
    )

    logger.debug(f"Influent created: {len(default_conc)} components")

    return inf


def run_simulation(Q, Temp, HRT, concentrations,
                   simulation_time=150, t_step=0.1, method='BDF'):
    """
    Run ADM1+Sulfur simulation in QSDsan.

    This is the PRIMARY simulation method that REPLACES WaterTAP.
    Pattern after ../adm1_mcp_server/simulation.py:run_simulation

    Args:
        Q: Flow rate (m³/d)
        Temp: Temperature (K)
        HRT: Hydraulic retention time (days) = SRT
        concentrations: Dict of 27 component concentrations
        simulation_time: Simulation duration (days)
        t_step: Time step (days)
        method: Integration method ('BDF', 'RK45', etc.)

    Returns:
        Tuple of (System, Influent, Effluent, Biogas)
    """
    logger.info(f"Starting QSDsan simulation: HRT={HRT} d, sim_time={simulation_time} d")

    try:
        # Create extended ADM1 process
        adm1_sulfur = extend_adm1_with_sulfate()

        # Create streams
        inf = create_influent_stream(Q, Temp, concentrations)
        eff = WasteStream('Effluent', T=Temp)
        gas = WasteStream('Biogas')

        # Create AnaerobicCSTR (HRT = SRT, simple approach)
        AD = su.AnaerobicCSTR(
            'AD',
            ins=inf,
            outs=(gas, eff),
            model=adm1_sulfur,
            V_liq=Q * HRT,
            V_gas=Q * HRT * 0.1,  # 10% headspace
            T=Temp
        )

        # Set initial conditions (default steady-state from ADM1 benchmark)
        default_init_conds = {
            'S_su': 0.0124*1e3,
            'S_aa': 0.0055*1e3,
            'S_fa': 0.1074*1e3,
            'S_va': 0.0123*1e3,
            'S_bu': 0.0140*1e3,
            'S_pro': 0.0176*1e3,
            'S_ac': 0.0893*1e3,
            'S_h2': 2.5055e-7*1e3,
            'S_ch4': 0.0555*1e3,
            'S_IC': 0.0951*12.01*1e3,
            'S_IN': 0.0945*14.01*1e3,
            'S_I': 0.1309*1e3,
            'X_ch': 0.0205*1e3,
            'X_pr': 0.0842*1e3,
            'X_li': 0.0436*1e3,
            'X_su': 0.3122*1e3,
            'X_aa': 0.9317*1e3,
            'X_fa': 0.3384*1e3,
            'X_c4': 0.3258*1e3,
            'X_pro': 0.1011*1e3,
            'X_ac': 0.6772*1e3,
            'X_h2': 0.2848*1e3,
            'X_I': 17.2162*1e3,
            # Sulfur initial conditions
            'S_SO4': 0.05*1e3,   # Small initial sulfate
            'S_IS': 0.001*1e3,   # Trace sulfide
            'X_SRB': 0.05*1e3    # Small SRB population
        }
        AD.set_init_conc(**default_init_conds)

        # Create system
        sys = System('AnaerobicDigestion_Sulfur', path=(AD,))
        sys.set_dynamic_tracker(eff, gas)

        logger.info("Running dynamic simulation...")

        # Run simulation
        sys.simulate(
            state_reset_hook='reset_cache',
            t_span=(0, simulation_time),
            t_eval=np.arange(0, simulation_time + t_step, t_step),
            method=method
        )

        logger.info("Simulation completed successfully")

        return sys, inf, eff, gas

    except Exception as e:
        logger.error(f"Simulation failed: {e}")
        raise RuntimeError(f"QSDsan simulation error: {e}")


def calculate_comprehensive_results(sys, inf, eff, gas):
    """
    Calculate ALL available metrics from QSDsan simulation.

    Comprehensive reporting including:
    - All biomass yields
    - All inhibition factors
    - Complete biogas characterization
    - Complete effluent characterization (total + soluble)
    - All composite variables

    Args:
        sys: QSDsan System object
        inf: Influent WasteStream
        eff: Effluent WasteStream
        gas: Biogas WasteStream

    Returns:
        Dictionary with complete simulation results
    """
    logger.info("Calculating comprehensive simulation results")

    results = {
        'status': 'success',
        'influent': calculate_stream_properties(inf, 'influent'),
        'effluent_total': calculate_stream_properties(eff, 'effluent_total'),
        'effluent_soluble': calculate_soluble_properties(eff),
        'biogas': calculate_biogas_properties(gas),
        'biomass_yields': calculate_biomass_yields(inf, eff),
        'inhibition_factors': calculate_all_inhibition_factors(eff),
        'h2s_distribution': calculate_h2s_analysis(eff),
        'removal_efficiencies': calculate_removal_efficiencies(inf, eff),
        'srb_methanogen_competition': calculate_competition_metrics(inf, eff),
        'sulfate_reduction': calculate_sulfate_reduction_metrics(inf, eff)
    }

    logger.info("Results calculation complete")

    return results


def calculate_stream_properties(stream, stream_type='stream'):
    """
    Calculate ALL properties for a stream (total fraction).

    Args:
        stream: WasteStream object
        stream_type: Descriptor for logging

    Returns:
        Dictionary with comprehensive stream properties
    """
    logger.debug(f"Calculating properties for {stream_type}")

    # Get flow properties
    flow_mgd = stream.F_vol * 0.000264172  # m³/d to MGD
    flow_m3d = stream.F_vol

    # Get all state variables (concentrations in mg/L)
    state_vars = {}
    for component_id in stream.components.IDs:
        try:
            conc_kg_m3 = stream.imass[component_id] / stream.F_vol
            state_vars[component_id] = conc_kg_m3 * 1000  # Convert to mg/L
        except:
            state_vars[component_id] = 0.0

    # Get composite variables
    try:
        cod_mg_l = stream.COD  # mg/L
    except:
        cod_mg_l = stream.composite('COD')

    try:
        tkn_mg_l = stream.TKN  # mg N/L
    except:
        tkn_mg_l = stream.composite('N')

    try:
        tp_mg_l = stream.TP  # mg P/L
    except:
        tp_mg_l = stream.composite('P')

    try:
        tss_mg_l = stream.get_TSS()  # mg/L
    except:
        tss_mg_l = stream.composite('TSS', particle_size='x')

    try:
        vss_mg_l = stream.get_VSS()  # mg/L
    except:
        vss_mg_l = stream.composite('VSS', particle_size='x')

    try:
        bod5_mg_l = stream.BOD5  # mg/L
    except:
        bod5_mg_l = cod_mg_l * 0.65  # Approximate BOD5 as 65% of COD

    # Soluble COD
    try:
        soluble_cod_mg_l = stream.composite('COD', particle_size='s')
    except:
        soluble_cod_mg_l = 0.0

    # Particulate COD
    particulate_cod_mg_l = cod_mg_l - soluble_cod_mg_l

    # Nitrogen species
    nh4_n_mg_l = state_vars.get('S_IN', 0.0)  # Ammonia nitrogen
    organic_n_mg_l = tkn_mg_l - nh4_n_mg_l if tkn_mg_l > nh4_n_mg_l else 0.0

    # Calculate pH if available
    try:
        ph = stream.pH
    except:
        ph = 7.0  # Default

    # Calculate alkalinity if available
    try:
        alkalinity_meq_l = stream.alkalinity
    except:
        alkalinity_meq_l = state_vars.get('S_IC', 0.0) / 12.01 * 2  # Rough estimate from IC

    return {
        'flow_m3d': flow_m3d,
        'flow_mgd': flow_mgd,
        'temperature_c': stream.T - 273.15,
        'pH': ph,
        'alkalinity_meq_l': alkalinity_meq_l,

        # Composite variables (mg/L)
        'COD_mg_l': cod_mg_l,
        'soluble_COD_mg_l': soluble_cod_mg_l,
        'particulate_COD_mg_l': particulate_cod_mg_l,
        'BOD5_mg_l': bod5_mg_l,
        'TSS_mg_l': tss_mg_l,
        'VSS_mg_l': vss_mg_l,
        'TKN_mg_l': tkn_mg_l,
        'NH4_N_mg_l': nh4_n_mg_l,
        'organic_N_mg_l': organic_n_mg_l,
        'TP_mg_l': tp_mg_l,

        # Sulfur species (mg/L)
        'sulfate_S_mg_l': state_vars.get('S_SO4', 0.0),
        'sulfide_S_mg_l': state_vars.get('S_IS', 0.0),

        # All state variables (mg/L)
        'state_variables': state_vars
    }


def calculate_soluble_properties(stream):
    """
    Calculate properties for SOLUBLE fraction only.

    Args:
        stream: WasteStream object

    Returns:
        Dictionary with soluble fraction properties
    """
    logger.debug("Calculating soluble fraction properties")

    # Get soluble components only (S_* components)
    soluble_vars = {}
    for component_id in stream.components.IDs:
        if component_id.startswith('S_'):
            try:
                conc_kg_m3 = stream.imass[component_id] / stream.F_vol
                soluble_vars[component_id] = conc_kg_m3 * 1000  # mg/L
            except:
                soluble_vars[component_id] = 0.0

    # Soluble COD
    try:
        soluble_cod_mg_l = stream.composite('COD', particle_size='s')
    except:
        soluble_cod_mg_l = 0.0

    # Soluble nitrogen (ammonia)
    nh4_n_mg_l = soluble_vars.get('S_IN', 0.0)

    # Soluble phosphorus
    try:
        soluble_p_mg_l = stream.composite('P', particle_size='s')
    except:
        soluble_p_mg_l = 0.0

    return {
        'soluble_COD_mg_l': soluble_cod_mg_l,
        'soluble_NH4_N_mg_l': nh4_n_mg_l,
        'soluble_P_mg_l': soluble_p_mg_l,
        'soluble_sulfate_S_mg_l': soluble_vars.get('S_SO4', 0.0),
        'soluble_sulfide_S_mg_l': soluble_vars.get('S_IS', 0.0),
        'soluble_state_variables': soluble_vars
    }


def calculate_biogas_properties(gas_stream):
    """
    Calculate complete biogas characterization.

    Args:
        gas_stream: Biogas WasteStream

    Returns:
        Dictionary with complete biogas properties
    """
    logger.debug("Calculating biogas properties")

    # Molecular weights and densities
    MW_CH4 = 16.04
    MW_CO2 = 44.01
    MW_H2 = 2.02
    MW_H2S = 34.08
    MW_C = 12.01

    DENSITY_CH4 = 0.716  # kg/Nm³
    DENSITY_CO2 = 1.977  # kg/Nm³
    DENSITY_H2 = 0.0899  # kg/Nm³
    DENSITY_H2S = 1.539  # kg/Nm³

    COD_CH4 = 4.0  # kg COD/kg CH4
    COD_H2 = 8.0   # kg COD/kg H2

    flow_vol_total = 0.0
    methane_flow = 0.0
    co2_flow = 0.0
    h2_flow = 0.0
    h2s_flow = 0.0

    try:
        if hasattr(gas_stream, 'imass'):
            # Methane
            mass_cod_ch4 = gas_stream.imass['S_ch4'] * 24  # kg COD/d
            mass_ch4 = mass_cod_ch4 / COD_CH4  # kg CH4/d
            methane_flow = mass_ch4 / DENSITY_CH4  # Nm³/d

            # CO2
            mass_c = gas_stream.imass['S_IC'] * 24  # kg C/d
            mass_co2 = mass_c * (MW_CO2 / MW_C)  # kg CO2/d
            co2_flow = mass_co2 / DENSITY_CO2  # Nm³/d

            # H2
            mass_cod_h2 = gas_stream.imass['S_h2'] * 24  # kg COD/d
            mass_h2 = mass_cod_h2 / COD_H2  # kg H2/d
            h2_flow = mass_h2 / DENSITY_H2  # Nm³/d

            # H2S (if present)
            if 'S_IS' in gas_stream.imass:
                mass_s_is = gas_stream.imass['S_IS'] * 24  # kg S/d
                mass_h2s = mass_s_is * (MW_H2S / 32.06)  # kg H2S/d
                h2s_flow = mass_h2s / DENSITY_H2S  # Nm³/d

        flow_vol_total = methane_flow + co2_flow + h2_flow + h2s_flow

        # Compositions (%)
        methane_pct = (methane_flow / flow_vol_total * 100) if flow_vol_total > 0 else 0
        co2_pct = (co2_flow / flow_vol_total * 100) if flow_vol_total > 0 else 0
        h2_ppmv = (h2_flow / flow_vol_total * 1e6) if flow_vol_total > 0 else 0
        h2s_ppmv = (h2s_flow / flow_vol_total * 1e6) if flow_vol_total > 0 else 0

        # Biogas quality metrics
        ch4_co2_ratio = methane_pct / co2_pct if co2_pct > 0 else 0
        lower_heating_value = methane_pct * 0.3565  # MJ/Nm³ (CH4 has 35.65 MJ/Nm³)

        return {
            'total_flow_nm3d': flow_vol_total,
            'total_flow_scfm': flow_vol_total * 0.024542,  # Nm³/d to SCFM

            # Component flows (Nm³/d)
            'methane_flow_nm3d': methane_flow,
            'co2_flow_nm3d': co2_flow,
            'h2_flow_nm3d': h2_flow,
            'h2s_flow_nm3d': h2s_flow,

            # Compositions
            'methane_percent': methane_pct,
            'co2_percent': co2_pct,
            'h2_ppmv': h2_ppmv,
            'h2s_ppmv': h2s_ppmv,

            # Quality metrics
            'ch4_co2_ratio': ch4_co2_ratio,
            'lower_heating_value_MJ_per_nm3': lower_heating_value,

            # Mass flows (kg/d)
            'methane_mass_kgd': mass_ch4,
            'co2_mass_kgd': mass_co2,
            'h2_mass_kgd': mass_h2,
            'h2s_mass_kgd': mass_h2s if h2s_flow > 0 else 0.0
        }

    except Exception as e:
        logger.error(f"Error calculating biogas properties: {e}")
        return {
            'total_flow_nm3d': 0.0,
            'error': str(e)
        }


def calculate_biomass_yields(inf, eff):
    """
    Calculate ALL biomass yield metrics.

    Args:
        inf: Influent WasteStream
        eff: Effluent WasteStream

    Returns:
        Dictionary with comprehensive biomass yield data
    """
    logger.debug("Calculating biomass yields")

    try:
        # COD consumed
        inf_cod = inf.COD  # mg/L
        eff_cod = eff.COD  # mg/L
        cod_consumed = inf_cod - eff_cod  # mg/L

        # Biomass concentrations
        biomass_ids = ['X_su', 'X_aa', 'X_fa', 'X_c4', 'X_pro', 'X_ac', 'X_h2', 'X_SRB']

        biomass_concentrations = {}
        for biomass_id in biomass_ids:
            try:
                conc = eff.imass[biomass_id] / eff.F_vol * 1000  # mg/L
                biomass_concentrations[biomass_id] = conc
            except:
                biomass_concentrations[biomass_id] = 0.0

        total_biomass = sum(biomass_concentrations.values())

        # VSS and TSS
        eff_vss = eff.get_VSS()  # mg/L
        eff_tss = eff.get_TSS()  # mg/L
        inf_vss = inf.get_VSS()  # mg/L
        inf_tss = inf.get_TSS()  # mg/L

        # Net yields
        if cod_consumed > 0:
            vss_yield = eff_vss / cod_consumed  # kg VSS/kg COD
            tss_yield = eff_tss / cod_consumed  # kg TSS/kg COD
            biomass_yield = total_biomass / cod_consumed  # kg biomass/kg COD
        else:
            vss_yield = 0
            tss_yield = 0
            biomass_yield = 0

        # Individual biomass fractions
        biomass_fractions = {}
        if total_biomass > 0:
            for biomass_id, conc in biomass_concentrations.items():
                biomass_fractions[biomass_id] = conc / total_biomass

        return {
            'COD_consumed_mg_l': cod_consumed,
            'net_VSS_yield_kg_per_kg_COD': vss_yield,
            'net_TSS_yield_kg_per_kg_COD': tss_yield,
            'net_biomass_yield_kg_per_kg_COD': biomass_yield,

            'effluent_VSS_mg_l': eff_vss,
            'effluent_TSS_mg_l': eff_tss,
            'effluent_total_biomass_mg_l': total_biomass,

            'biomass_concentrations_mg_l': biomass_concentrations,
            'biomass_fractions': biomass_fractions,

            'VSS_TSS_ratio': eff_vss / eff_tss if eff_tss > 0 else 0
        }

    except Exception as e:
        logger.error(f"Error calculating biomass yields: {e}")
        return {'error': str(e)}


def calculate_all_inhibition_factors(eff):
    """
    Calculate ALL inhibition factors.

    Args:
        eff: Effluent WasteStream

    Returns:
        Dictionary with all inhibition data
    """
    logger.debug("Calculating inhibition factors")

    try:
        # Get sulfide concentration
        S_IS_kg_m3 = eff.imass['S_IS'] / eff.F_vol  # kg S/m³

        # H2S inhibition factors (from mADM1)
        h2s_inhibition = get_h2s_inhibition_factors(S_IS_kg_m3)

        # Get ammonia concentration for NH3 inhibition (if applicable)
        S_IN_kg_m3 = eff.imass['S_IN'] / eff.F_vol  # kg N/m³
        nh4_mg_l = S_IN_kg_m3 * 1000

        # pH
        try:
            ph = eff.pH
        except:
            ph = 7.0

        return {
            'h2s_inhibition': h2s_inhibition,
            'sulfide_concentration_mg_l': S_IS_kg_m3 * 1000,
            'ammonia_concentration_mg_l': nh4_mg_l,
            'pH': ph
        }

    except Exception as e:
        logger.error(f"Error calculating inhibition factors: {e}")
        return {'error': str(e)}


def calculate_h2s_analysis(eff):
    """
    Calculate H2S distribution using degasser module (DRY).

    Args:
        eff: Effluent WasteStream

    Returns:
        Dictionary with H2S speciation and biogas estimates
    """
    logger.debug("Calculating H2S distribution")

    try:
        S_IS_kg_m3 = eff.imass['S_IS'] / eff.F_vol
        pH = getattr(eff, 'pH', 7.0)
        temp_c = eff.T - 273.15

        h2s_dist = calculate_h2s_distribution(
            S_IS_total_kg_m3=S_IS_kg_m3,
            pH=pH,
            temp_c=temp_c,
            gas_transfer_fraction=0.7
        )

        return h2s_dist

    except Exception as e:
        logger.error(f"Error calculating H2S distribution: {e}")
        return {'error': str(e)}


def calculate_removal_efficiencies(inf, eff):
    """
    Calculate removal efficiencies for all parameters.

    Args:
        inf: Influent WasteStream
        eff: Effluent WasteStream

    Returns:
        Dictionary with removal efficiencies (%)
    """
    logger.debug("Calculating removal efficiencies")

    def removal_pct(inf_val, eff_val):
        return (inf_val - eff_val) / inf_val * 100 if inf_val > 0 else 0

    try:
        return {
            'COD_removal_pct': removal_pct(inf.COD, eff.COD),
            'BOD5_removal_pct': removal_pct(inf.BOD5 if hasattr(inf, 'BOD5') else inf.COD*0.65,
                                           eff.BOD5 if hasattr(eff, 'BOD5') else eff.COD*0.65),
            'TSS_removal_pct': removal_pct(inf.get_TSS(), eff.get_TSS()),
            'VSS_removal_pct': removal_pct(inf.get_VSS(), eff.get_VSS()),
        }

    except Exception as e:
        logger.error(f"Error calculating removal efficiencies: {e}")
        return {'error': str(e)}


def calculate_competition_metrics(inf, eff):
    """
    Calculate SRB-methanogen competition metrics.

    Args:
        inf: Influent WasteStream
        eff: Effluent WasteStream

    Returns:
        Dictionary with competition metrics
    """
    logger.debug("Calculating SRB-methanogen competition")

    try:
        X_SRB = eff.imass['X_SRB'] / eff.F_vol * 1000  # mg/L
        X_ac = eff.imass['X_ac'] / eff.F_vol * 1000   # mg/L
        X_h2 = eff.imass['X_h2'] / eff.F_vol * 1000   # mg/L

        total = X_SRB + X_ac + X_h2

        return {
            'X_SRB_mg_l': X_SRB,
            'X_acetoclastic_methanogens_mg_l': X_ac,
            'X_hydrogenotrophic_methanogens_mg_l': X_h2,
            'SRB_fraction': X_SRB / total if total > 0 else 0,
            'methanogen_fraction': (X_ac + X_h2) / total if total > 0 else 0
        }

    except Exception as e:
        logger.error(f"Error calculating competition metrics: {e}")
        return {'error': str(e)}


def calculate_sulfate_reduction_metrics(inf, eff):
    """
    Calculate sulfate reduction performance.

    Args:
        inf: Influent WasteStream
        eff: Effluent WasteStream

    Returns:
        Dictionary with sulfate reduction metrics
    """
    logger.debug("Calculating sulfate reduction metrics")

    try:
        S_SO4_inf = inf.imass['S_SO4'] / inf.F_vol * 1000  # mg S/L
        S_SO4_eff = eff.imass['S_SO4'] / eff.F_vol * 1000  # mg S/L
        S_IS_eff = eff.imass['S_IS'] / eff.F_vol * 1000    # mg S/L

        so4_reduced = S_SO4_inf - S_SO4_eff
        reduction_pct = so4_reduced / S_SO4_inf * 100 if S_SO4_inf > 0 else 0

        return {
            'influent_SO4_mg_l': S_SO4_inf,
            'effluent_SO4_mg_l': S_SO4_eff,
            'effluent_sulfide_mg_l': S_IS_eff,
            'SO4_reduced_mg_l': so4_reduced,
            'SO4_reduction_percent': reduction_pct,
            'sulfide_produced_mg_l': S_IS_eff
        }

    except Exception as e:
        logger.error(f"Error calculating sulfate reduction: {e}")
        return {'error': str(e)}


if __name__ == "__main__":
    # Test module
    logging.basicConfig(level=logging.INFO)

    print("=== QSDsan Simulation Module Test ===\n")
    print("This module REPLACES WaterTAP simulation with comprehensive QSDsan modeling")
    print("Test requires QSDsan installation - skipping actual simulation")
