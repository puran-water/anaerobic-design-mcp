#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
WaterTAP simulation module for anaerobic digester with conditional flowsheets.

Supports two configurations based on heuristic sizing:
1. High TSS: AD + ZO Dewatering with centrate recycle
2. Low TSS: AD + MBR + ZO Dewatering with centrate recycle
"""

import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
import pyomo.environ as pyo
from pyomo.network import Arc
from pyomo.core.base.transformation import TransformationFactory

# IDAES imports
from idaes.core import FlowsheetBlock
from idaes.core.util.initialization import propagate_state
import idaes.core.util.scaling as iscale
from idaes.models.unit_models import Mixer, Separator, Feed
import idaes.logger as idaeslog

# WaterTAP imports
from watertap.core.solvers import get_solver
from watertap.unit_models.anaerobic_digester import AD
from watertap.property_models.unit_specific.anaerobic_digestion.adm1_properties import (
    ADM1ParameterBlock
)
from watertap.property_models.unit_specific.anaerobic_digestion.adm1_properties_vapor import (
    ADM1_vaporParameterBlock
)
from watertap.property_models.unit_specific.anaerobic_digestion.adm1_reactions import (
    ADM1ReactionParameterBlock
)

# Zero-Order imports for simplified modeling
from watertap.unit_models.zero_order import (
    MBRZO,
    CentrifugeZO
)
from watertap.property_models.unit_specific.anaerobic_digestion.modified_adm1_properties import (
    ModifiedADM1ParameterBlock
)
from watertap.property_models.unit_specific.anaerobic_digestion.modified_adm1_reactions import (
    ModifiedADM1ReactionParameterBlock
)
# Use MCAS property package for Zero-Order units with solutes
try:
    from watertap.property_models.multicomp_aq_sol_prop_pack import (
        MCASParameterBlock, 
        MaterialFlowBasis
    )
except ImportError:
    from watertap.property_models.mcas_properties import (
        MCASParameterBlock,
        MaterialFlowBasis
    )

# Import custom translators
from utils.translators import (
    Translator_ADM1_WaterZO,
    Translator_WaterZO_ADM1
)

# WaterTAP costing
from watertap.costing import WaterTAPCosting, WaterTAPCostingDetailed
from watertap.costing.zero_order_costing import ZeroOrderCosting
from idaes.core import UnitModelCostingBlock

logger = logging.getLogger(__name__)


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
        adm1_state: ADM1 state variables (27 components in kg/m³)
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
    
    # Define property packages
    m.fs.props_ADM1 = ADM1ParameterBlock()
    m.fs.props_vap_ADM1 = ADM1_vaporParameterBlock()
    m.fs.rxn_ADM1 = ADM1ReactionParameterBlock(
        property_package=m.fs.props_ADM1
    )
    
    # Define Zero-Order property package for MBR/dewatering
    # Only include tss and cod as solutes
    # Use mass basis for non-standard solutes per WaterTAP documentation
    m.fs.props_ZO = MCASParameterBlock(
        solute_list=["tss", "cod"],
        mw_data={"H2O": 18e-3, "tss": 1, "cod": 1},  # Placeholder MW for non-standard solutes
        ignore_neutral_charge=True,  # TSS and COD are neutral
        material_flow_basis=MaterialFlowBasis.mass  # Work with mass flows directly
    )
    
    # Create Feed unit for fresh feed
    m.fs.feed = Feed(property_package=m.fs.props_ADM1)
    
    # Set feed conditions from basis of design
    flow_m3_per_s = basis_of_design["feed_flow_m3d"] / (24 * 3600)
    m.fs.feed.flow_vol.fix(flow_m3_per_s)
    
    # Temperature and pressure
    temp_k = heuristic_config.get("operating_conditions", {}).get(
        "temperature_k", 308.15  # Default 35°C
    )
    pressure_pa = heuristic_config.get("operating_conditions", {}).get(
        "pressure_atm", 1.0
    ) * 101325
    
    m.fs.feed.temperature.fix(temp_k)
    m.fs.feed.pressure.fix(pressure_pa)
    
    # Set ADM1 state variables in feed
    for comp, value in adm1_state.items():
        if comp in m.fs.props_ADM1.component_list:
            # Check if component exists in feed before trying to fix it
            if hasattr(m.fs.feed, "conc_mass_comp"):
                try:
                    m.fs.feed.conc_mass_comp[0, comp].fix(value)
                except KeyError:
                    # Some components might not be in the Feed state
                    logger.debug(f"Component {comp} not in feed state, skipping")
    
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
    
    m.fs.AD.volume_liquid.fix(liquid_vol * pyo.units.m**3)
    m.fs.AD.volume_vapor.fix(vapor_vol * pyo.units.m**3)
    
    # Fix liquid outlet temperature (assume isothermal)
    m.fs.AD.liquid_outlet.temperature.fix(temp_k)
    
    # Note: AD inlet will be connected via mixer or directly from feed
    # DO NOT fix AD.inlet here to avoid DOF conflicts


def _build_high_tss_flowsheet(
    m: pyo.ConcreteModel,
    basis_of_design: Dict[str, Any],
    heuristic_config: Dict[str, Any]
) -> None:
    """
    Build high TSS flowsheet: AD -> ZO Dewatering -> Centrate recycle.
    """
    logger.info("Building high TSS configuration with ZO dewatering")
    
    # Add translator from ADM1 to Zero-Order
    m.fs.translator_AD_ZO = Translator_ADM1_WaterZO(
        inlet_property_package=m.fs.props_ADM1,
        outlet_property_package=m.fs.props_ZO
    )
    
    # Connect AD to translator
    m.fs.arc_AD_translator = Arc(
        source=m.fs.AD.liquid_outlet,
        destination=m.fs.translator_AD_ZO.inlet
    )
    
    # Add ZO centrifuge for dewatering
    m.fs.dewatering_zo = CentrifugeZO(
        property_package=m.fs.props_ZO,
        database="default"
    )
    
    # Connect translator to dewatering
    m.fs.arc_translator_dewatering = Arc(
        source=m.fs.translator_AD_ZO.outlet,
        destination=m.fs.dewatering_zo.inlet
    )
    
    # Configure dewatering from heuristics
    dewatering_config = heuristic_config.get("dewatering", {})
    
    # TSS removal (solids capture)
    capture_fraction = dewatering_config.get("capture_fraction", 0.95)
    m.fs.dewatering_zo.removal_frac_mass_comp[0, "tss"].fix(capture_fraction)
    
    # Minimal COD removal (mostly in solids)
    m.fs.dewatering_zo.removal_frac_mass_comp[0, "cod"].fix(0.1)
    
    # Energy consumption
    electricity_kw = dewatering_config.get("electricity_kw", 50.0)
    m.fs.dewatering_zo.electricity.fix(electricity_kw * pyo.units.kW)
    
    # Add translator from Zero-Order back to ADM1 for centrate
    m.fs.translator_ZO_AD = Translator_WaterZO_ADM1(
        inlet_property_package=m.fs.props_ZO,
        outlet_property_package=m.fs.props_ADM1
    )
    
    # Connect dewatering centrate to translator
    m.fs.arc_dewatering_translator = Arc(
        source=m.fs.dewatering_zo.treated,  # Centrate stream
        destination=m.fs.translator_ZO_AD.inlet
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
        source=m.fs.translator_ZO_AD.outlet,
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
    Build low TSS MBR flowsheet: AD -> MBR (5Q) -> Partial dewatering -> Recycle.
    
    Flow configuration:
    - 5Q to MBR (Q = feed flow)
    - 1Q permeate from MBR
    - 4Q retentate recycled to AD
    - Waste sludge pulled directly from AD to dewatering
    """
    logger.info("Building low TSS MBR configuration with ZO units")
    
    # Add splitter from AD for MBR feed and waste sludge
    m.fs.ad_splitter = Separator(
        property_package=m.fs.props_ADM1,
        outlet_list=["to_mbr", "waste_sludge"]
    )
    
    # Connect AD to splitter
    m.fs.arc_AD_splitter = Arc(
        source=m.fs.AD.liquid_outlet,
        destination=m.fs.ad_splitter.inlet
    )
    
    # Calculate split fractions
    # If daily waste is 2% of feed (20 m³/d from 1000 m³/d feed)
    # and we're processing 5Q through MBR, the waste fraction is small
    daily_waste_m3d = heuristic_config.get("daily_waste_sludge_m3d", 20.0)
    feed_flow_m3d = basis_of_design["feed_flow_m3d"]
    mbr_flow_m3d = 5 * feed_flow_m3d  # 5Q operation
    
    # Waste fraction from the AD outlet (which sees 5Q)
    waste_fraction = daily_waste_m3d / mbr_flow_m3d
    
    # Set split fractions
    for comp in m.fs.props_ADM1.component_list:
        m.fs.ad_splitter.split_fraction[0, "to_mbr", comp].fix(1.0 - waste_fraction)
        m.fs.ad_splitter.split_fraction[0, "waste_sludge", comp].fix(waste_fraction)
    
    # Translator ADM1 to Zero-Order for MBR
    m.fs.translator_AD_ZO = Translator_ADM1_WaterZO(
        inlet_property_package=m.fs.props_ADM1,
        outlet_property_package=m.fs.props_ZO
    )
    
    # Connect splitter to translator
    m.fs.arc_splitter_translator = Arc(
        source=m.fs.ad_splitter.to_mbr,
        destination=m.fs.translator_AD_ZO.inlet
    )
    
    # Add MBR unit (Zero-Order)
    m.fs.MBR = MBRZO(
        property_package=m.fs.props_ZO,
        database="default"
    )
    
    # Connect translator to MBR
    m.fs.arc_translator_MBR = Arc(
        source=m.fs.translator_AD_ZO.outlet,
        destination=m.fs.MBR.inlet
    )
    
    # Configure MBR from heuristics
    mbr_config = heuristic_config.get("mbr", {})
    
    # Set water recovery (20% for 5Q operation: 1Q permeate / 5Q feed)
    m.fs.MBR.recovery_frac_mass_H2O[0].fix(0.2)
    
    # TSS removal (near complete)
    m.fs.MBR.removal_frac_mass_comp[0, "tss"].fix(0.999)
    
    # COD removal (partial, most COD in permeate)
    m.fs.MBR.removal_frac_mass_comp[0, "cod"].fix(0.1)
    
    # MBR area and energy
    total_area = mbr_config.get("total_area_m2", 4000.0)
    m.fs.MBR.area.fix(total_area * pyo.units.m**2)
    
    # Energy consumption (typical for anaerobic MBR)
    m.fs.MBR.electricity.fix(0.3 * pyo.units.kWh / pyo.units.m**3)
    
    # Translator from Zero-Order back to ADM1 for retentate
    m.fs.translator_ZO_AD_mbr = Translator_WaterZO_ADM1(
        inlet_property_package=m.fs.props_ZO,
        outlet_property_package=m.fs.props_ADM1
    )
    
    # Connect MBR retentate to translator
    m.fs.arc_MBR_translator = Arc(
        source=m.fs.MBR.treated,  # This is actually retentate for MBR
        destination=m.fs.translator_ZO_AD_mbr.inlet
    )
    
    # Translator for waste sludge to ZO
    m.fs.translator_waste_ZO = Translator_ADM1_WaterZO(
        inlet_property_package=m.fs.props_ADM1,
        outlet_property_package=m.fs.props_ZO
    )
    
    # Connect waste sludge to translator
    m.fs.arc_waste_translator = Arc(
        source=m.fs.ad_splitter.waste_sludge,
        destination=m.fs.translator_waste_ZO.inlet
    )
    
    # Add dewatering for waste sludge
    m.fs.dewatering_zo = CentrifugeZO(
        property_package=m.fs.props_ZO,
        database="default"
    )
    
    # Connect waste translator to dewatering
    m.fs.arc_translator_dewatering = Arc(
        source=m.fs.translator_waste_ZO.outlet,
        destination=m.fs.dewatering_zo.inlet
    )
    
    # Configure dewatering
    dewatering_config = heuristic_config.get("dewatering", {})
    capture_fraction = dewatering_config.get("capture_fraction", 0.95)
    m.fs.dewatering_zo.removal_frac_mass_comp[0, "tss"].fix(capture_fraction)
    m.fs.dewatering_zo.removal_frac_mass_comp[0, "cod"].fix(0.1)
    
    electricity_kw = dewatering_config.get("electricity_kw", 30.0)
    m.fs.dewatering_zo.electricity.fix(electricity_kw * pyo.units.kW)
    
    # Translator for dewatering centrate back to ADM1
    m.fs.translator_centrate_AD = Translator_WaterZO_ADM1(
        inlet_property_package=m.fs.props_ZO,
        outlet_property_package=m.fs.props_ADM1
    )
    
    # Connect dewatering centrate to translator
    m.fs.arc_centrate_translator = Arc(
        source=m.fs.dewatering_zo.treated,
        destination=m.fs.translator_centrate_AD.inlet
    )
    
    # Mixer for all recycles (feed + MBR retentate + centrate)
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
        source=m.fs.translator_ZO_AD_mbr.outlet,
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
        
        # Cost AD unit using UnitModelCostingBlock
        m.fs.AD.costing = UnitModelCostingBlock(
            flowsheet_costing_block=m.fs.costing
        )
        
    elif costing_method == "WaterTAPCostingDetailed":
        m.fs.costing = WaterTAPCostingDetailed()
        
        # Cost AD unit using UnitModelCostingBlock
        m.fs.AD.costing = UnitModelCostingBlock(
            flowsheet_costing_block=m.fs.costing
        )
        
    elif costing_method == "ZeroOrderCosting":
        m.fs.costing = ZeroOrderCosting()
        
        # Cost ZO units (MBR, dewatering)
        if hasattr(m.fs, "MBR"):
            m.fs.MBR.costing = UnitModelCostingBlock(
                flowsheet_costing_block=m.fs.costing
            )
        if hasattr(m.fs, "dewatering_zo"):
            m.fs.dewatering_zo.costing = UnitModelCostingBlock(
                flowsheet_costing_block=m.fs.costing
            )
    
    # Process costing for entire flowsheet
    if hasattr(m.fs, "costing"):
        m.fs.costing.cost_process()


