"""
Sulfate reduction kinetics with H2S inhibition.

Adapted from QSDsan mADM1:
- Kinetic parameters from Flores-Alsina et al. (2016) Water Research 95, 370-382
- H2S inhibition coefficients from qsdsan/processes/_madm1.py:640-757
- Stoichiometry from qsdsan/data/process_data/_madm1.tsv

Licensed under NCSA Open Source License.

Attribution:
- QSD-Group/QSDsan, adm1 branch, commit b5a0757 (2024-11-22)
- See docs/qsdsan_sulfur_attribution.md for full details
"""
import logging
import numpy as np
from qsdsan import Process, Processes
from qsdsan.processes._adm1 import substr_inhibit, non_compet_inhibit, ADM1

from utils.extract_qsdsan_sulfur_components import (
    ADM1_SULFUR_CMPS,
    SULFUR_COMPONENT_INFO
)

logger = logging.getLogger(__name__)

# ============================================================================
# KINETIC PARAMETERS FROM QSDsan mADM1
# ============================================================================

# H2S inhibition coefficients (kg COD/m³) from _madm1.py lines 690-705
# Applied to methanogens and acetogens to model SRB competition
H2S_INHIBITION = {
    # Methanogens (most sensitive)
    'KI_h2s_ac': 0.460,    # Acetoclastic methanogens
    'KI_h2s_h2': 0.400,    # Hydrogenotrophic methanogens
    'KI_h2s_pro': 0.481,   # Propionate degraders
    'KI_h2s_c4': 0.481,    # Butyrate/valerate degraders

    # SRBs (more tolerant)
    'KI_h2s_aSRB': 0.499,  # Acetate-utilizing SRB
    'KI_h2s_hSRB': 0.499,  # H2-utilizing SRB
}

# SRB kinetic parameters from mADM1
SRB_PARAMETERS = {
    # H2-utilizing SRB
    'k_hSRB': 41.125,         # Max H2 uptake rate (d⁻¹)
    'K_hSRB': 5.96e-6,        # Half-sat for H2 (kg COD/m³)
    'K_so4_hSRB': 1.04e-4 * 32.06,  # Half-sat for SO4 (kg S/m³)
    'Y_hSRB': 0.05,           # Biomass yield (kg COD/kg COD)

    # Acetate-utilizing SRB (approximated from propionate values)
    'k_aSRB': 20.0,           # Max acetate uptake rate (d⁻¹)
    'K_aSRB': 0.15,           # Half-sat for acetate (kg COD/m³)
    'Y_aSRB': 0.05,           # Biomass yield

    # Decay
    'k_dec_SRB': 0.02,        # Decay rate (d⁻¹)
    'f_sI_xb': 0.1,           # Fraction to soluble inerts

    # Inhibition
    **H2S_INHIBITION           # Include all H2S inhibition constants
}


