"""
Extract sulfur components from QSDsan mADM1.

Based on QSD-Group/QSDsan, adm1 branch, commit b5a0757 (2024-11-22)
Licensed under NCSA Open Source License

This module creates an extended component set by:
1. Starting with standard 24-state ADM1
2. Extracting S_SO4, S_IS from QSDsan mADM1
3. Creating lumped X_SRB biomass
4. Maintaining ADM1 state vector ordering (positions 0-23 unchanged)

Attribution:
- Component definitions from qsdsan/processes/_madm1.py:88-227
- See docs/qsdsan_sulfur_attribution.md for full attribution
"""
import logging
from qsdsan import Component, Components
import qsdsan as qs

logger = logging.getLogger(__name__)

# Global component set (initialized on first import)
ADM1_SULFUR_CMPS = None
SULFUR_COMPONENT_INFO = None


def create_adm1_sulfur_cmps():
    """
    Create 30-component set: ADM1 (27) + Sulfur (3).

    ADM1 has 27 components (0-26): S_su...X_I, S_cat, S_an, H2O
    Sulfur components appended at end:
    - S_SO4: Sulfate (position 27)
    - S_IS: Total dissolved sulfide - H2S + HS⁻ + S²⁻ (position 28)
    - X_SRB: Lumped sulfate-reducing biomass (position 29)

    Returns:
        Components object with 30 components

    Raises:
        ImportError: If QSDsan ADM1 components cannot be loaded
    """
    logger.info("Creating extended ADM1+sulfur component set (30 components)")

    try:
        from qsdsan.processes._adm1 import create_adm1_cmps
    except ImportError as e:
        raise ImportError(
            f"Could not import QSDsan ADM1 components: {e}. "
            "Ensure QSDsan is installed and accessible."
        )

    # Try to import mADM1 (only available in adm1 branch)
    try:
        from qsdsan.processes._madm1 import create_madm1_cmps
        madm1_available = True
    except ImportError:
        madm1_available = False
        logger.warning("mADM1 module not available (requires QSDsan adm1 branch)")

    # Get base ADM1 components (positions 0-26) WITHOUT setting thermo yet
    # CRITICAL: Do not modify order - ADM1 kinetics depend on state vector positions
    # ADM1 has 27 components ending with S_cat, S_an, H2O
    base_cmps_compiled = create_adm1_cmps(set_thermo=False)
    logger.info(f"Loaded {len(base_cmps_compiled)} standard ADM1 components")

    # Verify ADM1 structure
    if len(base_cmps_compiled) != 27:
        raise RuntimeError(f"Expected 27 ADM1 components, got {len(base_cmps_compiled)}")
    last_three = list(base_cmps_compiled.IDs[-3:])
    if last_three != ['S_cat', 'S_an', 'H2O']:
        raise RuntimeError(f"Unexpected ADM1 component ordering, last 3: {last_three}")

    # Get mADM1 components (for extraction) or create manually
    if madm1_available:
        # Extract sulfur species from mADM1 (preferred method)
        madm1_cmps = create_madm1_cmps(set_thermo=False)
        logger.info(f"Loaded {len(madm1_cmps)} mADM1 components for extraction")

        # Position 27: S_SO4 - Sulfate
        S_SO4 = madm1_cmps['S_SO4'].copy('S_SO4')
        S_SO4.description = 'Sulfate (SO4²⁻) - substrate for sulfate-reducing bacteria'
        logger.debug(f"Extracted S_SO4: MW={S_SO4.chem_MW:.2f} g/mol, i_mass={S_SO4.i_mass:.4f}")

        # Position 28: S_IS - Total dissolved sulfide
        S_IS = madm1_cmps['S_IS'].copy('S_IS')
        S_IS.description = 'Total dissolved sulfide (H2S + HS⁻ + S²⁻)'
        logger.debug(f"Extracted S_IS: MW={S_IS.chem_MW:.2f} g/mol, i_mass={S_IS.i_mass:.4f}")

        # Position 29: X_SRB - Lumped sulfate-reducing biomass
        # Based on X_hSRB from mADM1, but lumped for simplicity
        X_SRB = madm1_cmps['X_hSRB'].copy('X_SRB')
        X_SRB.ID = 'X_SRB'
        X_SRB.description = 'Lumped sulfate-reducing biomass (H2 + acetate utilizers)'
        logger.debug(f"Created X_SRB (lumped): i_COD={X_SRB.i_COD:.3f}, i_N={X_SRB.i_N:.4f}")
    else:
        # Create sulfur components manually if mADM1 unavailable
        logger.info("Creating sulfur components manually from QSDsan primitives")
        from qsdsan import Component

        S_SO4 = Component.from_chemical('S_SO4', chemical='SO4-2',
                                       description='Sulfate (SO4²⁻) - substrate for SRB',
                                       measured_as='S',
                                       particle_size='Soluble',
                                       degradability='Undegradable',
                                       organic=False)
        S_IS = Component.from_chemical('S_IS', chemical='H2S',
                                      description='Total dissolved sulfide (H2S + HS⁻ + S²⁻)',
                                      measured_as='S',
                                      particle_size='Soluble',
                                      degradability='Undegradable',
                                      organic=False)
        # Create SRB biomass similar to other ADM1 biomass
        X_SRB = base_cmps_compiled['X_su'].copy('X_SRB')
        X_SRB.description = 'Lumped sulfate-reducing biomass (H2 + acetate utilizers)'

        logger.info("Created sulfur components manually (mADM1 not available)")

    # Build complete component list: ADM1 (27) + sulfur (3)
    # Following QSDsan pattern from _madm1.py: reuse component INSTANCES from compiled set
    # This preserves all properties (molar weights, etc.) that were set during ADM1 creation
    all_cmps_list = list(base_cmps_compiled.tuple) + [S_SO4, S_IS, X_SRB]
    extended_cmps = Components(all_cmps_list)

    logger.info(f"Extended component set created: {len(extended_cmps)} total components (27 ADM1 + 3 sulfur)")

    # Compile using same flags as ADM1 to preserve properties
    # This is the KEY FIX per Codex recommendation
    extended_cmps.default_compile(
        ignore_inaccurate_molar_weight=True,
        adjust_MW_to_measured_as=True
    )
    # Set active thermo on QSDsan (best-practice wrapper)
    qs.set_thermo(extended_cmps)

    logger.info("Component thermodynamics set successfully")

    return extended_cmps


