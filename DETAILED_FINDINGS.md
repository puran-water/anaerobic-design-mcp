# Detailed Dead Code Analysis - Complete Reference

## 1. Dead Tool Files (5 files, 46.8 KB total)

### File: `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/tools/sizing.py`
- **Size:** 6.8 KB
- **Status:** DEAD CODE
- **Implementation:** Async function `heuristic_sizing_ad()` that calls `perform_heuristic_sizing()` directly
- **Why dead:** 
  - Never imported in server.py
  - server.py (line 389-510) has its own implementation that uses JobManager subprocess pattern
  - Would cause name conflict if both were imported
- **Blocking risk:** Direct call to `perform_heuristic_sizing()` takes 10-30 seconds, blocking event loop
- **Imports from:**
  - `core.state` - design_state
  - `core.utils` - coerce_to_dict, to_float
  - `utils.heuristic_sizing` - perform_heuristic_sizing

---

### File: `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/tools/simulation.py`
- **Size:** 7.9 KB
- **Status:** DEAD CODE
- **Implementation:** Async function `simulate_ad_system_tool()` with CLI instruction mode
- **Why dead:**
  - Never imported in server.py
  - server.py (line 512-641) has its own implementation using JobManager subprocess
  - Test file comment says "Returns CLI execution instructions to avoid FastMCP STDIO connection timeout"
- **Blocking risk:** Simulation takes 2-5 minutes; would block event loop entirely if used directly
- **Imports from:**
  - `core.state` - design_state
  - `core.utils` - coerce_to_dict

---

### File: `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/tools/process_health.py`
- **Size:** 12 KB
- **Status:** DEAD CODE - Optional analysis tool
- **Implementation:** Async function `analyze_process_health()` for detailed process diagnostics
- **Why dead:**
  - No @mcp.tool() decorator in server.py
  - Never imported anywhere
  - Comment: "Optional analysis tool: Process health diagnostics"
  - Docstring mentions "Requires simulation results to be cached" but tool is never called
- **Imports from:**
  - `core.state` - design_state
  - `utils.extract_qsdsan_sulfur_components` - SULFUR_COMPONENT_INFO
  - `qsdsan.processes._adm1` - non_compet_inhibit, substr_inhibit
  - `utils.qsdsan_sulfur_kinetics` - H2S_INHIBITION
- **References:** grep shows NO calls to this function anywhere in codebase

---

### File: `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/tools/stream_details.py`
- **Size:** 8.1 KB
- **Status:** DEAD CODE - Optional analysis tool
- **Implementation:** Async function `analyze_stream_details()` for composition breakdown
- **Why dead:**
  - No @mcp.tool() decorator in server.py
  - Never imported anywhere
  - Comment: "Optional analysis tool: Detailed stream composition analysis"
  - Docstring says "Requires a simulation to have been run first"
- **Imports from:**
  - `core.state` - design_state
  - `utils.stream_analysis_sulfur` - analyze_liquid_stream, analyze_gas_stream
- **References:** grep shows NO calls to this function anywhere in codebase

---

### File: `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/tools/sulfur_balance.py`
- **Size:** 12 KB
- **Status:** DEAD CODE - Optional analysis tool
- **Implementation:** Async function `verify_sulfur_balance()` for mass balance verification
- **Why dead:**
  - No @mcp.tool() decorator in server.py
  - Never imported anywhere
  - Comment: "Optional analysis tool: Sulfur mass balance verification"
  - Docstring mentions "validates mass balance closure"
- **Imports from:**
  - `core.state` - design_state
  - `utils.stream_analysis_sulfur` - calculate_sulfur_metrics
- **References:** grep shows NO calls to this function anywhere in codebase

---

## 2. Broken Test File

### File: `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/tests/test_regression_catastrophe.py`

**Location:** Line 21
```python
from utils.watertap_simulation_modified import simulate_ad_system
```

**Problem:**
- File `utils/watertap_simulation_modified.py` does NOT exist
- No file in repository with similar name
- This import will cause ImportError when pytest tries to collect test

**Test Context:**
- File purpose: "P0: Regression test to pin and reproduce catastrophic AD failure"
- Decorated with: `@pytest.mark.xfail(reason="P0: Documenting catastrophic failure ...")`
- Goal: Document baseline failure case with TAN=77g-N/L, pH=4.0, biomass washout

**Current simulation modules:**
- `utils.qsdsan_simulation_sulfur` - Main simulation module
- `utils.qsdsan_reactor_madm1` - Reactor implementation
- `utils.qsdsan_madm1` - ADM1 process model

**Fix options:**
1. Delete if regression case no longer relevant
2. Replace import: `from utils.qsdsan_simulation_sulfur import run_simulation_sulfur`
3. Update test to use correct function signature

---

## 3. Optional Dependency (Graceful Fallback)

### File: `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/utils/h2s_speciation.py`

**Status:** Implemented with graceful fallback (NOT dead, but currently unused)

**Line 21:**
```python
from utils.speciation import strippable_fraction, effective_inlet_concentration
```

**What happens:**
```python
try:
    from utils.speciation import strippable_fraction, effective_inlet_concentration
    PHREEQC_AVAILABLE = True
    logger.info("Successfully imported PHREEQC-based speciation from degasser-design-mcp")
except ImportError as e:
    PHREEQC_AVAILABLE = False
    logger.warning(f"Could not import degasser speciation module: {e}")
    logger.warning("Falling back to Henderson-Hasselbalch approximation")
```

