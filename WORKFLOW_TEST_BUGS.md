# Workflow Testing Results - Bug Inventory

**Test Date**: 2025-10-21
**Test Type**: Complete end-to-end workflow validation

## Test Results Summary

| Step | Status | Issues Found |
|------|--------|--------------|
| 1. Reset design state | ✅ PASS | None |
| 2. Elicit basis of design | ✅ PASS | BUG #1 (FIXED) |
| 3. Generate ADM1 state (Codex) | ✅ PASS | BUG #4 (FIXED) |
| 4. Load ADM1 state | ✅ PASS | None |
| 5. Heuristic sizing | ✅ PASS | None |
| 6. mADM1 simulation | ❌ FAIL | BUG #5 (FIXED), BUG #6 (FIXED), BUG #7 (PARTIAL) |

---

## Previously Fixed Bugs (Validated in Testing)

### ✅ BUG #1: pH Not Stored in Basis of Design
- **Status**: FIXED and verified
- **Test Result**: pH and alkalinity now correctly stored when parameter_group="essential"
- **Evidence**: Collected 5 parameters (flow, COD, temperature, pH, alkalinity) vs 3 before fix

### ✅ BUG #3: Ion-Balance Threshold Rounding
- **Status**: FIXED (not directly tested but used by Codex validation)
- **Evidence**: Codex validation reported balanced=true with deviation 0.02

### ✅ BUG #4: Codex Agent Hangs
- **Status**: FIXED and verified
- **Test Result**: Codex completed successfully without hanging
- **Evidence**:
  - Agent returned after ~2-3 minutes with validated results
  - No stderr suppression occurred
  - Validation logs visible during execution
  - Agent respected new retry limits (succeeded on first attempt)

---

## New Bugs Found During Testing

### 🐛 BUG #5: Missing fluids.numerics.PY37 Patch in simulate_cli.py
**Severity**: High
**Component**: `utils/simulate_cli.py`
**Status**: ✅ FIXED

#### Problem
Simulation crashed immediately on import:
```
AttributeError: module 'fluids.numerics' has no attribute 'PY37'
```

#### Root Cause
The monkey-patch added to `qsdsan_validation_sync.py` was not replicated in `simulate_cli.py`, which also imports QSDsan.

#### Fix Applied
Added identical patch to top of `simulate_cli.py` (lines 9-15):
```python
import fluids.numerics
if not hasattr(fluids.numerics, 'PY37'):
    fluids.numerics.PY37 = True  # Python 3.12 > 3.7
```

#### Testing
✅ QSDsan import successful after fix
✅ Component loading completed in 2.2s

---

### 🐛 BUG #6: mADM1 Component Set Missing X_c (Composite Particulate)
**Severity**: Critical
**Component**: `utils/qsdsan_sulfur_kinetics.py`
**Status**: ✅ FIXED

#### Problem
Simulation crashed when initializing ADM1 process:
```
AttributeError: 'CompiledComponents' object has no attribute 'X_c'. Did you mean: 'X_I'?
```

#### Root Cause
The QSDsan `ADM1()` process class expects the standard ADM1 component `X_c` (composite particulate organic matter), which represents slowly degradable composite material.

Our mADM1 component set (63 components) does NOT include `X_c` because we directly specify:
- `X_ch` - Carbohydrates
- `X_pr` - Proteins
- `X_li` - Lipids

Standard ADM1 has `X_c` which then hydrolyzes into X_ch, X_pr, X_li. Our mADM1 skips the `X_c` composite step.

#### Why This Matters
QSDsan's `ADM1.__new__()` method tries to set:
```python
cmps.X_c.i_N = round(N_xc * N_mw, 4)  # Fails - X_c doesn't exist
```

#### Possible Solutions

**Option 1**: Add X_c to mADM1 component set (easier but changes model structure)
- Add X_c with composition parameters
- Set X_c = 0 in all influent states (use X_ch/X_pr/X_li directly)
- QSDsan's ADM1 class will be happy