def _init_component_info():
    """Initialize component info dictionary after component set is created."""
    global SULFUR_COMPONENT_INFO

    if ADM1_SULFUR_CMPS is None:
        raise RuntimeError("Component set not initialized. Call create_adm1_sulfur_cmps() first.")

    # Use dynamic indexing to get positions
    idx_SO4 = ADM1_SULFUR_CMPS.index('S_SO4')
    idx_IS = ADM1_SULFUR_CMPS.index('S_IS')
    idx_SRB = ADM1_SULFUR_CMPS.index('X_SRB')

    SULFUR_COMPONENT_INFO = {
        'S_SO4': {
            'index': idx_SO4,
            'description': 'Sulfate (SO4 2-)',
            'units': 'kg S/m3',
            'i_mass': ADM1_SULFUR_CMPS['S_SO4'].i_mass,
            'MW': ADM1_SULFUR_CMPS['S_SO4'].chem_MW,
            'typical_range_mg_l': (10, 500),
            'notes': 'Substrate for sulfate-reducing bacteria'
        },
        'S_IS': {
            'index': idx_IS,
            'description': 'Total dissolved sulfide (H2S + HS- + S2-)',
            'units': 'kg S/m3',
            'i_mass': ADM1_SULFUR_CMPS['S_IS'].i_mass,
            'MW': ADM1_SULFUR_CMPS['S_IS'].chem_MW,
            'typical_range_mg_l': (0.1, 100),
            'inhibition_threshold_mg_l': 50,
            'notes': 'Methanogen inhibitor, pH-dependent speciation'
        },
        'X_SRB': {
            'index': idx_SRB,
            'description': 'Sulfate-reducing biomass (lumped)',
            'units': 'kg COD/m3',
            'i_COD': ADM1_SULFUR_CMPS['X_SRB'].i_COD if hasattr(ADM1_SULFUR_CMPS['X_SRB'], 'i_COD') else 1.42,
            'i_N': ADM1_SULFUR_CMPS['X_SRB'].i_N if hasattr(ADM1_SULFUR_CMPS['X_SRB'], 'i_N') else 0.086,
            'typical_range_mg_l': (1, 50),
            'notes': 'Competes with methanogens for H2 and acetate'
        }
    }

    logger.debug(f"Component info initialized: S_SO4 at {idx_SO4}, S_IS at {idx_IS}, X_SRB at {idx_SRB}")


