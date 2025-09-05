#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
WaterTAP simulation module using Modified ADM1 and built-in translators.

Supports two configurations based on heuristic sizing:
1. High TSS: AD + Dewatering with centrate recycle
2. Low TSS: AD + MBR + Dewatering with centrate recycle
"""

import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
import pyomo.environ as pyo
from pyomo.network import Arc
from pyomo.core.base.transformation import TransformationFactory

# IDAES imports
from idaes.core import FlowsheetBlock, UnitModelCostingBlock
from idaes.core.util.initialization import propagate_state
from idaes.core.solvers import get_solver
import idaes.core.util.scaling as iscale
from idaes.models.unit_models import Mixer, Separator, Feed
import idaes.logger as idaeslog
from idaes.core.util.model_statistics import degrees_of_freedom

# WaterTAP imports - Using MODIFIED ADM1
from watertap.unit_models.anaerobic_digester import AD
from watertap.property_models.unit_specific.anaerobic_digestion.modified_adm1_properties import (
    ModifiedADM1ParameterBlock
)
from watertap.property_models.unit_specific.anaerobic_digestion.adm1_properties_vapor import (
    ADM1_vaporParameterBlock
)
from watertap.property_models.unit_specific.anaerobic_digestion.modified_adm1_reactions import (
    ModifiedADM1ReactionParameterBlock
)

# ASM2D for dewatering
from watertap.property_models.unit_specific.activated_sludge.modified_asm2d_properties import (
    ModifiedASM2dParameterBlock
)
from watertap.property_models.unit_specific.activated_sludge.modified_asm2d_reactions import (
    ModifiedASM2dReactionParameterBlock
)

# Built-in translators
from watertap.unit_models.translators.translator_adm1_asm2d import (
    Translator_ADM1_ASM2D
)
from watertap.unit_models.translators.translator_asm2d_adm1 import (
    Translator_ASM2d_ADM1  # Note: lowercase 'd' in ASM2d
)

# Dewatering unit
from watertap.unit_models.dewatering import (
    DewateringUnit,
    ActivatedSludgeModelType
)

# MBR - we'll use separator for now, can add MBRZO later
from idaes.models.unit_models.separator import SplittingType

# Costing
from watertap.costing import WaterTAPCosting
from watertap.costing.unit_models.anaerobic_digester import cost_anaerobic_digester
from watertap.costing.unit_models.dewatering import cost_dewatering

logger = logging.getLogger(__name__)

# Local utils
from .state_utils import clean_adm1_state, regularize_adm1_state_for_initialization


def _report_dof_breakdown(m: pyo.ConcreteModel, header: str = "") -> int:
    """Log the overall and per-unit degrees of freedom.

    Returns the overall DOF for convenience.
    """
    try:
        overall = degrees_of_freedom(m)
    except Exception:
        overall = -1
    if header:
        logger.info(f"DOF report ({header}): overall = {overall}")
    else:
        logger.info(f"DOF report: overall = {overall}")

    def unit_dof(name):
        if hasattr(m.fs, name):
            try:
                dof = degrees_of_freedom(getattr(m.fs, name))
                logger.info(f"  - {name:28s} DOF = {dof}")
            except Exception as e:
                logger.debug(f"  - {name}: DOF check failed ({e})")

    # Common blocks
    for blk in (
        "feed", "mixer", "AD", "ad_splitter",
        "translator_AD_ASM", "translator_ASM_AD", "translator_ASM_AD_mbr",
        "translator_dewatering_ASM", "translator_centrate_AD",
        "MBR", "dewatering",
    ):
        unit_dof(blk)

    return overall


def _fix_or_set(obj, val, label: Optional[str] = None):
    """
    Fix a Var or set a (mutable) Param value.

    Uses exception-based dispatch to avoid false positives from hasattr().
    Adds helpful context to errors for faster debugging.
    """
    name = label or (getattr(obj, "name", None) or str(obj))
    try:
        # Prefer Var-like fix when available
        obj.fix(val)
        return
    except AttributeError:
        # Not a Var (or doesn't expose fix): try Param-style set_value
        pass
    except Exception as e:
        # If fix exists but fails for other reasons, surface context
        logger.debug(f"fix() failed for {name} ({type(obj).__name__}): {e}")

    # Try Param set_value path
    try:
        obj.set_value(val)
        return
    except AttributeError:
        raise AttributeError(
            f"Object {name} (type={type(obj).__name__}) does not support fix() or set_value()"
        )
    except Exception as e:
        # Likely attempting to set an immutable Param or bad units
        raise type(e)(f"Failed to set {name} (type={type(obj).__name__}): {e}")


@dataclass
class SimulationConfig:
    """Configuration parameters for simulation."""
    solver: str = "ipopt"
    solver_options: Optional[Dict[str, Any]] = None
    costing_method: str = "WaterTAPCosting"
    
    def __post_init__(self):
        if self.solver_options is None:
            self.solver_options = {
                "nlp_scaling_method": "user-scaling",
                "linear_solver": "ma57",
                "OF_ma57_automatic_scaling": "yes",
                "max_iter": 300,
                "tol": 1e-8,
                "halt_on_ampl_error": "yes"
            }


def build_ad_flowsheet(
    basis_of_design: Dict[str, Any],
    adm1_state: Dict[str, Any],
    heuristic_config: Dict[str, Any],
    config: Optional[SimulationConfig] = None
) -> pyo.ConcreteModel:
    """
    Build conditional AD flowsheet based on heuristic configuration.
    
    Args:
        basis_of_design: Feed flow, COD, temperature, pH
        adm1_state: Modified ADM1 state variables (includes P-species)
        heuristic_config: Sizing results including flowsheet_type
        config: Simulation configuration
    
    Returns:
        Pyomo ConcreteModel with built flowsheet
    """
    if config is None:
        config = SimulationConfig()
    
    # Create model
    m = pyo.ConcreteModel(name="AD_Flowsheet")
    m.fs = FlowsheetBlock(dynamic=False)
    
    # Store configuration for reference
    m.fs.config = config
    
    # Build common components
    _build_common_components(m, basis_of_design, adm1_state, heuristic_config)
    
    # Build flowsheet based on configuration
    flowsheet_type = heuristic_config.get("flowsheet_type", "high_tss")
    
    logger.info(f"Building {flowsheet_type} flowsheet configuration")
    
    if flowsheet_type == "high_tss":
        _build_high_tss_flowsheet(m, basis_of_design, heuristic_config)
    elif flowsheet_type == "low_tss_mbr":
        _build_low_tss_mbr_flowsheet(m, basis_of_design, heuristic_config)
    else:
        raise ValueError(f"Unknown flowsheet type: {flowsheet_type}")
    
    # Apply arc expansion AFTER all arcs are created
    logger.info("Expanding arcs...")
    TransformationFactory("network.expand_arcs").apply_to(m)

    # Report DOF after expansion for visibility when building programmatically
    _report_dof_breakdown(m, header="build()-post-expand")
    
    # Add costing if specified
    if config.costing_method:
        _add_costing(m, config.costing_method)
    
    return m


def _build_common_components(
    m: pyo.ConcreteModel,
    basis_of_design: Dict[str, Any],
    adm1_state: Dict[str, Any],
    heuristic_config: Dict[str, Any]
) -> None:
    """Build components common to both flowsheets."""
    
    # Define MODIFIED ADM1 property packages
    m.fs.props_ADM1 = ModifiedADM1ParameterBlock()
    m.fs.props_vap_ADM1 = ADM1_vaporParameterBlock()
    m.fs.rxn_ADM1 = ModifiedADM1ReactionParameterBlock(
        property_package=m.fs.props_ADM1
    )
    
    # Define ASM2D property packages for downstream
    m.fs.props_ASM2D = ModifiedASM2dParameterBlock()
    m.fs.rxn_ASM2D = ModifiedASM2dReactionParameterBlock(
        property_package=m.fs.props_ASM2D
    )
    
    # Create Feed unit for fresh feed
    m.fs.feed = Feed(property_package=m.fs.props_ADM1)
    
    # Helper available at module scope: _fix_or_set
    
    # Set feed conditions from basis of design (use units explicitly)
    flow_m3_per_s = basis_of_design["feed_flow_m3d"] / (24 * 3600)
    _fix_or_set(
        m.fs.feed.properties[0].flow_vol,
        flow_m3_per_s * pyo.units.m**3 / pyo.units.s,
        label="feed.flow_vol",
    )
    
    # Temperature and pressure
    temp_k = heuristic_config.get("operating_conditions", {}).get(
        "temperature_k", 308.15  # Default 35°C
    )
    pressure_pa = heuristic_config.get("operating_conditions", {}).get(
        "pressure_atm", 1.0
    ) * 101325
    
    _fix_or_set(m.fs.feed.properties[0].temperature, temp_k * pyo.units.K, label="feed.temperature")
    _fix_or_set(m.fs.feed.properties[0].pressure, pressure_pa * pyo.units.Pa, label="feed.pressure")
    
    # Set scaling factors for feed properties to prevent IDAES warnings
    # These scaling factors help with numerical stability and prevent "Missing scaling factor" warnings
    iscale.set_scaling_factor(m.fs.feed.properties[0].flow_vol, max(1.0, 1.0/flow_m3_per_s))
    iscale.set_scaling_factor(m.fs.feed.properties[0].temperature, 0.01)  # ~1/100 for temperatures around 300K
    iscale.set_scaling_factor(m.fs.feed.properties[0].pressure, 1e-5)  # ~1/100000 for pressures around 100kPa
    
    # Normalize ADM1 state values to native floats (handles [value, unit, explanation])
    clean_state, state_warnings = clean_adm1_state(adm1_state)
    
    # Additional scaling for ions (kmol/m³ typically 0.01-0.05)
    if hasattr(m.fs.feed.properties[0], 'cations'):
        iscale.set_scaling_factor(m.fs.feed.properties[0].cations, 100)
    if hasattr(m.fs.feed.properties[0], 'anions'):
        iscale.set_scaling_factor(m.fs.feed.properties[0].anions, 100)
    
    # Scale high VFA concentrations (can be 5-10 kg/m³)
    for vfa in ['S_ac', 'S_pro', 'S_bu', 'S_va']:
        if vfa in m.fs.feed.properties[0].conc_mass_comp and vfa in clean_state:
            vfa_value = clean_state.get(vfa, 1.0)
            if vfa_value > 0.1:  # Only scale if significant
                iscale.set_scaling_factor(
                    m.fs.feed.properties[0].conc_mass_comp[vfa],
                    1.0/max(1.0, vfa_value)
                )
    if state_warnings:
        for w in state_warnings:
            logger.warning(w)

    # Build a safe initialization state consistent with alkalinity/pH if provided
    bod_alk = None
    bod_ph = 7.0
    try:
        bod = basis_of_design or {}
        if isinstance(bod.get("alkalinity_meq_l"), (int, float)):
            bod_alk = float(bod.get("alkalinity_meq_l"))
        if isinstance(bod.get("ph"), (int, float)):
            bod_ph = float(bod.get("ph"))
    except Exception:
        pass

    init_state, init_warnings = regularize_adm1_state_for_initialization(
        clean_state, target_alkalinity_meq_l=bod_alk, ph=bod_ph
    )
    if init_warnings:
        for w in init_warnings:
            logger.warning(f"Init-state adjust: {w}")

    # Save both states and config on the flowsheet for later re-application after init
    m.fs._final_adm1_state = clean_state
    m.fs._init_adm1_state = init_state
    m.fs._heuristic_config = heuristic_config  # Store for access during ramping

    # Set Modified ADM1 state variables in feed for initialization state
    for comp, value in init_state.items():
        if comp == "S_cat":
            # S_cat corresponds to the cations state variable (kmol/m^3)
            _fix_or_set(
                m.fs.feed.properties[0].cations,
                value * pyo.units.kmol / pyo.units.m**3,
                label="feed.cations",
            )
        elif comp == "S_an":
            # S_an corresponds to the anions state variable (kmol/m^3)
            _fix_or_set(
                m.fs.feed.properties[0].anions,
                value * pyo.units.kmol / pyo.units.m**3,
                label="feed.anions",
            )
        elif comp in m.fs.props_ADM1.component_list and comp != "H2O":
            # All other components are mass concentrations (kg/m^3)
            if comp in m.fs.feed.properties[0].conc_mass_comp:
                _fix_or_set(
                    m.fs.feed.properties[0].conc_mass_comp[comp],
                    value * pyo.units.kg / pyo.units.m**3,
                    label=f"feed.conc_mass_comp[{comp}]",
                )
    
    # Add default values for P-species if not provided
    # IMPORTANT: All P-species use kg/m³ units (NOT kmol/m³) in Modified ADM1
    # This is consistent with conc_mass_comp property in WaterTAP
    p_species = {
        "X_PAO": 0.01,   # kg/m³ - Phosphorus accumulating organisms
        "X_PHA": 0.001,  # kg/m³ - Polyhydroxyalkanoates  
        "X_PP": 0.06,    # kg/m³ - Polyphosphates (typical P-fraction * COD)
        "S_IP": 0.005,   # kg/m³ - Inorganic phosphorus (NOT kmol/m³)
        "S_K": 0.01,     # kg/m³ - Potassium (NOT kmol/m³)
        "S_Mg": 0.005    # kg/m³ - Magnesium (NOT kmol/m³)
    }
    
    for comp, default_value in p_species.items():
        # Use clean_state membership so we also backfill if provided value was non-numeric
        if comp not in clean_state and comp in m.fs.props_ADM1.component_list:
            _fix_or_set(
                m.fs.feed.properties[0].conc_mass_comp[comp],
                default_value * pyo.units.kg / pyo.units.m**3,
                label=f"feed.conc_mass_comp[{comp}]",
            )
    
    # Set cations and anions defaults if not provided (kmol/m^3)
    if "S_cat" not in init_state:
        _fix_or_set(
            m.fs.feed.properties[0].cations,
            0.04 * pyo.units.kmol / pyo.units.m**3,
            label="feed.cations",
        )
    if "S_an" not in init_state:
        # Maintain electroneutrality by default
        _fix_or_set(
            m.fs.feed.properties[0].anions,
            0.04 * pyo.units.kmol / pyo.units.m**3,
            label="feed.anions",
        )

    # Final safety net: ensure every ADM1 component (except H2O) has a fixed feed value
    # This avoids residual DOF from uninitialized trace species in the property package
    try:
        for comp in list(m.fs.props_ADM1.component_list):
            cname = str(comp)
            if cname == "H2O":
                continue
            # Only set if not already fixed by earlier steps
            v = m.fs.feed.properties[0].conc_mass_comp[cname]
            if (not v.fixed) and (v.value is None or not pyo.value(v) or pyo.value(v) < 0):
                _fix_or_set(
                    v,
                    1e-9 * pyo.units.kg / pyo.units.m**3,
                    label=f"feed.conc_mass_comp[{cname}]",
                )
    except Exception as e:
        logger.debug(f"Feed backfill for missing ADM1 components skipped: {e}")
    
    # Create AD unit
    m.fs.AD = AD(
        liquid_property_package=m.fs.props_ADM1,
        vapor_property_package=m.fs.props_vap_ADM1,
        reaction_package=m.fs.rxn_ADM1,
        has_heat_transfer=True,
        has_pressure_change=False,
        dynamic=False
    )
    
    # Set reactor volumes from heuristics
    digester_config = heuristic_config.get("digester", {})
    liquid_vol = digester_config.get("liquid_volume_m3", 3400)
    vapor_vol = digester_config.get("vapor_volume_m3", liquid_vol * 0.1)
    
    _fix_or_set(m.fs.AD.volume_liquid, liquid_vol * pyo.units.m**3, label="AD.volume_liquid")
    _fix_or_set(m.fs.AD.volume_vapor, vapor_vol * pyo.units.m**3, label="AD.volume_vapor")
    
    # Fix liquid outlet temperature (assume isothermal)
    _fix_or_set(m.fs.AD.liquid_outlet.temperature, temp_k * pyo.units.K, label="AD.liquid_outlet.temperature")


def _build_high_tss_flowsheet(
    m: pyo.ConcreteModel,
    basis_of_design: Dict[str, Any],
    heuristic_config: Dict[str, Any]
) -> None:
    """
    Build high TSS flowsheet: AD -> Translator -> Dewatering -> Recycle.
    Uses Modified ADM1 -> ASM2D translation.
    """
    logger.info("Building high TSS configuration with ASM2D dewatering")
    
    # Add translator from Modified ADM1 to ASM2D
    m.fs.translator_AD_ASM = Translator_ADM1_ASM2D(
        inlet_property_package=m.fs.props_ADM1,
        inlet_reaction_package=m.fs.rxn_ADM1,
        outlet_property_package=m.fs.props_ASM2D,
        outlet_reaction_package=m.fs.rxn_ASM2D,
        has_phase_equilibrium=False,
        outlet_state_defined=True
    )
    
    # Connect AD to translator
    m.fs.arc_AD_translator = Arc(
        source=m.fs.AD.liquid_outlet,
        destination=m.fs.translator_AD_ASM.inlet
    )
    
    # Add dewatering unit (ASM2D properties)
    m.fs.dewatering = DewateringUnit(
        property_package=m.fs.props_ASM2D,
        activated_sludge_model=ActivatedSludgeModelType.modified_ASM2D
    )
    
    # Connect translator to dewatering
    m.fs.arc_translator_dewatering = Arc(
        source=m.fs.translator_AD_ASM.outlet,
        destination=m.fs.dewatering.inlet
    )
    
    # Configure dewatering from heuristics
    dewatering_config = heuristic_config.get("dewatering", {})

    # Helper: compute p_dewat from solids capture, inlet TSS, and target cake solids
    def _estimate_tss_inlet_kg_m3_high_tss(hcfg: Dict[str, Any]) -> float:
        try:
            # Prefer sizing-basis steady-state TSS if available (mg/L)
            tss_mg_l = float(hcfg.get("sizing_basis", {}).get("steady_state_tss_mg_l"))
            return max(1e-6, tss_mg_l / 1000.0)
        except Exception:
            return 15.0  # fallback (kg/m³)

    def _compute_p_dewat_from_mass_balance(tss_in_kg_m3: float, capture_fr: float, cake_solids_frac: float) -> float:
        # Mass balance: Q_u/Q_in = (capture*TSS_in) / TSS_cake, where TSS_cake = cake_frac * rho
        rho_sludge = 1000.0  # kg/m³, assume near water density
        tss_cake = max(1e-6, cake_solids_frac * rho_sludge)
        p = (max(0.0, capture_fr) * max(1e-9, tss_in_kg_m3)) / tss_cake
        # Clamp to reasonable bounds to avoid infeasible soluble splits
        return float(min(max(p, 0.005), 0.9))

    # TSS removal (solids capture)
    capture_fraction = (
        dewatering_config.get("solids_capture_fraction")
        if dewatering_config.get("solids_capture_fraction") is not None
        else dewatering_config.get("capture_fraction", 0.95)
    )
    _fix_or_set(m.fs.dewatering.TSS_rem, capture_fraction, label="dewatering.TSS_rem")

    # Target cake solids (mass fraction, e.g., 0.22 for 22% TS)
    cake_solids = dewatering_config.get("cake_solids_fraction", 0.22)

    # Estimate inlet TSS to dewatering from sizing basis
    tss_in_kg_m3 = _estimate_tss_inlet_kg_m3_high_tss(heuristic_config)
    p_dewat_guess = _compute_p_dewat_from_mass_balance(tss_in_kg_m3, capture_fraction, cake_solids)
    _fix_or_set(m.fs.dewatering.p_dewat, p_dewat_guess, label="dewatering.p_dewat")
    
    # Fix dewatering hydraulics (either HRT or volume); default HRT = 1800 s
    hrt_s = dewatering_config.get("hydraulic_retention_time_s", 1800)
    try:
        _fix_or_set(m.fs.dewatering.hydraulic_retention_time[0], hrt_s * pyo.units.s, label="dewatering.hydraulic_retention_time")
    except Exception:
        # If not time-indexed, fall back to scalar var
        _fix_or_set(m.fs.dewatering.hydraulic_retention_time, hrt_s * pyo.units.s, label="dewatering.hydraulic_retention_time")
    
    # Add translator from ASM2D back to Modified ADM1 for centrate
    m.fs.translator_ASM_AD = Translator_ASM2d_ADM1(
        inlet_property_package=m.fs.props_ASM2D,
        inlet_reaction_package=m.fs.rxn_ASM2D,
        outlet_property_package=m.fs.props_ADM1,
        outlet_reaction_package=m.fs.rxn_ADM1,
        has_phase_equilibrium=False,
        outlet_state_defined=True,
        bio_P=True
    )
    
    # Connect dewatering overflow (centrate) to translator
    m.fs.arc_dewatering_translator = Arc(
        source=m.fs.dewatering.overflow,
        destination=m.fs.translator_ASM_AD.inlet
    )
    
    # Add mixer for feed and centrate recycle
    m.fs.mixer = Mixer(
        property_package=m.fs.props_ADM1,
        inlet_list=["fresh_feed", "centrate_recycle"]
    )
    
    # Connect feed to mixer
    m.fs.arc_feed_mixer = Arc(
        source=m.fs.feed.outlet,
        destination=m.fs.mixer.fresh_feed
    )
    
    # Connect centrate recycle to mixer
    m.fs.arc_centrate_mixer = Arc(
        source=m.fs.translator_ASM_AD.outlet,
        destination=m.fs.mixer.centrate_recycle
    )
    
    # Connect mixer to AD
    m.fs.arc_mixer_AD = Arc(
        source=m.fs.mixer.outlet,
        destination=m.fs.AD.inlet
    )


def _build_low_tss_mbr_flowsheet(
    m: pyo.ConcreteModel,
    basis_of_design: Dict[str, Any],
    heuristic_config: Dict[str, Any]
) -> None:
    """
    Build low TSS MBR flowsheet: AD -> parallel branches (MBR and Dewatering) -> Recycle.
    
    Key design:
    - AD outlet splits to MBR (5Q operation) and dewatering (waste sludge)
    - MBR retentate and dewatering centrate both recycle to AD
    - MBR permeate is treated effluent
    - Dewatering cake is waste solids
    """
    logger.info("Building low TSS MBR configuration with parallel dewatering")
    
    # Split AD outlet for MBR and dewatering (parallel configuration)
    m.fs.ad_splitter = Separator(
        property_package=m.fs.props_ADM1,
        outlet_list=["to_mbr", "to_dewatering"],
        split_basis=SplittingType.componentFlow
    )
    
    # Connect AD to splitter
    m.fs.arc_AD_splitter = Arc(
        source=m.fs.AD.liquid_outlet,
        destination=m.fs.ad_splitter.inlet
    )
    
    # Calculate split fractions (dewatering pulls waste sludge directly from AD)
    # Fix: Access nested dewatering config properly
    daily_waste_m3d = heuristic_config.get("dewatering", {}).get("daily_waste_sludge_m3d", 20.0)
    feed_flow_m3d = basis_of_design["feed_flow_m3d"]
    total_ad_flow_m3d = 5 * feed_flow_m3d  # Total flow from AD (including recycles)
    dewatering_fraction = daily_waste_m3d / total_ad_flow_m3d
    
    # Set split fractions
    # Important: For componentFlow splitters, fix only ONE outlet fraction per component.
    # The remaining outlet(s) are determined by the internal sum-to-one constraint.
    for comp in m.fs.props_ADM1.component_list:
        _fix_or_set(
            m.fs.ad_splitter.split_fraction[0, "to_dewatering", comp],
            dewatering_fraction,
            label=f"ad_splitter.split_fraction[0,to_dewatering,{comp}]",
        )
    
    # Translator to ASM2D for MBR
    m.fs.translator_AD_ASM = Translator_ADM1_ASM2D(
        inlet_property_package=m.fs.props_ADM1,
        inlet_reaction_package=m.fs.rxn_ADM1,
        outlet_property_package=m.fs.props_ASM2D,
        outlet_reaction_package=m.fs.rxn_ASM2D,
        has_phase_equilibrium=False,
        outlet_state_defined=True
    )
    
    # Connect splitter to translator
    m.fs.arc_splitter_translator = Arc(
        source=m.fs.ad_splitter.to_mbr,
        destination=m.fs.translator_AD_ASM.inlet
    )
    
    # MBR as ASM2D separator (simplified)
    m.fs.MBR = Separator(
        property_package=m.fs.props_ASM2D,
        outlet_list=["permeate", "retentate"],
        split_basis=SplittingType.componentFlow
    )
    
    # Connect translator to MBR
    m.fs.arc_translator_MBR = Arc(
        source=m.fs.translator_AD_ASM.outlet,
        destination=m.fs.MBR.inlet
    )
    
    # Configure MBR splits (5Q operation: 20% to permeate)
    # Data-driven approach using property package component classification
    
    # Get component sets from ASM2D property package
    # Note: ASM2D typically classifies components by their first letter:
    # X_* = particulates (should be retained by membrane)
    # S_* = solubles (partially pass through membrane)
    
    for comp in m.fs.props_ASM2D.component_list:
        comp_name = str(comp)
        
        if comp_name.startswith('X_'):
            # Particulate components - near-complete retention by MBR membrane
            _fix_or_set(
                m.fs.MBR.split_fraction[0, "permeate", comp],
                0.001,
                label=f"MBR.split_fraction[0,permeate,{comp}]",
            )  # 0.1% to permeate
            # Do not fix retentate fraction; let sum-to-one constraint determine it
        elif comp_name.startswith('S_'):
            # Soluble components - partially pass through membrane (5Q operation = 20% recovery)
            _fix_or_set(
                m.fs.MBR.split_fraction[0, "permeate", comp],
                0.2,
                label=f"MBR.split_fraction[0,permeate,{comp}]",
            )  # 20% to permeate
            # Do not fix retentate fraction; let sum-to-one constraint determine it
        else:
            # Default for any other components (shouldn't happen in ASM2D)
            logger.warning(f"Unexpected component {comp_name} in ASM2D, using soluble splits")
            _fix_or_set(
                m.fs.MBR.split_fraction[0, "permeate", comp],
                0.2,
                label=f"MBR.split_fraction[0,permeate,{comp}]",
            )
            # Do not fix retentate fraction; let sum-to-one constraint determine it
    
    # Translator for MBR retentate back to ADM1
    m.fs.translator_ASM_AD_mbr = Translator_ASM2d_ADM1(
        inlet_property_package=m.fs.props_ASM2D,
        inlet_reaction_package=m.fs.rxn_ASM2D,
        outlet_property_package=m.fs.props_ADM1,
        outlet_reaction_package=m.fs.rxn_ADM1,
        has_phase_equilibrium=False,
        outlet_state_defined=True,
        bio_P=True
    )
    
    # Connect MBR retentate to translator
    m.fs.arc_MBR_translator = Arc(
        source=m.fs.MBR.retentate,
        destination=m.fs.translator_ASM_AD_mbr.inlet
    )
    
    # Translator for dewatering stream to ASM2D
    m.fs.translator_dewatering_ASM = Translator_ADM1_ASM2D(
        inlet_property_package=m.fs.props_ADM1,
        inlet_reaction_package=m.fs.rxn_ADM1,
        outlet_property_package=m.fs.props_ASM2D,
        outlet_reaction_package=m.fs.rxn_ASM2D,
        has_phase_equilibrium=False,
        outlet_state_defined=True
    )
    
    # Connect AD splitter dewatering outlet to translator
    m.fs.arc_dewatering_translator = Arc(
        source=m.fs.ad_splitter.to_dewatering,
        destination=m.fs.translator_dewatering_ASM.inlet
    )
    
    # Dewatering unit (pulling directly from AD via splitter)
    m.fs.dewatering = DewateringUnit(
        property_package=m.fs.props_ASM2D,
        activated_sludge_model=ActivatedSludgeModelType.modified_ASM2D
    )
    
    # Connect translator to dewatering
    m.fs.arc_translator_dewatering = Arc(
        source=m.fs.translator_dewatering_ASM.outlet,
        destination=m.fs.dewatering.inlet
    )
    
    # Configure dewatering
    dewatering_config = heuristic_config.get("dewatering", {})
    capture_fraction = (
        dewatering_config.get("solids_capture_fraction")
        if dewatering_config.get("solids_capture_fraction") is not None
        else dewatering_config.get("capture_fraction", 0.95)
    )
    _fix_or_set(m.fs.dewatering.TSS_rem, capture_fraction, label="dewatering.TSS_rem")

    # For MBR branch, use digester MLSS as dewatering inlet concentration
    def _estimate_tss_inlet_kg_m3_low_tss(hcfg: Dict[str, Any]) -> float:
        try:
            tss_mg_l = float(hcfg.get("digester", {}).get("mlss_mg_l"))
            return max(1e-6, tss_mg_l / 1000.0)
        except Exception:
            return 15.0

    cake_solids = dewatering_config.get("cake_solids_fraction", 0.22)
    tss_in_kg_m3 = _estimate_tss_inlet_kg_m3_low_tss(heuristic_config)
    p_dewat_guess = _compute_p_dewat_from_mass_balance(tss_in_kg_m3, capture_fraction, cake_solids)
    _fix_or_set(m.fs.dewatering.p_dewat, p_dewat_guess, label="dewatering.p_dewat")
    # Fix dewatering hydraulics (either HRT or volume); default HRT = 1800 s
    hrt_s = dewatering_config.get("hydraulic_retention_time_s", 1800)
    try:
        _fix_or_set(m.fs.dewatering.hydraulic_retention_time[0], hrt_s * pyo.units.s, label="dewatering.hydraulic_retention_time")
    except Exception:
        _fix_or_set(m.fs.dewatering.hydraulic_retention_time, hrt_s * pyo.units.s, label="dewatering.hydraulic_retention_time")
    
    # Translator for centrate back to ADM1
    m.fs.translator_centrate_AD = Translator_ASM2d_ADM1(
        inlet_property_package=m.fs.props_ASM2D,
        inlet_reaction_package=m.fs.rxn_ASM2D,
        outlet_property_package=m.fs.props_ADM1,
        outlet_reaction_package=m.fs.rxn_ADM1,
        has_phase_equilibrium=False,
        outlet_state_defined=True,
        bio_P=True
    )
    
    # Connect dewatering centrate to translator
    m.fs.arc_centrate_translator = Arc(
        source=m.fs.dewatering.overflow,
        destination=m.fs.translator_centrate_AD.inlet
    )
    
    # Mixer for all recycles
    m.fs.mixer = Mixer(
        property_package=m.fs.props_ADM1,
        inlet_list=["fresh_feed", "mbr_recycle", "centrate_recycle"]
    )
    
    # Connect streams to mixer
    m.fs.arc_feed_mixer = Arc(
        source=m.fs.feed.outlet,
        destination=m.fs.mixer.fresh_feed
    )
    
    m.fs.arc_mbr_mixer = Arc(
        source=m.fs.translator_ASM_AD_mbr.outlet,
        destination=m.fs.mixer.mbr_recycle
    )
    
    m.fs.arc_centrate_mixer = Arc(
        source=m.fs.translator_centrate_AD.outlet,
        destination=m.fs.mixer.centrate_recycle
    )
    
    # Connect mixer to AD
    m.fs.arc_mixer_AD = Arc(
        source=m.fs.mixer.outlet,
        destination=m.fs.AD.inlet
    )


def _add_costing(m: pyo.ConcreteModel, costing_method: str) -> None:
    """Add costing to the flowsheet."""
    
    if costing_method == "WaterTAPCosting":
        m.fs.costing = WaterTAPCosting()
        
        # Cost AD unit
        m.fs.AD.costing = UnitModelCostingBlock(
            flowsheet_costing_block=m.fs.costing,
            costing_method=cost_anaerobic_digester,
        )
        
        # Cost dewatering unit
        if hasattr(m.fs, "dewatering"):
            m.fs.dewatering.costing = UnitModelCostingBlock(
                flowsheet_costing_block=m.fs.costing,
                costing_method=cost_dewatering
            )
        
        # Process costing
        m.fs.costing.cost_process()
        
        # Add LCOW calculation using feed volumetric flow
        m.fs.costing.add_LCOW(m.fs.feed.properties[0].flow_vol)


def _init_unit_callback(unit) -> None:
    """
    Unit initialization callback for SequentialDecomposition.
    Called for each unit individually.
    """
    # Initialize based on unit type
    if hasattr(unit, 'initialize'):
        # Skip AD here if it was explicitly initialized
        if getattr(unit, "_initialized", False):
            return
        try:
            unit.initialize(outlvl=idaeslog.WARNING)
        except Exception as e:
            logger.warning(f"Unit {getattr(unit, 'name', unit)} failed to initialize with default callback: {e}")
    else:
        logger.warning(f"Unit {unit} does not have initialize method")


def _apply_feed_state(m: pyo.ConcreteModel, state: Dict[str, float]) -> None:
    """Apply a given ADM1 state to the feed block (overwrite fixed values)."""
    if not state:
        return
    for comp, value in state.items():
        try:
            if comp == "S_cat":
                _fix_or_set(
                    m.fs.feed.properties[0].cations,
                    value * pyo.units.kmol / pyo.units.m**3,
                    label="feed.cations",
                )
            elif comp == "S_an":
                _fix_or_set(
                    m.fs.feed.properties[0].anions,
                    value * pyo.units.kmol / pyo.units.m**3,
                    label="feed.anions",
                )
            elif comp in m.fs.props_ADM1.component_list and comp != "H2O":
                if comp in m.fs.feed.properties[0].conc_mass_comp:
                    _fix_or_set(
                        m.fs.feed.properties[0].conc_mass_comp[comp],
                        value * pyo.units.kg / pyo.units.m**3,
                        label=f"feed.conc_mass_comp[{comp}]",
                    )
        except Exception as e:
            logger.debug(f"Skipped applying {comp}: {e}")


def _safe_initialize_ad(m: pyo.ConcreteModel) -> None:
    """Try to initialize AD with current state; on failure, apply a more conservative feed state and retry."""
    if not hasattr(m.fs, "AD"):
        return
    ad = m.fs.AD
    try:
        ad.initialize(outlvl=idaeslog.WARNING)
        setattr(ad, "_initialized", True)
        return
    except Exception as e:
        logger.warning(f"AD initialize failed ({e}); applying aggressive feed regularization and retrying")

    # Apply more conservative feed values directly at the feed block
    try:
        fallback_state = {}
        # Strongly suppress VFAs and dissolved gases
        for comp, val in ("S_ac", 0.03), ("S_pro", 0.01), ("S_bu", 0.01), ("S_va", 0.005), ("S_h2", 1e-7), ("S_ch4", 1e-7), ("S_co2", 1e-4):
            fallback_state[comp] = val
        # Moderate inorganic carbon and balance ions
        fallback_state["S_IC"] = 0.08
        fallback_state["S_cat"] = 0.02  # Harmonized with state_utils.py
        fallback_state["S_an"] = 0.02   # OTHER ions only, moderate value
        _apply_feed_state(m, fallback_state)
    except Exception as e:
        logger.debug(f"Failed to apply fallback feed state: {e}")

    try:
        ad.initialize(outlvl=idaeslog.WARNING)
        setattr(ad, "_initialized", True)
    except Exception as e:
        logger.warning(f"AD initialize still failing after fallback state: {e}")


def initialize_flowsheet(m: pyo.ConcreteModel, use_sequential_decomposition: bool = True) -> None:
    """
    Initialize the flowsheet using sequential decomposition for recycles.
    
    Args:
        m: Pyomo model
        use_sequential_decomposition: If True, use SD for recycle handling
    """
    
    if use_sequential_decomposition and hasattr(m.fs, 'mixer'):
        # Import SequentialDecomposition from Pyomo (IDAES no longer re-exports this)
        from pyomo.network import SequentialDecomposition
        
        # Identify tear streams (recycle arcs)
        tear_arcs = []
        if hasattr(m.fs, 'arc_mbr_mixer'):
            tear_arcs.append(m.fs.arc_mbr_mixer)  # MBR retentate recycle
        if hasattr(m.fs, 'arc_centrate_mixer'):
            tear_arcs.append(m.fs.arc_centrate_mixer)  # Centrate recycle
        
        if tear_arcs:
            logger.info(f"Using SequentialDecomposition with {len(tear_arcs)} tear streams")
            
            # Set up sequential decomposition
            seq = SequentialDecomposition()
            # Wegstein acceleration is generally more robust for recycle systems
            seq.options.tear_method = "Wegstein"
            seq.options.iterLim = 50  # Max iterations
            seq.options.tol = 1e-5  # Convergence tolerance (option name is 'tol')
            
            # Set tear streams using available API
            try:
                if hasattr(seq, "set_tear_set"):
                    seq.set_tear_set(tear_arcs)
                elif hasattr(seq, "options") and hasattr(seq.options, "tear_set"):
                    seq.options.tear_set = tear_arcs
                else:
                    # Fallback: assign attribute directly if present
                    setattr(seq, "tear_set", tear_arcs)
            except Exception as e:
                logger.debug(f"Unable to set explicit tear set: {e}")
            
            # Pre-initialize upstream units and AD to improve robustness
            try:
                m.fs.feed.initialize()
                propagate_state(m.fs.arc_feed_mixer)
                m.fs.mixer.initialize()
                propagate_state(m.fs.arc_mixer_AD)
                _safe_initialize_ad(m)
            except Exception as e:
                logger.debug(f"Pre-initialization before SD encountered an issue: {e}")

            # Optionally set initial guesses for tear streams
            # Example: seq.set_guesses_for(m.fs.AD.inlet, {m.fs.AD.inlet.flow_vol: 1.0, ...})
            
            # Run decomposition with unit initialization callback
            seq.run(m, _init_unit_callback)

            # After initialization, gradually ramp to final state
            if hasattr(m.fs, "_final_adm1_state") and hasattr(m.fs, "_init_adm1_state"):
                logger.info("Ramping from init to final feed state")
                
                # Get solver for intermediate solves
                solver = get_solver()
                
                # Components to ramp gradually (high VFAs and gases)
                ramp_components = ["S_ac", "S_pro", "S_bu", "S_va", "S_co2", "S_IC"]
                
                # Configurable ramp steps (can be set in heuristic_config)
                init_state = m.fs._init_adm1_state
                final_state = m.fs._final_adm1_state
                
                # Get ramp steps from config or use default
                if hasattr(m.fs, "_heuristic_config"):
                    default_steps = m.fs._heuristic_config.get("ramp_steps", [0.33, 0.67, 1.0])
                else:
                    default_steps = [0.33, 0.67, 1.0]
                
                for alpha in default_steps:
                    ramped_state = dict(init_state)
                    
                    # Ramp critical components gradually
                    for comp in ramp_components:
                        if comp in final_state and comp in init_state:
                            ramped_state[comp] = (1-alpha)*init_state[comp] + alpha*final_state[comp]
                        elif comp in final_state:
                            ramped_state[comp] = final_state[comp]
                    
                    # Apply other components at full strength
                    for comp in final_state:
                        if comp not in ramp_components:
                            ramped_state[comp] = final_state[comp]
                    
                    _apply_feed_state(m, ramped_state)
                    
                    # Solve at this intermediate point
                    results = solver.solve(m, tee=False)
                    if pyo.check_optimal_termination(results):
                        logger.info(f"Ramp solve successful at alpha={alpha:.2f}")
                    else:
                        logger.warning(f"Ramp solve failed at alpha={alpha:.2f}, continuing anyway")
                        # Continue anyway - sometimes later points converge even if earlier ones fail
            
            elif hasattr(m.fs, "_final_adm1_state"):
                # Fallback to direct application if no init state
                logger.info("Applying final feed state after initialization (no ramping)")
                _apply_feed_state(m, m.fs._final_adm1_state)

            logger.info("Sequential decomposition completed")
            return
    
    # Fallback to simple sequential initialization
    logger.info("Using simple sequential initialization")
    
    # Initialize feed
    m.fs.feed.initialize()
    
    # Initialize mixer if present
    if hasattr(m.fs, 'mixer'):
        propagate_state(m.fs.arc_feed_mixer)
        m.fs.mixer.initialize()
        propagate_state(m.fs.arc_mixer_AD)
    
    # Initialize AD
    _safe_initialize_ad(m)
    
    # Initialize downstream based on flowsheet type
    if hasattr(m.fs, "ad_splitter"):
        # Low TSS path with MBR
        propagate_state(m.fs.arc_AD_splitter)
        m.fs.ad_splitter.initialize()
        
        # To MBR branch
        propagate_state(m.fs.arc_splitter_translator)
        m.fs.translator_AD_ASM.initialize()
        
        propagate_state(m.fs.arc_translator_MBR)
        m.fs.MBR.initialize()
        
        propagate_state(m.fs.arc_MBR_translator)
        m.fs.translator_ASM_AD_mbr.initialize()
        
        # Dewatering branch (parallel with MBR)
        propagate_state(m.fs.arc_dewatering_translator)
        m.fs.translator_dewatering_ASM.initialize()
        
        propagate_state(m.fs.arc_translator_dewatering)
        m.fs.dewatering.initialize()
        
        propagate_state(m.fs.arc_centrate_translator)
        m.fs.translator_centrate_AD.initialize()
    else:
        # High TSS path
        propagate_state(m.fs.arc_AD_translator)
        m.fs.translator_AD_ASM.initialize()
        
        propagate_state(m.fs.arc_translator_dewatering)
        m.fs.dewatering.initialize()
        
        propagate_state(m.fs.arc_dewatering_translator)
        m.fs.translator_ASM_AD.initialize()

    # Apply final user-provided feed state after initialization
    if hasattr(m.fs, "_final_adm1_state"):
        logger.info("Applying final feed state after initialization")
        _apply_feed_state(m, m.fs._final_adm1_state)


def solve_flowsheet(
    m: pyo.ConcreteModel,
    tee: bool = True,
    raise_on_failure: bool = True
) -> Dict[str, Any]:
    """
    Solve the flowsheet and return results.
    """
    solver = get_solver()
    
    # Apply solver options from config if available
    if hasattr(m.fs, 'config') and hasattr(m.fs.config, 'solver_options') and m.fs.config.solver_options:
        for key, value in m.fs.config.solver_options.items():
            solver.options[key] = value
    
    # Route solver output to IDAES logger instead of stdout
    solve_logger = idaeslog.getSolveLogger("watertap.ad")
    with idaeslog.solver_log(solve_logger, idaeslog.INFO) as slc:
        results = solver.solve(m, tee=slc.tee if tee else False)
    
    if not pyo.check_optimal_termination(results):
        if raise_on_failure:
            raise RuntimeError(f"Solve failed: {results.solver.termination_condition}")
        else:
            logger.warning(f"Solve failed: {results.solver.termination_condition}")
    
    # Extract results
    # Compute biogas flow (convert to m^3/day) and methane fraction if available
    biogas_m3d = None
    ch4_frac = None
    try:
        biogas = pyo.units.convert(
            m.fs.AD.vapor_outlet.flow_vol[0],
            to_units=pyo.units.m**3 / pyo.units.day,
        )
        biogas_m3d = pyo.value(biogas)
    except Exception:
        pass
    try:
        # Prefer mole fraction if provided by vapor property package
        ch4_frac = pyo.value(m.fs.AD.vapor_outlet.mole_frac_comp[0, "S_ch4"])  # type: ignore
    except Exception:
        try:
            # Fallback: approximate from mass concentrations (not strictly mole fraction)
            ch4 = pyo.value(m.fs.AD.vapor_outlet.conc_mass_comp[0, "S_ch4"])  # type: ignore
            co2 = pyo.value(m.fs.AD.vapor_outlet.conc_mass_comp[0, "S_co2"])  # type: ignore
            h2 = pyo.value(m.fs.AD.vapor_outlet.conc_mass_comp[0, "S_h2"])   # type: ignore
            total = max(ch4 + co2 + h2, 1e-12)
            ch4_frac = ch4 / total
        except Exception:
            ch4_frac = None
    
    output = {
        "solver_status": str(results.solver.termination_condition),
        "biogas_production_m3d": biogas_m3d,
        "methane_fraction": ch4_frac,
    }
    
    # Add economic results if available
    if hasattr(m.fs, "costing"):
        output["total_capital_cost"] = pyo.value(m.fs.costing.total_capital_cost)
        output["total_operating_cost"] = pyo.value(m.fs.costing.total_operating_cost)
        output["LCOW"] = pyo.value(m.fs.costing.LCOW)
    
    # Add MBR results if present
    if hasattr(m.fs, "MBR"):
        output["mbr_permeate_flow_m3d"] = pyo.value(m.fs.MBR.permeate.flow_vol[0]) * 86400
    
    # Add dewatering results
    if hasattr(m.fs, "dewatering"):
        output["sludge_production_m3d"] = pyo.value(m.fs.dewatering.underflow.flow_vol[0]) * 86400
        output["centrate_flow_m3d"] = pyo.value(m.fs.dewatering.overflow.flow_vol[0]) * 86400
    
    return output


def simulate_ad_system(
    basis_of_design: Dict[str, Any],
    adm1_state: Dict[str, Any],
    heuristic_config: Dict[str, Any],
    costing_method: str = "WaterTAPCosting",
    initialize_only: bool = False,
    tee: bool = True
) -> Dict[str, Any]:
    """
    Main entry point for anaerobic digester simulation.
    
    This function:
    1. Builds the flowsheet based on heuristic configuration
    2. Initializes using SequentialDecomposition for recycles
    3. Solves the flowsheet
    4. Adds economic analysis
    5. Returns comprehensive results
    
    Args:
        basis_of_design: Design parameters (flow, COD, temperature, etc.)
        adm1_state: Modified ADM1 state variables including P-species
        heuristic_config: Heuristic sizing results with flowsheet type
        costing_method: Either "WaterTAPCosting" or "ZeroOrderCosting"
        initialize_only: If True, only build and initialize (don't solve)
        tee: Display solver output
        
    Returns:
        Dictionary with simulation results including:
        - status: Success/error status
        - flowsheet_type: Configuration used
        - operational_results: Biogas, methane, flows
        - economic_results: CAPEX, OPEX, LCOW if costing enabled
        - convergence_info: Solver statistics
        - warnings: Any issues encountered
        
    Example:
        ```python
        results = simulate_ad_system(
            basis_of_design={"feed_flow_m3d": 1000, "cod_mg_l": 30000},
            adm1_state=adm1_state_dict,
            heuristic_config=heuristic_results
        )
        ```
    """
    try:
        logger.info(f"Starting AD simulation for {heuristic_config['flowsheet_type']} configuration")
        
        # Create concrete model
        m = pyo.ConcreteModel()
        m.fs = FlowsheetBlock(dynamic=False)
        
        # Build flowsheet based on configuration
        flowsheet_type = heuristic_config.get("flowsheet_type", "high_tss")
        
        # Build common components (feed, AD, property packages)
        _build_common_components(m, basis_of_design, adm1_state, heuristic_config)
        
        # Build configuration-specific flowsheet
        if flowsheet_type == "low_tss_mbr":
            _build_low_tss_mbr_flowsheet(m, basis_of_design, heuristic_config)
        else:
            _build_high_tss_flowsheet(m, basis_of_design, heuristic_config)
        
        # Quick DOF snapshot prior to arc expansion (may be high due to unexpanded arcs)
        dof_pre = _report_dof_breakdown(m, header="pre-expand")
        
        # Expand arcs BEFORE initialization so SD can build its graph
        # (required by Pyomo/IDAES graph utilities)
        logger.info("Expanding arcs prior to initialization...")
        TransformationFactory("network.expand_arcs").apply_to(m)

        # DOF after arc expansion is the relevant number; require zero before SD
        dof = _report_dof_breakdown(m, header="post-expand")
        if dof != 0:
            logger.warning("Non-zero DOF after arc expansion; aborting initialization to avoid SD hang")
            raise RuntimeError(f"Model is under/over-specified (DOF={dof}); see logs for per-unit breakdown")

        # Apply default scaling factors for improved numerical stability
        try:
            iscale.calculate_scaling_factors(m)
        except Exception as e:
            logger.debug(f"Scaling factor calculation skipped: {e}")

        # Initialize flowsheet with SequentialDecomposition for recycles
        logger.info("Initializing flowsheet...")
        initialize_flowsheet(m, use_sequential_decomposition=True)
        
        if initialize_only:
            return {
                "status": "initialized",
                "flowsheet_type": flowsheet_type,
                "degrees_of_freedom": dof,
                "message": "Model built and initialized successfully"
            }
        
        # Solve flowsheet
        logger.info("Solving flowsheet...")
        solve_results = solve_flowsheet(m, tee=tee, raise_on_failure=False)
        
        # Add costing if requested
        if costing_method and solve_results.get("solver_status") == "optimal":
            logger.info(f"Adding {costing_method} costing...")
            _add_costing(m, costing_method)
            
            # Re-solve with costing
            solver = get_solver()
            
            # Apply solver options from config if available
            if hasattr(m.fs, 'config') and m.fs.config.solver_options:
                for key, value in m.fs.config.solver_options.items():
                    solver.options[key] = value
            
            solve_logger = idaeslog.getSolveLogger("watertap.ad.costing")
            with idaeslog.solver_log(solve_logger, idaeslog.INFO) as slc:
                cost_results = solver.solve(m, tee=False)
            
            if pyo.check_optimal_termination(cost_results):
                # Extract economic results
                if hasattr(m.fs, "costing"):
                    solve_results["total_capital_cost"] = pyo.value(m.fs.costing.total_capital_cost)
                    solve_results["total_operating_cost"] = pyo.value(m.fs.costing.total_operating_cost)
                    
                    if hasattr(m.fs.costing, "LCOW"):
                        solve_results["LCOW"] = pyo.value(m.fs.costing.LCOW)
        
        # Package results
        results = {
            "status": "success" if solve_results.get("solver_status") == "optimal" else "failed",
            "flowsheet_type": flowsheet_type,
            "operational_results": {
                "biogas_production_m3d": solve_results.get("biogas_production_m3d"),
                "methane_fraction": solve_results.get("methane_fraction"),
                "sludge_production_m3d": solve_results.get("sludge_production_m3d"),
                "centrate_flow_m3d": solve_results.get("centrate_flow_m3d")
            },
            "economic_results": {
                "total_capital_cost": solve_results.get("total_capital_cost"),
                "total_operating_cost": solve_results.get("total_operating_cost"),
                "LCOW": solve_results.get("LCOW")
            },
            "convergence_info": {
                "solver_status": solve_results.get("solver_status"),
                "degrees_of_freedom": dof
            }
        }
        
        # Add MBR results if applicable
        if flowsheet_type == "low_tss_mbr" and "mbr_permeate_flow_m3d" in solve_results:
            results["operational_results"]["mbr_permeate_flow_m3d"] = solve_results["mbr_permeate_flow_m3d"]
        
        logger.info(f"Simulation completed with status: {results['status']}")
        
        return results
        
    except Exception as e:
        logger.error(f"Simulation failed: {str(e)}")
        return {
            "status": "error",
            "error": str(type(e).__name__),
            "message": str(e),
            "flowsheet_type": heuristic_config.get("flowsheet_type")
        }
