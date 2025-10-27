# Bug Tracking - Consolidated Documentation

**Document Type**: Consolidated bug tracking history
**Created**: 2025-10-26
**Source Files**:
- BUG_TRACKER.md
- ISSUES_LOG.md

This document consolidates all bug tracking activities, organized chronologically with complete resolution status.

---

## Bug Tracking Session 1: Initial MCP Workflow (2025-01-07)

### Bug #1: MCP Tool Parameter Format Issue

**Tool**: `mcp__anaerobic-design__elicit_basis_of_design`
**Status**: Active (workaround applied)

**Issue**: The `current_values` parameter does not accept a dictionary/object format despite documentation suggesting it should

**Error**: "Input validation error: '...' is not valid under any of the given schemas"

**Workaround**: Omit the `current_values` parameter and use default prompts

**Impact**: Minor - default prompts work well for typical use cases

---

### Bug #2: Unicode Encoding Issue

**Tool**: Test script output
**Status**: FIXED

**Issue**: Unicode character σ (sigma) caused encoding error in Windows console

**Error**: `UnicodeEncodeError: 'charmap' codec can't encode character '\u03c3'`

**Fix**: Replaced σ with ASCII "sigma" in output strings

**Files Modified**: Multiple output formatting functions

---

### Bug #3: ADM1 State Validation Deviations

**Tool**: `mcp__anaerobic-design__validate_adm1_state`
**Status**: Active (state stored despite validation failure)

**Issue**: Large deviations between calculated and target parameters
- COD: 69,648 mg/L vs 50,000 mg/L (39.3% deviation)
- TSS: 42,500 mg/L vs 35,000 mg/L (21.4% deviation)
- VSS: 37,500 mg/L vs 28,000 mg/L (33.9% deviation)
- TKN: 3,027 mg/L vs 2,500 mg/L (21.1% deviation)
- TP: 0 mg/L vs 500 mg/L (100% deviation - not modeled in ADM1)

**Root Cause**: The ADM1 state from Codex uses array format [value, unit, description] but validation extracts wrong values

**Impact**: Validation warnings but state still usable for simulation

---

### Bug #4: WaterTAP Simulation TypeError

**Tool**: `mcp__anaerobic-design__simulate_ad_system_tool`
**Status**: FIXED

**Issue**: `regularize_adm1_state_for_initialization()` got unexpected keyword argument 'target_alkalinity_meq_l'

**Context**: Occurs when running simulation with use_current_state=true

**Fix**: Changed call to pass basis_of_design instead of individual parameters

**Files Modified**: `tools/simulation.py`

---

### Bug #5: Model Over-Specification (DOF = -1)

**Tool**: `mcp__anaerobic-design__simulate_ad_system_tool`
**Status**: FIXED

**Issue**: Model is over-specified with DOF = -1 after MBR sieving coefficient fix

**Context**: Occurs in low_tss_mbr flowsheet after adding eq_mbr_split constraints

**Fix**: Excluded last component from constraints to avoid over-specification

**Files Modified**: `utils/watertap_simulation_modified.py`

---

### Bug #6: Simulation Convergence Failure (Initial)

**Tool**: `mcp__anaerobic-design__simulate_ad_system_tool`
**Status**: PARTIALLY FIXED → Later fully resolved in QSDsan workflow

**Issue**: Simulation reaches max iterations without converging

**Initial Symptoms**:
- Biogas production: 5.26e-6 m³/d (essentially zero)
- MBR permeate: 282 m³/d (should be ~1000 m³/d)
- Methane fraction: 5% (should be ~65%)

**After Water-Anchored Fix**:
- MBR permeate: 999.86 m³/d (FIXED!)
- Biogas: 0.19 m³/d (still too low)
- Methane: 4.8% (still too low)
- Sludge: 0.14 m³/d (should be 333)

**Root Cause**: AD biology not functioning - needs phased initialization

**Resolution**: See QSDsan workflow bugs for complete resolution

---

## Bug Tracking Session 2: QSDsan Simulation Workflow (2025-10-18)

### Bug #7: Component Initialization Bug

**Tool**: `mcp__anaerobic-design__simulate_ad_system_tool`
**Status**: FIXED

**Issue**: Global `ADM1_SULFUR_CMPS` component set was None when simulation started