def create_sulfate_reduction_processes():
    """
    Create SRB processes with H2S inhibition using dynamic component indexing.

    Extracts from QSDsan mADM1:
    - Stoichiometry from _madm1.tsv
    - Kinetic parameters from _madm1.py
    - H2S inhibition using non_compet_inhibit()

    Returns:
        Processes object with 3 SRB processes
    """
    params = SRB_PARAMETERS
    i_mass_IS = SULFUR_COMPONENT_INFO['S_IS']['i_mass']

    # Get dynamic component indices from the extended component set
    # CRITICAL: Do not hardcode positions - use dynamic lookup
    idx_h2 = ADM1_SULFUR_CMPS.index('S_h2')
    idx_ac = ADM1_SULFUR_CMPS.index('S_ac')
    idx_SO4 = SULFUR_COMPONENT_INFO['S_SO4']['index']
    idx_IS = SULFUR_COMPONENT_INFO['S_IS']['index']
    idx_SRB = SULFUR_COMPONENT_INFO['X_SRB']['index']

    logger.info("Creating sulfate reduction processes")
    logger.debug(f"Component indices: H2={idx_h2}, Ac={idx_ac}, SO4={idx_SO4}, IS={idx_IS}, SRB={idx_SRB}")

    # ========================================================================
    # PROCESS 1: H2-utilizing sulfate reduction with H2S inhibition
    # ========================================================================

    # Define rate function with closure-captured indices
    def rate_SRB_h2(state_arr, params):
        """
        H2-utilizing SRB rate with dynamic component indexing.

        Reaction: 4 H2 + SO4²⁻ → HS⁻ + 3 H2O + OH⁻

        Implements from mADM1:
        - Dual-substrate Monod (H2, SO4)
        - H2S non-competitive inhibition
        """
        # Use dynamic indices (captured from closure)
        S_h2 = state_arr[idx_h2]
        S_SO4 = state_arr[idx_SO4]
        S_IS = state_arr[idx_IS]
        X_SRB = state_arr[idx_SRB]

        # Dual-substrate limitation
        f_h2 = substr_inhibit(S_h2, params['K_hSRB'])
        f_so4 = substr_inhibit(S_SO4, params['K_so4_hSRB'])

        # H2S non-competitive inhibition (from mADM1)
        I_h2s = non_compet_inhibit(S_IS, params['KI_h2s_hSRB'])

        rate = params['k_hSRB'] * X_SRB * f_h2 * f_so4 * I_h2s
        return rate

    # Create Process WITHOUT rate_equation (avoids symbolic parsing)
    # Per Codex: Use process.kinetics() to attach rate function
    growth_SRB_h2 = Process(
        'growth_SRB_h2',
        reaction={
            'S_h2': -1.0,                                    # H2 consumption
            'S_SO4': -(1 - params['Y_hSRB']) * i_mass_IS,   # SO4 reduction
            'S_IS': (1 - params['Y_hSRB']),                 # Sulfide production
            'X_SRB': params['Y_hSRB'],                      # Biomass growth
        },
        ref_component='X_SRB',
        conserved_for=('COD',),  # Don't specify S - components lack i_S attribute
        parameters=('k_hSRB', 'K_hSRB', 'K_so4_hSRB', 'KI_h2s_hSRB')
    )

    # Attach kinetics AFTER Process creation to bypass symbolic parsing
    growth_SRB_h2.kinetics(
        function=rate_SRB_h2,
        parameters={
            'k_hSRB': params['k_hSRB'],
            'K_hSRB': params['K_hSRB'],
            'K_so4_hSRB': params['K_so4_hSRB'],
            'KI_h2s_hSRB': params['KI_h2s_hSRB'],
        }
    )

    logger.debug("Created growth_SRB_h2 process with dynamic indexing")

    # ========================================================================
    # PROCESS 2: Acetate-utilizing sulfate reduction with H2S inhibition
    # ========================================================================

    # Define rate function with closure-captured indices
    def rate_SRB_ac(state_arr, params):
        """
        Acetate-utilizing SRB rate with dynamic component indexing.

        Reaction: CH3COO⁻ + SO4²⁻ → 2 HCO3⁻ + HS⁻
        """
        # Use dynamic indices (captured from closure)
        S_ac = state_arr[idx_ac]
        S_SO4 = state_arr[idx_SO4]
        S_IS = state_arr[idx_IS]
        X_SRB = state_arr[idx_SRB]

        f_ac = substr_inhibit(S_ac, params['K_aSRB'])
        f_so4 = substr_inhibit(S_SO4, params['K_so4_hSRB'])
        I_h2s = non_compet_inhibit(S_IS, params['KI_h2s_aSRB'])

        rate = params['k_aSRB'] * X_SRB * f_ac * f_so4 * I_h2s
        return rate

    # Create Process WITHOUT rate_equation (avoids symbolic parsing)
    growth_SRB_ac = Process(
        'growth_SRB_ac',
        reaction={
            'S_ac': -1.5,                                    # Acetate consumption
            'S_SO4': -(1 - params['Y_aSRB']) * i_mass_IS,  # SO4 reduction
            'S_IS': (1 - params['Y_aSRB']),                 # Sulfide production
            'S_IC': 0.5,                                     # Inorganic carbon production
            'X_SRB': params['Y_aSRB'],                      # Biomass growth
        },
        ref_component='X_SRB',
        conserved_for=('COD',),  # Don't specify S - components lack i_S attribute
        parameters=('k_aSRB', 'K_aSRB', 'K_so4_hSRB', 'KI_h2s_aSRB')
    )

    # Attach kinetics AFTER Process creation
    growth_SRB_ac.kinetics(
        function=rate_SRB_ac,
        parameters={
            'k_aSRB': params['k_aSRB'],
            'K_aSRB': params['K_aSRB'],
            'K_so4_hSRB': params['K_so4_hSRB'],
            'KI_h2s_aSRB': params['KI_h2s_aSRB'],
        }
    )

    logger.debug("Created growth_SRB_ac process with dynamic indexing")

    # ========================================================================
    # PROCESS 3: SRB decay
    # ========================================================================

    # Define rate function with closure-captured index
    def rate_SRB_decay(state_arr, params):
        """SRB decay (first-order) with dynamic component indexing."""
        # Use dynamic index (captured from closure)
        X_SRB = state_arr[idx_SRB]
        return params['k_dec_SRB'] * X_SRB

    # Create Process WITHOUT rate_equation (avoids symbolic parsing)
    decay_SRB = Process(
        'decay_SRB',
        reaction={
            'X_SRB': -1.0,
            'X_c': 1.0 - params['f_sI_xb'],  # To composites
            'S_I': params['f_sI_xb']         # To soluble inerts
        },
        ref_component='X_SRB',
        conserved_for=('COD',),
        parameters=('k_dec_SRB',)
    )

    # Attach kinetics AFTER Process creation
    decay_SRB.kinetics(
        function=rate_SRB_decay,
        parameters={'k_dec_SRB': params['k_dec_SRB']}
    )

    logger.debug("Created decay_SRB process with dynamic indexing")

    processes = Processes([growth_SRB_h2, growth_SRB_ac, decay_SRB])
    logger.info(f"Created {len(processes)} sulfate reduction processes")

    return processes


