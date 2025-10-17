"""
Stream analysis module for ADM1+sulfur simulation.

Native implementation for 30-component ADM1+sulfur system (27 ADM1 + 3 sulfur).
No dependency on parent ADM1 MCP server.

Public API:
- analyze_liquid_stream() - Analyze influent/effluent streams
- analyze_gas_stream() - Analyze biogas with H2S
- analyze_inhibition() - Complete inhibition including H2S effects
- analyze_biomass_yields() - COD removal and biomass production
- calculate_sulfur_metrics() - Comprehensive sulfur analysis with speciation
- calculate_h2s_speciation() - H2S/HS⁻ equilibrium (Henderson-Hasselbalch)
- calculate_h2s_gas_ppm() - H2S concentration in biogas
"""

import logging
from qsdsan.processes._adm1 import non_compet_inhibit
from utils.qsdsan_sulfur_kinetics import H2S_INHIBITION

# Native implementations for ADM1+sulfur model (30 components)
# No dependency on ADM1 MCP server - that uses standard 27-component ADM1
# Our model has 3 additional sulfur components: S_SO4, S_IS, X_SRB

logger = logging.getLogger(__name__)


def safe_get(stream, attr, default=None):
    """Safely get attribute from stream."""
    return getattr(stream, attr, default)


def safe_composite(stream, param, **kwargs):
    """Safely get composite property from QSDsan stream."""
    try:
        if hasattr(stream, 'composite'):
            return stream.composite(param, **kwargs)
        return None
    except:
        return None


def get_component_conc_kg_m3(stream, component_id):
    """
    Get component concentration in kg/m³.

    **Use this function for kinetic calculations** (e.g., inhibition functions).

    Parameters
    ----------
    stream : WasteStream
        QSDsan stream object
    component_id : str
        Component ID (e.g., 'S_IS', 'S_SO4', 'X_SRB')

    Returns
    -------
    float or None
        Concentration in kg/m³, or None if component not found

    Notes
    -----
    ADM1 kinetic functions (like `non_compet_inhibit`) expect kg/m³.
    This function ensures correct units for inhibition calculations.
    """
    try:
        if component_id not in stream.components.IDs:
            return None

        if stream.F_vol > 0:
            # Concentration (kg/m3) = mass flow (kg/d) / volumetric flow (m3/d)
            return stream.imass[component_id] / stream.F_vol
        else:
            return 0.0
    except:
        return None


def get_component_conc_mg_L(stream, component_id):
    """
    Get component concentration in mg/L.

    **Use this function for reporting and display**.

    Parameters
    ----------
    stream : WasteStream
        QSDsan stream object
    component_id : str
        Component ID (e.g., 'S_IS', 'S_SO4', 'X_SRB')

    Returns
    -------
    float or None
        Concentration in mg/L, or None if component not found

    Notes
    -----
    This is the standard reporting unit. For kinetic calculations,
    use `get_component_conc_kg_m3()` instead.
    """
    conc_kg_m3 = get_component_conc_kg_m3(stream, component_id)
    if conc_kg_m3 is not None:
        return conc_kg_m3 * 1000  # Convert kg/m³ to mg/L
    return None


# Legacy function for backward compatibility within this file
def get_component_conc(stream, component_id, units='mg/L'):
    """
    Legacy function - use get_component_conc_mg_L() or get_component_conc_kg_m3() instead.

    This function is deprecated but kept for internal compatibility.
    """
    if units == 'kg/m3':
        return get_component_conc_kg_m3(stream, component_id)
    else:
        return get_component_conc_mg_L(stream, component_id)


def _analyze_liquid_stream_core(stream, include_components=False):
    """
    Core liquid stream analysis (private helper).

    Provides base ADM1 metrics without sulfur roll-up.
    Used internally by analyze_liquid_stream().
    """
    try:
        result = {
            "success": True,
            "flow": stream.F_vol * 24 if hasattr(stream, 'F_vol') else 0,  # m3/d
            "temperature": stream.T if hasattr(stream, 'T') else 308.15,
            "pH": stream.pH if hasattr(stream, 'pH') else 7.0,
            "COD": stream.COD if hasattr(stream, 'COD') else 0,  # mg/L
            "TSS": stream.get_TSS() if hasattr(stream, 'get_TSS') else 0,
            "VSS": stream.get_VSS() if hasattr(stream, 'get_VSS') else 0,
            "TKN": stream.TKN if hasattr(stream, 'TKN') else 0,
            "TP": safe_composite(stream, 'P') if hasattr(stream, 'composite') else 0,
            "alkalinity": stream.SAlk * 50 if hasattr(stream, 'SAlk') else 0  # meq/L to mg/L as CaCO3
        }

        if include_components:
            # Include all 30 components (27 ADM1 + 3 sulfur)
            result["components"] = {}
            for comp_id in stream.components.IDs:
                result["components"][comp_id] = get_component_conc_mg_L(stream, comp_id)

        return result

    except Exception as e:
        logger.error(f"Error analyzing liquid stream: {e}")
        return {"success": False, "message": f"Error: {e}"}


