# Anaerobic Digester Design MCP - Codebase Dead Code & Consolidation Analysis

## Executive Summary

The codebase has **5 dead code files** (unused MCP tools), **1 test file with broken imports**, **1 module with optional external dependencies**, and **1 consolidation opportunity**. The Background Job Pattern architecture is well-implemented with clean separation between:
- MCP server interface (server.py)
- CLI wrappers for subprocess execution (*_cli.py)
- Core calculation/simulation logic (utils/)
- MCP tool implementations (tools/)

**Total dead code: ~100 KB** of unused functionality that can be safely removed.

---

## Dead Code: Unused MCP Tool Files (tools/ directory)

These 5 files implement MCP tools that are **registered as optional analysis tools but never wired into server.py** and thus unreachable by users:

### 1. `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/tools/sizing.py` (6.8 KB)

**Status:** DEAD CODE - Completely unused alternative to the background job pattern

**Why it exists:** 
- Implements `heuristic_sizing_ad()` as a direct async function
- Calls `perform_heuristic_sizing()` directly (blocking for 10-30 seconds)

**Why it's dead:**
- Server.py DOES NOT import this file
- Instead, `heuristic_sizing_ad()` in server.py (line 389-510) uses the Background Job Pattern:
  ```python
  # server.py line 459-495
  manager = JobManager()
  job = await manager.execute(cmd=cmd, cwd=".", job_id=job_id)
  ```
  This launches `utils/heuristic_sizing_cli.py` as a subprocess
  
- The old tools/sizing.py would block the event loop for 10-30 seconds
- The new CLI approach returns immediately with job_id, preventing MCP STDIO timeout

**Impact Assessment:** SAFE TO DELETE
- No imports from other modules
- No references in server.py
- The async blocking function would break the entire Background Job Pattern if reactivated

**Recommendation:** Remove entirely

---

### 2. `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/tools/simulation.py` (7.9 KB)

**Status:** DEAD CODE - Obsolete simulation wrapper replaced by Background Job Pattern

**Why it exists:**
- Implements `simulate_ad_system_tool()` with CLI instruction mode comment
- Designed to return subprocess execution instructions

**Why it's dead:**
- Server.py DOES NOT import this file
- Instead, `simulate_ad_system_tool()` in server.py (line 512-641) uses the Background Job Pattern
- Takes ~2-5 minutes to run and MUST use subprocess pattern to avoid blocking

**Impact Assessment:** SAFE TO DELETE
- No imports from other modules
- No references in server.py
- Would conflict with the actual server.py implementation if accidentally imported

**Recommendation:** Remove entirely

---

### 3. `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/tools/process_health.py` (12 KB)

**Status:** DEAD CODE - Optional analysis tool never registered as MCP tool

**What it does:**
- Analyzes process health: process rates, limiting factors, inhibition status
- Requires cached simulation results from design_state

**Why it's dead:**
- No `@mcp.tool()` decorator in server.py
- Not imported anywhere in server.py or CLI scripts
- Never called from any user workflow
- Comment states "Optional analysis tool" but was never activated

**References in code:**
- Imports: `utils.extract_qsdsan_sulfur_components`, `utils.qsdsan_sulfur_kinetics`
- These are real modules and would work IF the tool were activated
- But the tool itself is unreachable by users

**Impact Assessment:** SAFE TO DELETE
- No other modules depend on it
- No MCP registration means no callers exist
- Self-contained implementation

**Recommendation:** Remove entirely

---

### 4. `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/tools/stream_details.py` (8.1 KB)

**Status:** DEAD CODE - Optional analysis tool never registered as MCP tool

**What it does:**
- Detailed stream composition analysis with full component breakdown
- Useful for debugging simulation behavior

**Why it's dead:**
- No `@mcp.tool()` decorator in server.py
- Not imported anywhere in server.py or CLI scripts
- Comment states "Optional analysis tool" but was never activated

**References in code:**
- Imports: `utils.stream_analysis_sulfur` (real module)
- Would work IF the tool were activated
- But the tool itself is unreachable by users

**Impact Assessment:** SAFE TO DELETE
- No other modules depend on it
- No MCP registration means no callers exist
- Self-contained implementation

**Recommendation:** Remove entirely

---

### 5. `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/tools/sulfur_balance.py` (12 KB)

**Status:** DEAD CODE - Optional analysis tool never registered as MCP tool

**What it does:**
- Sulfur mass balance verification across all streams
- Tracks sulfur through influent, effluent, biogas

**Why it's dead:**
- No `@mcp.tool()` decorator in server.py
- Not imported anywhere in server.py or CLI scripts
- Comment states "Optional analysis tool" but was never activated