def extend_adm1_with_sulfate(base_adm1=None):
    """
    Extend ADM1 with sulfate reduction processes following QSDsan patterns.

    Since ADM1() returns a read-only CompiledProcesses object, we need to:
    1. Create base ADM1 with extended 30-component set
    2. Extract processes from the compiled ADM1
    3. Create new Processes object combining ADM1 + SRB processes
    4. Compile the combined process set

    Args:
        base_adm1: Optional base ADM1 process. If None, creates new one with extended components.

    Returns:
        Extended Processes object with ADM1 + sulfur kinetics (22 ADM1 + 3 SRB processes)
    """
    logger.info("Extending ADM1 with sulfate reduction")

    if base_adm1 is None:
        # Create base ADM1 with extended 30-component set
        logger.debug("Creating new ADM1 process with 30-component set")
        base_adm1 = ADM1(components=ADM1_SULFUR_CMPS)

    logger.debug(f"Base ADM1 has {len(base_adm1)} processes")

    # Create SRB processes
    sulfate_processes = create_sulfate_reduction_processes()

    # Extract processes from compiled ADM1 (it's read-only, so we need to get the tuple)
    # ADM1 returns a CompiledProcesses object, which has a .tuple attribute
    adm1_process_list = list(base_adm1.tuple)
    # sulfate_processes is a regular Processes object, iterate directly
    srb_process_list = list(sulfate_processes)

    # Create new Processes object combining both
    combined_processes = Processes(adm1_process_list + srb_process_list)

    logger.info(f"Extended ADM1 with {len(sulfate_processes)} SRB processes")
    logger.info(f"Total processes: {len(combined_processes)} (22 ADM1 + 3 SRB)")

    # Compile the combined process set
    combined_processes.compile(to_class=Processes)

    logger.info("ADM1 successfully extended with sulfate reduction")

    return combined_processes