def _analyze_gas_stream_core(stream):
    """
    Core gas stream analysis (private helper).

    Provides base biogas metrics without H2S.
    Used internally by analyze_gas_stream().
    """
    try:
        flow_total = stream.F_vol * 24  # m3/d

        # Get gas component mole fractions
        if stream.F_mol > 0:
            ch4_frac = stream.imol['S_ch4'] / stream.F_mol if 'S_ch4' in stream.components.IDs else 0
            co2_frac = stream.imol['S_IC'] / stream.F_mol if 'S_IC' in stream.components.IDs else 0
            h2_frac = stream.imol['S_h2'] / stream.F_mol if 'S_h2' in stream.components.IDs else 0
        else:
            ch4_frac = co2_frac = h2_frac = 0

        return {
            "success": True,
            "flow_total": flow_total,  # m3/d
            "methane_flow": flow_total * ch4_frac,
            "methane_percent": ch4_frac * 100,
            "co2_flow": flow_total * co2_frac,
            "co2_percent": co2_frac * 100,
            "h2_flow": flow_total * h2_frac,
            "h2_percent": h2_frac * 100
        }
    except Exception as e:
        logger.error(f"Error analyzing gas stream: {e}")
        return {"success": False, "message": f"Error: {e}"}


def analyze_biomass_yields(inf_stream, eff_stream):
    """
    Calculate biomass yields and COD removal for ADM1+sulfur model.

    Native implementation for 30-component system.
    """
    try:
        # COD removal efficiency
        cod_removal = (1 - eff_stream.COD / inf_stream.COD) * 100 if inf_stream.COD > 0 else 0

        # Calculate biomass change (includes SRB biomass)
        inf_vss = inf_stream.get_VSS() if hasattr(inf_stream, 'get_VSS') else 0
        eff_vss = eff_stream.get_VSS() if hasattr(eff_stream, 'get_VSS') else 0
        inf_tss = inf_stream.get_TSS() if hasattr(inf_stream, 'get_TSS') else 0
        eff_tss = eff_stream.get_TSS() if hasattr(eff_stream, 'get_TSS') else 0

        cod_removed = inf_stream.COD - eff_stream.COD

        # Yields (kg biomass / kg COD removed)
        vss_yield = (eff_vss - inf_vss) / cod_removed if cod_removed > 1e-6 else 0
        tss_yield = (eff_tss - inf_tss) / cod_removed if cod_removed > 1e-6 else 0

        return {
            "success": True,
            "VSS_yield": max(0, vss_yield),  # kg VSS/kg COD
            "TSS_yield": max(0, tss_yield),  # kg TSS/kg COD
            "COD_removal_efficiency": cod_removal  # %
        }
    except Exception as e:
        logger.error(f"Error calculating biomass yields: {e}")
        return {"success": False, "message": f"Error: {e}"}


def _analyze_inhibition_core(sim_results):
    """
    Core inhibition analysis (private helper).

    Provides base inhibition framework without H2S metrics.
    Used internally by analyze_inhibition().
    """
    try:
        # Extract streams
        if len(sim_results) >= 4:
            _, inf, eff, gas = sim_results[:4]
        else:
            return {"success": False, "message": "Incomplete simulation results"}

        # Basic inhibition framework
        # Extended by analyze_inhibition_sulfur() to add H2S inhibition

        return {
            "success": True,
            "inhibition_factors": [],  # Will be populated by sulfur extension
            "recommendations": []
        }

    except Exception as e:
        logger.error(f"Error in inhibition analysis: {e}")
        return {"success": False, "message": f"Error: {e}"}