**Fallback mechanism:** 
- Uses `_henderson_hasselbalch_h2s()` function (line 125-151)
- Provides pH-dependent H2S/HS⁻ speciation

**Current usage:** 
- Module is NOT imported by anything (grep shows zero references)
- But has fallback, so no impact if external repo unavailable

**Assessment:** 
- Safe to keep (graceful degradation)
- Consider if should be activated for better speciation calculations
- Or remove if not part of current workflow

---

## 4. Duplicate Functionality (Acceptable Pattern)

### `tools/chemical_dosing.py` vs `utils/chemical_dosing.py`

**NOT a problem - this is the correct architecture**

**`utils/chemical_dosing.py` (9.3 KB):**
```python
# Pure functions for calculation logic
def estimate_fecl3_for_sulfide_removal(sulfide_mg_L, target_removal=0.90, safety_factor=1.2)
def estimate_fecl3_for_phosphate_removal(phosphate_mg_L, target_removal=0.80, safety_factor=1.5)
def estimate_naoh_for_ph_adjustment(current_pH, target_pH, alkalinity_meq_L)
def estimate_na2co3_for_alkalinity(current_alkalinity, target_alkalinity)
```

**`tools/chemical_dosing.py` (9.3 KB):**
```python
# MCP tool wrapper (async, state management)
async def estimate_chemical_dosing_tool(use_current_state, custom_params, objectives):
    from utils.chemical_dosing import (
        estimate_fecl3_for_sulfide_removal,
        estimate_fecl3_for_phosphate_removal,
        estimate_naoh_for_ph_adjustment,
        estimate_na2co3_for_alkalinity
    )
```

**Why this is GOOD design:**
- Separation of concerns (domain logic vs MCP interface)
- `utils/` functions can be:
  - Called directly from CLI scripts
  - Unit tested independently
  - Reused by multiple tools
- `tools/` provides:
  - State management (design_state)
  - Async context for MCP
  - Error handling and logging

**Recommendation:** KEEP AS-IS

---

## 5. Tools File Import Status in server.py

### USED Tools (registered with @mcp.tool):
```python
# Line 194-195: elicit_basis_of_design
from tools.basis_of_design import elicit_basis_of_design as _impl

# Line 200-201: get_design_state  
from tools.state_management import get_design_state as _impl

# Line 206-207: reset_design
from tools.state_management import reset_design as _impl

# Line 376-386: check_strong_ion_balance
from tools.validation import check_strong_ion_balance as _impl

# Line 665-666: estimate_chemical_dosing
from tools.chemical_dosing import estimate_chemical_dosing_tool as _impl
```

### UNUSED Tools (NOT registered):
- tools/sizing.py - NOT IMPORTED
- tools/simulation.py - NOT IMPORTED
- tools/process_health.py - NOT IMPORTED
- tools/stream_details.py - NOT IMPORTED
- tools/sulfur_balance.py - NOT IMPORTED

---

## 6. Complete Impact Analysis

### Dependencies that Would Break if Removed:

**None.** The 5 dead tool files have:
- No incoming imports
- No usage in server.py
- No usage in CLI scripts
- No usage in tests
- No usage in other utils/

Grep results for imports of these modules: **EMPTY**

### Reverse Dependencies:

**What depends on the dead tools:**
- Nothing. They are true leaf nodes.

---

## 7. File Dependency Graph

```
server.py (main MCP server)
  ├─ tools/basis_of_design.py ✓ USED
  ├─ tools/state_management.py ✓ USED
  ├─ tools/validation.py ✓ USED
  ├─ tools/chemical_dosing.py ✓ USED
  │  └─ utils/chemical_dosing.py ✓ USED
  ├─ tools/sizing.py ✗ DEAD
  ├─ tools/simulation.py ✗ DEAD
  ├─ tools/process_health.py ✗ DEAD
  ├─ tools/stream_details.py ✗ DEAD
  ├─ tools/sulfur_balance.py ✗ DEAD
  └─ utils/job_manager.py ✓ USED
     └─ utils/job_state_reconciler.py ✓ USED

CLI Scripts (for subprocess execution)
  ├─ utils/validate_cli.py ✓ USED
  ├─ utils/heuristic_sizing_cli.py ✓ USED
  └─ utils/simulate_cli.py ✓ USED
     ├─ utils/qsdsan_loader.py ✓ USED
     ├─ utils/qsdsan_simulation_sulfur.py ✓ USED
     ├─ utils/output_formatters.py ✓ USED
     └─ utils/stream_analysis_sulfur.py ✓ USED

Tests
  ├─ tests/test_qsdsan_simulation_basic.py ✓ WORKING
  │  ├─ utils/qsdsan_simulation_sulfur.py ✓
  │  └─ utils/stream_analysis_sulfur.py ✓
  └─ tests/test_regression_catastrophe.py ✗ BROKEN
     └─ utils/watertap_simulation_modified.py ✗ MISSING
```

---

## Removal Checklist

Before removing, verify:
- [ ] No imports in server.py
- [ ] No imports in utils/*.py
- [ ] No imports in CLI scripts
- [ ] No imports in other tools/*.py
- [ ] No imports in tests/
- [ ] Grep shows zero references
- [ ] No MCP @tool decorator registration

**All 6 files pass all checks.**