def create_rate_function_with_h2s_inhibition(srb_rate_functions, base_cmps, base_params, base_unit_conv=None):
    """
    Create custom rate function that applies H2S inhibition to methanogens.

    Following Codex recommendation:
    - Keep base ADM1 components (27) separate for _rhos_adm1 calls
    - Use extended state (30) for full model and SRB processes

    Args:
        srb_rate_functions: Tuple of (rate_SRB_h2, rate_SRB_ac, rate_SRB_decay)
        base_cmps: Base ADM1 components (27 components, compiled)
        base_params: Base ADM1 parameters dictionary
        base_unit_conv: Optional cached unit conversion array

    Returns:
        Custom rate function for use with set_rate_function()
    """
    # Get component index for S_IS
    idx_IS = SULFUR_COMPONENT_INFO['S_IS']['index']

    # Methanogen process indices in ADM1 (from inspection)
    IDX_UPTAKE_ACETATE = 10  # Acetoclastic methanogen
    IDX_UPTAKE_H2 = 11       # Hydrogenotrophic methanogen

    # Get H2S inhibition constants
    KI_h2s_ac = H2S_INHIBITION['KI_h2s_ac']
    KI_h2s_h2 = H2S_INHIBITION['KI_h2s_h2']

    # Capture ADM1 component count for state slicing
    adm1_count = len(base_cmps)  # 27

    logger.info(f"Creating custom rate function with H2S inhibition on methanogens")
    logger.debug(f"S_IS index: {idx_IS}, base ADM1 components: {adm1_count}")

    def rhos_adm1_with_h2s_inhibition(state_arr, params):
        """
        Custom rate function: ADM1 (22) + H2S inhibition + SRB (3).

        Following Codex's approach:
        1. Slice state to 27 components for _rhos_adm1 call
        2. Use captured base_cmps and base_params (not the extended 30-component set)
        3. Apply H2S inhibition to methanogens
        4. Append SRB rates using full 30-component state

        Args:
            state_arr: State variable array (30 components)
            params: Parameter dictionary from compiled processes (has 30 components)

        Returns:
            Rate vector (25 processes: 22 ADM1 + 3 SRB)
        """
        # Import here to avoid circular dependency
        from qsdsan.processes._adm1 import _rhos_adm1

        # 1. Get base ADM1 rates (22 processes)
        # Slice state to only ADM1 components (first 27)
        state_base = state_arr[:adm1_count]

        # Use the captured base ADM1 parameters (27 components)
        # CRITICAL: Pass a copy because _rhos_adm1 mutates the dict
        base_params_local = base_params.copy()
        if base_unit_conv is not None:
            base_params_local['unit_conv'] = base_unit_conv

        rhos_base = _rhos_adm1(state_base, base_params_local)

        # 2. Apply H2S inhibition to methanogens
        # Extract S_IS from state
        S_IS = state_arr[idx_IS]

        # Calculate H2S inhibition factors (non-competitive)
        I_h2s_ac = non_compet_inhibit(S_IS, KI_h2s_ac)
        I_h2s_h2 = non_compet_inhibit(S_IS, KI_h2s_h2)

        # Apply inhibition to methanogen rates
        rhos_base[IDX_UPTAKE_ACETATE] *= I_h2s_ac   # Acetoclastic
        rhos_base[IDX_UPTAKE_H2] *= I_h2s_h2         # Hydrogenotrophic

        # 3. Append SRB rates (3 processes)
        rate_h2, rate_ac, rate_decay = srb_rate_functions
        rhos_srb = np.array([
            rate_h2(state_arr, params),
            rate_ac(state_arr, params),
            rate_decay(state_arr, params)
        ])

        # Combine: 22 ADM1 + 3 SRB = 25 total
        return np.concatenate([rhos_base, rhos_srb])

    return rhos_adm1_with_h2s_inhibition