def calculate_h2s_speciation(S_IS_total, pH, temperature_K=308.15, input_units='kg/m3'):
    """
    Calculate H2S/HS⁻ speciation using Henderson-Hasselbalch equation.

    The dissolved sulfide equilibrium:
        H2S ⇌ H+ + HS⁻
        pH = pKa + log([HS⁻]/[H2S])

    Parameters
    ----------
    S_IS_total : float
        Total dissolved sulfide concentration
    pH : float
        pH of the solution
    temperature_K : float, optional
        Temperature in K (default 308.15 = 35°C)
    input_units : str, optional
        Units of S_IS_total: 'kg/m3' (default) or 'mg/L'

    Returns
    -------
    dict
        Dictionary containing:
        - 'H2S_dissolved_kg_m3': H2S concentration in kg S/m³ (for inhibition calcs)
        - 'H2S_dissolved_mg_L': H2S concentration in mg S/L (for reporting)
        - 'HS_dissolved_kg_m3': HS⁻ concentration in kg S/m³
        - 'HS_dissolved_mg_L': HS⁻ concentration in mg S/L
        - 'fraction_H2S': Fraction as H2S (0-1)
        - 'pKa': pKa value used

    Notes
    -----
    - pKa(H2S) ≈ 7.0 at 35°C (typical digester temperature)
    - At pH 7.0: 50% H2S, 50% HS⁻
    - At pH 6.0: 91% H2S (highly inhibitory)
    - At pH 8.0: 91% HS⁻ (less inhibitory)

    **CRITICAL** (per Codex review):
    - H2S inhibition intensity depends strongly on pH through this speciation
    - Must use kg/m³ for inhibition calculations (kinetic functions expect these units)
    - Must report both forms to interpret inhibition correctly
    """
    # Convert to kg/m3 if needed
    if input_units == 'mg/L':
        S_IS_total_kg_m3 = S_IS_total / 1000
    else:
        S_IS_total_kg_m3 = S_IS_total

    # pKa as function of temperature (simplified)
    # pKa ≈ 7.0 at 35°C, varies slightly with T
    pKa_H2S = 7.0  # Could refine with temperature correction

    # Henderson-Hasselbalch: pH = pKa + log([HS⁻]/[H2S])
    # Rearranging: [H2S]/[HS⁻] = 10^(pKa - pH)
    # fraction_H2S = [H2S] / ([H2S] + [HS⁻]) = 1 / (1 + 10^(pH - pKa))

    fraction_H2S = 1.0 / (1.0 + 10**(pH - pKa_H2S))
    fraction_HS = 1.0 - fraction_H2S

    H2S_dissolved_kg_m3 = S_IS_total_kg_m3 * fraction_H2S
    HS_dissolved_kg_m3 = S_IS_total_kg_m3 * fraction_HS

    logger.debug(f"H2S speciation at pH={pH:.2f}: {fraction_H2S*100:.1f}% H2S, {fraction_HS*100:.1f}% HS⁻")
    logger.debug(f"H2S concentration: {H2S_dissolved_kg_m3:.6f} kg S/m³ ({H2S_dissolved_kg_m3*1000:.4f} mg S/L)")

    return {
        'H2S_dissolved_kg_m3': H2S_dissolved_kg_m3,  # For inhibition calculations!
        'H2S_dissolved_mg_L': H2S_dissolved_kg_m3 * 1000,  # For reporting
        'HS_dissolved_kg_m3': HS_dissolved_kg_m3,
        'HS_dissolved_mg_L': HS_dissolved_kg_m3 * 1000,
        'fraction_H2S': fraction_H2S,
        'pKa': pKa_H2S
    }


def calculate_h2s_gas_ppm(gas_stream):
    """
    Calculate H2S concentration in biogas.

    Parameters
    ----------
    gas_stream : WasteStream
        Biogas stream from simulation

    Returns
    -------
    float
        H2S concentration in ppmv (parts per million by volume)

    Notes
    -----
    - H2S in biogas typically 100-10,000 ppm
    - >2000 ppm: Highly corrosive, requires treatment
    - <1000 ppm: Acceptable for some applications
    - H2S partitions to gas phase based on Henry's law
    """
    try:
        # Get S_IS concentration in gas phase
        # In QSDsan/ADM1, S_IS represents dissolved sulfide
        # Gaseous H2S would be tracked separately or via phase equilibrium

        # Check if gas stream has S_IS or H2S component
        if hasattr(gas_stream, 'imass'):
            # Try to get sulfide in gas
            if 'S_IS' in gas_stream.components.IDs:
                # Mass flow rate of H2S (kg/d)
                m_h2s = gas_stream.imass['S_IS'] * 24  # kg/d

                # Total gas flow (m3/d at standard conditions)
                V_gas = gas_stream.F_vol * 24  # m3/d

                if V_gas > 0:
                    # Concentration in mg/m3
                    c_h2s_mg_m3 = (m_h2s * 1e6) / V_gas  # mg/m3

                    # Convert to ppmv using ideal gas law
                    # ppmv = (c_mg_m3 * 24.45) / MW
                    # where 24.45 L/mol at STP, MW = 34 g/mol for H2S
                    MW_H2S = 34.0  # g/mol
                    ppmv = (c_h2s_mg_m3 * 24.45) / MW_H2S

                    return ppmv

        # Fallback: estimate from dissolved sulfide if available
        # Typically H2S in gas is small fraction of total S
        logger.warning("Could not calculate H2S in biogas directly, returning 0")
        return 0.0

    except Exception as e:
        logger.warning(f"Error calculating H2S in biogas: {e}")
        return 0.0