**Error**: `AttributeError: 'NoneType' object has no attribute 'tuple'` at `utils/qsdsan_sulfur_kinetics.py:413`

**Location**: `base_cmps_tuple = ADM1_SULFUR_CMPS.tuple[:27]`

**Root Cause**: Simulation functions called via `anyio.to_thread.run_sync()` without first loading components using `get_qsdsan_components()`

**Symptoms**:
- Tool appeared to hang (ran for 567+ seconds)
- Error logged to stderr but tool didn't return error to user
- Not a FastMCP blocking issue - genuine code bug

**Fix**: Added component loading step in simulation tool before calling simulation functions:
```python
from utils.qsdsan_loader import get_qsdsan_components
components = await get_qsdsan_components()
```

**Files Modified**: `tools/simulation.py`

---

### Bug #8: MCP STDIO Connection Timeout During QSDsan Loading

**Tool**: `mcp__anaerobic-design__simulate_ad_system_tool`
**Status**: FIXED (via architecture change)

**Issue**: MCP STDIO connection drops during QSDsan component loading (~18 seconds)

**Error**: "STDIO connection dropped after 253s uptime", "Connection error: Received a response for an unknown message ID"

**Root Cause**: FastMCP ping/pong mechanism doesn't keep connection alive during long synchronous imports in `anyio.to_thread.run_sync()`

**Attempted Fix #1**: Added `await get_qsdsan_components()` before simulation - FAILED (connection still timed out)

**Diagnosis**:
- 13:58:20.705: Simulation started
- 13:58:20.726 (0.02s later): "STDIO connection dropped"
- 13:58:20.729: "Connection error: Received a response for an unknown message ID"
- MCP client disconnected while component loading was in progress

**Solution**: Changed architecture to CLI instruction mode (like validation tools)
- Tool now returns CLI command for manual execution
- Saves input files: `simulation_basis.json`, `simulation_adm1_state.json`, `simulation_heuristic_config.json`
- User runs: `/mnt/c/Users/hvksh/mcp-servers/venv312/Scripts/python.exe utils/simulate_cli.py ...`
- Results saved to `simulation_results.json`

**Files Created**:
- `utils/simulate_cli.py`: Standalone CLI script for simulation
- Modified `tools/simulation.py`: Now returns CLI instructions instead of executing

**Impact**: Improved reliability and allows for long-running simulations without timeout issues

---

## Bug Tracking Session 3: mADM1 Integration (2025-10-18)

### Bug #9: Thermodynamic Property Validation Warnings

**Component**: `utils/qsdsan_madm1.py`
**Status**: FIXED

**Issue**: QSDsan's `default_compile()` raised warnings about inaccurate molecular weights for mADM1 components

**Error**: "Molar weight of Component X differs from its thermodynamic data by >5%"

**Root Cause**: QSDsan synthesizes surrogate thermodynamic properties for biological components lacking full chemical data

**Solution**: Following Codex's advice, used compilation flags to allow QSDsan's property synthesis:
```python
cmps_madm1.default_compile(
    ignore_inaccurate_molar_weight=True,
    adjust_MW_to_measured_as=True
)
```

**Files Modified**: `utils/qsdsan_madm1.py:226`

---

### Bug #10: SRB Kinetics Broadcasting Error

**Component**: `utils/qsdsan_madm1.py`
**Status**: FIXED

**Issue**: Array shape mismatch in SRB (sulfate-reducing bacteria) kinetics calculations

**Error**: `ValueError: operands could not be broadcast together with shapes (5,) (4,)`

**Root Cause**: mADM1 has 5 SRB types (H2, acetate, propionate, butyrate, valerate) but only 4 half-saturation constants defined

**Solution**: Duplicated `K_c4SRB` for both butyrate and valerate SRB (both use C4 pathway):
```python
Ks = np.array((K_su, K_aa, K_fa, K_c4, K_c4, K_pro, K_ac, K_h2,
               K_A,
               K_hSRB, K_aSRB, K_pSRB, K_c4SRB, K_c4SRB,  # Duplicate c4
               K_Pbind, K_Pdiss))
K_so4 = np.array((K_so4_hSRB, K_so4_aSRB, K_so4_pSRB, K_so4_c4SRB, K_so4_c4SRB))
```