def extend_adm1_with_sulfate_and_inhibition(base_adm1=None):
    """
    Extend ADM1 with sulfate reduction AND apply H2S inhibition to methanogens.

    This is the complete solution that:
    1. Combines ADM1 + SRB processes (structure/stoichiometry)
    2. Sets custom rate function with H2S inhibition (kinetics)

    Following Codex recommendation: Keep base ADM1 components (27) separate for _rhos_adm1 calls,
    while using extended components (30) for the full model.

    Args:
        base_adm1: Optional base ADM1 process. If None, creates new one.

    Returns:
        Extended CompiledProcesses object with custom rate function
    """
    from qsdsan import CompiledProcesses

    logger.info("Extending ADM1 with sulfate reduction and H2S inhibition")

    # CRITICAL: Capture base ADM1 assets for _rhos_adm1 calls
    # _rhos_adm1 expects the original 27-component system
    # Since global thermo is already set to 30 components, we need to extract
    # just the first 27 components and their unit conversion
    from qsdsan import Components
    from qsdsan.processes import mass2mol_conversion
    import numpy as np

    # Get first 27 components from our extended 30-component set
    # Use tuple for slicing, then extract i_mass and chem_MW arrays
    base_cmps_tuple = ADM1_SULFUR_CMPS.tuple[:27]

    # Pre-calculate unit_conversion for 27 components
    # mass2mol_conversion needs i_mass and chem_MW arrays
    base_i_mass = np.array([c.i_mass for c in base_cmps_tuple])
    base_chem_MW = np.array([c.chem_MW for c in base_cmps_tuple])
    base_unit_conv = base_i_mass / base_chem_MW
    logger.debug(f"Pre-calculated unit conversion for {len(base_unit_conv)} base ADM1 components")

    # Get base ADM1 parameters (will use 30-component set initially)
    if base_adm1 is None:
        temp_adm1 = ADM1(components=ADM1_SULFUR_CMPS)
    else:
        temp_adm1 = base_adm1
    base_params = temp_adm1.rate_function.params.copy()

    # Create a minimal Components-like object for base 27 components
    # _rhos_adm1 needs this to access component properties
    base_cmps = Components(base_cmps_tuple)
    base_params['components'] = base_cmps
    base_params['unit_conv'] = base_unit_conv
    logger.debug(f"Captured base ADM1 parameters with {len(base_cmps)} components")

    if base_adm1 is None:
        # Create ADM1 with extended 30-component set for the full model
        logger.debug("Creating new ADM1 process with 30-component set")
        base_adm1 = ADM1(components=ADM1_SULFUR_CMPS)

    # Create SRB processes with their rate functions
    sulfate_processes = create_sulfate_reduction_processes()

    # Extract SRB rate functions for custom wrapper
    # These were created in create_sulfate_reduction_processes() with closures
    # Need to access by ID, not index
    rate_SRB_h2_func = sulfate_processes['growth_SRB_h2'].rate_function
    rate_SRB_ac_func = sulfate_processes['growth_SRB_ac'].rate_function
    rate_SRB_decay_func = sulfate_processes['decay_SRB'].rate_function

    # Combine ADM1 + SRB processes (structure)
    adm1_process_list = list(base_adm1.tuple)
    srb_process_list = list(sulfate_processes)
    combined_processes = Processes(adm1_process_list + srb_process_list)

    logger.info(f"Combined {len(adm1_process_list)} ADM1 + {len(srb_process_list)} SRB processes")

    # Compile to CompiledProcesses (enables set_rate_function method)
    # Per Codex: compile() modifies object in-place and returns None
    # After compilation, combined_processes becomes CompiledProcesses
    combined_processes.compile()
    logger.debug(f"Compiled to {type(combined_processes).__name__}")

    # Create custom rate function with H2S inhibition
    # Pass the captured base ADM1 components and parameters for _rhos_adm1 calls
    custom_rate_func = create_rate_function_with_h2s_inhibition(
        srb_rate_functions=(rate_SRB_h2_func, rate_SRB_ac_func, rate_SRB_decay_func),
        base_cmps=base_cmps,
        base_params=base_params,
        base_unit_conv=base_unit_conv
    )

    # Set the custom rate function on the compiled process
    combined_processes.set_rate_function(custom_rate_func)

    # Merge base ADM1 parameters with SRB parameters
    combined_params = base_params.copy()
    combined_params.update(SRB_PARAMETERS)
    combined_params['components'] = ADM1_SULFUR_CMPS

    # Set parameters on the rate function
    combined_processes.rate_function.set_params(**combined_params)
    logger.debug(f"Set {len(combined_params)} parameters on custom rate function")

    logger.info("Custom rate function set with H2S inhibition on methanogens")
    logger.info(f"Final model: 25 processes (22 ADM1 + 3 SRB) with H2S inhibition")

    return combined_processes


