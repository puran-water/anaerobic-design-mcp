# Codebase Analysis Reports

## Overview

Complete analysis of dead code, test files with broken imports, deprecated utilities, and duplicate functionality in the anaerobic-design-mcp repository.

**Analysis Date:** November 4, 2025

**Total Dead Code:** ~50 KB (safe to remove)

---

## Reports

### 1. CODEBASE_ANALYSIS.md
**Comprehensive Analysis (14 KB, 400+ lines)**

Primary report with full technical depth. Includes:
- Executive summary with key statistics
- Detailed analysis of 5 dead tool files
  - Why each file exists
  - Why it's dead (never imported, never registered)
  - Impact assessment
  - Code blocking risks
- Analysis of broken test file
- Optional dependencies with graceful fallbacks
- Duplicate functionality evaluation
- Architecture review of Background Job Pattern
- Summary table of files to remove
- Complete recommended actions

**Read this if:** You want comprehensive understanding of the codebase issues and architecture

**Key sections:**
- Lines 1-20: Executive Summary
- Lines 50-200: Dead code analysis (5 tools)
- Lines 210-250: Broken test file
- Lines 260-310: Optional dependencies
- Lines 320-350: Architecture review
- Lines 360-420: Recommendations

---

### 2. CLEANUP_RECOMMENDATIONS.md
**Quick Reference (3.5 KB)**

Executive summary with actionable items. Includes:
- Dead code summary with sizes
- High priority items (what to delete)
- Quick cleanup commands
- Impact assessment
- Architecture notes
- Files to keep
- Optional future work

**Read this if:** You just want to know what to delete and why

**Key sections:**
- Quick deletion commands
- Impact assessment
- Architecture notes

---

### 3. DETAILED_FINDINGS.md
**Technical Reference (9.9 KB, 350+ lines)**

File-by-file technical breakdown. Includes:
- Complete file analysis (5 dead tools)
  - File path, size, status
  - Implementation details
  - Why it's dead
  - What it imports
  - Blocking risks
- Broken test file with line numbers
- Optional dependency analysis
- Duplicate functionality assessment
- Import status in server.py
- Complete impact analysis
- Dependency graph
- Removal checklist

**Read this if:** You need file-by-file technical details, import lists, or dependency analysis

**Key sections:**
- Lines 1-100: Dead tool files (1-5)
- Lines 110-140: Broken test file
- Lines 150-180: Optional dependencies
- Lines 200-220: Duplicate functionality
- Lines 240-280: Import status
- Lines 300-350: Dependency graph

---

## Quick Decision Guide

### "Should I delete this file?"

| File | Status | Action | Read |
|------|--------|--------|------|
| tools/sizing.py | DEAD | DELETE | CODEBASE_ANALYSIS.md lines 50-75 |
| tools/simulation.py | DEAD | DELETE | CODEBASE_ANALYSIS.md lines 80-110 |
| tools/process_health.py | DEAD | DELETE | CODEBASE_ANALYSIS.md lines 115-150 |
| tools/stream_details.py | DEAD | DELETE | CODEBASE_ANALYSIS.md lines 155-180 |
| tools/sulfur_balance.py | DEAD | DELETE | CODEBASE_ANALYSIS.md lines 185-210 |
| tests/test_regression_catastrophe.py | BROKEN | DELETE | CODEBASE_ANALYSIS.md lines 220-250 |
| utils/h2s_speciation.py | OPTIONAL | KEEP/EVALUATE | CODEBASE_ANALYSIS.md lines 260-290 |
| tools/chemical_dosing.py | USED | KEEP | CODEBASE_ANALYSIS.md lines 320-340 |

---

## Key Findings Summary

### Dead Code (46.8 KB)
Five tool files that implement MCP tools but are never registered or used:
- Represent old blocking implementation that was replaced by Background Job Pattern
- Would cause name conflicts if imported
- All have zero dependencies (safe to remove)

### Broken Test (2-3 KB)
One test file with import error:
- Line 21: Imports non-existent `utils.watertap_simulation_modified`
- Marked with `@pytest.mark.xfail` (expected failure)
- Safe to delete or fix

### Optional Unused Module (7 KB)
`utils/h2s_speciation.py` has graceful fallback, so it's safe to keep as-is

### Correct Architecture
`tools/chemical_dosing.py` + `utils/chemical_dosing.py` is proper pattern (not a problem):
- Domain logic in utils/ (reusable, testable)
- MCP wrapper in tools/ (async, state management)

---

## Deletion Commands

```bash
# Delete all dead tool files (46.8 KB)
rm tools/sizing.py \
   tools/simulation.py \
   tools/process_health.py \
   tools/stream_details.py \
   tools/sulfur_balance.py

# Delete broken test (2-3 KB)
rm tests/test_regression_catastrophe.py
```

**Impact:** ZERO - No other modules import these files

---

## Architecture Quality Notes

### Positive
- Clean separation of concerns (tools/ = MCP interface, utils/ = domain logic)
- Background Job Pattern correctly prevents event loop blocking
- CLI wrappers properly isolate subprocess execution
- Core logic reusable across multiple callers
- Error handling with automatic cleanup

### Areas for Improvement
- Remove or activate optional tools (don't leave them hanging)
- Fix broken test imports
- Consider consolidating optional tools if planned for future

---

## File Organization

**MCP Server:**
- server.py - Main MCP server with 14 registered tools

**MCP Tools (tools/):**
- basis_of_design.py ✓ USED
- state_management.py ✓ USED
- validation.py ✓ USED
- chemical_dosing.py ✓ USED
- sizing.py ✗ DEAD
- simulation.py ✗ DEAD
- process_health.py ✗ DEAD
- stream_details.py ✗ DEAD
- sulfur_balance.py ✗ DEAD

**Background Job Infrastructure (utils/):**
- job_manager.py - Subprocess executor ✓ CORE
- job_state_reconciler.py - State persistence ✓ CORE
- validate_cli.py - Validation subprocess ✓ CORE
- heuristic_sizing_cli.py - Sizing subprocess ✓ CORE
- simulate_cli.py - Simulation subprocess ✓ CORE
- (42 other utils/ files) - Calculation logic ✓ CORE

**Tests:**
- test_qsdsan_simulation_basic.py ✓ WORKING
- test_regression_catastrophe.py ✗ BROKEN

---

## Next Steps

### Immediate (High Priority)
1. Review CLEANUP_RECOMMENDATIONS.md
2. Run deletion commands
3. Commit: "chore: Remove dead code and broken test"

### Future (Optional)
1. Evaluate utils/h2s_speciation.py
2. Decide on optional analysis tools (activate or remove)
3. Document decision

---

## Report Metadata

| Report | Size | Lines | Focus |
|--------|------|-------|-------|
| CODEBASE_ANALYSIS.md | 14 KB | 420+ | Comprehensive technical analysis |
| CLEANUP_RECOMMENDATIONS.md | 3.5 KB | 80+ | Quick reference for action items |
| DETAILED_FINDINGS.md | 9.9 KB | 350+ | File-by-file technical reference |
| ANALYSIS_INDEX.md | 4 KB | 250+ | This file - navigation guide |

Total: 30.4 KB of analysis documentation

---

## Questions?

Each report is self-contained and can be read independently. Use this index to navigate:

**"What should I delete?"** → CLEANUP_RECOMMENDATIONS.md

**"Why is this dead?"** → CODEBASE_ANALYSIS.md

**"What are the technical details?"** → DETAILED_FINDINGS.md

**"What's the dependency graph?"** → DETAILED_FINDINGS.md (line 300+)