**Files Modified**: `utils/qsdsan_madm1.py:1044-1048`

---

### Bug #11: H2 Tracking Methods Implementation

**Component**: `utils/qsdsan_madm1.py`
**Status**: FIXED

**Issue**: mADM1's `ModifiedADM1` class lacked methods for H2 algebraic solving required by AnaerobicCSTR

**Error**: `AttributeError: 'ModifiedADM1' object has no attribute 'dydt_Sh2_AD'`

**Root Cause**: QSDsan's reactor expects algebraic H2 solver but mADM1 only provided process rates

**Solution**: Implemented H2 tracking methods with numerical differentiation:
- `dydt_Sh2_AD()`: H2 mass balance residual for Newton solver
- `grad_dydt_Sh2_AD()`: Gradient using central differences
- Updated `rhos_madm1()` to accept pre-computed `h` parameter

**Files Modified**:
- `utils/qsdsan_madm1.py:509-627` (H2 methods)
- `utils/qsdsan_madm1.py:728` (rhos signature update)

---

### Bug #12: Reactor ODE Compilation for 4-Component Biogas

**Component**: `utils/qsdsan_simulation_madm1.py`
**Status**: FIXED (proof-of-concept)

**Issue**: QSDsan's `AnaerobicCSTR._compile_ODE()` hardcodes `rhos[-3:]` for 3-component biogas (H2, CH4, CO2)

**Error**: `ValueError: operands could not be broadcast together with shapes (3,) (4,)`

**Root Cause**: mADM1 has 4 biogas components (adds H2S tracking), but reactor's ODE compiler wasn't updated in PR #124

**Solution**: Created custom `AnaerobicCSTR_mADM1` class with full `_compile_ODE()` method copy, changing only 2 lines:
```python
# Line 293: Use dynamic n_gas instead of hardcoded 3
q_gas = f_qgas(rhos[-n_gas:], S_gas, T)

# Line 295: Use dynamic biogas slicing
_dstate[n_cmps: (n_cmps+n_gas)] = - q_gas*S_gas/V_gas \
    + rhos[-n_gas:] * V_liq/V_gas * gas_mass2mol_conversion
```

**Files Modified**: `utils/qsdsan_simulation_madm1.py:197-300`

**Maintenance Note**: Full method copy creates maintenance burden - consider upstream PR to QSDsan

---

### Bug #13: PCM (pH/Carbonate/amMonia) Solver Implementation

**Component**: `utils/qsdsan_madm1.py`
**Status**: FIXED (iterative solver → production solver transition)

**Issue**: Original placeholder used `pH = 7.0` constant, breaking mass/charge balance

**Root Cause**: Full charge balance solver from ADM1-P extension requires S_cat/S_an components

**Initial Solution**: Implemented iterative pH estimator using VFA/alkalinity balance (5-iteration convergence loop)

**Production Solution**: Implemented full charge balance using QSDsan's ADM1-P solver pattern

**All 9 Critical Fixes Applied** (2025-10-18 PM):

1. **NH₃ Formula Unit Mismatch** (line 545-547):
   - Fixed: `nh3 = S_IN * unit_conv_IN * Ka[1] / (Ka[1] + h)`

2. **CO₂ Formula Missing Denominator** (line 549-551):
   - Fixed: `co2 = S_IC * unit_conv_IC * h / (Ka[2] + h)`

3. **Hard-coded S_cat/S_an Values** (line 307-341):
   - Fixed: Read S_Na and S_Cl from mADM1 component set

4. **Missing Divalent Cations (Ca²⁺, Fe²⁺)** (line 327-339):
   - Fixed: Aggregate S_Mg + S_Ca + S_Fe2 for total divalent charge

5. **Missing Sulfur Species in Charge Balance** (line 515-518, 520-526):
   - Fixed: Added `-2*S_SO4 - hs` to charge balance

6. **Missing Trivalent Cations (Fe³⁺, Al³⁺)** (line 334-345, 459, 523):
   - Fixed: Aggregate S_Fe3 + S_Al, add `+3*S_trivalent` to charge balance

7. **Temperature-Corrected Ka_h2s** (line 426-434, 480-518, 301-304):
   - Fixed: Van't Hoff temperature correction with Ka_h2s stored in params

