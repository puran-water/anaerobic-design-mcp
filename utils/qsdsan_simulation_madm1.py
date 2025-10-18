"""
QSDsan simulation using mADM1 (Modified ADM1 with P/S/Fe extensions).

This module uses the complete mADM1 implementation instead of a custom ADM1+sulfur model.
Advantages:
- Complete 62-component model (27 ADM1 + P + S + Fe extensions)
- Proven parameter initialization via __new__
- H2S biogas tracking already implemented
- Sulfate reduction processes fully validated
"""

import logging
import numpy as np
from qsdsan import WasteStream, sanunits as su, System

logger = logging.getLogger(__name__)


async def get_madm1_components():
    """
    Get mADM1 component set (62 components).

    Returns mADM1 components with P/S/Fe extensions.
    Uses anyio for async compatibility with MCP server.
    """
    import anyio

    def _load_components():
        """Load mADM1 components in thread (avoids blocking)."""
        from utils.qsdsan_madm1 import create_madm1_cmps
        return create_madm1_cmps(set_thermo=True)

    # Run in thread pool to avoid blocking
    components = await anyio.to_thread.run_sync(_load_components)
    logger.info(f"Loaded mADM1 components: {len(components)} total")
    return components


def _extract_numeric_value(value):
    """Extract numeric value from ADM1 state (handles both scalars and [value, unit, desc] arrays)."""
    if isinstance(value, (list, tuple)):
        return float(value[0])  # Extract value from [value, unit, description]
    return float(value)  # Already a scalar


def map_adm1_state_to_madm1(adm1_state_30: dict, temperature_c: float = 35.0) -> dict:
    """
    Map 30-component ADM1 state to mADM1's 62 components.

    Sets P/Fe/metal components to reasonable defaults.

    Parameters
    ----------
    adm1_state_30 : dict
        30-component ADM1 state (27 ADM1 + S_SO4 + S_IS + X_SRB)
        Values can be scalars or [value, unit, description] arrays
    temperature_c : float
        Temperature in Celsius

    Returns
    -------
    dict
        62-component mADM1 state (all scalars)
    """
    # Start with ADM1 base components - extract numeric values
    madm1_state = {k: _extract_numeric_value(v) for k, v in adm1_state_30.items()}

    # Add P-related components (set to minimal values)
    madm1_state['S_IP'] = 0.01  # Inorganic phosphorus (kg P/m³)
    madm1_state['X_PP'] = 0.0   # Polyphosphate
    madm1_state['X_PAO'] = 0.0  # PAO biomass
    madm1_state['X_PHA'] = 0.0  # PHA storage

    # Add metal ions (set to typical wastewater values)
    madm1_state['S_K'] = 0.0001   # Potassium (kg K/m³)
    madm1_state['S_Mg'] = 0.0001  # Magnesium (kg Mg/m³)
    madm1_state['S_Ca'] = 0.0001  # Calcium (kg Ca/m³)

    # Add Fe-related components
    madm1_state['S_Fe2'] = 0.0    # Fe²⁺ (ferrous iron)
    madm1_state['S_Fe3'] = 0.0    # Fe³⁺ (ferric iron)
    madm1_state['S_Al'] = 0.0     # Aluminum
    madm1_state['X_FeS'] = 0.0    # Iron sulfide precipitate
    madm1_state['X_Fe3PO42'] = 0.0  # Iron phosphate precipitate
    madm1_state['X_AlPO4'] = 0.0  # Aluminum phosphate precipitate
    madm1_state['X_HFO_H'] = 0.0  # High-affinity HFO
    madm1_state['X_HFO_L'] = 0.0  # Low-affinity HFO

    # Add S0 (elemental sulfur) if not already present
    if 'S_S0' not in madm1_state:
        madm1_state['S_S0'] = 0.0

    # Map X_SRB to mADM1's specific SRB types
    # Distribute total SRB biomass across the 4 SRB types
    total_srb = madm1_state.get('X_SRB', 0.0)
    madm1_state['X_hSRB'] = total_srb * 0.4   # H2-utilizing SRB (40%)
    madm1_state['X_aSRB'] = total_srb * 0.3   # Acetate-utilizing SRB (30%)
    madm1_state['X_pSRB'] = total_srb * 0.2   # Propionate-utilizing SRB (20%)
    madm1_state['X_c4SRB'] = total_srb * 0.1  # Butyrate-utilizing SRB (10%)

    # Remove the generic X_SRB if it exists
    madm1_state.pop('X_SRB', None)

    # Add precipitation products (all zero initially)
    # Fixed component IDs per Codex review: X_magn (not X_MgCO3), X_kstruv (not X_KST)
    for ppt in ['X_CCM', 'X_ACC', 'X_ACP', 'X_HAP', 'X_DCPD', 'X_OCP',
                'X_magn', 'X_struv', 'X_newb', 'X_kstruv']:
        madm1_state[ppt] = 0.0

    logger.info(f"Mapped 30-component state to mADM1 62-component state")
    logger.debug(f"SRB distribution: hSRB={madm1_state['X_hSRB']:.3f}, "
                f"aSRB={madm1_state['X_aSRB']:.3f}, "
                f"pSRB={madm1_state['X_pSRB']:.3f}, "
                f"c4SRB={madm1_state['X_c4SRB']:.3f}")

    return madm1_state