def initialize_flowsheet(m: pyo.ConcreteModel) -> None:
    """Initialize the flowsheet."""
    
    # Initialize feed
    m.fs.feed.initialize()
    
    # Propagate state through the flowsheet
    propagate_state(m.fs.arc_feed_mixer)
    
    # Initialize mixer
    m.fs.mixer.initialize()
    
    # Propagate to AD
    propagate_state(m.fs.arc_mixer_AD)
    
    # Initialize AD (may take time)
    m.fs.AD.initialize(outlvl=idaeslog.INFO)
    
    # Initialize downstream units based on flowsheet type
    if hasattr(m.fs, "MBR"):
        # Low TSS path
        propagate_state(m.fs.arc_AD_splitter)
        m.fs.ad_splitter.initialize()
        
        propagate_state(m.fs.arc_splitter_translator)
        m.fs.translator_AD_ZO.initialize()
        
        propagate_state(m.fs.arc_translator_MBR)
        m.fs.MBR.initialize()
        
        # Initialize waste path
        propagate_state(m.fs.arc_waste_translator)
        m.fs.translator_waste_ZO.initialize()
        
        propagate_state(m.fs.arc_translator_dewatering)
        m.fs.dewatering_zo.initialize()
        
    else:
        # High TSS path
        propagate_state(m.fs.arc_AD_translator)
        m.fs.translator_AD_ZO.initialize()
        
        propagate_state(m.fs.arc_translator_dewatering)
        m.fs.dewatering_zo.initialize()