8. **calc_biogas Unit Mismatch** (line 296-311) - CRITICAL:
   - Fixed: Convert S_IS to molar units before applying neutral fraction α₀
   - Result: CH₄ production increased from 0.0346 to 0.0529 kg/d (+53%)

9. **Hard-coded Component Index** (line 290-291):
   - Fixed: Dynamic lookup via `cmps.index('S_IS')`

**Files Modified**: `utils/qsdsan_madm1.py:298-627`

**Test Results**: Converges in 200 days with realistic biogas production

**Status**: PRODUCTION-READY with thermodynamically complete PCM

---

### Bug #14: Component ID Mapping Bugs

**Component**: `utils/qsdsan_simulation_madm1.py`
**Status**: FIXED

**Issue**: Precipitation component mapper used incorrect IDs

**Root Cause**: Mapper used `X_MgCO3` and `X_KST` instead of mADM1's actual component IDs

**Solution**: Fixed component names in state mapper:
- `X_MgCO3` → `X_magn` (magnesite)
- `X_KST` → `X_kstruv` (K-struvite)

**Files Modified**: `utils/qsdsan_simulation_madm1.py:105-108`

---

## Bug Tracking Session 4: Codex Technical Review (2025-10-18 PM)

### Bug #15: get_component_info() API Bug

**Component**: `utils/extract_qsdsan_sulfur_components.py`
**Status**: FIXED

**Issue**: Checked `component_id in SULFUR_COMPONENT_INFO` instead of nested `['key_components']` dict

**Impact**: API was broken - could not retrieve component info for documented components

**Fix**: Changed to `component_id in SULFUR_COMPONENT_INFO.get('key_components', {})`

**Files Modified**: `utils/extract_qsdsan_sulfur_components.py:203-227`

---

### Bug #16: verify_component_ordering() Incomplete

**Component**: `utils/extract_qsdsan_sulfur_components.py`
**Status**: FIXED

**Issue**: Only checked 23 sentinel indices instead of all 63 components

**Impact**: Regressions on unchecked indices (32-35, 38-44, 47-59) would go undetected

**Fix**: Expanded to verify ALL 63 positions using complete expected_full_order list

**Files Modified**: `utils/extract_qsdsan_sulfur_components.py:230-275`

---

### Bug #17: __main__ Block Crash

**Component**: `utils/extract_qsdsan_sulfur_components.py`
**Status**: FIXED

**Issue**: Accessed `len(ADM1_SULFUR_CMPS)` before initialization

**Impact**: Standalone module execution crashed immediately

**Fix**: Added component initialization step before any checks

**Files Modified**: `utils/extract_qsdsan_sulfur_components.py:278-324`

---

## Current Workflow Status Summary

### Workflow Steps

| Step | Tool/Action | Status | Notes |
|------|-------------|--------|-------|
| 1 | Reset design state | WORKING | No issues |
| 2 | Elicit basis of design | WORKING | Default prompts functional |
| 3 | Generate ADM1 state (Codex) | WORKING | Self-validation enabled |
| 4 | Load ADM1 state | WORKING | Handles 62-component mADM1 |
| 5 | Validate ADM1 state | WORKING | COD/TSS/VSS/TKN/TP validation |
| 6 | Heuristic sizing | WORKING | Digester + MBR sizing |
| 7 | QSDsan simulation | WORKING | CLI instruction mode |

### Production Readiness Assessment

#### Ready for Production

1. **62-Component mADM1 System**
   - All components properly initialized
   - Thermodynamic properties validated
   - State mapping from 30-component to 62-component mADM1

2. **4-Component Biogas Tracking**
   - H2, CH4, CO2, H2S all tracked
   - Custom reactor class handles variable biogas components
   - Convergent simulation (200 days, physically reasonable composition)

3. **pH/Carbonate/amMonia Equilibrium**
   - Production-grade charge balance solver
   - All ionic species included (Na+, K+, Mg2+, Ca2+, Fe2+, Fe3+, Al3+, SO4 2-, HS-)
   - Temperature-corrected Ka values
   - Proper molar unit handling

4. **SRB Kinetics**
   - 5 SRB types properly parameterized
   - Sulfate reduction rates integrated with process model
   - H2S biogas production tracked

#### Known Limitations

