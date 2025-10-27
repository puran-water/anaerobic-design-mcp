# Test Files and Debugging Scripts Analysis Report

## Executive Summary

This project contains **14 test files** and **3 standalone utility scripts** that require categorization. After thorough analysis:

- **3 Useful Regression Tests** (KEEP - active development)
- **8 Obsolete Temporary Debugging Scripts** (DELETE)
- **3 Standalone Extraction Scripts** (DELETE - WaterTAP-specific)
- **2 PAUSE Point Documentation Files** (DELETE - workflow artifacts)

---

## Category 1: Useful Regression Tests (KEEP)

### 1. `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/tests/test_regression_catastrophe.py`

**Status:** KEEP (Active regression test)  
**Last Modified:** Oct 16 (via git)  
**Purpose:** P0 baseline test for catastrophic AD failure modes  
**Referenced In:** CLAUDE.md includes detailed documentation about this test  
**Value:** 
- Documents baseline failure conditions (TAN toxicity, pH collapse, VFA accumulation)
- Marked with `xfail` to prevent CI blocking
- Tracks improvement progress on biomass washout and methanogenic inhibition bugs
- Non-deterministic by design (solver convergence variations)

**Keep Because:**
- Explicitly mentioned in CLAUDE.md as important regression test
- Validates fix effectiveness (directional improvement metrics)
- Used to track system stabilization over development phases

---

### 2. `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/tests/test_qsdsan_simulation_basic.py`

**Status:** KEEP (Active integration test)  
**Last Modified:** Oct 16 (modified by linter)  
**Purpose:** Smoke test for complete QSDsan refactored simulation workflow  
**Value:**
- Tests 30-component initialization
- Validates COD removal, biogas production, pH, H2S speciation
- Runs through complete state initialization and simulation pipeline
- Provides validation metrics (checks_passed / checks_total)

**Keep Because:**
- Part of active "WaterTAP → QSDsan migration" workflow
- Tests new sulfur component integration
- Validates core simulation pipeline
- Created during Phase 3 of major refactoring

---

### 3. `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/tests/__init__.py`

**Status:** KEEP (Package marker)  
**Purpose:** Makes `tests/` a Python package  
**Value:** Required for pytest test discovery

---

## Category 2: Obsolete Debugging Scripts (DELETE)

### 4. `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/test_direct_simulation.py`

**Status:** DELETE (Obsolete WaterTAP debugging)  
**Last Modified:** Sep 7 (73+ days old)  
**Purpose:** Direct WaterTAP simulation test to extract digester metrics  
**Issues:**
- Tests deprecated WaterTAP integration (now replaced by QSDsan)
- Imports `watertap_simulation_modified` - old simulation layer
- Specifically tests WaterTAP-specific metrics extraction
- No active references in current codebase
- Outputs: `simulation_result_direct.json` (temporary debug file)

**Delete Because:**
- Part of pre-QSDsan migration codebase
- WaterTAP layer has been completely replaced
- No calls from any active tool or test
- 73+ days without modification (pre-refactoring)

---

### 5. `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/test_p1_verification.py`

**Status:** DELETE (Obsolete WaterTAP debugging)  
**Last Modified:** Sep 9 (71+ days old)  
**Purpose:** Test P1 nitrogen fix for WaterTAP simulation  
**Issues:**
- Tests deprecated `watertap_simulation_modified` module
- Specific to nitrogen routing bug fix in WaterTAP layer
- No active references in current tools
- Tests fixed an issue that's now handled differently in QSDsan layer

**Delete Because:**
- WaterTAP layer is deprecated
- Nitrogen handling now integrated into QSDsan simulation
- No active tool references this test
- Only commented reference in PAUSE_BEFORE_TESTING.py

---

### 6. `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/test_simulation_fixes.py`

**Status:** DELETE (Obsolete WaterTAP convergence debugging)  
**Last Modified:** Sep 8 (72+ days old)  
**Purpose:** Test script to validate WaterTAP simulation convergence fixes  
**Issues:**
- Tests WaterTAP-specific convergence issues
- Checks "scaling warnings" (WaterTAP solver-specific)
- Validates MBR nitrogen passage (WaterTAP-specific)
- Data from this test is referenced in test_regression_catastrophe.py but the fixes are now integrated

**Delete Because:**
- Tests deprecated WaterTAP solver issues
- QSDsan layer handles this differently
- Referenced only in comments within test_regression_catastrophe.py
- 72+ days without modification

---

### 7. `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/test_adm1_extension.py`

**Status:** DELETE (Temporary ADM1 development script)  
**Last Modified:** Oct 16 (recent but development artifact)  
**Purpose:** Test ADM1 extension with sulfate reduction processes  
**Issues:**
- Tests internal ADM1 model structure (not exposed to users)
- Tests specific to sulfur kinetics implementation details
- Functionality now integrated into core simulation
- Not called from any active tool or test