def get_h2s_inhibition_factors(S_IS_kg_m3: float) -> dict:
    """
    Calculate H2S inhibition factors for reporting.

    Useful for validation and diagnostics.

    Args:
        S_IS_kg_m3: Sulfide concentration (kg S/m³)

    Returns:
        Dictionary with inhibition factors (0-1, where 1=no inhibition)

    Example:
        >>> factors = get_h2s_inhibition_factors(0.05)  # 50 mg S/L
        >>> print(f"Methanogens: {factors['acetoclastic_methanogens']*100:.0f}% activity")
    """
    return {
        'acetoclastic_methanogens': non_compet_inhibit(
            S_IS_kg_m3, H2S_INHIBITION['KI_h2s_ac']
        ),
        'hydrogenotrophic_methanogens': non_compet_inhibit(
            S_IS_kg_m3, H2S_INHIBITION['KI_h2s_h2']
        ),
        'propionate_degraders': non_compet_inhibit(
            S_IS_kg_m3, H2S_INHIBITION['KI_h2s_pro']
        ),
        'butyrate_degraders': non_compet_inhibit(
            S_IS_kg_m3, H2S_INHIBITION['KI_h2s_c4']
        ),
        'acetate_utilizing_SRB': non_compet_inhibit(
            S_IS_kg_m3, H2S_INHIBITION['KI_h2s_aSRB']
        ),
        'h2_utilizing_SRB': non_compet_inhibit(
            S_IS_kg_m3, H2S_INHIBITION['KI_h2s_hSRB']
        ),
    }


def get_kinetic_parameters():
    """
    Get all SRB kinetic parameters for reference.

    Returns:
        Dictionary with all kinetic parameters
    """
    return SRB_PARAMETERS.copy()


def get_h2s_inhibition_constants():
    """
    Get H2S inhibition constants for reference.

    Returns:
        Dictionary with inhibition constants (kg COD/m³)
    """
    return H2S_INHIBITION.copy()


if __name__ == "__main__":
    # Test the module
    logging.basicConfig(level=logging.INFO)

    print("=== QSDsan Sulfur Kinetics Module Test ===\n")

    # 1. Create processes
    print("1. Creating sulfate reduction processes:")
    try:
        processes = create_sulfate_reduction_processes()
        print(f"   [OK] Created {len(processes)} processes")
        for p in processes:
            print(f"      - {p.ID}")
    except Exception as e:
        print(f"   [ERROR] {e}")
    print()

    # 2. H2S inhibition factors
    print("2. H2S Inhibition Factors at Different Sulfide Concentrations:")
    print(f"   {'S_IS (mg/L)':<15} {'Acetoclastic':<15} {'Hydrogenotrophic':<18} {'Status'}")
    print("   " + "-"*65)

    for S_IS_mg_l in [10, 25, 50, 75, 100]:
        S_IS_kg_m3 = S_IS_mg_l / 1000
        factors = get_h2s_inhibition_factors(S_IS_kg_m3)
        status = "OK" if factors['acetoclastic_methanogens'] > 0.7 else \
                 "Moderate" if factors['acetoclastic_methanogens'] > 0.5 else "Severe"
        print(f"   {S_IS_mg_l:<15} {factors['acetoclastic_methanogens']:<15.2f} "
              f"{factors['hydrogenotrophic_methanogens']:<18.2f} {status}")
    print()

    # 3. Kinetic parameters
    print("3. SRB Kinetic Parameters:")
    params = get_kinetic_parameters()
    print(f"   H2-utilizing SRB:")
    print(f"      k_max = {params['k_hSRB']:.2f} d^-1")
    print(f"      K_H2 = {params['K_hSRB']:.2e} kg COD/m^3")
    print(f"      Y = {params['Y_hSRB']:.3f}")
    print(f"   Acetate-utilizing SRB:")
    print(f"      k_max = {params['k_aSRB']:.2f} d^-1")
    print(f"      K_ac = {params['K_aSRB']:.3f} kg COD/m^3")
    print(f"      Y = {params['Y_aSRB']:.3f}")