def calculate_sulfur_metrics(inf, eff, gas):
    """
    Comprehensive sulfur analysis with mass balance and speciation.

    Parameters
    ----------
    inf : WasteStream
        Influent stream
    eff : WasteStream
        Effluent stream
    gas : WasteStream
        Biogas stream

    Returns
    -------
    dict
        Flat dictionary with all sulfur metrics at top level:
        - Sulfate: sulfate_in_mg_L, sulfate_out_mg_L, sulfate_removal_pct,
                   sulfate_in_kg_S_d, sulfate_out_kg_S_d
        - Sulfide: sulfide_total_mg_L, sulfide_out_kg_S_d,
                   H2S_dissolved_mg_L, H2S_dissolved_kg_m3, HS_dissolved_mg_L,
                   fraction_H2S, pH
        - Biogas: h2s_biogas_ppm, h2s_biogas_percent, h2s_biogas_kg_S_d
        - SRB: srb_biomass_mg_COD_L, srb_yield_kg_VSS_per_kg_COD
        - Inhibition: inhibition_acetoclastic_pct, inhibition_acetoclastic_factor,
                      inhibition_hydrogenotrophic_pct, inhibition_hydrogenotrophic_factor,
                      KI_h2s_acetoclastic, KI_h2s_hydrogenotrophic
        - speciation: Full speciation dict for reuse by other functions

    Raises
    ------
    ValueError
        If streams are missing required sulfur components (S_SO4, S_IS)
        or have zero flow when mass balance is expected

    Notes
    -----
    **Clean flat structure** - No nested dicts. All keys at top level for easy access.

    This function provides comprehensive sulfur analysis:
    1. Sulfate mass balance (concentrations and flows)
    2. Dissolved sulfide with H2S/HS⁻ speciation
    3. H2S in biogas (ppm, %, mass flow)
    4. SRB biomass and yield
    5. H2S inhibition on methanogens (acetoclastic and hydrogenotrophic)

    **Fail-fast validation**: This function validates inputs strictly for design-grade tools.
    Missing sulfur components indicate the stream is not from an ADM1+sulfur simulation.
    """
    # Fail-fast validation for design-grade tool
    # Check influent has required sulfur components
    if 'S_SO4' not in inf.components.IDs:
        raise ValueError(
            "Influent stream missing S_SO4 component - not a valid ADM1+sulfur stream. "
            "This function requires a 30-component ADM1+sulfur simulation (not 27-component ADM1)."
        )

    # Check effluent has all sulfur components
    if 'S_SO4' not in eff.components.IDs:
        raise ValueError(
            "Effluent stream missing S_SO4 component - not a valid ADM1+sulfur stream. "
            "This function requires a 30-component ADM1+sulfur simulation (not 27-component ADM1)."
        )
    if 'S_IS' not in eff.components.IDs:
        raise ValueError(
            "Effluent stream missing S_IS component - not a valid ADM1+sulfur stream. "
            "This function requires a 30-component ADM1+sulfur simulation (not 27-component ADM1)."
        )

    # Check for zero flows when mass balance is expected
    if inf.F_vol <= 0:
        raise ValueError(
            f"Influent stream has zero or negative flow (F_vol={inf.F_vol}). "
            "Cannot perform sulfur mass balance without flow information."
        )
    if eff.F_vol <= 0:
        raise ValueError(
            f"Effluent stream has zero or negative flow (F_vol={eff.F_vol}). "
            "Cannot perform sulfur mass balance without flow information."
        )
    if gas.F_vol <= 0:
        raise ValueError(
            f"Biogas stream has zero or negative flow (F_vol={gas.F_vol}). "
            "Cannot perform sulfur mass balance without biogas flow information."
        )

    try:
        # Get sulfur component concentrations using explicit unit functions
        S_SO4_in_mg_L = get_component_conc_mg_L(inf, 'S_SO4')
        S_SO4_out_mg_L = get_component_conc_mg_L(eff, 'S_SO4')
        S_IS_total_mg_L = get_component_conc_mg_L(eff, 'S_IS')
        S_IS_total_kg_m3 = get_component_conc_kg_m3(eff, 'S_IS')  # For inhibition!
        X_SRB = get_component_conc_mg_L(eff, 'X_SRB')  # mg COD/L

        pH = getattr(eff, 'pH', 7.0)

        # 1. Mass balance (both concentrations and mass flows)
        sulfate_removal = 0.0
        if S_SO4_in_mg_L and S_SO4_in_mg_L > 1e-6:
            sulfate_removal = (1 - S_SO4_out_mg_L/S_SO4_in_mg_L) * 100

        # Calculate mass flows (kg S/d) from concentrations and flow rates
        Q_inf_m3_d = inf.F_vol * 24  # m3/d
        Q_eff_m3_d = eff.F_vol * 24  # m3/d
        Q_gas_m3_d = gas.F_vol * 24  # m3/d

        # Mass flows: concentration (mg S/L) * flow (m3/d) * (1 kg / 1e6 mg) * (1000 L / m3)
        # Simplifies to: concentration (mg S/L) * flow (m3/d) / 1000 = kg S/d
        sulfate_in_kg_S_d = (S_SO4_in_mg_L * Q_inf_m3_d / 1000) if S_SO4_in_mg_L else 0.0
        sulfate_out_kg_S_d = (S_SO4_out_mg_L * Q_eff_m3_d / 1000) if S_SO4_out_mg_L else 0.0
        sulfide_out_kg_S_d = (S_IS_total_mg_L * Q_eff_m3_d / 1000) if S_IS_total_mg_L else 0.0

        # H2S in biogas: use gas stream S_IS mass flow directly
        # gas.imass['S_IS'] is already in kg/hr, convert to kg/d
        if hasattr(gas, 'imass') and 'S_IS' in gas.components.IDs:
            h2s_biogas_kg_S_d = gas.imass['S_IS'] * 24  # kg/hr to kg/d
        else:
            h2s_biogas_kg_S_d = 0.0

        mass_balance = {
            # Concentrations (for reporting)
            "sulfate_in": S_SO4_in_mg_L if S_SO4_in_mg_L else 0.0,  # mg S/L
            "sulfate_out": S_SO4_out_mg_L if S_SO4_out_mg_L else 0.0,  # mg S/L
            "sulfate_removal_pct": sulfate_removal,  # %

            # Mass flows (for balance calculations)
            "sulfate_in_kg_S_d": sulfate_in_kg_S_d,
            "sulfate_out_kg_S_d": sulfate_out_kg_S_d,
            "sulfide_out_kg_S_d": sulfide_out_kg_S_d,
            "h2s_biogas_kg_S_d": h2s_biogas_kg_S_d
        }

        # 2. Dissolved sulfide with speciation
        # CRITICAL: Pass kg/m3 to speciation (which then returns both units)
        speciation = calculate_h2s_speciation(
            S_IS_total_kg_m3 if S_IS_total_kg_m3 else 0.0,
            pH,
            input_units='kg/m3'
        )

        dissolved_sulfide = {
            "total": S_IS_total_mg_L if S_IS_total_mg_L else 0.0,  # mg S/L for reporting
            "H2S": speciation['H2S_dissolved_mg_L'],  # mg S/L for reporting
            "HS_minus": speciation['HS_dissolved_mg_L'],  # mg S/L for reporting
            "pH": pH,
            "fraction_H2S": speciation['fraction_H2S']
        }

        # 3. Biogas H2S
        h2s_ppm = calculate_h2s_gas_ppm(gas)

        # Calculate H2S concentration in biogas (vol%)
        # H2S ppm / 10000 = vol%
        h2s_percent = h2s_ppm / 10000.0

        biogas_h2s = {
            "h2s_ppm": h2s_ppm,
            "concentration_ppm": h2s_ppm,  # Alias for sulfur_balance.py compatibility
            "concentration_percent": h2s_percent,  # vol%
            "h2s_mg_per_L": speciation['H2S_dissolved_mg_L']  # Use speciation result
        }

        # 4. SRB performance
        srb_performance = {
            "biomass_conc": X_SRB if X_SRB else 0.0,  # mg COD/L
            "yield": calculate_srb_yield(inf, eff)
        }

        # 5. H2S inhibition on methanogens
        # CRITICAL: Use kg/m3 for inhibition calculations!
        H2S_dissolved_kg_m3 = speciation['H2S_dissolved_kg_m3']

        # Get inhibition constants from kinetics module (these are in kg/m3)
        KI_h2s_ac = H2S_INHIBITION['KI_h2s_ac']  # kg S/m3 for acetoclastic
        KI_h2s_h2 = H2S_INHIBITION['KI_h2s_h2']  # kg S/m3 for hydrogenotrophic

        # Calculate inhibition factors (0-1, where 1 = no inhibition)
        # CRITICAL: Both concentrations must be in kg/m3!
        I_ac = non_compet_inhibit(H2S_dissolved_kg_m3, KI_h2s_ac)
        I_h2 = non_compet_inhibit(H2S_dissolved_kg_m3, KI_h2s_h2)

        # Convert to inhibition percentage (0-100, where 0 = no inhibition)
        inhibition_pct_ac = (1 - I_ac) * 100
        inhibition_pct_h2 = (1 - I_h2) * 100

        # Use mg/L for reporting
        H2S_dissolved_mg_L = speciation['H2S_dissolved_mg_L']

        h2s_inhibition = {
            "acetoclastic": {
                "inhibition_pct": inhibition_pct_ac,
                "activity_factor": I_ac,  # 1 = full activity
                "KI": KI_h2s_ac
            },
            "hydrogenotrophic": {
                "inhibition_pct": inhibition_pct_h2,
                "activity_factor": I_h2,
                "KI": KI_h2s_h2
            },
            "H2S_concentration_mg_L": H2S_dissolved_mg_L,  # mg S/L for reporting
            "H2S_concentration_kg_m3": H2S_dissolved_kg_m3  # kg S/m3 (used for inhibition calcs)
        }

        logger.info(f"Sulfur metrics: SO4 removal={sulfate_removal:.1f}%, "
                   f"H2S={H2S_dissolved_mg_L:.4f} mg S/L, "
                   f"Inhibition: ac={inhibition_pct_ac:.1f}%, h2={inhibition_pct_h2:.1f}%")

        # Return flat structure (no nested dicts) - cleaner API
        return {
            "success": True,
            # Sulfate mass balance
            "sulfate_in_mg_L": S_SO4_in_mg_L if S_SO4_in_mg_L else 0.0,
            "sulfate_out_mg_L": S_SO4_out_mg_L if S_SO4_out_mg_L else 0.0,
            "sulfate_removal_pct": sulfate_removal,
            "sulfate_in_kg_S_d": sulfate_in_kg_S_d,
            "sulfate_out_kg_S_d": sulfate_out_kg_S_d,

            # Dissolved sulfide (effluent)
            "sulfide_total_mg_L": S_IS_total_mg_L if S_IS_total_mg_L else 0.0,
            "sulfide_out_kg_S_d": sulfide_out_kg_S_d,
            "H2S_dissolved_mg_L": H2S_dissolved_mg_L,
            "H2S_dissolved_kg_m3": H2S_dissolved_kg_m3,
            "HS_dissolved_mg_L": speciation['HS_dissolved_mg_L'],
            "fraction_H2S": speciation['fraction_H2S'],
            "pH": pH,

            # Biogas H2S
            "h2s_biogas_ppm": h2s_ppm,
            "h2s_biogas_percent": h2s_percent,
            "h2s_biogas_kg_S_d": h2s_biogas_kg_S_d,

            # SRB performance
            "srb_biomass_mg_COD_L": X_SRB if X_SRB else 0.0,
            "srb_yield_kg_VSS_per_kg_COD": calculate_srb_yield(inf, eff),

            # H2S inhibition on methanogens
            "inhibition_acetoclastic_pct": inhibition_pct_ac,
            "inhibition_acetoclastic_factor": I_ac,
            "inhibition_hydrogenotrophic_pct": inhibition_pct_h2,
            "inhibition_hydrogenotrophic_factor": I_h2,
            "KI_h2s_acetoclastic": KI_h2s_ac,
            "KI_h2s_hydrogenotrophic": KI_h2s_h2,

            # Speciation object for reuse
            "speciation": speciation
        }

    except Exception as e:
        logger.error(f"Error calculating sulfur metrics: {e}")
        return {
            "success": False,
            "message": f"Error calculating sulfur metrics: {e}"
        }