**Delete Because:**
- Development/debugging only - not part of workflow
- Tests internal model structure that's already validated
- Functionality integrated into main simulation pipeline
- No active references
- Temporary testing artifact for development

---

### 8. `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/test_h2s_inhibition.py`

**Status:** DELETE (Temporary H2S inhibition development script)  
**Last Modified:** Oct 16 (recent but development artifact)  
**Purpose:** Test H2S inhibition on methanogens using custom rate functions  
**Issues:**
- Tests internal kinetics model structure
- Specific to custom rate function implementation
- Functionality now integrated into core simulation
- Not referenced in any active code

**Delete Because:**
- Development/debugging artifact for kinetics implementation
- Functionality fully integrated into main simulation
- No active tool calls this test
- Tests internal model details, not user-facing features
- Temporary testing script for development

---

### 9. `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/test_pause_before_mcp.py`

**Status:** DELETE (Workflow artifact/documentation)  
**Last Modified:** Oct 16 (documentation only)  
**Purpose:** PAUSE POINT marker for MCP testing workflow  
**Issues:**
- Purely a workflow artifact - waits for user input
- Contains only print statements and `input()` call
- Documents completed refactoring tasks (now in code)
- No executable logic

**Delete Because:**
- Pure documentation/workflow artifact
- Changes documented - no longer needed for reference
- Not part of test suite or actual tools
- Input() call won't work in automated environments
- Redundant with CLAUDE.md instructions

---

### 10. `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/inspect_adm1_processes.py`

**Status:** DELETE (Temporary ADM1 inspection script)  
**Last Modified:** Oct 16 (temporary debugging)  
**Purpose:** Inspect ADM1 process structure to understand H2S inhibition  
**Issues:**
- Pure exploration/debugging script - prints process details
- No computational value - just introspection
- Tests exploration of QSDsan internals (not part of workflow)
- Output only used during development

**Delete Because:**
- Development artifact - no application in workflow
- Pure introspection with `print()` statements
- Functionality now understood and integrated
- Not called from any active code
- No test assertions - just exploration

---

## Category 3: Standalone Extraction Scripts (DELETE)

### 11. `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/check_flow_balance.py`

**Status:** DELETE (Obsolete WaterTAP debugging)  
**Last Modified:** Sep-Oct (mixed - recent linting)  
**Purpose:** Check flow balance from WaterTAP simulation  
**Issues:**
- Imports `watertap_simulation_modified` (deprecated)
- Runs standalone - never integrated into MCP tools
- Detailed flow balance analysis no longer needed in workflow
- Requires external `adm1_state.json` file

**Delete Because:**
- Depends on deprecated WaterTAP layer
- Functionality (if needed) should be in MCP tools
- Not called from any active code
- Standalone debugging script, not part of workflow
- Can be reimplemented in QSDsan if needed

---

### 12. `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/extract_all_metrics.py`

**Status:** DELETE (Obsolete WaterTAP debugging)  
**Last Modified:** Sep-Oct (mixed - recent linting)  
**Purpose:** Extract comprehensive metrics from WaterTAP simulation  
**Issues:**
- Imports `watertap_simulation_modified` (deprecated)
- Runs standalone - never integrated into MCP tools
- Creates detailed report to `full_metrics_report.json`
- Requires external dependencies (`adm1_state.json`, `heuristic_sizing_config.json`)

**Delete Because:**
- Depends on deprecated WaterTAP layer
- Not integrated into MCP workflow
- Can be reimplemented as MCP tool if metrics extraction is needed
- Standalone debugging script

---

### 13. `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/extract_full_metrics.py`

**Status:** DELETE (Obsolete WaterTAP debugging)  
**Last Modified:** Sep-Oct (mixed - recent linting)  
**Purpose:** Extract full simulation metrics and generate comprehensive report  
**Issues:**
- Imports `watertap_simulation_modified` (deprecated)
- Runs standalone - never integrated into MCP tools
- Attempts to load `heuristic_sizing_config.json` and digester metrics
- Outputs to `simulation_logs/` directory

**Delete Because:**
- Depends on deprecated WaterTAP layer
- Not integrated into MCP workflow
- Standalone debugging script
- Can be reimplemented if needed

---

## Category 4: Temporary Output Files (DELETE)

### 14. `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/PAUSE_BEFORE_TESTING.py`

**Status:** DELETE (Workflow artifact)  
**Last Modified:** Oct 16 (documentation only)  
**Purpose:** PAUSE POINT marker for major refactoring  
**Issues:**
- Pure documentation - contains only print statements and `input()`
- Lists completed changes (all now in code)
- No executable logic
- References CLAUDE.md methodology