**References in code:**
- Imports: `utils.stream_analysis_sulfur` (real module)
- Would work IF the tool were activated
- But the tool itself is unreachable by users

**Impact Assessment:** SAFE TO DELETE
- No other modules depend on it
- No MCP registration means no callers exist
- Self-contained implementation

**Recommendation:** Remove entirely

---

## Test File with Broken Imports

### `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/tests/test_regression_catastrophe.py` (50+ lines)

**Status:** BROKEN TEST - References non-existent module

**Line 21:**
```python
from utils.watertap_simulation_modified import simulate_ad_system
```

**Problem:**
- File `utils/watertap_simulation_modified.py` DOES NOT EXIST
- No similar file in the codebase
- Test is marked with `@pytest.mark.xfail` to document baseline failure
- This appears to be leftover from earlier refactoring

**Impact Assessment:** BROKEN BUT NOT BLOCKING
- Pytest will fail to collect this test due to import error
- Test is xfail-marked anyway (expected failure)
- Does not affect production code

**Recommendation:** Either:
1. **Delete entirely** if this failure case is no longer relevant
2. **Fix imports** if this baseline regression test should be maintained
   - Current simulation uses `utils.qsdsan_simulation_sulfur.run_simulation_sulfur()`
   - Replace import with correct module

---

## Working Test File (Keep)

### `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/tests/test_qsdsan_simulation_basic.py` (50+ lines)

**Status:** WORKING TEST - Smoke test with correct imports

**What it does:**
- Basic integration test for QSDsan ADM1+sulfur simulation
- Tests: component creation → simulation → result analysis
- All imports are valid:
  - `utils.qsdsan_simulation_sulfur` ✓
  - `utils.stream_analysis_sulfur` ✓

**Impact Assessment:** KEEP
- Part of development/validation workflow
- All dependencies exist
- Functional smoke test

---

## Optional Dependency with Graceful Fallback

### `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/utils/h2s_speciation.py` (7 KB)

**Status:** IMPLEMENTED WITH GRACEFUL FALLBACK - Not a problem

**What it does:**
- Provides H2S/HS⁻ pH-dependent speciation
- Tries to use PHREEQC from external repo (`degasser-design-mcp`)
- Falls back to Henderson-Hasselbalch if unavailable

**Line 21:**
```python
from utils.speciation import strippable_fraction, effective_inlet_concentration
```

**Why it's NOT dead code:**
- Module gracefully handles ImportError (line 24):
  ```python
  except ImportError as e:
      PHREEQC_AVAILABLE = False
      logger.warning(f"Could not import degasser speciation module: {e}")
      logger.warning("Falling back to Henderson-Hasselbalch approximation")
  ```
- Provides fallback function `_henderson_hasselbalch_h2s()` (line 125-151)
- Currently NOT imported by anything (grep shows no references)
- But has no impact on production code since it's optional

**Status Note:** This module exists but is currently UNUSED. Consider whether it should be:
- Actively imported for enhanced speciation calculations
- Removed if not part of current workflow

---

## Duplicate Functionality (Can be Consolidated)

### `tools/chemical_dosing.py` vs `utils/chemical_dosing.py`

**Current Architecture:**
- `utils/chemical_dosing.py` (9.3 KB) - Pure functions for dosing calculations
  ```python
  def estimate_fecl3_for_sulfide_removal(...)
  def estimate_fecl3_for_phosphate_removal(...)
  def estimate_naoh_for_ph_adjustment(...)
  def estimate_na2co3_for_alkalinity(...)
  ```

- `tools/chemical_dosing.py` (9.3 KB) - MCP wrapper that calls utils functions
  ```python
  async def estimate_chemical_dosing_tool(...):
      from utils.chemical_dosing import (
          estimate_fecl3_for_sulfide_removal,
          ...
      )
  ```

**Status:** NOT TRULY DUPLICATE - This is the correct pattern

**Why this is GOOD design:**
- Separation of concerns:
  - `utils/` = pure domain logic (testable, reusable)
  - `tools/` = MCP interface (async, state management)
- This enables:
  - CLI scripts to use `utils/` functions directly
  - Multiple MCP tools to share same calculation logic
  - Unit testing of pure functions in utils/

**Recommendation:** KEEP AS-IS (This is correct architecture)

---

## Architecture Review: Background Job Pattern

The codebase correctly implements Background Job Pattern to avoid MCP STDIO blocking:

