# Attribution for QSDsan mADM1 Sulfur Extension

## Overview

This project extends the standard ADM1 (Anaerobic Digestion Model No. 1) with sulfur/H2S capabilities by extracting and adapting components from QSDsan's experimental mADM1 (modified ADM1) implementation.

## Source Repository

- **Repository**: [QSD-Group/QSDsan](https://github.com/QSD-Group/QSDsan)
- **Branch**: `adm1` (experimental)
- **Commit**: `b5a0757` (2024-11-22)
- **License**: NCSA Open Source License

## QSDsan Components Used

### 1. Component Definitions (`utils/extract_qsdsan_sulfur_components.py`)

**Source**: `qsdsan/processes/_madm1.py` lines 88-227

**Components Extracted**:
- **S_SO4** (Sulfate): Substrate for sulfate-reducing bacteria
  - Defined via `Component.from_chemical()` using SO4-2 chemistry
  - Measured as sulfur (S), soluble, undegradable, inorganic

- **S_IS** (Total dissolved sulfide): H2S + HS⁻ + S²⁻
  - Defined via `Component.from_chemical()` using H2S chemistry
  - Measured as sulfur (S), soluble, undegradable, inorganic

- **X_SRB** (Sulfate-reducing biomass): Lumped H2 + acetate utilizers
  - Created by copying X_su biomass template from ADM1
  - Represents combined hydrogenotrophic and acetoclastic SRB populations

**Method**:
1. Attempted to import from mADM1 (if adm1 branch available)
2. Falls back to manual creation using `Component.from_chemical()` if mADM1 unavailable
3. Preserves ADM1 component ordering (positions 0-26) by appending sulfur components at positions 27-29

**Key Adaptation**:
- mADM1 has 63 components with detailed SRB speciation (6 SRB species: X_hSRB, X_pSRB, X_aSRB, etc.)
- This implementation uses **lumped X_SRB** for simplicity (combines all SRB types)
- Total component count: **30** (27 ADM1 + 3 sulfur) vs mADM1's 63

### 2. Kinetic Parameters (`utils/qsdsan_sulfur_kinetics.py`)

**Source**: `qsdsan/processes/_madm1.py` lines 640-757

**Parameters Extracted**:

#### H2S Inhibition Coefficients (kg COD/m³)
From mADM1 lines 690-705:
```python
H2S_INHIBITION = {
    'KI_h2s_ac': 0.460,    # Acetoclastic methanogens
    'KI_h2s_h2': 0.400,    # Hydrogenotrophic methanogens
    'KI_h2s_pro': 0.481,   # Propionate degraders
    'KI_h2s_c4': 0.481,    # Butyrate/valerate degraders
    'KI_h2s_aSRB': 0.499,  # Acetate-utilizing SRB
    'KI_h2s_hSRB': 0.499,  # H2-utilizing SRB
}
```

#### SRB Growth Kinetics
From mADM1 parameters and Flores-Alsina et al. (2016):
```python
SRB_PARAMETERS = {
    # H2-utilizing SRB
    'k_hSRB': 41.125,         # Max H2 uptake rate (d⁻¹)
    'K_hSRB': 5.96e-6,        # Half-sat for H2 (kg COD/m³)
    'K_so4_hSRB': 1.04e-4 * 32.06,  # Half-sat for SO4 (kg S/m³)
    'Y_hSRB': 0.05,           # Biomass yield

    # Acetate-utilizing SRB (approximated from propionate values)
    'k_aSRB': 20.0,           # Max acetate uptake rate (d⁻¹)
    'K_aSRB': 0.15,           # Half-sat for acetate (kg COD/m³)
    'Y_aSRB': 0.05,           # Biomass yield

    # Decay
    'k_dec_SRB': 0.02,        # Decay rate (d⁻¹)
}
```

**Reference**:
> Flores-Alsina, X., Solon, K., Mbamba, C.K., Tait, S., Gernaey, K.V., Jeppsson, U., Batstone, D.J., 2016. Modelling phosphorus (P), sulfur (S) and iron (Fe) interactions for dynamic simulations of anaerobic digestion processes. Water Research 95, 370-382. https://doi.org/10.1016/j.watres.2016.03.012

### 3. Stoichiometry (`utils/qsdsan_sulfur_kinetics.py`)

**Source**: `qsdsan/data/process_data/_madm1.tsv`

**Current Implementation**: Simplified stoichiometry based on biochemical reactions:

#### H2-utilizing SRB (growth_SRB_h2)
Reaction: 4 H2 + SO4²⁻ → HS⁻ + 3 H2O + OH⁻
```python
reaction={
    'S_h2': -1.0,                                    # H2 consumption
    'S_SO4': -(1 - Y_hSRB) * i_mass_IS,             # SO4 reduction
    'S_IS': (1 - Y_hSRB),                           # Sulfide production
    'X_SRB': Y_hSRB,                                # Biomass growth
}
```

#### Acetate-utilizing SRB (growth_SRB_ac)
Reaction: CH3COO⁻ + SO4²⁻ → 2 HCO3⁻ + HS⁻
```python
reaction={
    'S_ac': -1.5,                                    # Acetate consumption
    'S_SO4': -(1 - Y_aSRB) * i_mass_IS,             # SO4 reduction
    'S_IS': (1 - Y_aSRB),                           # Sulfide production
    'S_IC': 0.5,                                     # Inorganic carbon
    'X_SRB': Y_aSRB,                                # Biomass growth
}
```

**TODO**: Extract full stoichiometry from `_madm1.tsv` including:
- Nutrient (N, P) coefficients
- Precise COD/molecular weight scaling factors
- Ion balance corrections (S_cat, S_an)

### 4. Inhibition Functions (`utils/qsdsan_sulfur_kinetics.py`)

**Source**: `qsdsan/processes/_adm1.py`

**Functions Reused**:
- `substr_inhibit(S, K)`: Monod substrate limitation
- `non_compet_inhibit(I, KI)`: Non-competitive inhibition (used for H2S)

**Implementation in Rate Equations**:
```python
def rate_SRB_h2(state_arr, params):
    # Substrate limitation
    f_h2 = substr_inhibit(S_h2, params['K_hSRB'])
    f_so4 = substr_inhibit(S_SO4, params['K_so4_hSRB'])

    # H2S inhibition
    I_h2s = non_compet_inhibit(S_IS, params['KI_h2s_hSRB'])

    # Rate equation
    rate = params['k_hSRB'] * X_SRB * f_h2 * f_so4 * I_h2s
    return rate
```

## Differences from QSDsan mADM1

| Feature | QSDsan mADM1 | This Implementation |
|---------|-------------|---------------------|
| **Components** | 63 (detailed speciation) | 30 (lumped) |
| **SRB Types** | 6 species (hSRB, pSRB, aSRB, etc.) | 1 lumped X_SRB |
| **Processes** | ~40 (includes precipitation, gas transfer) | 25 (22 ADM1 + 3 SRB) |
| **Stoichiometry** | Full from _madm1.tsv | Simplified biochemical |
| **H2S Inhibition** | On all processes | On SRB only (TODO: add to methanogens) |
| **State Variables** | Full mADM1 (63-component) | ADM1 (27) + sulfur (3) |

## Design Decisions

### 1. Component Set Extension Pattern
**Decision**: Append sulfur components to ADM1 instead of using full mADM1

**Rationale**:
- Preserves compatibility with existing ADM1 state variable estimation tools
- Simpler for users (30 components vs 63)
- Sufficient for industrial wastewater (no precipitation modeling needed)
- Easier to maintain and test

**Trade-offs**:
- ❌ No mineral precipitation modeling
- ❌ Less detailed SRB speciation
- ✅ Simpler component set
- ✅ Compatible with standard ADM1 calibration data

### 2. Lumped SRB Biomass
**Decision**: Single X_SRB instead of separate X_hSRB, X_pSRB, X_aSRB

**Rationale**:
- Most industrial applications don't measure SRB speciation separately
- Reduces parameter estimation complexity
- Sufficient for biogas production and H2S inhibition modeling

**Trade-offs**:
- ❌ Cannot distinguish between acetate vs H2 competition dynamics
- ❌ Less detailed for high-sulfate wastewaters
- ✅ Easier parameter estimation
- ✅ Suitable for moderate sulfate concentrations (<500 mg/L)

### 3. Process Extension via Composition
**Decision**: Create new `Processes` object combining ADM1 + SRB

**Rationale**:
- QSDsan's ADM1 returns read-only `CompiledProcesses` object
- Cannot use `.extend()` method directly (TypeError: object is read-only)
- Composition pattern: extract process lists, combine, recompile

**Implementation**:
```python
adm1_process_list = list(base_adm1.tuple)
srb_process_list = list(sulfate_processes)
combined_processes = Processes(adm1_process_list + srb_process_list)
combined_processes.compile(to_class=Processes)
```

### 4. Dynamic Component Indexing
**Decision**: Use `ADM1_SULFUR_CMPS.index('component_id')` instead of hardcoded positions

**Rationale**:
- ADM1 has 27 components (not 24 as initially assumed)
- Future-proof against component set changes
- Prevents index mismatch bugs

**Pattern**:
```python
# Capture indices at function creation time (closure)
idx_h2 = ADM1_SULFUR_CMPS.index('S_h2')
idx_SO4 = SULFUR_COMPONENT_INFO['S_SO4']['index']

def rate_SRB_h2(state_arr, params):
    S_h2 = state_arr[idx_h2]    # Use closure-captured index
    S_SO4 = state_arr[idx_SO4]
    # ...
```

## Integration with degasser-design-mcp

### H2S Speciation (`utils/h2s_speciation.py`)

**Source**: Reused from `degasser-design-mcp/utils/speciation.py`

**Why**: DRY principle - avoid reimplementing PHREEQC-based pH-dependent speciation

**Functions Reused**:
- `strippable_fraction()`: pH-dependent H2S(aq) vs HS⁻ split
- `effective_inlet_concentration()`: Strippable H2S for biogas estimation

**Method**:
```python
# Add degasser-design-mcp to Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "degasser-design-mcp"))
from utils.speciation import strippable_fraction, effective_inlet_concentration
```

**Fallback**: Henderson-Hasselbalch approximation if PHREEQC unavailable

## Testing and Validation

### Component Set Tests
- [x] Verify 30 total components (27 ADM1 + 3 sulfur)
- [x] Verify component ordering (ADM1 0-26, sulfur 27-29)
- [x] Verify sulfur component properties (MW, i_mass, i_COD)

### Kinetics Tests
- [x] Create 3 SRB processes (growth_SRB_h2, growth_SRB_ac, decay_SRB)
- [x] Verify dynamic component indexing
- [x] Verify H2S inhibition factors

### Extension Tests
- [x] Extend ADM1 with SRB processes
- [x] Verify total process count (22 ADM1 + 3 SRB)
- [x] Verify SRB processes accessible by ID

### Pending Tests
- [ ] Extract full stoichiometry from _madm1.tsv
- [ ] Implement H2S inhibition on ADM1 methanogen processes
- [ ] Validate against mADM1 simulation results
- [ ] Test with high-sulfate wastewater case

## License Compliance

This implementation complies with QSDsan's NCSA Open Source License:

**NCSA Open Source License Requirements**:
1. ✅ Copyright notice included in source files
2. ✅ License text referenced in documentation
3. ✅ Attribution to QSD-Group/QSDsan provided
4. ✅ Modifications documented (lumped SRB, simplified stoichiometry)

**Copyright Notice** (included in source files):
```
Adapted from QSDsan mADM1:
- Kinetic parameters from Flores-Alsina et al. (2016) Water Research 95, 370-382
- H2S inhibition coefficients from qsdsan/processes/_madm1.py:640-757
- Stoichiometry from qsdsan/data/process_data/_madm1.tsv

Licensed under NCSA Open Source License.

Attribution:
- QSD-Group/QSDsan, adm1 branch, commit b5a0757 (2024-11-22)
- See docs/qsdsan_sulfur_attribution.md for full details
```

## References

1. **QSDsan Framework**:
   - Li, Y., Zhang, X., Morgan, V.L., Lohman, H.A.C., Rowles, L.S., Mittal, S., Kogler, A., Cusick, R.D., Tarpeh, W.A., Guest, J.S. (2022). QSDsan: An integrated platform for quantitative sustainable design of sanitation and resource recovery systems. Environmental Science: Water Research & Technology, 8(10), 2289-2303. https://doi.org/10.1039/D2EW00455K

2. **mADM1 Parameters**:
   - Flores-Alsina, X., Solon, K., Mbamba, C.K., Tait, S., Gernaey, K.V., Jeppsson, U., Batstone, D.J. (2016). Modelling phosphorus (P), sulfur (S) and iron (Fe) interactions for dynamic simulations of anaerobic digestion processes. Water Research, 95, 370-382. https://doi.org/10.1016/j.watres.2016.03.012

3. **Standard ADM1**:
   - Batstone, D.J., Keller, J., Angelidaki, I., Kalyuzhnyi, S.V., Pavlostathis, S.G., Rozzi, A., Sanders, W.T.M., Siegrist, H., Vavilin, V.A. (2002). The IWA Anaerobic Digestion Model No 1 (ADM1). Water Science and Technology, 45(10), 65-73. https://doi.org/10.2166/wst.2002.0292

## Contact and Contributions

This implementation is part of the anaerobic-design-mcp project.

For questions or contributions related to:
- **QSDsan**: See https://github.com/QSD-Group/QSDsan
- **This implementation**: Create an issue in the anaerobic-design-mcp repository

---

*Last updated: 2025-01-16*