**Option 2**: Use custom ADM1 process that doesn't require X_c (correct but complex)
- Modify `extend_adm1_with_sulfate_and_inhibition()` to use modified ADM1
- Skip X_c hydrolysis step
- Directly use X_ch, X_pr, X_li hydrolysis

**Option 3**: Patch QSDsan's ADM1 class to make X_c optional (fragile)
- Monkey-patch the ADM1.__new__() method
- Check for X_c existence before setting properties
- Not recommended - breaks on QSDsan updates

#### Codex Recommendation (via /codex-opinion)
**Use Option 2** - Replace ADM1() with ModifiedADM1() to avoid X_c requirement.

Codex analysis confirmed:
- QSDsan's ADM1.__new__() expects X_c component (line 579 sets cmps.X_c.i_N)
- ModifiedADM1 in utils/qsdsan_madm1.py already supports 63-component mADM1
- ModifiedADM1 uses X_ch/X_pr/X_li directly (no X_c composite step)
- This is the **QSDsan-endorsed pattern** (matches ADM1_p_extension architecture)

#### Fix Applied
Replaced all `ADM1(components=ADM1_SULFUR_CMPS)` calls with `ModifiedADM1(components=ADM1_SULFUR_CMPS)` in utils/qsdsan_sulfur_kinetics.py:
- Line 289: Added import `from utils.qsdsan_madm1 import ModifiedADM1`
- Line 295: extend_adm1_with_sulfate_and_inhibition()
- Line 324: extend_adm1_with_sulfate_and_inhibition() (wrapper)
- Line 513: extend_adm1_with_sulfate_and_inhibition() (alternative wrapper)

#### Test Results
✅ Simulation now successfully creates ModifiedADM1 process
✅ Component set loads 63 mADM1 components without X_c error
⚠️ **Revealed BUG #7**: Component indexing issues in SRB process creation

The X_c issue is resolved, but revealed deeper component indexing problems.

---

### 🐛 BUG #7: Component Indexing and Process Creation Issues
**Severity**: Critical
**Component**: `utils/qsdsan_sulfur_kinetics.py`
**Status**: ⚠️ PARTIALLY FIXED (4 sub-issues resolved, 1 remaining)

This bug manifested as a cascade of related component indexing and process creation issues after fixing BUG #6.

#### Part 1: S_IS KeyError in create_sulfate_reduction_processes()
**Error**:
```
KeyError: 'S_IS'
  File "utils/qsdsan_sulfur_kinetics.py", line 236
    sulfate_processes = create_sulfate_reduction_processes()
```

**Root Cause**: Hardcoded dictionary-style component access `ADM1_SULFUR_CMPS['S_IS']` fails because mADM1 has different component naming (`S_IP` instead of `S_IS` for inorganic soluble phosphorus).

**Fix by Codex** (lines 26-44):
Added dynamic component resolution helpers:
```python
def _resolve_component_index(cmps, comp_id):
    """Return component index, raise a helpful error if missing."""
    from qsdsan._components import UndefinedComponent
    try:
        return cmps.index(comp_id)
    except (ValueError, AttributeError, UndefinedComponent) as err:
        raise KeyError(f"Component '{comp_id}' not found") from err

def _resolve_srb_component(cmps):
    """Resolve the SRB biomass component in the current component set."""
    from qsdsan._components import UndefinedComponent
    for candidate in ('X_SRB', 'X_hSRB'):
        try:
            return candidate, cmps.index(candidate)
        except (ValueError, AttributeError, UndefinedComponent):
            continue
    raise KeyError("No SRB biomass component found")
```

Reworked create_sulfate_reduction_processes() to use `.index()` lookups instead of dictionary access.

**Status**: ✅ FIXED

---

#### Part 2: UndefinedComponent Not Caught
**Error**:
```
qsdsan._components.UndefinedComponent: 'X_SRB'
  File "utils/qsdsan_sulfur_kinetics.py", line 38
    return candidate, cmps.index(candidate)
```