def solve_flowsheet(
    m: pyo.ConcreteModel,
    tee: bool = True,
    raise_on_failure: bool = True
) -> Dict[str, Any]:
    """
    Solve the flowsheet and return results.
    
    Args:
        m: Pyomo model
        tee: Show solver output
        raise_on_failure: Raise exception if solve fails
    
    Returns:
        Dictionary of results
    """
    solver = get_solver()
    
    results = solver.solve(m, tee=tee)
    
    if not pyo.check_optimal_termination(results):
        if raise_on_failure:
            raise RuntimeError(f"Solve failed with status: {results.solver.termination_condition}")
        else:
            logger.warning(f"Solve failed with status: {results.solver.termination_condition}")
    
    # Extract key results
    output = {
        "solver_status": str(results.solver.termination_condition),
        "objective_value": pyo.value(m.fs.costing.total_capital_cost) if hasattr(m.fs, "costing") else None,
        "biogas_production_m3d": pyo.value(m.fs.AD.biogas_production[0]) * 86400 if hasattr(m.fs.AD, "biogas_production") else None,
        "methane_fraction": pyo.value(m.fs.AD.CH4_fraction[0]) if hasattr(m.fs.AD, "CH4_fraction") else None,
    }
    
    # Add MBR results if present
    if hasattr(m.fs, "MBR"):
        output["mbr_permeate_flow_m3d"] = pyo.value(m.fs.MBR.properties_permeate[0].flow_vol) * 86400
        output["mbr_area_m2"] = pyo.value(m.fs.MBR.area)
    
    # Add dewatering results
    if hasattr(m.fs, "dewatering_zo"):
        output["sludge_production_m3d"] = pyo.value(m.fs.dewatering_zo.properties_byproduct[0].flow_vol) * 86400
        output["centrate_flow_m3d"] = pyo.value(m.fs.dewatering_zo.properties_treated[0].flow_vol) * 86400
    
    return output