def calculate_srb_yield(inf, eff):
    """
    Calculate SRB biomass yield (kg VSS/kg COD removed).

    Parameters
    ----------
    inf : WasteStream
        Influent stream
    eff : WasteStream
        Effluent stream

    Returns
    -------
    float
        SRB yield in kg VSS/kg COD

    Notes
    -----
    SRB yield typically 0.05-0.15 kg VSS/kg COD (lower than aerobic bacteria).
    """
    try:
        # Get SRB biomass change
        X_SRB_in = get_component_conc_mg_L(inf, 'X_SRB')
        X_SRB_out = get_component_conc_mg_L(eff, 'X_SRB')

        if not X_SRB_in:
            X_SRB_in = 0.0
        if not X_SRB_out:
            X_SRB_out = 0.0

        # COD removed
        COD_in = inf.COD
        COD_out = eff.COD
        COD_removed = COD_in - COD_out

        if COD_removed > 1e-6:
            # Assume X_SRB is in COD units, need to convert to VSS
            # Typical VSS/COD ratio for biomass ≈ 0.9
            VSS_COD_ratio = 0.9
            SRB_yield = (X_SRB_out - X_SRB_in) * VSS_COD_ratio / COD_removed
            return max(0.0, SRB_yield)  # Only positive growth

        return 0.0

    except Exception as e:
        logger.warning(f"Error calculating SRB yield: {e}")
        return 0.0


