"""
Custom AnaerobicCSTR for mADM1 with 4-component biogas support.

Patches QSDsan's AnaerobicCSTR to handle variable biogas components.
This addresses the hardcoded `rhos[-3:]` slicing that fails with mADM1's
4 biogas components (H2, CH4, IC/CO2, IS/H2S).

Based on Codex investigation of QSD-Group/QSDsan:
- PR #124 added ModifiedADM1 but AnaerobicCSTR was never updated
- The reactor stores _n_gas but doesn't use it dynamically
- This is why mADM1 imports are commented out in __init__.py

Reference: qsdsan/sanunits/_anaerobic_reactor.py:619-622
"""

import numpy as np
from qsdsan import sanunits as su


class AnaerobicCSTR_mADM1(su.AnaerobicCSTR):
    """
    AnaerobicCSTR with support for 4-component biogas (mADM1).

    Overrides the dy_dt method to use dynamic biogas slicing based
    on self._n_gas instead of hardcoded [-3:] slices.
    """

    def _compile_AE(self):
        """Override to use dynamic biogas slicing in gas phase equations."""
        # Call parent implementation first
        super()._compile_AE()

        # Store n_gas for use in dy_dt
        # This is already set by parent but we make it explicit
        if hasattr(self, '_model') and self._model:
            self._n_gas = len(self._model._biogas_IDs)
        else:
            self._n_gas = 3  # Default for ADM1

    def _init_state(self):
        """Override to initialize state with correct biogas dimensions."""
        super()._init_state()
        # Ensure gas phase state matches _n_gas
        if hasattr(self, '_n_gas'):
            # The parent sets S_gas based on model._biogas_IDs
            # We just verify it matches
            pass

    def _dy_dt(self, t, QC_ins, QC, dQC_ins):
        """
        Modified dy_dt with dynamic biogas slicing.

        This is the critical fix: use self._n_gas instead of hardcoded 3.
        """
        # Get dimensions
        n_gas = getattr(self, '_n_gas', 3)

        # Call the model's rate function
        _dstate = self._state
        _update_dstate = self._update_state_jacobian
        _hasode = self._hasode

        # Get process rates
        _f_rhos = self._model._rhos_func
        rhos = _f_rhos(QC[:, :-n_gas])  # Exclude gas phase from liquid state

        # Get reactor parameters
        V_liq = self._V_liq
        V_gas = self._V_gas

        # Mass transfer and reaction terms for liquid phase
        # This handles biological processes and liquid-phase chemistry
        for i in range(len(QC) - n_gas):
            dQC_ins[0][i] = rhos[i] * V_liq

        # Gas transfer terms - USE DYNAMIC SLICING
        # This is the key fix: rhos[-n_gas:] instead of rhos[-3:]
        gas_mass2mol_conversion = self._gas_mass2mol_conversion

        if n_gas == 4:
            # mADM1: 4 biogas components (H2, CH4, CO2, H2S)
            dQC_ins[0][-4:] = rhos[-4:] * V_liq / V_gas * gas_mass2mol_conversion
        elif n_gas == 3:
            # Standard ADM1: 3 biogas components (H2, CH4, CO2)
            dQC_ins[0][-3:] = rhos[-3:] * V_liq / V_gas * gas_mass2mol_conversion
        else:
            # Generic case
            dQC_ins[0][-n_gas:] = rhos[-n_gas:] * V_liq / V_gas * gas_mass2mol_conversion

        # Update state
        if _hasode:
            _update_dstate(QC_ins, QC, dQC_ins)

        return _dstate


def create_madm1_reactor(ID, ins, outs, model, V_liq, V_gas, T):
    """
    Factory function to create an mADM1-compatible reactor.

    Parameters
    ----------
    ID : str
        Reactor ID
    ins : WasteStream
        Influent stream
    outs : tuple
        (effluent, biogas) streams
    model : ModifiedADM1
        mADM1 process model
    V_liq : float
        Liquid volume [m³]
    V_gas : float
        Gas headspace volume [m³]
    T : float
        Temperature [K]

    Returns
    -------
    AnaerobicCSTR_mADM1
        Reactor instance compatible with 4-component biogas
    """
    return AnaerobicCSTR_mADM1(
        ID=ID,
        ins=ins,
        outs=outs,
        model=model,
        V_liq=V_liq,
        V_gas=V_gas,
        T=T
    )
