#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Custom translators for ADM1 to Zero-Order property packages.

These translators enable integration of MBR (Zero-Order) with AD (ADM1) models.
"""

import pyomo.environ as pyo
from pyomo.network import Port
from pyomo.core import Set
from idaes.core import declare_process_block_class
from idaes.models.unit_models.translator import TranslatorData
from idaes.core.util.initialization import fix_state_vars, revert_state_vars
import idaes.logger as idaeslog


@declare_process_block_class("Translator_ADM1_WaterZO")
class Translator_ADM1_WaterZOData(TranslatorData):
    """
    Translator block to convert ADM1 properties to Zero-Order Water properties.
    
    Maps ADM1 particulate components to TSS for MBR modeling.
    """
    
    CONFIG = TranslatorData.CONFIG()
    
    def build(self):
        """Build the translator block."""
        # Call parent build which creates inlet/outlet ports and state blocks
        super().build()
        
        # Get time domain
        time = self.flowsheet().time
        
        # Add translation constraints using state blocks
        # MCAS uses flow_mass_phase_comp instead of flow_vol
        @self.Constraint(time, doc="Water flow balance")
        def water_flow_balance(b, t):
            # Convert volumetric flow to mass flow for water
            # Assuming density of water ~ 1000 kg/m³
            return b.properties_out[t].flow_mass_phase_comp["Liq", "H2O"] == \
                   b.properties_in[t].flow_vol * 1000  # Convert m³/s to kg/s
        
        @self.Constraint(time, doc="Temperature balance")
        def temperature_balance(b, t):
            return b.properties_out[t].temperature == b.properties_in[t].temperature
        
        @self.Constraint(time, doc="Pressure balance")
        def pressure_balance(b, t):
            return b.properties_out[t].pressure == b.properties_in[t].pressure
        
        # Define ADM1 particulate components set
        self.adm1_particulates = Set(initialize=[
            "X_c", "X_ch", "X_pr", "X_li",  # Composite and biodegradable
            "X_su", "X_aa", "X_fa", "X_c4", "X_pro", "X_ac", "X_h2",  # Biomass
            "X_I"  # Inert
        ])
        
        # Map TSS from ADM1 particulates
        @self.Constraint(time, doc="TSS mapping from ADM1 particulates")
        def tss_mapping(b, t):
            # MCAS uses flow_mass_phase_comp for mass flows
            # Sum particulates that exist in inlet and convert to mass flow
            tss_mass_flow = sum(
                b.properties_in[t].conc_mass_comp[comp] * b.properties_in[t].flow_vol
                for comp in b.adm1_particulates
                if comp in b.properties_in[t].params.component_list
            )
            
            return b.properties_out[t].flow_mass_phase_comp["Liq", "tss"] == tss_mass_flow
        
        # Map COD if needed
        @self.Constraint(time, doc="COD mapping from ADM1 components")
        def cod_mapping(b, t):
            # Define COD components (simplified - no conversion factors)
            cod_components = [
                # Soluble
                "S_su", "S_aa", "S_fa", "S_va", "S_bu", "S_pro", "S_ac",
                # Particulate
                "X_c", "X_ch", "X_pr", "X_li",
                "X_su", "X_aa", "X_fa", "X_c4", "X_pro", "X_ac", "X_h2"
            ]
            
            # Sum components that exist in inlet and convert to mass flow
            cod_mass_flow = sum(
                b.properties_in[t].conc_mass_comp[comp] * b.properties_in[t].flow_vol
                for comp in cod_components
                if comp in b.properties_in[t].params.component_list
            )
            
            return b.properties_out[t].flow_mass_phase_comp["Liq", "cod"] == cod_mass_flow
    
    def initialize_build(self, state_args_in=None, state_args_out=None, 
                        outlvl=idaeslog.NOTSET, solver=None, optarg=None):
        """
        Initialize the translator block.
        
        Args:
            state_args_in: Initial values for inlet state vars
            state_args_out: Initial values for outlet state vars
            outlvl: Output level for logging
            solver: Solver to use
            optarg: Solver options
        """
        # Fix inlet state
        flags_in = fix_state_vars(self.properties_in, state_args_in)
        
        # Fix outlet state if provided
        if state_args_out is not None:
            flags_out = fix_state_vars(self.properties_out, state_args_out)
        else:
            # Estimate outlet from inlet
            for t in self.flowsheet().time:
                if hasattr(self.properties_out[t], "flow_vol"):
                    self.properties_out[t].flow_vol.set_value(
                        pyo.value(self.properties_in[t].flow_vol)
                    )
                if hasattr(self.properties_out[t], "temperature"):
                    self.properties_out[t].temperature.set_value(
                        pyo.value(self.properties_in[t].temperature)
                    )
                if hasattr(self.properties_out[t], "pressure"):
                    self.properties_out[t].pressure.set_value(
                        pyo.value(self.properties_in[t].pressure)
                    )
            flags_out = None
        
        # Revert state vars
        revert_state_vars(self.properties_in, flags_in)
        if flags_out is not None:
            revert_state_vars(self.properties_out, flags_out)


@declare_process_block_class("Translator_WaterZO_ADM1")
class Translator_WaterZO_ADM1Data(TranslatorData):
    """
    Translator block to convert Zero-Order Water properties back to ADM1.
    
    Maps TSS from MBR retentate back to ADM1 particulates for recycle.
    """
    
    CONFIG = TranslatorData.CONFIG()
    
    def build(self):
        """Build the translator block."""
        # Call parent build which creates inlet/outlet ports and state blocks
        super().build()
        
        # Get time domain
        time = self.flowsheet().time
        
        # Add translation constraints using state blocks
        @self.Constraint(time, doc="Flow volume balance")
        def flow_vol_balance(b, t):
            return b.properties_out[t].flow_vol == b.properties_in[t].flow_vol
        
        @self.Constraint(time, doc="Temperature balance")
        def temperature_balance(b, t):
            return b.properties_out[t].temperature == b.properties_in[t].temperature
        
        @self.Constraint(time, doc="Pressure balance")
        def pressure_balance(b, t):
            return b.properties_out[t].pressure == b.properties_in[t].pressure
        
        # Define sets for ADM1 components
        self.adm1_biomass = Set(initialize=[
            "X_su", "X_aa", "X_fa", "X_c4", "X_pro", "X_ac", "X_h2"
        ], doc="Active biomass components")
        
        self.adm1_particulates_other = Set(initialize=[
            "X_c", "X_ch", "X_pr", "X_li"
        ], doc="Other particulate components")
        
        self.adm1_solubles = Set(initialize=[
            "S_su", "S_aa", "S_fa", "S_va", "S_bu", "S_pro", "S_ac",
            "S_h2", "S_ch4", "S_IC", "S_IN", "S_I", "S_cat", "S_an", "S_co2"
        ], doc="Soluble components")
        
        # Parameters for TSS distribution
        self.biomass_fraction = pyo.Param(
            initialize=0.75,
            doc="Fraction of TSS that is active biomass (vs inerts)"
        )
        
        # Map TSS back to ADM1 particulates with proper distribution
        # 75% to biomass, 25% to inerts (more realistic than 100% to X_I)
        @self.Constraint(time, self.adm1_biomass, 
                        doc="Map TSS to biomass components")
        def tss_to_biomass(b, t, comp):
            if hasattr(b.properties_in[t], "conc_mass_comp") and \
               hasattr(b.properties_in[t].params, "solute_set") and \
               "tss" in b.properties_in[t].params.solute_set and \
               comp in b.properties_out[t].params.component_list:
                
                # Get inlet TSS
                tss_in = b.properties_in[t].conc_mass_comp["tss"]
                
                # Distribute biomass fraction equally among active biomass
                n_biomass = len(b.adm1_biomass)
                biomass_per_comp = (tss_in * b.biomass_fraction) / n_biomass
                
                return b.properties_out[t].conc_mass_comp[comp] == biomass_per_comp
            else:
                return pyo.Constraint.Skip
        
        # Map remaining TSS to inerts
        @self.Constraint(time, doc="Map remaining TSS to inerts")
        def tss_to_inerts(b, t):
            if hasattr(b.properties_in[t], "conc_mass_comp") and \
               "tss" in b.properties_in[t].params.solute_set and \
               "X_I" in b.properties_out[t].params.component_list:
                
                tss_in = b.properties_in[t].conc_mass_comp["tss"]
                inert_fraction = tss_in * (1 - b.biomass_fraction)
                
                return b.properties_out[t].conc_mass_comp["X_I"] == inert_fraction
            else:
                return pyo.Constraint.Skip
        
        # Set other particulates to trace levels using indexed constraints
        @self.Constraint(time, self.adm1_particulates_other, 
                        doc="Set other particulates to trace")
        def set_other_particulates(b, t, comp):
            if comp in b.properties_out[t].params.component_list:
                return b.properties_out[t].conc_mass_comp[comp] == 0.001
            else:
                return pyo.Constraint.Skip
        
        # Set solubles using indexed constraints
        @self.Constraint(time, self.adm1_solubles,
                        doc="Set soluble components")
        def set_solubles(b, t, comp):
            if comp in b.properties_out[t].params.component_list:
                # S_IC and S_IN may persist at higher levels
                if comp in ["S_IC", "S_IN"]:
                    return b.properties_out[t].conc_mass_comp[comp] == 0.01
                else:
                    return b.properties_out[t].conc_mass_comp[comp] == 0.001
            else:
                return pyo.Constraint.Skip
    
    def initialize_build(self, state_args_in=None, state_args_out=None,
                        outlvl=idaeslog.NOTSET, solver=None, optarg=None):
        """
        Initialize the translator block.
        
        Args:
            state_args_in: Initial values for inlet state vars
            state_args_out: Initial values for outlet state vars
            outlvl: Output level for logging
            solver: Solver to use
            optarg: Solver options
        """
        # Fix inlet state
        flags_in = fix_state_vars(self.inlet, state_args_in)
        
        # Fix outlet state if provided
        if state_args_out is not None:
            flags_out = fix_state_vars(self.outlet, state_args_out)
        else:
            # Estimate outlet from inlet
            for t in self.flowsheet().time:
                if hasattr(self.outlet, "flow_vol"):
                    self.outlet.flow_vol[t].set_value(
                        pyo.value(self.inlet.flow_vol[t])
                    )
                if hasattr(self.outlet, "temperature"):
                    self.outlet.temperature[t].set_value(
                        pyo.value(self.inlet.temperature[t])
                    )
                if hasattr(self.outlet, "pressure"):
                    self.outlet.pressure[t].set_value(
                        pyo.value(self.inlet.pressure[t])
                    )
            flags_out = None
        
        # Revert state vars
        revert_state_vars(self.inlet, flags_in)
        if flags_out is not None:
            revert_state_vars(self.outlet, flags_out)