**Root Cause**: QSDsan raises `UndefinedComponent` (not `ValueError`) when a component is not found. The helper functions only caught `ValueError` and `AttributeError`.

**Fix Applied** (lines 28, 39):
Added `UndefinedComponent` to exception handling:
```python
from qsdsan._components import UndefinedComponent
try:
    return cmps.index(comp_id)
except (ValueError, AttributeError, UndefinedComponent) as err:
    raise KeyError(...) from err
```

**Status**: ✅ FIXED

---

#### Part 3: Cannot Set Attribute on Processes Object
**Error**:
```
TypeError: can't set attribute; use <Processes>.append or <Processes>.extend instead
  Line 291: processes._srb_biomass_id = srb_biomass_id
```

**Root Cause**: Codex's initial fix tried to attach `_srb_biomass_id` as an attribute on the `Processes` object, but QSDsan's `Processes` class doesn't allow arbitrary attribute assignment.

**Fix Applied** (line 294):
Changed create_sulfate_reduction_processes() to return a tuple:
```python
# Return both processes and the SRB biomass ID for downstream use
return processes, srb_biomass_id
```

Updated all 3 call sites to unpack the tuple (lines 329, 518, 683):
```python
sulfate_processes, srb_biomass_id = create_sulfate_reduction_processes()
```

**Status**: ✅ FIXED

---

#### Part 4: Duplicate Process IDs
**Error**:
```
ValueError: Processes with duplicate IDs were found: {'growth_SRB_h2'}
Biomass IDs: ('X_su', 'X_aa', 'X_fa', 'X_c4', 'X_pro', 'X_ac', 'X_h2',
              'X_PAO', 'X_hSRB', 'X_aSRB', 'X_pSRB', 'X_c4SRB', 'X_hSRB')
                                                                 ^^^^^^ duplicate
```

**Root Cause (Identified by Codex)**: ModifiedADM1 **already ships with sulfur biology** (process IDs `growth_SRB_h2`, biomass IDs `X_hSRB`, `X_aSRB`, etc.). When `extend_adm1_with_sulfate_and_inhibition()` runs, it calls `create_sulfate_reduction_processes()` and appends those **same SRB reactions** to the base ADM1 tuple again, causing duplicates.

**Fix Applied** (lines 514-584):
1. Build set of existing process IDs before combining
2. Filter out SRB processes that already exist in ModifiedADM1
3. Only append `srb_biomass_id` to biomass_IDs if not already present
4. Only compile if we created a new Processes object
5. Skip custom rate function if using built-in SRB kinetics

```python
existing_process_ids = {p.ID for p in base_adm1.tuple}
srb_process_list = [p for p in sulfate_processes if p.ID not in existing_process_ids]

if len(srb_process_list) == 0:
    processes = base_adm1  # Use built-in SRB kinetics
else:
    processes = Processes(adm1_process_list + srb_process_list)

if srb_biomass_id not in base_adm1._biomass_IDs:
    ADM1_Sulfur._biomass_IDs = (*base_adm1._biomass_IDs, srb_biomass_id)
else:
    ADM1_Sulfur._biomass_IDs = base_adm1._biomass_IDs
```

**Test Results**:
✅ Duplicate process ID error FIXED
✅ No duplicate X_hSRB in biomass IDs
⚠️ **Revealed BUG #7 Part 5**: X_SRB component name mismatch

**Status**: ✅ FIXED

---

#### Part 5: X_SRB Component Name Mismatch (CURRENT BLOCKER)
**Error**:
```
KeyError: 'X_SRB'
qsdsan._components.UndefinedComponent: 'X_SRB'
  File "utils/qsdsan_simulation_sulfur.py", line 159
    inf.set_flow_by_concentration(...)
```

**Root Cause**: The simulation code (qsdsan_simulation_sulfur.py) is hardcoded to use **lumped SRB biomass** (`X_SRB`), but mADM1 uses **disaggregated SRB biomass** components:
- `X_hSRB` - Hydrogen-utilizing SRB
- `X_aSRB` - Acetate-utilizing SRB
- `X_pSRB` - Propionate-utilizing SRB
- `X_c4SRB` - Butyrate/valerate-utilizing SRB