def analyze_liquid_stream(stream, include_components=False):
    """
    Analyze liquid stream for ADM1+sulfur model.

    Native implementation for 30-component system (27 ADM1 + 3 sulfur).

    Parameters
    ----------
    stream : WasteStream
        Liquid stream (influent or effluent)
    include_components : bool, optional
        Include all 30 component concentrations (default False)

    Returns
    -------
    dict
        Complete ADM1+sulfur metrics including:
        - Standard composites (COD, TSS, VSS, TKN, TP, alkalinity)
        - Sulfur section (sulfate, total_sulfide, srb_biomass)
        - All 30 components (if include_components=True)
    """
    # Get base ADM1 analysis
    result = _analyze_liquid_stream_core(stream, include_components=include_components)

    if not result.get('success', False):
        return result

    # Add sulfur metrics
    try:
        S_SO4 = get_component_conc_mg_L(stream, 'S_SO4')
        S_IS = get_component_conc_mg_L(stream, 'S_IS')
        X_SRB = get_component_conc_mg_L(stream, 'X_SRB')

        result['sulfur'] = {
            "sulfate": S_SO4 if S_SO4 else 0.0,  # mg S/L
            "total_sulfide": S_IS if S_IS else 0.0,  # mg S/L
            "srb_biomass": X_SRB if X_SRB else 0.0  # mg COD/L
        }

    except Exception as e:
        logger.warning(f"Could not add sulfur metrics to liquid stream: {e}")
        result['sulfur'] = {
            "sulfate": 0.0,
            "total_sulfide": 0.0,
            "srb_biomass": 0.0
        }

    return result


