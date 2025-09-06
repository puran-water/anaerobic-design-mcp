#!/usr/bin/env python3
"""Debug DOF issue with volumetric constraints."""

import pyomo.environ as pyo
from idaes.core.util.model_statistics import degrees_of_freedom

# Create a simple test model to understand DOF
m = pyo.ConcreteModel()

# Mock properties
m.flow_vol_in = pyo.Var(initialize=1.0)
m.flow_vol_out1 = pyo.Var(initialize=0.2)
m.flow_vol_out2 = pyo.Var(initialize=0.8)

# Component splits (say we have 3 components including H2O)
m.split_H2O = pyo.Var(bounds=(0,1), initialize=0.2)
m.split_S = pyo.Var(bounds=(0,1), initialize=0.999)
m.split_X = pyo.Var(bounds=(0,1), initialize=0.001)

print("Initial DOF before constraints:", degrees_of_freedom(m))

# Standard Separator constraint: sum of outlets = inlet
m.mass_balance = pyo.Constraint(expr=m.flow_vol_out1 + m.flow_vol_out2 == m.flow_vol_in)
print("DOF after mass balance:", degrees_of_freedom(m))

# If we fix inlet
m.flow_vol_in.fix(1.0)
print("DOF after fixing inlet:", degrees_of_freedom(m))

# Case 1: Standard approach - fix splits
m.split_H2O.fix(0.2)
m.split_S.fix(0.999)
m.split_X.fix(0.001)
print("DOF after fixing all splits:", degrees_of_freedom(m))

# Case 2: Volumetric constraints approach
m.split_H2O.unfix()  # Unfix H2O split
print("DOF after unfixing H2O split:", degrees_of_freedom(m))

# Add volumetric constraints
m.vol_constraint1 = pyo.Constraint(expr=m.flow_vol_out1 == 0.2 * m.flow_vol_in)
m.vol_constraint2 = pyo.Constraint(expr=m.flow_vol_out2 == 0.8 * m.flow_vol_in)
print("DOF after adding volumetric constraints:", degrees_of_freedom(m))

print("\nConclusion:")
print("With componentFlow Separator and volumetric constraints:")
print("1. We must NOT fix H2O split fraction")
print("2. We ADD 2 volumetric constraints") 
print("3. The volumetric constraints determine flow_vol_out1 and flow_vol_out2")
print("4. H2O split becomes a dependent variable")
print("\nThe issue: We're likely not properly unfixing H2O or there's a conflict elsewhere")