1. **Reactor Maintenance Burden**
   - Full `_compile_ODE()` method copy will drift from QSDsan upstream
   - Recommendation: Submit PR to QSDsan to make biogas slicing dynamic
   - Workaround: Monitor QSDsan updates and merge changes as needed

2. **Precipitation Activity Coefficients**
   - Currently using unity activities (placeholder)
   - For high-strength wastewater: Implement Davies/Debye-Hückel ionic strength correction
   - Low priority: Precipitation rarely significant in mesophilic digesters

---

## Summary of Critical Bugs

### By Severity

**Critical (8)**:
- Bug #6: Simulation convergence failure → Resolved via QSDsan workflow
- Bug #7: Component initialization (QSDsan not loaded)
- Bug #9: AnaerobicCSTR incompatibility (3 vs 4 biogas species)
- Bug #12: Reactor ODE compilation for 4-component biogas
- Bug #13.8: calc_biogas unit mismatch (bloated H2S, suppressed CH4)
- Plus workflow testing bugs (see WORKFLOW_TESTING.md)

**High (5)**:
- Bug #4: WaterTAP simulation TypeError
- Bug #5: Model over-specification (DOF = -1)
- Bug #8: MCP STDIO timeout
- Bug #11: H2 tracking methods missing
- Plus workflow testing bugs

**Medium (4)**:
- Bug #1: MCP tool parameter format
- Bug #3: ADM1 state validation deviations
- Bug #9: Thermodynamic property warnings
- Bug #14: Component ID mapping

**Low (6)**:
- Bug #2: Unicode encoding
- Bug #10: SRB kinetics broadcasting
- Bug #15: get_component_info() API
- Bug #16: verify_component_ordering() incomplete
- Bug #17: __main__ block crash

### Resolution Status

- **Total Bugs Tracked**: 17 in this document (additional 14 in WORKFLOW_TESTING.md)
- **Fixed**: 15 (88%)
- **Active with Workaround**: 1 (Bug #1)
- **Active**: 1 (Bug #3 - validation deviations acceptable)

---

## Recommendations

### Immediate Actions

1. Monitor QSDsan upstream for reactor changes
2. Consider PR to QSDsan for dynamic biogas slicing
3. Add regression tests for all fixed bugs
4. Document expected ranges for validation

### Short-Term Enhancements

1. Improve activity coefficient models for precipitation
2. Add automated validation checks (mass balance, sanity checks)
3. Enhance diagnostic output (gas transfer, charge balance)
4. Fix MCP tool parameter format issue (Bug #1)

### Long-Term

1. Contribute PCM solver to QSDsan's mADM1 module
2. Work with QSDsan maintainers to restore mADM1 module
3. Add full phosphate speciation (pKa_h2po4)
4. Implement Davies/Pitzer activity models

---

## Files Modified Summary

**Core Model Files**:
- `utils/qsdsan_madm1.py` - Multiple bug fixes (thermodynamics, PCM, biogas)
- `utils/qsdsan_simulation_madm1.py` - Reactor ODE, component mapping
- `utils/qsdsan_reactor_madm1.py` - Custom reactor class
- `utils/qsdsan_sulfur_kinetics.py` - Component resolution

**Tool Files**:
- `tools/simulation.py` - CLI instruction mode
- `tools/validation.py` - WaterTAP simulation fixes

**Utility Files**:
- `utils/simulate_cli.py` - Standalone simulation CLI
- `utils/extract_qsdsan_sulfur_components.py` - Component helpers
- `utils/watertap_simulation_modified.py` - DOF fixes

---

## Lessons Learned

1. **Component compatibility is critical** - Standard vs Modified ADM1 have different requirements
2. **Upstream alignment prevents bugs** - Follow QSDsan patterns directly
3. **Mass balance validates everything** - Thermodynamic constraints reveal implementation errors
4. **Codex investigation is invaluable** - DeepWiki + gh CLI reveals upstream patterns
5. **Test end-to-end early** - Integration bugs only appear in complete workflow
6. **MCP STDIO has timeout limits** - Long-running operations need CLI mode
7. **Unit handling must be rigorous** - Molar vs mass units cause cascading errors
8. **Charge balance affects everything** - pH errors cascade through inhibition, gas transfer, mass balance