def analyze_gas_stream(stream):
    """
    Analyze biogas stream for ADM1+sulfur model.

    Native implementation for 30-component system (27 ADM1 + 3 sulfur).

    Parameters
    ----------
    stream : WasteStream
        Biogas stream

    Returns
    -------
    dict
        Complete biogas metrics including:
        - Gas flows (total, CH4, CO2, H2)
        - Gas composition (CH4%, CO2%, H2%)
        - H2S content (ppm)
    """
    # Get base ADM1 gas analysis
    result = _analyze_gas_stream_core(stream)

    if not result.get('success', False):
        return result

    # Add H2S
    try:
        h2s_ppm = calculate_h2s_gas_ppm(stream)
        result['h2s_ppm'] = h2s_ppm

        logger.debug(f"Biogas analysis: CH4={result.get('methane_percent', 0):.1f}%, "
                    f"H2S={h2s_ppm:.1f} ppm")

    except Exception as e:
        logger.warning(f"Could not add H2S to gas stream: {e}")
        result['h2s_ppm'] = 0.0

    return result


def analyze_inhibition(sim_results, speciation=None):
    """
    Analyze inhibition for ADM1+sulfur model.

    Native implementation for 30-component system (27 ADM1 + 3 sulfur).

    Parameters
    ----------
    sim_results : tuple
        (sys, inf, eff, gas, ...) from simulation
    speciation : dict, optional
        Pre-calculated H2S speciation from calculate_sulfur_metrics().
        If provided, avoids recalculation. If None, will calculate.

    Returns
    -------
    dict
        Complete inhibition analysis including:
        - H₂S inhibition (acetoclastic and hydrogenotrophic methanogens)
        - Inhibition factors sorted by severity
        - Recommendations for mitigation

    Notes
    -----
    **Performance optimization**: Pass speciation from calculate_sulfur_metrics()
    to avoid recalculating the Henderson-Hasselbalch equilibrium.
    """
    try:
        # Get base ADM1 inhibition analysis
        inhibition = _analyze_inhibition_core(sim_results)

        if not inhibition.get('success', False):
            return inhibition

        # Extract streams from results
        if len(sim_results) >= 4:
            _, inf, eff, gas = sim_results[:4]
        else:
            logger.warning("Simulation results tuple incomplete for inhibition analysis")
            return inhibition

        # Get pH (needed for recommendations regardless of speciation source)
        pH = getattr(eff, 'pH', 7.0)

        # Use provided speciation or calculate if not provided
        if speciation is None:
            # Calculate speciation
            S_IS_total_kg_m3 = get_component_conc_kg_m3(eff, 'S_IS')
            if not S_IS_total_kg_m3:
                S_IS_total_kg_m3 = 0.0

            speciation = calculate_h2s_speciation(S_IS_total_kg_m3, pH, input_units='kg/m3')

        H2S_dissolved_kg_m3 = speciation['H2S_dissolved_kg_m3']

        # Calculate inhibition factors
        KI_h2s_ac = H2S_INHIBITION['KI_h2s_ac']  # kg S/m3
        KI_h2s_h2 = H2S_INHIBITION['KI_h2s_h2']  # kg S/m3

        # CRITICAL: Both concentrations must be in kg/m3!
        I_ac = non_compet_inhibit(H2S_dissolved_kg_m3, KI_h2s_ac)
        I_h2 = non_compet_inhibit(H2S_dissolved_kg_m3, KI_h2s_h2)

        # Convert to inhibition percentage
        inhibition_pct_ac = (1 - I_ac) * 100
        inhibition_pct_h2 = (1 - I_h2) * 100

        # Add to inhibition factors list
        # Use mg/L for reporting
        H2S_dissolved_mg_L = speciation['H2S_dissolved_mg_L']

        inhibition['inhibition_factors'].extend([
            {
                "type": "H₂S Inhibition (Acetoclastic)",
                "value": inhibition_pct_ac,
                "concentration": H2S_dissolved_mg_L,  # mg S/L for reporting
                "concentration_units": "mg S/L",
                "KI": KI_h2s_ac
            },
            {
                "type": "H₂S Inhibition (Hydrogenotrophic)",
                "value": inhibition_pct_h2,
                "concentration": H2S_dissolved_mg_L,  # mg S/L for reporting
                "concentration_units": "mg S/L",
                "KI": KI_h2s_h2
            }
        ])

        # Re-sort by inhibition value
        inhibition['inhibition_factors'].sort(key=lambda x: x.get("value", 0), reverse=True)

        # Add H2S-specific recommendations if significant inhibition
        if inhibition_pct_ac > 10 or inhibition_pct_h2 > 10:
            h2s_recommendations = [
                f"H₂S Inhibition Detected (Acetoclastic: {inhibition_pct_ac:.1f}%, Hydrogenotrophic: {inhibition_pct_h2:.1f}%)",
                f"H₂S concentration: {H2S_dissolved_mg_L:.4f} mg S/L at pH {pH:.2f}",
                "Consider reducing sulfate loading or enhancing H₂S stripping",
                "Monitor sulfate-to-COD ratio (ideally < 0.5 kg SO4/kg COD)",
                "Consider pH adjustment to shift H₂S/HS⁻ equilibrium (higher pH reduces H₂S)"
            ]

            if 'recommendations' in inhibition:
                inhibition['recommendations'].extend(h2s_recommendations)
            else:
                inhibition['recommendations'] = h2s_recommendations

        logger.info(f"H2S inhibition analysis: ac={inhibition_pct_ac:.1f}%, h2={inhibition_pct_h2:.1f}%")

        return inhibition

    except Exception as e:
        logger.error(f"Error in H2S inhibition analysis: {e}")
        # Return base inhibition if extension fails
        try:
            return _analyze_inhibition_core(sim_results)
        except:
            return {
                "success": False,
                "message": f"Error in inhibition analysis: {e}"
            }