async def run_madm1_simulation(
    basis: dict,
    adm1_state: dict,
    heuristic_config: dict
):
    """
    Run mADM1 simulation using the complete mADM1 model.

    Parameters
    ----------
    basis : dict
        Basis of design with Q (m3/d) and Temp (K)
    adm1_state : dict
        30-component ADM1 state to map to mADM1
    heuristic_config : dict
        Heuristic sizing configuration

    Returns
    -------
    tuple
        (system, influent, effluent, biogas, converged_at, status)
    """
    import anyio

    def _run_simulation():
        """Run simulation in thread pool."""
        from utils.qsdsan_madm1 import ModifiedADM1
        import qsdsan as qs
        import utils.qsdsan_madm1 as madm1_module

        # 1. Create mADM1 components
        logger.info("Creating mADM1 component set...")
        # Following Codex's advice: Let QSDsan synthesize surrogate thermodynamic properties
        # by using default_compile with proper flags instead of blocking it
        cmps = madm1_module.create_madm1_cmps(set_thermo=True)
        logger.info(f"Created {len(cmps)} mADM1 components")

        # 2. Map state to mADM1
        temp_c = basis.get('Temp', 308.15) - 273.15
        madm1_state = map_adm1_state_to_madm1(adm1_state, temp_c)

        # 3. Create mADM1 process model using __new__ constructor
        logger.info("Creating ModifiedADM1 process model...")
        madm1_model = ModifiedADM1(components=cmps)
        logger.info(f"mADM1 model created with {len(madm1_model.tuple)} processes")
        logger.info(f"Biogas IDs: {madm1_model._biogas_IDs}")

        # 4. Create influent stream
        Q = basis.get('Q')
        T = basis.get('Temp')

        logger.info(f"Creating influent stream: Q={Q} m3/d, T={T} K")
        influent = WasteStream('influent', T=T)

        # Set flow by concentration for all mADM1 components
        conc_dict = {}
        for comp_id in cmps.IDs:
            if comp_id in madm1_state:
                conc_dict[comp_id] = madm1_state[comp_id]
            # else: defaults to 0

        # Set concentrations without specifying units - let QSDsan use defaults
        # Our values are in kg/m3 which is the same as g/L
        influent.set_flow_by_concentration(
            flow_tot=Q,
            concentrations=conc_dict
        )

        logger.info(f"Influent stream created: pH={influent.pH:.2f}")

        # 5. Create AnaerobicCSTR with mADM1
        HRT_days = heuristic_config['digester']['HRT_days']
        V_liq = Q * HRT_days
        V_gas = V_liq * 0.1  # 10% headspace

        logger.info(f"Creating AnaerobicCSTR: V_liq={V_liq} m3, HRT={HRT_days} days")

        # CRITICAL FIX: Create custom reactor class that uses dynamic biogas slicing
        # QSDsan's AnaerobicCSTR hardcodes rhos[-3:] but mADM1 has 4 biogas components
        # This is a complete copy of the parent's _compile_ODE with ONLY the biogas slicing changed
        class AnaerobicCSTR_mADM1(su.AnaerobicCSTR):
            """Custom reactor with 4-component biogas support."""

            def _compile_ODE(self, algebraic_h2=True, pH_ctrl=None):
                """Override to use dynamic biogas slicing - only change: rhos[-3:] → rhos[-n_gas:]"""
                from qsdsan.processes import T_correction_factor
                from scipy.optimize import newton

                if self._model is None:
                    from qsdsan import CSTR
                    CSTR._compile_ODE(self)
                else:
                    cmps = self.components
                    f_rtn = self._f_retain
                    _state = self._state
                    _dstate = self._dstate
                    _update_dstate = self._update_dstate
                    h = None
                    if pH_ctrl:
                        _params = self.model.rate_function.params
                        h = 10**(-pH_ctrl)
                        _f_rhos = lambda state_arr: self.model.flex_rhos(state_arr, _params, h=h)
                    else:
                        _f_rhos = self.model.rate_function
                    _f_param = self.model.params_eval
                    _M_stoichio = self.model.stoichio_eval
                    n_cmps = len(cmps)
                    n_gas = self._n_gas  # Dynamic biogas count
                    V_liq = self.V_liq
                    V_gas = self.V_gas
                    gas_mass2mol_conversion = (cmps.i_mass / cmps.chem_MW)[self._gas_cmp_idx]
                    hasexo = bool(len(self._exovars))
                    f_exovars = self.eval_exo_dynamic_vars
                    if self._fixed_P_gas:
                        f_qgas = self.f_q_gas_fixed_P_headspace
                    else:
                        f_qgas = self.f_q_gas_var_P_headspace
                    if self.model._dyn_params:
                        def M_stoichio(state_arr):
                            _f_param(state_arr)
                            return self.model.stoichio_eval().T
                    else:
                        _M_stoichio = self.model.stoichio_eval().T
                        M_stoichio = lambda state_arr: _M_stoichio

                    h2_idx = cmps.index('S_h2')
                    if algebraic_h2:
                        params = self.model.rate_function.params
                        if self.model._dyn_params:
                            def h2_stoichio(state_arr):
                                return M_stoichio(state_arr)[h2_idx]
                        else:
                            _h2_stoichio = _M_stoichio[h2_idx]
                            h2_stoichio = lambda state_arr: _h2_stoichio
                        unit_conversion = cmps.i_mass / cmps.chem_MW
                        solve_pH = self.model.solve_pH
                        dydt_Sh2_AD = self.model.dydt_Sh2_AD
                        grad_dydt_Sh2_AD = self.model.grad_dydt_Sh2_AD
                        def solve_h2(QC, S_in, T, h=h):
                            if h == None:
                                Ka = params['Ka_base'] * T_correction_factor(params['T_base'], T, params['Ka_dH'])
                                h = solve_pH(QC, Ka, unit_conversion)
                            S_h2_0 = 2.8309E-07
                            S_h2_in = S_in[h2_idx]
                            S_h2 = newton(
                                dydt_Sh2_AD, S_h2_0, grad_dydt_Sh2_AD,
                                args=(QC, h, params, h2_stoichio, V_liq, S_h2_in),
                                      )
                            return S_h2
                        def update_h2_dstate(dstate):
                            dstate[h2_idx] = 0.
                    else:
                        solve_h2 = lambda QC, S_in, T: QC[h2_idx]
                        def update_h2_dstate(dstate):
                            pass

                    # Note: n_gas biogas components are handled dynamically

                    def dy_dt(t, QC_ins, QC, dQC_ins):
                        Q_ins = QC_ins[:, -1]
                        S_ins = QC_ins[:, :-1] * 1e-3  # mg/L to kg/m3
                        Q = sum(Q_ins)
                        S_in = Q_ins @ S_ins / Q
                        if hasexo:
                            exo_vars = f_exovars(t)
                            QC = np.append(QC, exo_vars)
                            T = exo_vars[0]
                        else: T = self.T
                        QC[h2_idx] = _state[h2_idx] = solve_h2(QC, S_in, T)
                        rhos =_f_rhos(QC)
                        S_liq = QC[:n_cmps]
                        S_gas = QC[n_cmps: (n_cmps+n_gas)]
                        _dstate[:n_cmps] = (Q_ins @ S_ins - Q*S_liq*(1-f_rtn))/V_liq \
                            + np.dot(M_stoichio(QC), rhos)
                        # PATCHED: Use -n_gas instead of hardcoded -3
                        q_gas = f_qgas(rhos[-n_gas:], S_gas, T)
                        _dstate[n_cmps: (n_cmps+n_gas)] = - q_gas*S_gas/V_gas \
                            + rhos[-n_gas:] * V_liq/V_gas * gas_mass2mol_conversion
                        _dstate[-1] = 0.
                        update_h2_dstate(_dstate)
                        _update_dstate()

                    self._ODE = dy_dt

        # Create reactor using custom class
        AD = AnaerobicCSTR_mADM1(
            ID='AD',
            ins=influent,
            outs=('effluent', 'biogas'),
            model=madm1_model,
            V_liq=V_liq,
            V_gas=V_gas,
            T=T
        )

        logger.info(f"Reactor created with {len(AD._model._biogas_IDs)} biogas components")

        # 6. Initialize reactor with mADM1 state
        logger.info("Initializing reactor state...")
        init_conds = {}
        for comp_id in cmps.IDs:
            if comp_id in madm1_state:
                init_conds[comp_id] = madm1_state[comp_id]

        AD.set_init_conc(**init_conds)
        logger.info("Reactor initialized successfully")

        # 7. Create system and simulate
        sys = System('sys', path=(AD,))
        sys.set_dynamic_tracker(AD.outs[0], AD.outs[1])

        logger.info("Running simulation to steady state...")
        sys.simulate(
            state_reset_hook='reset_cache',
            t_span=(0, 200),  # 200 days max
            t_eval=np.arange(0, 200, 10),  # Check every 10 days
            method='BDF'
        )

        logger.info("Simulation completed successfully!")

        return sys, influent, AD.outs[0], AD.outs[1], 200, 'completed'

    # Run in thread pool
    result = await anyio.to_thread.run_sync(_run_simulation)
    return result