# Component set will be initialized via async loader (utils/qsdsan_loader.py)
# This prevents blocking the MCP event loop during module import
ADM1_SULFUR_CMPS = None
SULFUR_COMPONENT_INFO = None

logger.info("Component set initialization deferred to async loader")


def set_global_components(components):
    """
    Set the global component set (called by async loader).

    Args:
        components: The compiled QSDsan Components object
    """
    global ADM1_SULFUR_CMPS
    ADM1_SULFUR_CMPS = components
    _init_component_info()
    logger.info("Global ADM1_SULFUR_CMPS set by async loader")


def get_component_info(component_id: str = None):
    """
    Get information about sulfur components.

    Args:
        component_id: Optional component ID ('S_SO4', 'S_IS', 'X_SRB').
                     If None, returns info for all sulfur components.

    Returns:
        Dictionary with component information

    Example:
        >>> info = get_component_info('S_SO4')
        >>> print(f"Sulfate MW: {info['MW']:.2f} g/mol")
    """
    if SULFUR_COMPONENT_INFO is None:
        raise RuntimeError("Component info not initialized")

    if component_id is None:
        return SULFUR_COMPONENT_INFO
    elif component_id in SULFUR_COMPONENT_INFO:
        return SULFUR_COMPONENT_INFO[component_id]
    else:
        raise ValueError(f"Unknown component ID: {component_id}. Valid IDs: S_SO4, S_IS, X_SRB")


def verify_component_ordering():
    """
    Verify that ADM1 component ordering is preserved.

    This is critical - ADM1 kinetics depend on specific state vector positions.

    Returns:
        Boolean indicating if ordering is correct

    Raises:
        AssertionError: If component ordering is incorrect
    """
    if ADM1_SULFUR_CMPS is None:
        raise RuntimeError("Component set not initialized")

    # Check total count
    assert len(ADM1_SULFUR_CMPS) == 30, f"Expected 30 components, got {len(ADM1_SULFUR_CMPS)}"

    # Check critical ADM1 positions (standard ADM1 is 0-26)
    expected_order = {
        0: 'S_su',
        1: 'S_aa',
        6: 'S_ac',
        7: 'S_h2',
        10: 'S_IN',   # Corrected: S_IN at 10, not S_IC
        11: 'S_I',    # Corrected: S_I at 11, not S_IN
        23: 'X_I',
        24: 'S_cat',  # ADM1 component 24
        25: 'S_an',   # ADM1 component 25
        26: 'H2O',    # ADM1 component 26
        27: 'S_SO4',  # First sulfur component
        28: 'S_IS',   # Second sulfur component
        29: 'X_SRB'   # Third sulfur component
    }

    for idx, expected_id in expected_order.items():
        actual_id = ADM1_SULFUR_CMPS.IDs[idx]
        assert actual_id == expected_id, \
            f"Component ordering broken: position {idx} is '{actual_id}', expected '{expected_id}'"

    logger.info("Component ordering verified: ADM1 positions 0-26 preserved, sulfur at 27-29")
    return True


if __name__ == "__main__":
    # Test the module
    logging.basicConfig(level=logging.INFO)

    print("=== QSDsan Sulfur Component Extraction Test ===\n")

    # 1. Verify component set
    print("1. Component Set:")
    print(f"   Total components: {len(ADM1_SULFUR_CMPS)}")
    print(f"   First 5: {ADM1_SULFUR_CMPS.IDs[:5]}")
    print(f"   Last 5: {ADM1_SULFUR_CMPS.IDs[-5:]}")
    print()

    # 2. Verify ordering
    print("2. Component Ordering Verification:")
    try:
        verify_component_ordering()
        print("   [OK] Component ordering is correct")
    except AssertionError as e:
        print(f"   [FAIL] Component ordering error: {e}")
    print()

    # 3. Sulfur component info
    print("3. Sulfur Component Details:")
    for cid in ['S_SO4', 'S_IS', 'X_SRB']:
        info = get_component_info(cid)
        print(f"   {cid} (position {info['index']}):")
        print(f"      Description: {info['description']}")
        print(f"      Units: {info['units']}")
        if 'MW' in info:
            print(f"      Molecular weight: {info['MW']:.2f} g/mol")
        if 'typical_range_mg_l' in info:
            print(f"      Typical range: {info['typical_range_mg_l'][0]}-{info['typical_range_mg_l'][1]} mg/L")
        print()