**Delete Because:**
- Pure documentation artifact
- Changes documented in code comments
- Not part of test suite
- Workflow marker only - no functional value

---

### Temporary Output Files (Auto-delete)

These are generated during test runs and should be cleaned up:

- `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/test_p1_results.txt` (324 KB - Sep 9)
- `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/test_results.json` (147 bytes - Sep 8)
- `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/simulation_result_direct.json` (147 bytes - Sep 9)

---

## QSDsan Repository Tests

The `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/QSDsan_repo/tests/` directory contains upstream QSDsan library tests:

- `test_bst_units.py`
- `test_component.py`
- `test_dyn_sys.py`
- `test_exposan.py`
- `test_junctions.py`
- `test_process.py`
- `test_sanunit.py`
- `test_waste_stream.py`

**Status:** KEEP (Library tests - not your code)  
**Reason:** These are part of the QSDsan library vendored in the project and should not be modified

---

## Summary Table

| File | Category | Size | Age | Action |
|------|----------|------|-----|--------|
| test_regression_catastrophe.py | Regression Test | ~8 KB | Oct 16 | **KEEP** |
| test_qsdsan_simulation_basic.py | Integration Test | ~6 KB | Oct 16 | **KEEP** |
| tests/__init__.py | Package Marker | 0 bytes | - | **KEEP** |
| test_direct_simulation.py | WaterTAP Debug | ~5 KB | Sep 7 | **DELETE** |
| test_p1_verification.py | WaterTAP Debug | ~4 KB | Sep 9 | **DELETE** |
| test_simulation_fixes.py | WaterTAP Debug | ~8 KB | Sep 8 | **DELETE** |
| test_adm1_extension.py | Dev Artifact | ~2 KB | Oct 16 | **DELETE** |
| test_h2s_inhibition.py | Dev Artifact | ~3 KB | Oct 16 | **DELETE** |
| test_pause_before_mcp.py | Workflow Doc | ~1 KB | Oct 16 | **DELETE** |
| inspect_adm1_processes.py | Dev Artifact | ~1 KB | Oct 16 | **DELETE** |
| PAUSE_BEFORE_TESTING.py | Workflow Doc | ~2 KB | Oct 16 | **DELETE** |
| check_flow_balance.py | WaterTAP Debug | ~9 KB | Sep-Oct | **DELETE** |
| extract_all_metrics.py | WaterTAP Debug | ~10 KB | Sep-Oct | **DELETE** |
| extract_full_metrics.py | WaterTAP Debug | ~9 KB | Sep-Oct | **DELETE** |
| Output Files (3x) | Temp Files | ~325 KB | Sep 7-9 | **DELETE** |

---

## Deletion Command

```bash
# Remove obsolete test files
rm /mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/test_direct_simulation.py
rm /mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/test_p1_verification.py
rm /mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/test_simulation_fixes.py
rm /mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/test_adm1_extension.py
rm /mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/test_h2s_inhibition.py
rm /mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/test_pause_before_mcp.py
rm /mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/inspect_adm1_processes.py
rm /mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/PAUSE_BEFORE_TESTING.py

# Remove extraction scripts (WaterTAP layer)
rm /mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/check_flow_balance.py
rm /mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/extract_all_metrics.py
rm /mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/extract_full_metrics.py

# Remove temporary output files
rm /mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/test_p1_results.txt
rm /mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/test_results.json
rm /mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/simulation_result_direct.json
```

---

## Recommendations

1. **Establish a testing convention:**
   - Move any future development scripts to `/tmp/` or project-specific debug branches
   - Only keep permanent tests in `/tests/` directory
   - Use pytest for all permanent tests

2. **Consider creating an MCP tool for metrics extraction:**
   - The extract_*.py scripts suggest a need for detailed result analysis
   - This could be reimplemented as a proper MCP tool with structured output

3. **Document test expectations:**
   - The `test_regression_catastrophe.py` xfail expectations are already well-documented
   - Continue this pattern for other critical tests

4. **Clean up after releases:**
   - Remove temporary debugging scripts before merging to main
   - These should live in branches, not production code

---

## Analysis Methodology

This categorization was based on:

1. **Code content analysis** - Examining imports, function calls, and logic
2. **Temporal analysis** - Tracking modification dates and project phases
3. **Reference analysis** - Searching for active calls to these scripts/functions
4. **Dependency analysis** - Checking for deprecated module imports
5. **Documentation alignment** - Cross-referencing with CLAUDE.md and git history

All findings are conservative - scripts are only marked DELETE if they have clear evidence of obsolescence or temporary status.