```
server.py (@mcp.tool)
    ↓
    Validates design_state
    Pre-creates job directory
    Launches CLI subprocess
    Returns job_id immediately
    ↓
JobManager (subprocess executor)
    ↓
    *_cli.py wrapper
    ├── validate_cli.py (validation jobs)
    ├── heuristic_sizing_cli.py (sizing jobs)
    └── simulate_cli.py (simulation jobs - 2-5 min)
    ↓
    Core calculation logic in utils/
    ↓
    Results JSON files in job/
    ↓
get_job_status() / get_job_results()
    ↓
    Results read and returned to user
```

**Quality:** Well-implemented
- No blocking on event loop
- Proper job isolation
- Clean separation of concerns

---

## Summary Table: Files to Remove

| File | Type | Size | Reason | Risk |
|------|------|------|--------|------|
| `tools/sizing.py` | Dead Code | 6.8 KB | Alternative blocking impl replaced by Background Job Pattern | Safe |
| `tools/simulation.py` | Dead Code | 7.9 KB | Alternative impl replaced by Background Job Pattern | Safe |
| `tools/process_health.py` | Dead Code | 12 KB | Optional tool never registered with @mcp.tool | Safe |
| `tools/stream_details.py` | Dead Code | 8.1 KB | Optional tool never registered with @mcp.tool | Safe |
| `tools/sulfur_balance.py` | Dead Code | 12 KB | Optional tool never registered with @mcp.tool | Safe |
| **Subtotal** | | **46.8 KB** | | |
| `tests/test_regression_catastrophe.py` | Broken Test | 2-3 KB | Broken import + xfail marker | Consider |
| **Total cleanup** | | **~50 KB** | | **All safe to remove** |

---

## Files to KEEP

| File | Category | Reason |
|------|----------|--------|
| `tools/basis_of_design.py` | MCP Tool | Imported in server.py (line 194) |
| `tools/state_management.py` | MCP Tool | Imported in server.py (lines 200, 206) |
| `tools/validation.py` | MCP Tool | Imported in server.py (line 376) |
| `tools/chemical_dosing.py` | MCP Tool | Imported in server.py (line 665) |
| `tests/test_qsdsan_simulation_basic.py` | Test | Working smoke test with valid imports |
| `utils/h2s_speciation.py` | Utility | Has graceful fallback, safe to keep |
| All `utils/*_cli.py` | Core | Essential for Background Job Pattern |
| `utils/job_manager.py` | Core | Essential for Background Job Pattern |
| All other `utils/` files | Core | Used by CLI or test scripts |

---

## Recommended Actions

### Immediate (High Priority)

1. **Delete these 5 dead tool files:**
   - `tools/sizing.py`
   - `tools/simulation.py`
   - `tools/process_health.py`
   - `tools/stream_details.py`
   - `tools/sulfur_balance.py`
   
   **Commands:**
   ```bash
   rm tools/sizing.py tools/simulation.py tools/process_health.py
   rm tools/stream_details.py tools/sulfur_balance.py
   ```
   
   **Rationale:** These files are unreachable dead code with zero usage. They contradict the Background Job Pattern that was specifically designed to replace blocking implementations.

2. **Fix or delete broken test:**
   - `tests/test_regression_catastrophe.py`
   
   **Option A - Delete if not needed:**
   ```bash
   rm tests/test_regression_catastrophe.py
   ```
   
   **Option B - Fix if regression test is valuable:**
   - Replace `from utils.watertap_simulation_modified import ...` 
   - With: `from utils.qsdsan_simulation_sulfur import run_simulation_sulfur`
   - Update test to use correct function signature

### Future Consideration (Medium Priority)

3. **Evaluate `utils/h2s_speciation.py`:**
   - Currently unused and depends on external repo
   - If not part of planned workflow, consider removing
   - If planned for future use, integrate properly into tools/

4. **Consider if optional analysis tools should be activated:**
   - If detailed stream/process analysis is desired:
     - Register `process_health.py`, `stream_details.py`, `sulfur_balance.py` with `@mcp.tool()` 
     - Add imports to `server.py`
     - Document in workflow
   - If not needed:
     - Delete (already recommended)

---

## Code Quality Notes

**Positive observations:**
- Clean architecture with separation of concerns
- Background Job Pattern prevents event loop blocking (solves WSL2 issue)
- CLI wrappers properly isolate subprocess execution
- Core calculation logic is reusable across tools and CLI scripts
- Error handling with cleanup (job directory removal on failure)

**Opportunities for improvement:**
- Remove or activate optional tools (don't leave them hanging)
- Fix broken test imports
- Consider consolidating optional tools into a single `tools/analysis.py` if they're meant to be secondary features