**Locations**:
- Line 144: Default init_conds includes `('X_SRB', 0.01)`
- Lines 257-259: X_SRB validation check
- Line 495: Logging statement references X_SRB

**Investigation Needed**:
- Determine if we should map X_SRB → X_hSRB (primary SRB)
- Or distribute X_SRB seed population across all 4 SRB types
- Update influent stream creation to handle disaggregated biomass

**Status**: ⚠️ UNDER INVESTIGATION

---

### Key Insight from Codex

**ModifiedADM1 already contains complete sulfur biology**. The `extend_adm1_with_sulfate_and_inhibition()` function may be redundant for mADM1 use cases. We might only need:
1. H2S inhibition logic (if not already in ModifiedADM1)
2. Component mapping for influent/effluent streams
3. Analysis tools for sulfur metrics

**Question**: Do we even need the extend function if ModifiedADM1 has all components and processes?

---

#### Summary of BUG #7 Fixes

**Files Modified**: `utils/qsdsan_sulfur_kinetics.py`

**Changes Made**:
1. Added dynamic component resolution helpers (lines 26-44)
2. Reworked create_sulfate_reduction_processes() to use runtime lookups (lines 230-294)
3. Added UndefinedComponent exception handling (lines 28, 39)
4. Changed return signature to tuple (line 294)
5. Updated 3 call sites to unpack tuple (lines 329, 518, 683)
6. Replaced ADM1 with ModifiedADM1 (lines 22, 295, 324, 513)

**Progress**: 4 of 5 sub-issues resolved, 1 remaining

---

### ⚠️ BUG #2: ADM1 State JSON Format (Still Deferred)
**Status**: Not blocking workflow, remains low priority

---

## Workflow Success Rate

- **Steps Completed**: 5/6 (83%)
- **Critical Path Blocked**: Yes (simulation fails on BUG #7 part 4)
- **User-Facing Workflow**: Cannot complete end-to-end until duplicate process ID issue resolved
- **Progress on Blockers**:
  - BUG #5: ✅ FIXED
  - BUG #6: ✅ FIXED
  - BUG #7: ⚠️ 4 of 5 sub-issues fixed, 1 remaining

---

## Next Actions

1. **IMMEDIATE**: Fix BUG #7 part 4 (duplicate process IDs)
   - Investigate why X_hSRB appears twice in biomass_IDs
   - Check process combination logic in extend_adm1_with_sulfate_and_inhibition()
   - Verify sulfate_processes only added once

2. **VERIFY**: Re-run simulation to confirm it completes successfully
   - Target: All 6 workflow steps passing
   - Confirm biogas production, COD removal, H2S metrics

3. **COMMIT**: All fixes once workflow passes
   - BUG #5: fluids.numerics.PY37 patch
   - BUG #6: ModifiedADM1 replacement
   - BUG #7: Dynamic component resolution and process creation fixes

4. **DOCUMENT**: Update BUG_FIXES_SUMMARY.md with complete bug inventory

---

## Files Modified This Session

1. `utils/simulate_cli.py` - Added fluids.numerics.PY37 patch (BUG #5)
2. `utils/qsdsan_sulfur_kinetics.py` - Major refactoring (BUG #6, BUG #7)
   - Replaced ADM1 with ModifiedADM1 (4 locations)
   - Added dynamic component resolution helpers
   - Reworked create_sulfate_reduction_processes() with runtime lookups
   - Changed return signature to tuple (processes, srb_biomass_id)
   - Updated 3 call sites to unpack tuple
   - Added UndefinedComponent exception handling

---

## Test Evidence Files

- `simulation_basis.json` - Basis of design used for simulation
- `simulation_adm1_state.json` - ADM1 state from Codex (62 components, validated)
- `simulation_heuristic_config.json` - Heuristic sizing configuration
- `adm1_state.json` - Latest Codex-generated state (COD=4886 mg/L, pH=7.02, VALID)
