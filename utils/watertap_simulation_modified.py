#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
WaterTAP simulation module using Modified ADM1 and built-in translators.

Supports two configurations based on heuristic sizing:
1. High TSS: AD + Dewatering with centrate recycle
2. Low TSS: AD + MBR + Dewatering with centrate recycle
"""

import logging
import math
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
from idaes.core.util.model_diagnostics import DiagnosticsToolbox

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


def _log_port_state(port, name: str, level: int = logging.INFO) -> None:
    """Log a concise snapshot of a Port state for debugging recycle collapse.

    Shows flow (m³/d), temperature (K), pressure (Pa), and a few key concentrations.
    """
    try:
        q = None
        try:
            q = pyo.value(pyo.units.convert(port.flow_vol[0], to_units=pyo.units.m**3/pyo.units.day))
        except Exception:
            pass
        t = None
        p = None
        try:
            t = pyo.value(port.temperature[0])
        except Exception:
            pass
        try:
            p = pyo.value(port.pressure[0])
        except Exception:
            pass

        msg = f"{name}: Q={q:.6g} m3/d, T={t if t is not None else 'NA'} K, P={p if p is not None else 'NA'} Pa"
        logger.log(level, msg)

        # Try to print a few representative concentrations if present
        sample = ["S_ac", "S_IC", "S_co2", "S_ch4", "X_c"]
        comps = []
        try:
            for c in sample:
                if (0, c) in port.conc_mass_comp:
                    val = pyo.value(port.conc_mass_comp[0, c])
                    comps.append(f"{c}={val:.3g}")
        except Exception:
            pass
        if comps:
            logger.log(level, f"{name} conc: " + ", ".join(comps))
    except Exception:
        # Never let logging raise
        return


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
    # Optional diagnostics flags
    enable_diagnostics: bool = False
    dump_near_zero_vars: bool = False
    # SD controls
    sd_iter_lim: int = 1
    sd_tol: float = 1e-6
    
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


def _log_key_flows(m: pyo.ConcreteModel, header: str = "") -> None:
    """Log key volumetric flows and split info to diagnose low-flow basin.

    Reports flows (m^3/d) for feed, AD inlet/outlet, MBR inlet/permeate/retentate,
    and the AD splitter dewatering fraction. Also checks the MBR volumetric
    recovery constraint residual.
    """
    try:
        def qd(expr):
            try:
                return float(pyo.value(pyo.units.convert(expr, to_units=pyo.units.m**3/pyo.units.day)))
            except Exception:
                return None
        msg = []
        if header:
            msg.append(f"Flow diagnostics ({header}):")
        # Feed
        if hasattr(m.fs, "feed"):
            msg.append(f"  feed.outlet.Q = {qd(m.fs.feed.outlet.flow_vol[0])}")
        # Mixer
        if hasattr(m.fs, "mixer"):
            try:
                msg.append(f"  mixer.outlet.Q = {qd(m.fs.mixer.outlet.flow_vol[0])}")
                if hasattr(m.fs.mixer, "mbr_recycle"):
                    msg.append(f"  mixer.mbr_recycle.Q = {qd(m.fs.mixer.mbr_recycle.flow_vol[0])}")
                if hasattr(m.fs.mixer, "centrate_recycle"):
                    msg.append(f"  mixer.centrate_recycle.Q = {qd(m.fs.mixer.centrate_recycle.flow_vol[0])}")
            except Exception:
                pass
        # AD
        if hasattr(m.fs, "AD"):
            msg.append(f"  AD.inlet.Q = {qd(m.fs.AD.inlet.flow_vol[0])}")
            msg.append(f"  AD.liquid_outlet.Q = {qd(m.fs.AD.liquid_outlet.flow_vol[0])}")
        # Splitter
        if hasattr(m.fs, "ad_splitter"):
            try:
                f_dewat = None
                # totalFlow splitter: single fraction Var/Param
                if (0, "to_dewatering") in m.fs.ad_splitter.split_fraction:
                    f_dewat = pyo.value(m.fs.ad_splitter.split_fraction[0, "to_dewatering"])
                msg.append(f"  ad_splitter.to_dewatering fraction = {f_dewat}")
                # Flows downstream of splitter if available
                if hasattr(m.fs.ad_splitter, "to_mbr"):
                    msg.append(f"  ad_splitter.to_mbr.Q = {qd(m.fs.ad_splitter.to_mbr.flow_vol[0])}")
                if hasattr(m.fs.ad_splitter, "to_dewatering"):
                    msg.append(f"  ad_splitter.to_dewatering.Q = {qd(m.fs.ad_splitter.to_dewatering.flow_vol[0])}")
            except Exception:
                pass
        # MBR
        if hasattr(m.fs, "MBR"):
            msg.append(f"  MBR.inlet.Q = {qd(m.fs.MBR.inlet.flow_vol[0])}")
            msg.append(f"  MBR.permeate.Q = {qd(m.fs.MBR.permeate.flow_vol[0])}")
            msg.append(f"  MBR.retentate.Q = {qd(m.fs.MBR.retentate.flow_vol[0])}")
            try:
                # Report actual module recovery
                q_in = pyo.value(m.fs.MBR.inlet.flow_vol[0])
                q_perm = pyo.value(m.fs.MBR.permeate.flow_vol[0])
                actual_recovery = q_perm / q_in if q_in > 0 else None
                msg.append(f"  MBR module recovery = {actual_recovery:.3f} (target 0.2)")
            except Exception:
                pass
        logger.info("\n".join(msg))
    except Exception:
        # Never let diagnostics fail the run
        return


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
    
    # Store basis_of_design for reference in solve_flowsheet
    m.fs.basis_of_design = basis_of_design
    
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
        clean_state, basis_of_design
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

    # Guard-rail: if density is exposed on state, set a scaling factor to stabilize products with flow
    try:
        if hasattr(m.fs.feed.properties[0], "dens_mass"):
            iscale.set_scaling_factor(m.fs.feed.properties[0].dens_mass, 1e-3)
    except Exception:
        pass
    
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
    
    # Add MLSS constraints with proper units for AD liquid phase
    # Target: 10-15 kg/m³ (operational requirement for MBR flux management)
    @m.fs.Constraint(doc="AD MLSS lower bound")
    def eq_AD_mlss_lower(b):
        return b.AD.liquid_phase.properties_out[0].TSS >= 10.0 * pyo.units.kg/pyo.units.m**3

    @m.fs.Constraint(doc="AD MLSS upper bound")  
    def eq_AD_mlss_upper(b):
        return b.AD.liquid_phase.properties_out[0].TSS <= 15.0 * pyo.units.kg/pyo.units.m**3

    logger.info("Added MLSS constraints: 10-15 kg/m³ for AD liquid phase")
    
    # Ensure strictly positive S_H and good initial pH on AD properties to prevent log10 errors
    if hasattr(m.fs, "AD") and hasattr(m.fs.AD, "liquid_phase"):
        # AD is steady-state, so access properties at time 0 directly
        for side in ("properties_in", "properties_out"):
            try:
                blk = getattr(m.fs.AD.liquid_phase, side)[0]
                if hasattr(blk, "S_H"):
                    try:
                        blk.S_H.setlb(1e-14)  # Strict positive lower bound
                        if blk.S_H.value is None or blk.S_H.value <= 0:
                            blk.S_H.set_value(1e-7)  # ~pH 7
                    except Exception:
                        pass
                if hasattr(blk, "pH"):
                    try:
                        if blk.pH.value is None:
                            blk.pH.set_value(7.0)
                    except Exception:
                        pass
            except Exception:
                pass


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
    
    # Helper function for dewatering calculation
    def _compute_p_dewat_from_mass_balance(tss_in_kg_m3: float, capture_fr: float, cake_solids_frac: float) -> float:
        # Mass balance: Q_u/Q_in = (capture*TSS_in) / TSS_cake, where TSS_cake = cake_frac * rho
        rho_sludge = 1000.0  # kg/m³, assume near water density
        tss_cake = max(1e-6, cake_solids_frac * rho_sludge)
        p = (max(0.0, capture_fr) * max(1e-9, tss_in_kg_m3)) / tss_cake
        # Clamp to reasonable bounds to avoid infeasible soluble splits
        return float(min(max(p, 0.005), 0.9))
    
    # Split AD outlet for MBR and dewatering (parallel configuration)
    # FIXED: Using totalFlow to prevent zero-mass collapse in recycle
    m.fs.ad_splitter = Separator(
        property_package=m.fs.props_ADM1,
        outlet_list=["to_mbr", "to_dewatering"],
        split_basis=SplittingType.totalFlow  # Changed from componentFlow to prevent zero collapse
    )
    
    # Connect AD to splitter
    m.fs.arc_AD_splitter = Arc(
        source=m.fs.AD.liquid_outlet,
        destination=m.fs.ad_splitter.inlet
    )
    
    # Placeholder for water balance - will be added after MBR and dewatering are created
    
    # Calculate split fractions (dewatering pulls waste sludge directly from AD)
    # Priority: explicit volume_fraction (if provided) > daily_waste_m3d / (expected AD flow)
    # This avoids tiny implied fractions if heuristics provide a direct volumetric ratio.
    dewat_cfg = heuristic_config.get("dewatering", {}) if isinstance(heuristic_config, dict) else {}
    feed_flow_m3d = float(basis_of_design.get("feed_flow_m3d", 1000.0))
    # Expected AD liquid outlet flow ~ (1 + recirc_ratio) * feed. Default recirc_ratio = 4.0 (5Q operation)
    recirc_ratio = float(heuristic_config.get("mbr", {}).get("recirc_ratio", 4.0)) if isinstance(heuristic_config, dict) else 4.0
    total_ad_flow_m3d = (1.0 + recirc_ratio) * feed_flow_m3d

    if dewat_cfg.get("volume_fraction") is not None:
        dewatering_fraction = float(dewat_cfg.get("volume_fraction"))
        logger.info(f"Using provided dewatering volume_fraction = {dewatering_fraction}")
    else:
        daily_waste_m3d = float(dewat_cfg.get("daily_waste_sludge_m3d", 20.0))
        # Guard against unphysical fractions
        dewatering_fraction = max(1e-5, min(0.9, daily_waste_m3d / max(total_ad_flow_m3d, 1e-6)))
        logger.info(
            f"Computed dewatering fraction (by volume): {dewatering_fraction} = {daily_waste_m3d}/{total_ad_flow_m3d}"
        )
    
    # CRITICAL CHANGE: Unfix splitter fraction to let MLSS constraints determine wasting
    # This resolves DOF = -1 issue while maintaining operational MLSS target
    try:
        # Unfix to allow optimization based on MLSS constraint
        m.fs.ad_splitter.split_fraction[0, "to_dewatering"].unfix()
        # Set reasonable bounds for sludge wasting (1-8% typical for MBR systems)
        m.fs.ad_splitter.split_fraction[0, "to_dewatering"].setlb(0.01)   # Min 1%
        m.fs.ad_splitter.split_fraction[0, "to_dewatering"].setub(0.08)   # Max 8%
        # Use heuristic value as initial guess
        m.fs.ad_splitter.split_fraction[0, "to_dewatering"].set_value(dewatering_fraction)
        logger.info(f"AD splitter fraction UNFIXED for MLSS control, bounds [0.01, 0.08], initial {dewatering_fraction:.4f}")
    except Exception as e:
        logger.warning(f"Could not fix splitter fraction: {e}")
        # If we can't fix it, at least set value and bounds
        try:
            m.fs.ad_splitter.split_fraction[0, "to_dewatering"].set_value(dewatering_fraction)
            # TIGHTENED BOUNDS: More realistic range to prevent extreme splits
            m.fs.ad_splitter.split_fraction[0, "to_dewatering"].setlb(0.001)  # Was 1e-4
            m.fs.ad_splitter.split_fraction[0, "to_dewatering"].setub(0.5)    # Was 0.8
        except Exception:
            pass
    
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
    
    # MBR as ASM2D separator (componentFlow with manual splits)
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
    
    # CRITICAL FIX: Add explicit volumetric anchors for MBR
    # 1) Recovery constraint (perm/inlet)
    #    Make recovery a Var so we can add one more equality (overall balance)
    #    while maintaining DOF = 0. Keep it near the design value (0.2) with
    #    reasonable bounds.
    # REMOVED: mbr_recovery variable and volumetric constraint to avoid over-constraining
    # The recovery is now set directly on the H2O split fraction
    # m.fs.mbr_recovery = pyo.Var(bounds=(0.05, 0.8), initialize=0.2)
    # m.fs.eq_mbr_perm_vol = pyo.Constraint(
    #     expr=m.fs.MBR.permeate.flow_vol[0] == m.fs.mbr_recovery * m.fs.MBR.inlet.flow_vol[0]
    # )
    
    # Set MBR recovery directly on water split (module recovery ~20% for 5:1 recycle)
    mbr_module_recovery = 0.2  # 1Q permeate from 5Q inlet
    
    # 2) Replace the strict permeate==feed anchor with an overall external
    #    volumetric balance: MBR permeate + dewatering underflow == feed.
    #    This permits non-zero waste sludge while keeping the overall volumetric
    #    balance consistent and avoids the prior infeasibility.
    #    Note: this constraint is created after the dewatering unit below.
    # Note: Don't add retentate constraint - Separator's mass balance handles it
    # The retentate flow is determined by: inlet = permeate + retentate
    
    # Set bounds on MBR inlet to guide solution (not fix)
    feed_flow_m3s = float(basis_of_design.get("feed_flow_m3d", 1000.0)) / 86400.0
    m.fs.MBR.inlet.flow_vol[0].setlb(4.5 * feed_flow_m3s)  # Min 4.5Q
    m.fs.MBR.inlet.flow_vol[0].setub(5.5 * feed_flow_m3s)  # Max 5.5Q
    
    # Don't fix MBR inlet - let it emerge from mass balances
    
    # Set lower bounds to keep flows strictly positive and away from degenerate solution
    m.fs.MBR.permeate.flow_vol[0].setlb(1e-4)  # 8.64 m³/d minimum
    m.fs.MBR.retentate.flow_vol[0].setlb(1e-3)  # 86.4 m³/d minimum
    
    # ADD UPPER BOUNDS to prevent unbounded growth and improve convergence
    m.fs.MBR.inlet.flow_vol[0].setub(10.0 * feed_flow_m3s)    # Max 10Q total
    m.fs.MBR.permeate.flow_vol[0].setub(2.0 * feed_flow_m3s)  # Max 2Q permeate
    m.fs.MBR.retentate.flow_vol[0].setub(8.0 * feed_flow_m3s) # Max 8Q retentate

    # Optional: enforce minimum MBR inlet/permeate flows to escape low-flow basin
    # Enabled via heuristic_config['diagnostics']['force_mbr_min_constraints'] = True
    try:
        diag = heuristic_config.get("diagnostics", {}) if isinstance(heuristic_config, dict) else {}
        if bool(diag.get("force_mbr_min_constraints", False)):
            feed_m3d = float(basis_of_design.get("feed_flow_m3d", 1000.0))
            # Defaults: 5Q inlet min and 1Q permeate min unless overridden
            min_in_m3d = float(diag.get("mbr_inlet_min_m3d", 5.0 * feed_m3d))
            min_perm_m3d = float(diag.get("mbr_permeate_min_m3d", 1.0 * feed_m3d))
            m.fs.force_mbr_inlet_min = pyo.Constraint(
                expr=m.fs.MBR.inlet.flow_vol[0] >= (min_in_m3d / 86400.0) * pyo.units.m**3 / pyo.units.s
            )
            m.fs.force_mbr_perm_min = pyo.Constraint(
                expr=m.fs.MBR.permeate.flow_vol[0] >= (min_perm_m3d / 86400.0) * pyo.units.m**3 / pyo.units.s
            )
            logger.info(
                f"Activated MBR min-flow constraints: inlet >= {min_in_m3d} m3/d, permeate >= {min_perm_m3d} m3/d"
            )
    except Exception as e:
        logger.warning(f"Failed to set MBR min-flow constraints: {e}")
    
    # --- SIEVING-ANCHORED MBR SPLITS (physically consistent & numerically stable)
    # Fix for structural inconsistency: tie component mass splits to volumetric recovery
    # via sieving coefficients to maintain concentration consistency
    
    # 1) User-tunable defaults (can be overridden via heuristic_config['mbr'])
    mbr_cfg = heuristic_config.get("mbr", {}) if isinstance(heuristic_config, dict) else {}

    # Our "sigma" here is a passage coefficient (Cp/Cf relative to water split),
    # not the SKK reflection coefficient. For soluble species, sigma should be ~1.0
    # (nearly full passage), and for particulates sigma should be ~1e-4 (nearly no passage).
    sigma_soluble = float(mbr_cfg.get("sigma_soluble", 1.0))       # default: full passage
    sigma_partic = float(mbr_cfg.get("sigma_particulate", 1e-4))   # default: no passage
    sigma_h2o = float(mbr_cfg.get("sigma_h2o", 1.0))              # water follows volume

    # Accept alternate semantics if user provided reflection-type values
    # (i.e., 1=rejection, 0=passage). If this pattern is detected (soluble near 0 and
    # particulate near 1), auto-convert unless explicitly disabled.
    try:
        # CRITICAL FIX: Default to False to prevent unexpected NH4+ retention
        # This ensures sigma values are interpreted as passage coefficients (1=pass)
        # unless user explicitly requests reflection semantics
        auto_correct = bool(mbr_cfg.get("auto_correct_sigma", False))
    except Exception:
        auto_correct = False  # Keep False even on exception to prevent NH4+ trap

    try:
        if auto_correct and sigma_soluble <= 0.05 and sigma_partic >= 0.95:
            logger.warning(
                "MBR sigma appears to use reflection semantics (soluble≈0, particulate≈1). "
                "Interpreting as reflection coefficients and converting to passage: "
                f"soluble→{1.0 - sigma_soluble:.3f}, particulate→{1.0 - sigma_partic:.3f}. "
                "Set mbr.auto_correct_sigma=False to disable."
            )
            sigma_soluble = 1.0 - sigma_soluble
            sigma_partic = 1.0 - sigma_partic
    except Exception:
        pass

    # Guard-rails: warn on clearly non-physical values
    if sigma_soluble < 0.8:
        logger.warning(
            f"sigma_soluble={sigma_soluble:.3f} implies significant rejection of dissolved species. "
            "Membranes in MBRs typically pass dissolved ions like ammonia (S_IN). "
            "This can cause TAN accumulation and pH crash."
        )
    if sigma_partic > 1e-2:
        logger.warning(
            f"sigma_particulate={sigma_partic:.3f} allows particulate passage to permeate. "
            "Typical MBR behavior is near-zero passage for particulates."
        )
    
    # 2) Define σ_j for all components
    sigma_init = {}
    for comp in m.fs.props_ASM2D.component_list:
        cname = str(comp)
        if cname == "H2O":
            sigma_init[comp] = sigma_h2o
        elif cname.startswith("X_"):
            sigma_init[comp] = sigma_partic
        else:
            # Treat all non-particulate components as soluble
            sigma_init[comp] = sigma_soluble
    
    m.fs.mbr_sigma = pyo.Param(
        m.fs.props_ASM2D.component_list, initialize=sigma_init, mutable=True
    )
    
    # 3) Expose splits as Vars and tie them to recovery with one constraint per component
    for comp in m.fs.props_ASM2D.component_list:
        # Ensure they are Vars (not fixed constants from earlier logic)
        try:
            m.fs.MBR.split_fraction[0, "permeate", comp].unfix()
        except Exception:
            pass
        # Seed a consistent initial guess
        m.fs.MBR.split_fraction[0, "permeate", comp].set_value(
            mbr_module_recovery * pyo.value(m.fs.mbr_sigma[comp])
        )
    
    # Water-anchored sieving approach: explicitly exclude H2O, not "last component"
    # This prevents freeing a sensitive species that could disrupt AD chemistry
    components_to_constrain = [j for j in m.fs.props_ASM2D.component_list if str(j) != "H2O"]
    
    # Fix H2O split fraction to the desired module recovery
    m.fs.MBR.split_fraction[0, "permeate", "H2O"].fix(mbr_module_recovery)
    
    # Tie all non-H2O components to H2O's split (water-anchored pattern)
    # All components follow H2O based on their sigma values
    m.fs.eq_mbr_split = pyo.Constraint(
        components_to_constrain,
        rule=lambda b, j: b.MBR.split_fraction[0, "permeate", j] == 
                         b.mbr_sigma[j] * b.MBR.split_fraction[0, "permeate", "H2O"]
    )
    # Provide explicit scaling for custom constraints to satisfy IDAES scaling checks
    try:
        for j in components_to_constrain:
            iscale.constraint_scaling_transform(m.fs.eq_mbr_split[j], 1.0)
    except Exception:
        pass
    
    logger.info(f"Applied sieving coefficient approach (passage): σ_soluble={sigma_soluble}, σ_particulate={sigma_partic}")

    # P1: Runtime verification of S_NH4 split constraint
    try:
        if "S_NH4" in m.fs.props_ASM2D.component_list:
            # Check initial values
            nh4_split = pyo.value(m.fs.MBR.split_fraction[0, "permeate", "S_NH4"])
            h2o_split = pyo.value(m.fs.MBR.split_fraction[0, "permeate", "H2O"])
            sigma_nh4 = pyo.value(m.fs.mbr_sigma["S_NH4"])
            expected = sigma_nh4 * h2o_split
            
            logger.info(
                f"P1 Verification: S_NH4 split = {nh4_split:.4f}, "
                f"H2O split = {h2o_split:.4f}, σ_NH4 = {sigma_nh4:.4f}, "
                f"expected = {expected:.4f}"
            )
            
            if abs(nh4_split - expected) > 1e-6:
                logger.warning(
                    f"P1: S_NH4 not following water split initially! "
                    f"Deviation = {abs(nh4_split - expected):.6f}"
                )
            else:
                logger.info("P1: S_NH4 correctly following water split constraint")
        else:
            logger.warning("P1: S_NH4 not found in ASM2D component list - using S_IN instead")
            if "S_IN" in m.fs.props_ASM2D.component_list:
                logger.info(f"MBR S_IN passage coefficient set to σ={sigma_soluble}")
    except Exception as e:
        logger.debug(f"P1: Could not verify nitrogen split: {e}")
    
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
            # CRITICAL: Must use 15 kg/m³ for proper SRT
            # Lower TSS reduces biomass inventory and degrades performance
            return 15.0

    cake_solids = dewatering_config.get("cake_solids_fraction", 0.22)
    tss_in_kg_m3 = _estimate_tss_inlet_kg_m3_low_tss(heuristic_config)
    p_dewat_guess = _compute_p_dewat_from_mass_balance(tss_in_kg_m3, capture_fraction, cake_solids)
    _fix_or_set(m.fs.dewatering.p_dewat, p_dewat_guess, label="dewatering.p_dewat")
    
    # SRT constraint - this is the key to proper solids control
    # SRT = (Solids Inventory) / (Solids Wasted per Day)
    # We fix SRT and let the wasting flow emerge
    srt_days = heuristic_config.get("digester", {}).get("srt_days", 30)
    m.fs.srt_target = pyo.Param(initialize=srt_days, mutable=True)
    
    # Create SRT constraint
    # Note: We'll link this to AD TSS after AD is created
    # For now, just create a placeholder that will be connected later
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

    # Overall external volume balance: P + U = F (anchors flows and prevents volumetric drift)
    m.fs.eq_overall_external_vol_balance = pyo.Constraint(
        expr=m.fs.MBR.permeate.flow_vol[0] + m.fs.dewatering.underflow.flow_vol[0] ==
             m.fs.feed.properties[0].flow_vol
    )
    # Scale the volumetric balance by feed flow (dimensionless O(1) equation)
    try:
        _Qf = float(basis_of_design.get("feed_flow_m3d", 1000.0)) / 86400.0
        if _Qf > 0:
            iscale.constraint_scaling_transform(m.fs.eq_overall_external_vol_balance, 1.0/_Qf)
    except Exception:
        pass
    
    # Add SRT monitoring expressions for operational visibility
    # SRT = (TSS in digester × volume) / (net biomass production rate)
    @m.fs.Expression(doc="Biomass inventory in AD (kg)")
    def biomass_inventory(b):
        return (b.AD.liquid_phase.properties_out[0].TSS * 
                b.AD.volume_liquid[0])
    
    @m.fs.Expression(doc="Net biomass production rate (kg/s)")
    def net_biomass_production(b):
        # Biomass leaving via dewatering underflow
        # For modified_ASM2D, use TSS expression instead of X_TSS component
        if hasattr(b.dewatering.underflow_state[0], 'TSS'):
            # Use TSS expression for modified_ASM2D
            return (b.dewatering.underflow_state[0].TSS * 
                    b.dewatering.underflow.flow_vol[0])
        else:
            # Fallback: sum all particulate components
            tss_conc = sum(b.dewatering.underflow.conc_mass_comp[0, comp]
                          for comp in ["X_I", "X_S", "X_H", "X_PAO", "X_AUT", "X_PHA", "X_PP"]
                          if (0, comp) in b.dewatering.underflow.conc_mass_comp)
            return tss_conc * b.dewatering.underflow.flow_vol[0]
    
    @m.fs.Expression(doc="Solids Retention Time (days)")
    def SRT_days(b):
        # Avoid division by zero with small epsilon
        eps = 1e-10 * pyo.units.kg / pyo.units.s
        return (b.biomass_inventory / 
                (b.net_biomass_production + eps)) * (1.0 * pyo.units.day / pyo.units.s)
    
    @m.fs.Expression(doc="MLSS in AD (mg/L)")
    def AD_MLSS_mg_L(b):
        return b.AD.liquid_phase.properties_out[0].TSS * 1000.0  # Convert kg/m³ to mg/L
    
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
    
    # DIAGNOSTIC: Add lower bounds to prevent zero-collapse on tear streams
    # These bounds are intentionally modest and only serve as anti-collapse guards.
    logger.info("Adding lower bounds to tear stream flows to prevent zero collapse")
    try:
        m.fs.mixer.mbr_recycle.flow_vol[0].setlb(1e-3)   # ~86 m³/d minimum for MBR recycle
        m.fs.mixer.centrate_recycle.flow_vol[0].setlb(1e-5)  # ~0.86 m³/d minimum for centrate
    except Exception:
        pass

    # Optional: lower bounds on dewatering inlet/outlet flows to avoid numerical zero
    try:
        diag = heuristic_config.get("diagnostics", {}) if isinstance(heuristic_config, dict) else {}
        if bool(diag.get("anti_collapse_dewatering_lb", True)):
            # Apply small LBs (~0.1-1 m³/d) in m³/s units
            small_lb_s = (diag.get("dewatering_lb_m3d", 1.0) / 86400.0) * pyo.units.m**3 / pyo.units.s
            m.fs.dewatering.inlet.flow_vol[0].setlb(small_lb_s)
            m.fs.dewatering.overflow.flow_vol[0].setlb(1e-8)  # ~8.64e-4 m³/d
            m.fs.dewatering.underflow.flow_vol[0].setlb(1e-8)
    except Exception:
        # LBs are optional; skip if not supported by property package
        pass

    # Guard-rail to exclude pathological zero-flow at AD liquid outlet
    # Physically, AD liquid out should be close to liquid in (gas leaves separately)
    try:
        m.fs.ad_no_collapse = pyo.Constraint(
            expr=m.fs.AD.liquid_outlet.flow_vol[0] >= 0.9 * m.fs.AD.inlet.flow_vol[0]
        )
    except Exception:
        pass


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
    
    # ROBUSTNESS IMPROVEMENT: Temporarily relax ammonia inhibition for initial solve
    original_K_I_nh3 = None
    try:
        if hasattr(m.fs, "rxn_ADM1") and hasattr(m.fs.rxn_ADM1, "K_I_nh3"):
            original_K_I_nh3 = pyo.value(m.fs.rxn_ADM1.K_I_nh3)
            # Increase tolerance 10x to reduce inhibition during initialization
            m.fs.rxn_ADM1.K_I_nh3.set_value(original_K_I_nh3 * 10.0)
            logger.info(f"Temporarily relaxed K_I_nh3 from {original_K_I_nh3:.4f} to {original_K_I_nh3 * 10.0:.4f} for initialization")
    except Exception as e:
        logger.debug(f"Could not relax K_I_nh3: {e}")
    
    # Helper: aggressively ensure unit-level DoF == 0 by fixing AD.inlet
    def _fix_ad_inlet_from(port_src) -> None:
        try:
            # Copy scalar state vars
            try:
                ad.inlet.flow_vol[0].fix(pyo.value(port_src.flow_vol[0]))
            except Exception:
                pass
            try:
                ad.inlet.temperature[0].fix(pyo.value(port_src.temperature[0]))
            except Exception:
                pass
            try:
                ad.inlet.pressure[0].fix(pyo.value(port_src.pressure[0]))
            except Exception:
                pass

            # Copy ions if present
            try:
                if hasattr(port_src, "cations") and (0,) in port_src.cations:
                    ad.inlet.cations[0].fix(pyo.value(port_src.cations[0]))
            except Exception:
                pass
            try:
                if hasattr(port_src, "anions") and (0,) in port_src.anions:
                    ad.inlet.anions[0].fix(pyo.value(port_src.anions[0]))
            except Exception:
                pass

            # Copy component concentrations (skip H2O)
            try:
                comps = list(getattr(m.fs.props_ADM1, "component_list", []))
                for comp in comps:
                    cname = str(comp)
                    if cname == "H2O":
                        continue
                    # Guard: only if both ports expose the variable
                    try:
                        val = pyo.value(port_src.conc_mass_comp[0, cname])
                        ad.inlet.conc_mass_comp[0, cname].fix(val)
                    except Exception:
                        continue
            except Exception:
                pass
        except Exception:
            # Do not fail initialization due to state propagation issues
            return

    # Helper: unfix AD.inlet after init so flowsheet DoF stays consistent
    def _unfix_ad_inlet() -> None:
        try:
            for v in [ad.inlet.flow_vol[0], ad.inlet.temperature[0], ad.inlet.pressure[0]]:
                try:
                    v.unfix()
                except Exception:
                    pass
            # Ions
            for maybe in (getattr(ad.inlet, "cations", None), getattr(ad.inlet, "anions", None)):
                try:
                    if maybe is not None:
                        maybe[0].unfix()
                except Exception:
                    pass
            # Components
            try:
                comps = list(getattr(m.fs.props_ADM1, "component_list", []))
                for comp in comps:
                    cname = str(comp)
                    if cname == "H2O":
                        continue
                    try:
                        ad.inlet.conc_mass_comp[0, cname].unfix()
                    except Exception:
                        continue
            except Exception:
                pass
        except Exception:
            return
    try:
        # Try to make AD unit-level DoF zero by fixing inlet from mixer outlet if available, else feed
        try:
            if hasattr(m.fs, "mixer"):
                _fix_ad_inlet_from(m.fs.mixer.outlet)
            else:
                _fix_ad_inlet_from(m.fs.feed.outlet)
        except Exception:
            pass

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
        # Retry init (ensure inlet still fixed)
        ad.initialize(outlvl=idaeslog.WARNING)
        setattr(ad, "_initialized", True)
    except Exception as e:
        logger.warning(f"AD initialize still failing after fallback state: {e}")
    finally:
        # Always unfix AD.inlet state after initialization attempts
        _unfix_ad_inlet()
        
        # Restore original K_I_nh3 value after initialization
        if original_K_I_nh3 is not None:
            try:
                m.fs.rxn_ADM1.K_I_nh3.set_value(original_K_I_nh3)
                logger.info(f"Restored K_I_nh3 to original value: {original_K_I_nh3:.4f}")
            except Exception as e:
                logger.debug(f"Could not restore K_I_nh3: {e}")


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
            # Use Direct method to avoid Wegstein overshoot
            seq.options.tear_method = "Direct"
            # Do multiple direct iterations to substantially close tear streams
            # before the final global solve, avoiding large arc mismatches.
            try:
                iter_lim = int(getattr(m.fs, "config", None).sd_iter_lim) if hasattr(m.fs, "config") else 20
            except Exception:
                iter_lim = 20
            try:
                tol_val = float(getattr(m.fs, "config", None).sd_tol) if hasattr(m.fs, "config") else 1e-6
            except Exception:
                tol_val = 1e-6
            seq.options.iterLim = iter_lim
            seq.options.tol = tol_val  # Convergence tolerance (option name is 'tol')
            
            # If the environment forces Wegstein elsewhere, neutralize acceleration
            # to behave like Direct (for safety against negative tear updates)
            try:
                seq.options.accel_min = 0.0
                seq.options.accel_max = 0.0
            except Exception:
                pass
            
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

            # Important: Build the SD graph BEFORE registering tear guesses.
            # Pyomo's SequentialDecomposition expects create_graph() first so that
            # set_guesses_for() can associate guesses with the correct Ports.
            try:
                seq.create_graph(m)
            except Exception as e:
                logger.debug(f"SequentialDecomposition.create_graph failed or not needed: {e}")
            
            # Pre-initialize upstream units and AD to improve robustness
            try:
                m.fs.feed.initialize()
                propagate_state(m.fs.arc_feed_mixer)
                m.fs.mixer.initialize()
                propagate_state(m.fs.arc_mixer_AD)
                _safe_initialize_ad(m)
            except Exception as e:
                logger.debug(f"Pre-initialization before SD encountered an issue: {e}")

            # Helper: build guess dicts directly from the curated init/final ADM1 state
            # rather than reading property Vars (avoids uninitialized/negative values)
            def _build_guess_dict_from_state(state: Dict[str, float], Q: float,
                                             conc_scale_part: float = 0.8,
                                             conc_scale_sol: float = 0.8) -> Dict[str, Any]:
                # IMPORTANT: Provide plain numerics (no Pyomo units) in guesses.
                # All values here use native units of corresponding Vars (m^3/s, K, Pa, kg/m^3, kmol/m^3).
                guesses: Dict[str, Any] = {
                    "flow_vol": {0: float(Q)},
                    "temperature": {0: 308.15},
                    "pressure": {0: 101325.0},
                }
                # Ions (kmol/m3) if available in state; fall back to safe defaults
                s_cat = state.get("S_cat", 0.04)  # Default from fixed_adm1_state
                s_an = state.get("S_an", 0.026)   # Default from fixed_adm1_state
                try:
                    if s_cat is None and hasattr(m.fs.feed.properties[0], "cations"):
                        feed_cat = pyo.value(m.fs.feed.properties[0].cations)
                        if feed_cat is not None and feed_cat > 0:
                            s_cat = float(feed_cat)
                    if s_an is None and hasattr(m.fs.feed.properties[0], "anions"):
                        feed_an = pyo.value(m.fs.feed.properties[0].anions)
                        if feed_an is not None and feed_an > 0:
                            s_an = float(feed_an)
                except Exception:
                    pass
                # Always provide positive ion values
                guesses["cations"] = {0: float(max(s_cat if s_cat else 0.04, 1e-6))}
                guesses["anions"] = {0: float(max(s_an if s_an else 0.026, 1e-6))}
                # Concentrations from state dict; clamp to nonnegative
                conc_map: Dict[Any, float] = {}
                for comp in m.fs.props_ADM1.component_list:
                    cname = str(comp)
                    if cname == "H2O":
                        continue
                    # Skip ions - they're handled as cations/anions above
                    if cname in ["S_cat", "S_an"]:
                        continue
                    val = state.get(cname, None)
                    if val is None:
                        # If state didn't include this component, try feed conc as fallback
                        try:
                            feed_val = pyo.value(m.fs.feed.properties[0].conc_mass_comp[comp])
                            # Only use if it's a valid positive number
                            if feed_val is not None and feed_val > 0:
                                val = float(feed_val)
                            else:
                                val = 1e-6  # Safe default
                        except Exception:
                            val = 1e-6  # Safe default
                    # Ensure val is positive before scaling
                    val = max(float(val), 1e-10)
                    scale = conc_scale_part if cname.startswith("X_") else conc_scale_sol
                    conc_map[(0, comp)] = float(max(val * scale, 1e-10))
                if conc_map:
                    guesses["conc_mass_comp"] = conc_map
                return guesses

            # Set initial guesses for tear streams to avoid zero-flow convergence
            try:
                # Set heuristic tear selection for better convergence
                seq.options.select_tear_method = "heuristic"

                # Get feed flow for scaling guesses
                feed_Q = pyo.value(m.fs.feed.properties[0].flow_vol)  # m³/s
                logger.info(f"Feed flow for tear initialization: {feed_Q:.6f} m³/s")

                # For low TSS MBR configuration - set guesses on mixer inlet ports (destination of tear arcs)
                if hasattr(m.fs, 'MBR') and hasattr(m.fs, 'translator_ASM_AD_mbr') and hasattr(m.fs, 'mixer'):
                    # Expect ~4Q recycle for 5Q operation
                    Q_recycle_guess = 4.0 * feed_Q
                    mbr_recycle_port = m.fs.mixer.mbr_recycle
                    # Use physically correct concentration factors:
                    # Particulates: 5/4 = 1.25 (5Q in, 4Q return, 99.9% rejection)
                    # Solubles: 1.0 (pass through freely, same concentration everywhere)
                    # Build from curated init state if available, else fallback to feed-based
                    init_state = getattr(m.fs, "_init_adm1_state", {}) or {}
                    if init_state:
                        mbr_guess = _build_guess_dict_from_state(init_state, Q_recycle_guess,
                                                                 conc_scale_part=1.25, conc_scale_sol=1.0)
                    else:
                        # Last resort fallback
                        mbr_guess = _build_guess_dict_from_state({}, Q_recycle_guess,
                                                                 conc_scale_part=1.25, conc_scale_sol=1.0)
                    # Register guesses with SD so they persist across unit initialization
                    seq.set_guesses_for(mbr_recycle_port, mbr_guess)
                    logger.info(
                        f"Registered MBR recycle tear guess via SD: {Q_recycle_guess:.6f} m³/s"
                    )

                # For dewatering centrate recycle
                if hasattr(m.fs, 'dewatering') and hasattr(m.fs, 'translator_centrate_AD') and hasattr(m.fs, 'mixer'):
                    p_dewat = pyo.value(m.fs.dewatering.p_dewat)
                    # Heuristic: ~8% of 5Q goes to dewatering, centrate is (1-p_dewat) of that
                    Q_to_dewat = 0.08 * 5.0 * feed_Q
                    Q_centrate_guess = (1 - p_dewat) * Q_to_dewat
                    centrate_port = m.fs.mixer.centrate_recycle
                    # Centrate has very low particulates (95% capture) but moderate solubles
                    init_state = getattr(m.fs, "_init_adm1_state", {}) or {}
                    if init_state:
                        cent_guess = _build_guess_dict_from_state(init_state, Q_centrate_guess,
                                                                  conc_scale_part=0.01, conc_scale_sol=0.2)
                    else:
                        cent_guess = _build_guess_dict_from_state({}, Q_centrate_guess,
                                                                  conc_scale_part=0.01, conc_scale_sol=0.2)
                    seq.set_guesses_for(centrate_port, cent_guess)
                    logger.info(
                        f"Registered centrate recycle tear guess via SD: {Q_centrate_guess:.6f} m³/s"
                    )

                logger.info("Tear stream initialization registered with SD")

            except Exception as e:
                logger.warning(f"Could not register recycle tear guesses: {e}")
                # Continue anyway - initialization may still work
            
            # Optional: quick snapshot before SD
            try:
                _log_port_state(m.fs.feed.outlet, "feed.outlet (pre-SD)")
                if hasattr(m.fs, 'mixer'):
                    if hasattr(m.fs.mixer, 'mbr_recycle'):
                        _log_port_state(m.fs.mixer.mbr_recycle, "mixer.mbr_recycle (pre-SD)")
                    if hasattr(m.fs.mixer, 'centrate_recycle'):
                        _log_port_state(m.fs.mixer.centrate_recycle, "mixer.centrate_recycle (pre-SD)")
            except Exception:
                pass

            # Proactively propagate known upstream states to downstream units (non-tear arcs)
            # to avoid zero-flow initialization in units outside the pre-init path.
            try:
                # Common arcs present in both configurations
                if hasattr(m.fs, 'arc_AD_translator'):
                    propagate_state(m.fs.arc_AD_translator)
                if hasattr(m.fs, 'arc_translator_dewatering'):
                    propagate_state(m.fs.arc_translator_dewatering)
                if hasattr(m.fs, 'arc_dewatering_translator'):
                    propagate_state(m.fs.arc_dewatering_translator)

                # Low TSS MBR configuration specific arcs
                if hasattr(m.fs, 'arc_AD_splitter'):
                    propagate_state(m.fs.arc_AD_splitter)
                if hasattr(m.fs, 'arc_splitter_translator'):
                    propagate_state(m.fs.arc_splitter_translator)
                if hasattr(m.fs, 'arc_translator_MBR'):
                    propagate_state(m.fs.arc_translator_MBR)
                if hasattr(m.fs, 'arc_MBR_translator'):
                    propagate_state(m.fs.arc_MBR_translator)
                if hasattr(m.fs, 'arc_centrate_translator'):
                    propagate_state(m.fs.arc_centrate_translator)
            except Exception as e:
                logger.debug(f"Optional pre-SD propagate_state skipped: {e}")

            # Phased initialization strategy with MLSS constraint handling
            # Phase 1: Temporarily deactivate MLSS constraints and fix splitter
            mlss_constraints_deactivated = False
            if hasattr(m.fs, 'eq_AD_mlss_lower') and hasattr(m.fs, 'eq_AD_mlss_upper'):
                try:
                    m.fs.eq_AD_mlss_lower.deactivate()
                    m.fs.eq_AD_mlss_upper.deactivate()
                    mlss_constraints_deactivated = True
                    logger.info("Phase 1: Temporarily deactivated MLSS constraints for initialization")
                except Exception as e:
                    logger.debug(f"Could not deactivate MLSS constraints: {e}")
            
            if hasattr(m.fs, 'ad_splitter'):
                # Calculate expected split based on target MLSS (12.5 kg/m³ midpoint)
                # With typical yield ~0.1 kg TSS/kg COD and SRT 30 days
                # Split fraction ≈ 1/SRT for steady state
                expected_split = 1.0 / 30.0  # ≈ 0.033 for 30-day SRT
                try:
                    m.fs.ad_splitter.split_fraction[0, "to_dewatering"].fix(expected_split)
                    logger.info(f"Phase 1: Fixed ad_splitter dewatering fraction to {expected_split:.3f}")
                except Exception as e:
                    logger.debug(f"Could not fix splitter fraction: {e}")
            
            # Phase 2: Run Sequential Decomposition with relaxed constraints
            seq.run(m, _init_unit_callback)
            
            # Phase 3: Release splitter and reactivate MLSS constraints
            if hasattr(m.fs, 'ad_splitter'):
                try:
                    m.fs.ad_splitter.split_fraction[0, "to_dewatering"].unfix()
                    logger.info("Phase 3: Released ad_splitter fraction for final solve")
                except Exception as e:
                    logger.debug(f"Could not unfix splitter fraction: {e}")
            
            # Reactivate MLSS constraints after initialization
            if mlss_constraints_deactivated:
                try:
                    m.fs.eq_AD_mlss_lower.activate()
                    m.fs.eq_AD_mlss_upper.activate()
                    logger.info("Phase 3: Reactivated MLSS constraints for final solve")
                except Exception as e:
                    logger.debug(f"Could not reactivate MLSS constraints: {e}")

            # Snapshot of key flows post-initialization for diagnostics
            try:
                _log_key_flows(m, header="post-initialize")
            except Exception:
                pass

            # Optional diagnostics after SD
            try:
                if hasattr(m.fs, 'config') and getattr(m.fs.config, 'enable_diagnostics', False):
                    dt = DiagnosticsToolbox(m)
                    dt.report_structural_issues()
                    dt.report_numerical_issues()
                    if getattr(m.fs.config, 'dump_near_zero_vars', False):
                        dt.display_variables_with_value_near_zero()
            except Exception as e:
                logger.debug(f"Diagnostics toolbox (post-SD) skipped: {e}")

            # After initialization, gradually ramp to final state
            if hasattr(m.fs, "_final_adm1_state") and hasattr(m.fs, "_init_adm1_state"):
                logger.info("Ramping from init to final feed state")
                
                # Get solver for intermediate solves
                solver = get_solver()
                
                # Components to ramp gradually (all potentially inhibitory components)
                ramp_components = [
                    "S_ac", "S_pro", "S_bu", "S_va",  # VFAs - can cause pH drop
                    "S_co2", "S_IC",  # Carbon dioxide system - affects pH
                    "S_IN", "S_nh4",  # Nitrogen - ammonia inhibition
                    "S_h2", "S_ch4",  # Dissolved gases
                    "S_cat", "S_an",  # Ionic balance affects pH
                    "S_H"  # Direct pH control
                ]
                
                # Configurable ramp steps (can be set in heuristic_config)
                init_state = m.fs._init_adm1_state
                final_state = m.fs._final_adm1_state
                
                # Get ramp steps from config or use default
                # Use more steps for better convergence with inhibitory feeds
                if hasattr(m.fs, "_heuristic_config"):
                    default_steps = m.fs._heuristic_config.get("ramp_steps", 
                        [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
                else:
                    default_steps = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
                
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

            # Optional: snapshot after SD
            try:
                if hasattr(m.fs, 'AD'):
                    _log_port_state(m.fs.AD.inlet, "AD.inlet (post-SD)")
                    _log_port_state(m.fs.AD.liquid_outlet, "AD.liquid_outlet (post-SD)")
                    _log_port_state(m.fs.AD.vapor_outlet, "AD.vapor_outlet (post-SD)")
                if hasattr(m.fs, 'MBR'):
                    _log_port_state(m.fs.MBR.permeate, "MBR.permeate (post-SD)")
                    _log_port_state(m.fs.MBR.retentate, "MBR.retentate (post-SD)")
                if hasattr(m.fs, 'dewatering'):
                    _log_port_state(m.fs.dewatering.overflow, "dewatering.overflow (post-SD)")
                    _log_port_state(m.fs.dewatering.underflow, "dewatering.underflow (post-SD)")
            except Exception:
                pass

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


def audit_translator_nitrogen(m: pyo.ConcreteModel, logger) -> None:
    """
    P1: Audit nitrogen conservation across all translators.
    
    This function checks if nitrogen is being properly mapped between
    ADM1 (S_IN) and ASM2D (S_NH4) in all translators. Scaling issues
    or incorrect mapping can cause artificial TAN accumulation.
    """
    translator_pairs = [
        ("translator_AD_ASM", "S_IN", "S_NH4"),
        ("translator_ASM_AD_mbr", "S_NH4", "S_IN"),
        ("translator_dewatering_ASM", "S_IN", "S_NH4"),
        ("translator_centrate_AD", "S_NH4", "S_IN")
    ]
    
    issues_found = False
    
    for trans_name, in_comp, out_comp in translator_pairs:
        if hasattr(m.fs, trans_name):
            trans = getattr(m.fs, trans_name)
            try:
                # Get inlet/outlet nitrogen concentrations
                if hasattr(trans, "properties_in") and hasattr(trans, "properties_out"):
                    n_in = pyo.value(trans.properties_in[0].conc_mass_comp.get(in_comp, 0))
                    n_out = pyo.value(trans.properties_out[0].conc_mass_comp.get(out_comp, 0))
                elif hasattr(trans, "inlet") and hasattr(trans, "outlet"):
                    n_in = pyo.value(trans.inlet.conc_mass_comp.get(in_comp, 0))
                    n_out = pyo.value(trans.outlet.conc_mass_comp.get(out_comp, 0))
                else:
                    continue
                
                # Check for scaling issues
                if n_in > 1e-10:
                    ratio = n_out / n_in
                    
                    if ratio > 2.0 or ratio < 0.5:
                        logger.warning(
                            f"P1 CRITICAL: {trans_name} nitrogen scaling issue! "
                            f"{in_comp}={n_in:.4f} → {out_comp}={n_out:.4f} kg/m³ "
                            f"(ratio={ratio:.2f}, expected ~1.0)"
                        )
                        issues_found = True
                    else:
                        logger.debug(
                            f"P1: {trans_name} N mapping OK: "
                            f"{in_comp}={n_in:.4f} → {out_comp}={n_out:.4f} kg/m³"
                        )
                else:
                    logger.debug(f"P1: {trans_name} has near-zero nitrogen")
                    
            except Exception as e:
                logger.debug(f"P1: Could not audit {trans_name}: {e}")
    
    if issues_found:
        logger.error(
            "P1: Translator nitrogen mapping issues detected! "
            "This is likely causing the TAN accumulation."
        )
    else:
        logger.info("P1: All translator nitrogen mappings appear correct")
    
    return None


def solve_flowsheet(
    m: pyo.ConcreteModel,
    tee: bool = True,
    raise_on_failure: bool = True
) -> Dict[str, Any]:
    """
    Solve the flowsheet and return results.
    """
    solver = get_solver()
    
    # Add robust solver options for difficult ADM1 problems with pH calculations
    # Updated solver configuration per IDAES best practices
    solver.options["nlp_scaling_method"] = "user-scaling"  # Use user-provided scaling
    solver.options["max_iter"] = 500                       # Sufficient for complex systems
    solver.options["mu_strategy"] = "adaptive"
    solver.options["mu_init"] = 1e-8                       # Per Codex recommendation
    solver.options["bound_push"] = 1e-8                    # Relaxed for stiff recycle systems
    solver.options["bound_frac"] = 0.01                    # Fraction of bound distance
    solver.options["bound_relax_factor"] = 0               # No bound relaxation
    solver.options["tol"] = 1e-8                           # Start tight, can relax to 1e-6
    solver.options["compl_inf_tol"] = 1e-6                 # Complementarity tolerance
    
    # ENHANCED OPTIONS for infeasible/difficult problems
    solver.options["acceptable_tol"] = 1e-6                # Fallback tolerance
    solver.options["acceptable_iter"] = 15                 # Allow acceptable point after 15 iters
    solver.options["expect_infeasible_problem"] = "yes"    # Prepare for potential infeasibility
    solver.options["print_info_string"] = "yes"            # More diagnostic output
    
    # Try to use HSL linear solver if available (ma57 or ma27)
    try:
        solver.options["linear_solver"] = "ma57"
    except:
        try:
            solver.options["linear_solver"] = "mumps"
        except:
            pass  # Use default linear solver
    
    # Warm-start options for robustness on re-solves
    solver.options["warm_start_init_point"] = "yes"
    solver.options["warm_start_bound_push"] = 1e-8
    
    # Apply solver options from config if available (may override defaults)
    if hasattr(m.fs, 'config') and hasattr(m.fs.config, 'solver_options') and m.fs.config.solver_options:
        for key, value in m.fs.config.solver_options.items():
            solver.options[key] = value
    
    # Route solver output to IDAES logger instead of stdout
    solve_logger = idaeslog.getSolveLogger("watertap.ad")
    with idaeslog.solver_log(solve_logger, idaeslog.INFO) as slc:
        results = solver.solve(m, tee=slc.tee if tee else False)

    if not pyo.check_optimal_termination(results):
        # Optional diagnostics on solve failure
        try:
            if hasattr(m.fs, 'config') and getattr(m.fs.config, 'enable_diagnostics', False):
                dt = DiagnosticsToolbox(m)
                dt.report_structural_issues()
                dt.report_numerical_issues()
                dt.display_infeasible_constraints()
        except Exception as e:
            logger.debug(f"Diagnostics toolbox (solve failure) skipped: {e}")
        if raise_on_failure:
            raise RuntimeError(f"Solve failed: {results.solver.termination_condition}")
        else:
            logger.warning(f"Solve failed: {results.solver.termination_condition}")
    
    # Enhanced biogas diagnostics
    if hasattr(m.fs, 'AD'):
        try:
            logger.info("=== AD Biogas Diagnostics ===")
            # Check pH and inhibition factors
            try:
                ad_ph = pyo.value(m.fs.AD.liquid_phase.properties_out[0].pH)
            except:
                # Calculate pH from S_H if pH property not available
                # In Modified ADM1 here, S_H is handled via conc_mass_comp with kg/m^3 units.
                # Since MW(H+) ≈ 1 g/mol, kg/m^3 numerically equals g/L, which equals mol/L.
                # Therefore, pH = -log10(S_H[kg/m^3]) without any additional factor.
                import math
                try:
                    S_H = pyo.value(m.fs.AD.liquid_phase.properties_out[0].conc_mass_comp["S_H"])
                except:
                    S_H = 1e-7  # Default pH 7
                # Guard against log of non-positive due to numerical noise
                S_H_eff = max(S_H, 1e-20)
                ad_ph = -math.log10(S_H_eff)
            
            try:
                ad_tss = pyo.value(m.fs.AD.liquid_phase.properties_out[0].TSS)
            except:
                ad_tss = 0
            
            logger.info(f"AD pH: {ad_ph:.2f}")
            logger.info(f"AD TSS: {ad_tss:.1f} mg/L")
            
            # Check if vapor outlet exists and is connected
            if hasattr(m.fs.AD, 'vapor_outlet'):
                vapor_flow = pyo.value(m.fs.AD.vapor_outlet.flow_vol[0])
                logger.info(f"Vapor outlet flow: {vapor_flow:.6f} m³/s ({vapor_flow*86400:.2f} m³/d)")
                
                # Check gas composition
                try:
                    ch4_conc = pyo.value(m.fs.AD.vapor_outlet.conc_mass_comp[0, "S_ch4"])
                    co2_conc = pyo.value(m.fs.AD.vapor_outlet.conc_mass_comp[0, "S_co2"])
                    h2_conc = pyo.value(m.fs.AD.vapor_outlet.conc_mass_comp[0, "S_h2"])
                    logger.info(f"Gas composition - CH4: {ch4_conc:.3f}, CO2: {co2_conc:.3f}, H2: {h2_conc:.6f} kg/m³")
                except Exception as e:
                    logger.warning(f"Could not get gas composition: {e}")
                    
                # Check biomass concentrations
                try:
                    x_ac = pyo.value(m.fs.AD.liquid_phase.properties_out[0].conc_mass_comp["X_ac"])
                    x_h2 = pyo.value(m.fs.AD.liquid_phase.properties_out[0].conc_mass_comp["X_h2"])
                    logger.info(f"Methanogen biomass - X_ac: {x_ac:.3f}, X_h2: {x_h2:.3f} kg/m³")
                except Exception as e:
                    logger.debug(f"Could not get biomass concentrations: {e}")
                    
                # Check VFA levels in DIGESTATE (not feed)
                try:
                    s_ac = pyo.value(m.fs.AD.liquid_phase.properties_out[0].conc_mass_comp["S_ac"])
                    s_pro = pyo.value(m.fs.AD.liquid_phase.properties_out[0].conc_mass_comp["S_pro"])
                    s_bu = pyo.value(m.fs.AD.liquid_phase.properties_out[0].conc_mass_comp["S_bu"])
                    s_va = pyo.value(m.fs.AD.liquid_phase.properties_out[0].conc_mass_comp["S_va"])
                    total_vfa = s_ac + s_pro + s_bu + s_va
                    logger.info(f"DIGESTATE VFA levels - Acetate: {s_ac:.3f}, Propionate: {s_pro:.3f}, Butyrate: {s_bu:.3f}, Valerate: {s_va:.3f} kg/m³")
                    logger.info(f"DIGESTATE Total VFA: {total_vfa:.3f} kg/m³")
                except Exception as e:
                    logger.debug(f"Could not get VFA levels: {e}")
                    
                # Check DIGESTATE ammonia (feed + protein degradation - biomass assimilation)
                try:
                    s_in = pyo.value(m.fs.AD.liquid_phase.properties_out[0].conc_mass_comp["S_IN"])
                    logger.info(f"DIGESTATE total ammonia nitrogen: {s_in:.3f} kg N/m³ = {s_in*1000:.1f} mg N/L")
                except Exception as e:
                    logger.debug(f"Could not get ammonia level: {e}")
                    
                # CRITICAL: Extract ALL inhibition factors from reaction block
                try:
                    logger.info("=== INHIBITION FACTORS (0=complete inhibition, 1=no inhibition) ===")
                    rxn = m.fs.AD.liquid_phase.reactions[0]

                    # Complete list of inhibition factors from Modified ADM1 (confirmed via DeepWiki)
                    inhibition_vars = [
                        # pH inhibition (critical for methanogens) — these are EXPONENTS in the model
                        ("I_pH_aa", "pH inhibition on amino acid degraders"),
                        ("I_pH_ac", "pH inhibition on ACETOCLASTIC METHANOGENS - CRITICAL"),
                        ("I_pH_h2", "pH inhibition on HYDROGENOTROPHIC METHANOGENS - CRITICAL"),

                        # Nutrient limitation (direct 0–1 multipliers)
                        ("I_IN_lim", "Inorganic nitrogen limitation"),
                        ("I_IP_lim", "Inorganic phosphorus limitation"),

                        # Hydrogen inhibition (direct 0–1 multipliers)
                        ("I_h2_fa", "H2 inhibition on fatty acid degraders"),
                        ("I_h2_c4", "H2 inhibition on valerate/butyrate degraders"),
                        ("I_h2_pro", "H2 inhibition on propionate degraders"),

                        # Ammonia inhibition (direct 0–1 multipliers)
                        ("I_nh3", "FREE AMMONIA inhibition - CRITICAL"),

                        # H2S inhibition (direct 0–1 multipliers; often unity if Z_h2s=0)
                        ("I_h2s_ac", "H2S inhibition on acetoclastic methanogens"),
                        ("I_h2s_c4", "H2S inhibition on C4 degraders"),
                        ("I_h2s_h2", "H2S inhibition on hydrogenotrophic methanogens"),
                        ("I_h2s_pro", "H2S inhibition on propionate degraders"),
                    ]

                    pH_exponent_keys = {"I_pH_aa", "I_pH_ac", "I_pH_h2"}

                    for var_name, description in inhibition_vars:
                        try:
                            if hasattr(rxn, var_name):
                                raw_val = pyo.value(getattr(rxn, var_name))
                                if var_name in pH_exponent_keys:
                                    # Convert exponent to final 0–1 factor used by the kinetics
                                    fac = math.exp(raw_val)
                                    fac = max(0.0, min(1.0, fac))
                                    if fac < 0.9:
                                        logger.warning(
                                            f"  {var_name}: factor={fac:.4e} (exp={raw_val:.3f}) - {description} ***INHIBITED***"
                                        )
                                    else:
                                        logger.info(
                                            f"  {var_name}: factor={fac:.4f} (exp={raw_val:.3f}) - {description}"
                                        )
                                else:
                                    fac = max(0.0, min(1.0, raw_val))
                                    if fac < 0.9:
                                        logger.warning(f"  {var_name}: {fac:.4f} - {description} ***INHIBITED***")
                                    else:
                                        logger.info(f"  {var_name}: {fac:.4f} - {description}")
                        except Exception:
                            pass
                    
                    # Also check overall reaction rates for methanogens
                    try:
                        if hasattr(rxn, "rate"):
                            for i, rate_var in rxn.rate.items():
                                if "X_ac" in str(i) or "X_h2" in str(i):
                                    rate_val = pyo.value(rate_var)
                                    logger.info(f"  Reaction rate for {i}: {rate_val:.6f} kg/m³/d")
                    except:
                        pass
                        
                    logger.info("=== END INHIBITION FACTORS ===")
                except Exception as e:
                    logger.warning(f"Could not extract inhibition factors: {e}")
            else:
                logger.warning("AD vapor outlet not found - biogas production will be zero!")
            logger.info("=== End Biogas Diagnostics ===")
        except Exception as e:
            logger.warning(f"Biogas diagnostics failed: {e}")
    
    # Extract comprehensive digester performance metrics
    digester_metrics = {}
    
    # Extract basic biogas metrics
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
    
    # Extract digestate characteristics
    if hasattr(m.fs, 'AD'):
        try:
            # Get digestate pH (calculate from S_H if pH not available)
            try:
                digester_metrics["digestate_pH"] = pyo.value(m.fs.AD.liquid_phase.properties_out[0].pH)
            except:
                # Calculate pH from S_H mass concentration (kg/m^3 ≡ g/L ≡ mol/L for H+)
                import math
                try:
                    S_H = pyo.value(m.fs.AD.liquid_phase.properties_out[0].conc_mass_comp["S_H"])
                except:
                    S_H = 1e-7  # Default pH 7
                S_H_eff = max(S_H, 1e-20)
                digester_metrics["digestate_pH"] = -math.log10(S_H_eff)
                # Also report the pH we computed explicitly for cross-checking
                digester_metrics["digestate_pH_from_S_H"] = digester_metrics["digestate_pH"]
            
            # Get digestate VFAs (kg/m³)
            vfa_components = ["S_ac", "S_pro", "S_bu", "S_va"]
            digester_metrics["digestate_VFAs_kg_m3"] = {}
            total_vfa = 0
            for vfa in vfa_components:
                try:
                    vfa_conc = pyo.value(m.fs.AD.liquid_phase.properties_out[0].conc_mass_comp[vfa])
                    digester_metrics["digestate_VFAs_kg_m3"][vfa] = vfa_conc
                    total_vfa += vfa_conc
                except:
                    pass
            digester_metrics["digestate_total_VFA_kg_m3"] = total_vfa
            
            # Get digestate ammonia
            digester_metrics["digestate_TAN_kg_N_m3"] = pyo.value(
                m.fs.AD.liquid_phase.properties_out[0].conc_mass_comp["S_IN"]
            )
            digester_metrics["digestate_TAN_mg_N_L"] = digester_metrics["digestate_TAN_kg_N_m3"] * 1000
            
            # Get biomass concentrations
            biomass_components = ["X_ac", "X_h2", "X_su", "X_aa", "X_fa", "X_c4", "X_pro"]
            digester_metrics["biomass_kg_m3"] = {}
            for bio in biomass_components:
                try:
                    digester_metrics["biomass_kg_m3"][bio] = pyo.value(
                        m.fs.AD.liquid_phase.properties_out[0].conc_mass_comp[bio]
                    )
                except:
                    pass
            
            # Get ALL inhibition factors from reaction block
            if hasattr(m.fs.AD.liquid_phase, 'reactions'):
                rxn = m.fs.AD.liquid_phase.reactions[0]
                digester_metrics["inhibition_factors"] = {}
                digester_metrics["inhibition_exponents_raw"] = {}

                # List of inhibition terms to report
                inhibition_list = [
                    "I_pH_aa", "I_pH_ac", "I_pH_h2",  # pH inhibition (stored as exponent in model)
                    "I_IN_lim", "I_IP_lim",            # Nutrient limitation (0–1)
                    "I_h2_fa", "I_h2_c4", "I_h2_pro", # H2 inhibition (0–1)
                    "I_nh3",                            # Ammonia inhibition (0–1)
                    "I_h2s_ac", "I_h2s_c4", "I_h2s_h2", "I_h2s_pro",  # H2S (0–1)
                ]

                pH_exponent_keys = {"I_pH_aa", "I_pH_ac", "I_pH_h2"}

                for inhib in inhibition_list:
                    try:
                        if hasattr(rxn, inhib):
                            raw_val = pyo.value(getattr(rxn, inhib))
                            if inhib in pH_exponent_keys:
                                # Save raw exponent and 0–1 factor
                                digester_metrics["inhibition_exponents_raw"][inhib] = float(raw_val)
                                fac = math.exp(raw_val)
                                digester_metrics["inhibition_factors"][inhib] = float(max(0.0, min(1.0, fac)))
                            else:
                                digester_metrics["inhibition_factors"][inhib] = float(max(0.0, min(1.0, raw_val)))
                    except Exception:
                        pass

                # Flag critical inhibitions based on final 0–1 factors
                critical_inhibitions = []
                for name, value in digester_metrics["inhibition_factors"].items():
                    try:
                        if float(value) < 0.5:  # Severe inhibition if < 0.5
                            critical_inhibitions.append(f"{name}={float(value):.3f}")
                    except Exception:
                        continue
                digester_metrics["critical_inhibitions"] = critical_inhibitions
            
            # Get digestate TSS and VSS
            digester_metrics["digestate_TSS_mg_L"] = pyo.value(m.fs.AD.liquid_phase.properties_out[0].TSS)
            digester_metrics["digestate_VSS_mg_L"] = pyo.value(m.fs.AD.liquid_phase.properties_out[0].VSS)
            
            # Add detailed biomass composition for MLSS calculation
            biomass_components = [
                "X_su", "X_aa", "X_fa", "X_c4", "X_pro", "X_ac", "X_h2",  # Active biomass
                "X_ch", "X_pr", "X_li", "X_I", "X_P", "X_S"  # Composite particulates
            ]
            digester_metrics["biomass_composition_kg_m3"] = {}
            total_biomass_kg_m3 = 0
            for comp in biomass_components:
                try:
                    conc = pyo.value(m.fs.AD.liquid_phase.properties_out[0].conc_mass_comp[comp])
                    digester_metrics["biomass_composition_kg_m3"][comp] = conc
                    total_biomass_kg_m3 += conc
                except:
                    pass
            digester_metrics["total_biomass_kg_m3"] = total_biomass_kg_m3
            digester_metrics["MLSS_mg_L"] = digester_metrics["digestate_TSS_mg_L"]
            digester_metrics["MLVSS_mg_L"] = digester_metrics["digestate_VSS_mg_L"]
            
        except Exception as e:
            logger.warning(f"Could not extract all digester metrics: {e}")
    
    # Write digester metrics to a log file for inspection
    try:
        import json
        import datetime
        import os
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        # Use relative path that works on both Windows and Linux
        log_dir = "simulation_logs"
        os.makedirs(log_dir, exist_ok=True)
        log_filename = os.path.join(log_dir, f"digester_metrics_{timestamp}.json")
        with open(log_filename, 'w') as f:
            json.dump(digester_metrics, f, indent=2, default=str)
        logger.info(f"Digester metrics written to {log_filename}")
    except Exception as e:
        logger.warning(f"Could not write digester metrics to file: {e}")
    
    # Calculate COD removal based on biogas production
    cod_removal_info = {}
    try:
        # Get feed COD
        feed_flow_m3d = pyo.value(m.fs.feed.properties[0].flow_vol) * 86400  # m³/d
        # Try to get COD from feed state
        try:
            feed_cod_mg_l = pyo.value(m.fs.feed.properties[0].COD) * 1000  # Convert kg/m³ to mg/L
        except:
            # Use basis_of_design if available
            basis_of_design = getattr(m.fs, 'basis_of_design', None)
            feed_cod_mg_l = basis_of_design.get("cod_mg_l", 50000) if basis_of_design else 50000
        
        feed_cod_kg_d = feed_flow_m3d * (feed_cod_mg_l / 1000)  # kg COD/d
        
        # Calculate COD to methane using volumetric basis
        # 0.35 m³ CH4 per kg COD removed (at STP)
        ch4_m3d = biogas_m3d * ch4_frac if ch4_frac else 0
        cod_to_ch4_kg_d = ch4_m3d / 0.35  # kg COD/d converted to CH4
        
        cod_removal_pct = 100 * cod_to_ch4_kg_d / feed_cod_kg_d if feed_cod_kg_d > 0 else 0
        
        cod_removal_info = {
            "feed_cod_mg_l": feed_cod_mg_l,
            "feed_cod_kg_d": feed_cod_kg_d,
            "ch4_production_m3d": ch4_m3d,
            "cod_to_ch4_kg_d": cod_to_ch4_kg_d,
            "cod_removal_percent": cod_removal_pct
        }
    except Exception as e:
        logger.warning(f"Could not calculate COD removal: {e}")
    
    output = {
        "solver_status": str(results.solver.termination_condition),
        "biogas_production_m3d": biogas_m3d,
        "methane_fraction": ch4_frac,
        "cod_removal": cod_removal_info,
        "digester_performance": digester_metrics,
    }
    
    # Add HRT metrics - both effective and design
    hrt_info = {}
    try:
        # Get AD volume (m³)
        ad_volume_m3 = pyo.value(m.fs.AD.volume_liquid[0]) if hasattr(m.fs.AD, "volume_liquid") else 3400
        
        # Get feed flow (m³/d)
        feed_flow_m3d = pyo.value(m.fs.feed.properties[0].flow_vol) * 86400
        
        # Get AD inlet flow (includes recycles) (m³/d)
        ad_inlet_flow_m3d = pyo.value(m.fs.AD.inlet.flow_vol[0]) * 86400
        
        # Calculate HRTs
        design_hrt_days = ad_volume_m3 / feed_flow_m3d if feed_flow_m3d > 0 else None
        effective_hrt_days = ad_volume_m3 / ad_inlet_flow_m3d if ad_inlet_flow_m3d > 0 else None
        recycle_ratio = ad_inlet_flow_m3d / feed_flow_m3d if feed_flow_m3d > 0 else None
        
        hrt_info = {
            "ad_volume_m3": ad_volume_m3,
            "feed_flow_m3d": feed_flow_m3d,
            "ad_inlet_flow_m3d": ad_inlet_flow_m3d,
            "design_hrt_days": design_hrt_days,
            "effective_hrt_days": effective_hrt_days,
            "recycle_ratio": recycle_ratio
        }
    except Exception as e:
        logger.warning(f"Could not calculate HRT metrics: {e}")
    
    output["hrt_metrics"] = hrt_info
    
    # Add comprehensive biomass metrics (MLSS, SRT, net yield)
    biomass_metrics = {}
    try:
        # Get biomass concentrations at digester outlet
        ad_tss_mg_l = pyo.value(m.fs.AD.liquid_phase.properties_out[0].TSS)
        ad_vss_mg_l = pyo.value(m.fs.AD.liquid_phase.properties_out[0].VSS)
        ad_iss_mg_l = ad_tss_mg_l - ad_vss_mg_l  # Inorganic suspended solids
        
        # MLSS is the mixed liquor suspended solids (TSS in the digester)
        mlss_mg_l = ad_tss_mg_l
        mlvss_mg_l = ad_vss_mg_l
        
        # Get biomass inventory in digester (kg)
        ad_volume_m3 = pyo.value(m.fs.AD.volume_liquid[0]) if hasattr(m.fs.AD, "volume_liquid") else 3400
        biomass_inventory_kg = ad_volume_m3 * (ad_tss_mg_l / 1000)  # kg TSS
        biomass_inventory_vss_kg = ad_volume_m3 * (ad_vss_mg_l / 1000)  # kg VSS
        
        # Get sludge wasting rate (kg/d)
        # From dewatering unit if present
        sludge_wasting_kg_d = 0
        if hasattr(m.fs, "dewatering"):
            try:
                # Sludge flow rate (m³/d)
                sludge_flow_m3d = pyo.value(m.fs.dewatering.liquid_outlet.flow_vol[0]) * 86400
                # TSS in sludge (mg/L)
                sludge_tss_mg_l = pyo.value(m.fs.dewatering.liquid_outlet.conc_mass_comp[0, "X_TSS"]) * 1000
                sludge_wasting_kg_d = sludge_flow_m3d * (sludge_tss_mg_l / 1000)
            except:
                try:
                    # Alternative: use cake outlet from thickener
                    cake_flow = pyo.value(m.fs.thickener.underflow.flow_vol[0]) * 86400
                    cake_tss = pyo.value(m.fs.thickener.underflow.TSS[0])
                    sludge_wasting_kg_d = cake_flow * (cake_tss / 1000)
                except:
                    pass
        
        # Calculate SRT (days)
        srt_days = biomass_inventory_kg / sludge_wasting_kg_d if sludge_wasting_kg_d > 0 else None
        
        # Calculate net biomass yield (kg TSS/kg COD)
        # Get COD applied
        feed_flow_m3d = pyo.value(m.fs.feed.properties[0].flow_vol) * 86400
        try:
            feed_cod_mg_l = pyo.value(m.fs.feed.properties[0].COD) * 1000
        except:
            basis_of_design = getattr(m.fs, 'basis_of_design', None)
            feed_cod_mg_l = basis_of_design.get("cod_mg_l", 50000) if basis_of_design else 50000
        
        cod_applied_kg_d = feed_flow_m3d * (feed_cod_mg_l / 1000)
        
        # Get COD removed (from methane production)
        ch4_m3d = biogas_m3d * ch4_frac if (biogas_m3d and ch4_frac) else 0
        cod_removed_kg_d = ch4_m3d / 0.35  # 0.35 m³ CH4/kg COD
        
        # Calculate net yields
        net_yield_per_cod_applied = sludge_wasting_kg_d / cod_applied_kg_d if cod_applied_kg_d > 0 else None
        net_yield_per_cod_removed = sludge_wasting_kg_d / cod_removed_kg_d if cod_removed_kg_d > 0 else None
        
        # Get detailed biomass composition (all X_ components)
        biomass_composition = {}
        particulate_components = [
            "X_su", "X_aa", "X_fa", "X_c4", "X_pro", "X_ac", "X_h2",  # Active biomass
            "X_ch", "X_pr", "X_li", "X_I", "X_P", "X_S"  # Composite particulates
        ]
        total_biomass_mg_l = 0
        for comp in particulate_components:
            try:
                conc = pyo.value(m.fs.AD.liquid_phase.properties_out[0].conc_mass_comp[comp]) * 1000  # mg/L
                biomass_composition[comp] = conc
                total_biomass_mg_l += conc
            except:
                pass
        
        # Calculate active biomass fraction
        active_biomass = ["X_su", "X_aa", "X_fa", "X_c4", "X_pro", "X_ac", "X_h2"]
        active_biomass_mg_l = sum(biomass_composition.get(comp, 0) for comp in active_biomass)
        active_fraction = active_biomass_mg_l / total_biomass_mg_l if total_biomass_mg_l > 0 else 0
        
        biomass_metrics = {
            "mlss_mg_l": mlss_mg_l,
            "mlvss_mg_l": mlvss_mg_l,
            "mliss_mg_l": ad_iss_mg_l,
            "vss_vss_ratio": mlvss_mg_l / mlss_mg_l if mlss_mg_l > 0 else None,
            "biomass_inventory_kg": biomass_inventory_kg,
            "biomass_inventory_vss_kg": biomass_inventory_vss_kg,
            "sludge_wasting_kg_d": sludge_wasting_kg_d,
            "srt_days": srt_days,
            "net_yield_kg_tss_per_kg_cod_applied": net_yield_per_cod_applied,
            "net_yield_kg_tss_per_kg_cod_removed": net_yield_per_cod_removed,
            "biomass_composition_mg_l": biomass_composition,
            "total_biomass_mg_l": total_biomass_mg_l,
            "active_biomass_mg_l": active_biomass_mg_l,
            "active_biomass_fraction": active_fraction,
            "cod_applied_kg_d": cod_applied_kg_d,
            "cod_removed_kg_d": cod_removed_kg_d
        }
        
        logger.info(f"=== BIOMASS METRICS ===")
        logger.info(f"MLSS: {mlss_mg_l:.1f} mg/L, MLVSS: {mlvss_mg_l:.1f} mg/L")
        logger.info(f"Biomass inventory: {biomass_inventory_kg:.1f} kg TSS")
        logger.info(f"Sludge wasting: {sludge_wasting_kg_d:.1f} kg/d")
        if srt_days:
            logger.info(f"SRT: {srt_days:.1f} days")
        if net_yield_per_cod_applied:
            logger.info(f"Net yield: {net_yield_per_cod_applied:.3f} kg TSS/kg COD applied")
        if net_yield_per_cod_removed:
            logger.info(f"Net yield: {net_yield_per_cod_removed:.3f} kg TSS/kg COD removed")
        logger.info(f"Active biomass fraction: {active_fraction:.2%}")
        
    except Exception as e:
        logger.warning(f"Could not calculate biomass metrics: {e}")
    
    output["biomass_metrics"] = biomass_metrics
    
    # Add economic results if available
    if hasattr(m.fs, "costing"):
        output["total_capital_cost"] = pyo.value(m.fs.costing.total_capital_cost)
        output["total_operating_cost"] = pyo.value(m.fs.costing.total_operating_cost)
        output["LCOW"] = pyo.value(m.fs.costing.LCOW)
    
    # Add MBR results if present
    if hasattr(m.fs, "MBR"):
        q_in = pyo.value(m.fs.MBR.inlet.flow_vol[0])
        q_perm = pyo.value(m.fs.MBR.permeate.flow_vol[0])
        q_ret = pyo.value(m.fs.MBR.retentate.flow_vol[0])
        
        output["mbr_inlet_flow_m3d"] = q_in * 86400
        output["mbr_permeate_flow_m3d"] = q_perm * 86400
        output["mbr_retentate_flow_m3d"] = q_ret * 86400
        # Module recovery is defined relative to the MBR inlet, not plant feed
        # R_module = Q_perm / Q_in
        output["mbr_module_recovery"] = (q_perm / q_in) if q_in > 0 else None
        
        # Nitrogen mass balance check at MBR
        try:
            # P1 Fix: Determine correct nitrogen component based on property package
            # ASM2D uses S_NH4, ADM1 uses S_IN
            if "S_NH4" in m.fs.props_ASM2D.component_list:
                n_component = "S_NH4"
            elif "S_IN" in m.fs.props_ASM2D.component_list:
                n_component = "S_IN"
            else:
                n_component = None
                logger.warning("P1: No nitrogen component found in ASM2D property package")
            
            if not n_component:
                raise ValueError("Cannot find nitrogen component (S_NH4 or S_IN) in ASM2D")
            
            logger.debug(f"P1: Using {n_component} for nitrogen balance check")
            
            # Get nitrogen concentrations (kg/m³) using correct component
            # Fix indexing: Use component-only for Port or [0, comp] for state block
            try:
                # Try Port indexing first (component-only)
                N_in_conc = pyo.value(m.fs.MBR.inlet.conc_mass_comp[n_component])
                N_perm_conc = pyo.value(m.fs.MBR.permeate.conc_mass_comp[n_component])
                N_ret_conc = pyo.value(m.fs.MBR.retentate.conc_mass_comp[n_component])
            except:
                # Fall back to state block indexing [time, component]
                N_in_conc = pyo.value(m.fs.MBR.mixed_state[0].conc_mass_comp[n_component])
                N_perm_conc = pyo.value(m.fs.MBR.permeate_state[0].conc_mass_comp[n_component])
                N_ret_conc = pyo.value(m.fs.MBR.retentate_state[0].conc_mass_comp[n_component])
            
            # Get flows (m³/s)
            flow_in = q_in
            flow_perm = q_perm
            flow_ret = q_ret
            
            # Calculate nitrogen flows (kg/s)
            N_in = flow_in * N_in_conc
            N_perm = flow_perm * N_perm_conc
            N_ret = flow_ret * N_ret_conc
            
            # Check balance
            residual = abs(N_in - N_perm - N_ret)
            residual_percent = 100 * residual / max(N_in, 1e-10)
            
            # Calculate passage fraction for nitrogen component
            passage_N = N_perm / max(N_in, 1e-10)
            passage_H2O = flow_perm / max(flow_in, 1e-10)
            
            # Expected passage based on sigma_soluble
            mbr_config = heuristic_config.get("mbr", {}) if heuristic_config else {}
            sigma_soluble = float(mbr_config.get("sigma_soluble", 1.0))
            expected_passage = sigma_soluble * passage_H2O
            
            output["nitrogen_balance"] = {
                "nitrogen_component": n_component,
                f"{n_component}_inlet_kg_m3": N_in_conc,
                f"{n_component}_permeate_kg_m3": N_perm_conc,
                f"{n_component}_retentate_kg_m3": N_ret_conc,
                "N_flow_in_kg_d": N_in * 86400,
                "N_flow_permeate_kg_d": N_perm * 86400,
                "N_flow_retentate_kg_d": N_ret * 86400,
                "mass_balance_error_percent": residual_percent,
                f"{n_component}_passage_fraction": passage_N,
                "H2O_passage_fraction": passage_H2O,
                f"expected_{n_component}_passage": expected_passage,
                "anomalous_rejection": abs(passage_N - expected_passage) > 0.1
            }
            
            # Log warning if nitrogen is being rejected anomalously
            if abs(passage_N - expected_passage) > 0.1:
                logger.warning(
                    f"P1: Anomalous {n_component} rejection detected at MBR: "
                    f"passage={passage_N:.3f} vs expected={expected_passage:.3f}. "
                    f"This can cause TAN accumulation."
                )
            
            # Assert mass balance
            if residual_percent > 0.1:  # 0.1% tolerance
                logger.warning(f"Nitrogen mass balance error at MBR: {residual_percent:.3f}%")
            
        except Exception as e:
            logger.warning(f"Could not check nitrogen balance: {e}")
            output["nitrogen_balance"] = {"error": str(e)}
    
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

        # Attach a default SimulationConfig to hold options and diagnostics toggles
        try:
            m.fs.config = SimulationConfig()
            # Allow users to toggle diagnostics via heuristic_config if provided
            diag_cfg = heuristic_config.get("diagnostics", {}) if isinstance(heuristic_config, dict) else {}
            if isinstance(diag_cfg, dict):
                m.fs.config.enable_diagnostics = bool(diag_cfg.get("enable", False))
                m.fs.config.dump_near_zero_vars = bool(diag_cfg.get("dump_near_zero", False))
                # SD tuning overrides
                if "sd_iter_lim" in diag_cfg:
                    try:
                        m.fs.config.sd_iter_lim = int(diag_cfg.get("sd_iter_lim"))
                    except Exception:
                        pass
                if "sd_tol" in diag_cfg:
                    try:
                        m.fs.config.sd_tol = float(diag_cfg.get("sd_tol"))
                    except Exception:
                        pass
            
            # Also check simulation config for solver options and SD settings
            sim_cfg = heuristic_config.get("simulation", {}) if isinstance(heuristic_config, dict) else {}
            if isinstance(sim_cfg, dict):
                if "solver_options" in sim_cfg and isinstance(sim_cfg["solver_options"], dict):
                    m.fs.config.solver_options = sim_cfg["solver_options"]
                if "sd_iter_lim" in sim_cfg:
                    try:
                        m.fs.config.sd_iter_lim = int(sim_cfg.get("sd_iter_lim"))
                    except Exception:
                        pass
                if "use_sd" in sim_cfg:
                    m.fs.config.use_sd = bool(sim_cfg.get("use_sd", True))
        except Exception:
            pass
        
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
            # ------------------------------------------------------------------
            # Manual pre-scaling: define robust scaling on key state variables
            # prior to automatic calculation to avoid "missing scaling" warnings.
            # ------------------------------------------------------------------
            
            # Apply comprehensive scaling to ALL ADM1 state blocks
            # This is critical for convergence with components spanning 12 orders of magnitude
            def apply_adm1_scaling(blk):
                """Apply scaling to any ADM1 state block"""
                if not blk:
                    return
                    
                # S_H scaling (pH ~7 means S_H ~1e-7)
                if hasattr(blk, "S_H"):
                    # Follow WaterTAP/IDAES guidance (1e5–1e8). Choose conservative 1e6.
                    iscale.set_scaling_factor(blk.S_H, 1e6)
                    blk.S_H.setlb(1e-14)  # Strict lower bound
                    blk.S_H.setub(1e-3)   # Upper bound to prevent pH excursions
                
                # Ion scaling
                if hasattr(blk, "cations"):
                    iscale.set_scaling_factor(blk.cations, 1e2)
                if hasattr(blk, "anions"):
                    iscale.set_scaling_factor(blk.anions, 1e2)
                
                # Concentration scaling for extreme components
                if hasattr(blk, "conc_mass_comp"):
                    # Dissolved gases - need extreme scaling
                    for comp, factor in [("S_h2", 1e5), ("S_ch4", 1e5), ("S_co2", 1e3)]:
                        if (0, comp) in blk.conc_mass_comp:
                            iscale.set_scaling_factor(blk.conc_mass_comp[0, comp], factor)

            def apply_asm2d_scaling(blk):
                """Apply scaling to any ASM2D state block

                Heuristics (kg/m^3):
                - Dissolved inorganics (S_IN, S_PO4, S_IC, S_K, S_Mg): 1e2
                - Dissolved gases/trace (S_O2, S_NO3, S_N2): 1e3
                - Soluble organics (S_A, S_F, S_I): 1e2
                - Particulates (X_*): 1e0 (order unity typical 1–15)
                """
                if not blk or not hasattr(blk, "conc_mass_comp"):
                    return
                try:
                    comp_list = list(blk.params.component_list) if hasattr(blk, "params") and hasattr(blk.params, "component_list") else []
                except Exception:
                    comp_list = []
                # Fallback: try to discover components from indexed Var
                if not comp_list:
                    try:
                        comp_list = [j for (_t, j) in blk.conc_mass_comp.keys() if _t == 0]
                    except Exception:
                        comp_list = []
                for j in comp_list:
                    name = str(j)
                    sf = None
                    if name in ("S_IN", "S_PO4", "S_IC", "S_K", "S_Mg"):
                        sf = 1e2
                    elif name in ("S_O2", "S_NO3", "S_N2"):
                        sf = 1e3
                    elif name in ("S_A", "S_F", "S_I"):
                        sf = 1e2
                    elif name.startswith("X_"):
                        sf = 1e0
                    else:
                        # Default for other solubles
                        sf = 1e2
                    try:
                        if (0, j) in blk.conc_mass_comp:
                            iscale.set_scaling_factor(blk.conc_mass_comp[0, j], sf)
                    except Exception:
                        pass
            
            # Apply manual scaling to all relevant state blocks BEFORE auto-scaling
            t = 0  # Steady-state time index
            
            # Feed
            if hasattr(m.fs, "feed") and hasattr(m.fs.feed, "properties"):
                apply_adm1_scaling(m.fs.feed.properties[t])
            
            # Mixer and its ports
            if hasattr(m.fs, "mixer"):
                for port in ["outlet", "mixed_state", "mbr_recycle", "centrate_recycle", "feed_inlet"]:
                    if hasattr(m.fs.mixer, port):
                        try:
                            port_obj = getattr(m.fs.mixer, port)
                            if hasattr(port_obj, "__getitem__"):
                                apply_adm1_scaling(port_obj[t])
                        except:
                            pass
            
            # AD unit
            if hasattr(m.fs, "AD") and hasattr(m.fs.AD, "liquid_phase"):
                for side in ["properties_in", "properties_out"]:
                    if hasattr(m.fs.AD.liquid_phase, side):
                        apply_adm1_scaling(getattr(m.fs.AD.liquid_phase, side)[t])
                # Also AD inlet/outlet ports
                for port in ["inlet", "liquid_outlet"]:
                    if hasattr(m.fs.AD, port):
                        try:
                            port_obj = getattr(m.fs.AD, port)
                            if hasattr(port_obj, "__getitem__"):
                                apply_adm1_scaling(port_obj[t])
                        except:
                            pass
            
            # AD splitter
            if hasattr(m.fs, "ad_splitter"):
                for port in ["mixed_state", "to_mbr_state", "to_dewatering_state"]:
                    if hasattr(m.fs.ad_splitter, port):
                        try:
                            port_obj = getattr(m.fs.ad_splitter, port)
                            if hasattr(port_obj, "__getitem__"):
                                apply_adm1_scaling(port_obj[t])
                        except:
                            pass
            
            # Translators and downstream ASM2D states
            for translator in ["translator_AD_ASM", "translator_ASM_AD_mbr", "translator_centrate_AD"]:
                if hasattr(m.fs, translator):
                    trans_obj = getattr(m.fs, translator)
                    # For ADM1->ASM2D translators, scale ADM1 properties_in and ASM2D properties_out
                    if "AD_ASM" in translator:
                        if hasattr(trans_obj, "properties_in"):
                            try:
                                apply_adm1_scaling(trans_obj.properties_in[t])
                            except:
                                pass
                        if hasattr(trans_obj, "properties_out"):
                            try:
                                apply_asm2d_scaling(trans_obj.properties_out[t])
                            except:
                                pass
                    # For ASM2D->ADM1 translators, scale ASM2D properties_in and ADM1 properties_out
                    elif ("ASM_AD" in translator or translator.endswith("_AD")):
                        if hasattr(trans_obj, "properties_in"):
                            try:
                                apply_asm2d_scaling(trans_obj.properties_in[t])
                            except:
                                pass
                        if hasattr(trans_obj, "properties_out"):
                            try:
                                apply_adm1_scaling(trans_obj.properties_out[t])
                            except:
                                pass

            # MBR and Dewatering (ASM2D states)
            try:
                if hasattr(m.fs, "MBR"):
                    if hasattr(m.fs.MBR, "properties_in"):
                        apply_asm2d_scaling(m.fs.MBR.properties_in[t])
                    if hasattr(m.fs.MBR, "properties_out"):
                        # properties_out is indexed by outlet; loop if so
                        try:
                            for k in m.fs.MBR.properties_out.keys():
                                apply_asm2d_scaling(m.fs.MBR.properties_out[k])
                        except Exception:
                            apply_asm2d_scaling(m.fs.MBR.properties_out[t])
                if hasattr(m.fs, "dewatering"):
                    if hasattr(m.fs.dewatering, "properties_in"):
                        apply_asm2d_scaling(m.fs.dewatering.properties_in[t])
                    for attr in ("overflow_state", "underflow_state", "properties_treated", "properties_byproduct"):
                        if hasattr(m.fs.dewatering, attr):
                            blk = getattr(m.fs.dewatering, attr)
                            try:
                                apply_asm2d_scaling(blk[t])
                            except Exception:
                                pass
            except Exception:
                pass

            # Now let IDAES/WaterTAP scalers propagate and fill remaining factors
            iscale.calculate_scaling_factors(m)
            
            logger.info("Applied comprehensive ADM1 scaling to all state blocks")
            
            # CRITICAL: Add ASM2D scaling function - Modified ASM2D doesn't scale conc_mass_comp by default
            def apply_asm2d_scaling(blk):
                """Apply scaling to ASM2D state blocks (critical for convergence)"""
                if not blk:
                    return
                
                if hasattr(blk, "conc_mass_comp"):
                    # Soluble nutrients and ions (1e2 scaling for mg/L range)
                    for comp in ["S_IN", "S_PO4", "S_IC", "S_K", "S_Mg"]:
                        if (0, comp) in blk.conc_mass_comp:
                            iscale.set_scaling_factor(blk.conc_mass_comp[0, comp], 1e2)
                    
                    # Dissolved gases (1e3 scaling for low concentrations)
                    for comp in ["S_O2", "S_NO3", "S_N2"]:
                        if (0, comp) in blk.conc_mass_comp:
                            iscale.set_scaling_factor(blk.conc_mass_comp[0, comp], 1e3)
                    
                    # Organic solubles (1e2 scaling)
                    for comp in ["S_F", "S_A", "S_NH4", "S_NO2", "S_ALK"]:
                        if (0, comp) in blk.conc_mass_comp:
                            iscale.set_scaling_factor(blk.conc_mass_comp[0, comp], 1e2)
                    
                    # Particulates (1e0 to 1e1 scaling for g/L range)
                    for comp_idx in blk.conc_mass_comp.keys():
                        comp_name = str(comp_idx[1])
                        if comp_name.startswith("X_"):
                            # Enhanced scaling for TSS (critical for MLSS control)
                            if comp_name == "X_TSS":
                                # TSS typically 10-15 kg/m³ = 10-15 g/L
                                iscale.set_scaling_factor(blk.conc_mass_comp[comp_idx], 1e-1)
                            # Higher scaling for lower concentration particulates
                            elif comp_name in ["X_AUT", "X_PP", "X_PHA"]:
                                iscale.set_scaling_factor(blk.conc_mass_comp[comp_idx], 1e1)
                            else:
                                iscale.set_scaling_factor(blk.conc_mass_comp[comp_idx], 1e0)
                
                # Scale flow if present
                if hasattr(blk, "flow_vol"):
                    try:
                        flow_val = pyo.value(blk.flow_vol[0])
                        if flow_val and flow_val > 0:
                            iscale.set_scaling_factor(blk.flow_vol[0], 1.0/flow_val)
                    except:
                        pass
            
            # Apply ASM2D scaling to all relevant units (translators, MBR, dewatering)
            logger.info("Applying ASM2D scaling to translators and downstream units...")
            
            # Translators (both input and output sides as appropriate)
            translator_scaling_map = {
                "translator_AD_ASM": "properties_out",      # ADM1 -> ASM2D
                "translator_ASM_AD": "properties_in",       # ASM2D -> ADM1
                "translator_ASM_AD_mbr": "properties_in",   # ASM2D -> ADM1
                "translator_dewatering_ASM": "properties_out",  # ADM1 -> ASM2D
                "translator_centrate_AD": "properties_in"   # ASM2D -> ADM1
            }
            
            for trans_name, prop_side in translator_scaling_map.items():
                if hasattr(m.fs, trans_name):
                    trans_obj = getattr(m.fs, trans_name)
                    if hasattr(trans_obj, prop_side):
                        try:
                            apply_asm2d_scaling(getattr(trans_obj, prop_side)[t])
                        except Exception as e:
                            logger.debug(f"ASM2D scaling for {trans_name}.{prop_side} skipped: {e}")
            
            # MBR unit (all ASM2D states)
            if hasattr(m.fs, "MBR"):
                for state in ["mixed_state", "permeate_state", "retentate_state"]:
                    if hasattr(m.fs.MBR, state):
                        try:
                            apply_asm2d_scaling(getattr(m.fs.MBR, state)[t])
                        except Exception as e:
                            logger.debug(f"ASM2D scaling for MBR.{state} skipped: {e}")
                # Also scale inlet/outlet ports
                for port in ["inlet", "permeate", "retentate"]:
                    if hasattr(m.fs.MBR, port):
                        try:
                            port_obj = getattr(m.fs.MBR, port)
                            if hasattr(port_obj, "__getitem__"):
                                apply_asm2d_scaling(port_obj[t])
                        except Exception as e:
                            logger.debug(f"ASM2D scaling for MBR.{port} skipped: {e}")
            
            # Dewatering unit (all ASM2D states)
            if hasattr(m.fs, "dewatering"):
                for state in ["mixed_state", "underflow_state", "overflow_state"]:
                    if hasattr(m.fs.dewatering, state):
                        try:
                            apply_asm2d_scaling(getattr(m.fs.dewatering, state)[t])
                        except Exception as e:
                            logger.debug(f"ASM2D scaling for dewatering.{state} skipped: {e}")
                # Also scale inlet/outlet ports
                for port in ["inlet", "underflow", "overflow"]:
                    if hasattr(m.fs.dewatering, port):
                        try:
                            port_obj = getattr(m.fs.dewatering, port)
                            if hasattr(port_obj, "__getitem__"):
                                apply_asm2d_scaling(port_obj[t])
                        except Exception as e:
                            logger.debug(f"ASM2D scaling for dewatering.{port} skipped: {e}")
            
            logger.info("Applied comprehensive ASM2D scaling to all state blocks")
            
            # Volumetric constraints have been removed to avoid over-constraining
            # No scaling needed for removed constraints
            
            # MBR recovery is now fixed directly on H2O split fraction
            # No separate mbr_recovery variable to scale
                
        except Exception as e:
            logger.debug(f"Scaling factor calculation skipped: {e}")

        # Initialize flowsheet with SequentialDecomposition for recycles
        logger.info("Initializing flowsheet...")
        # Check if use_sd was set in config, default to True
        use_sd = getattr(m.fs.config, 'use_sd', True) if hasattr(m.fs, 'config') else True
        logger.info(f"Sequential Decomposition: {'Enabled' if use_sd else 'Disabled'}")
        initialize_flowsheet(m, use_sequential_decomposition=use_sd)
        
        # P1: Audit translator nitrogen mapping after initialization
        audit_translator_nitrogen(m, logger)
        
        if initialize_only:
            return {
                "status": "initialized",
                "flowsheet_type": flowsheet_type,
                "degrees_of_freedom": dof,
                "message": "Model built and initialized successfully"
            }
        
        # Optional: seed MBR flows to target 5Q/1Q as initial values (not fixed)
        try:
            diag_cfg = heuristic_config.get("diagnostics", {}) if isinstance(heuristic_config, dict) else {}
            if bool(diag_cfg.get("seed_force_mbr", False)) and hasattr(m.fs, "MBR"):
                feed_m3d = float(basis_of_design.get("feed_flow_m3d", 1000.0))
                q_in = (5.0 * feed_m3d) / 86400.0
                q_perm = (1.0 * feed_m3d) / 86400.0
                try:
                    m.fs.MBR.inlet.flow_vol[0].set_value(q_in * pyo.units.m**3 / pyo.units.s)
                    m.fs.MBR.permeate.flow_vol[0].set_value(q_perm * pyo.units.m**3 / pyo.units.s)
                    # Also seed recycle to ~4Q at the mixer port if present
                    if hasattr(m.fs.mixer, "mbr_recycle"):
                        m.fs.mixer.mbr_recycle.flow_vol[0].set_value((4.0 * feed_m3d / 86400.0) * pyo.units.m**3 / pyo.units.s)
                    logger.info(f"Seeded MBR flows: inlet≈{5.0*feed_m3d} m3/d, permeate≈{feed_m3d} m3/d")
                except Exception as e:
                    logger.debug(f"Seeding MBR initial flows skipped: {e}")
        except Exception:
            pass

        # Log a pre-solve snapshot
        try:
            _log_key_flows(m, header="pre-solve")
        except Exception:
            pass

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
        
        # Post-solve flow snapshot for final diagnostics
        try:
            _log_key_flows(m, header="post-solve")
        except Exception:
            pass
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
