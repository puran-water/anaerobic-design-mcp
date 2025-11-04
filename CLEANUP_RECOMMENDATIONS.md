# Code Cleanup Recommendations - Quick Reference

## Dead Code Summary

**Total removable code: ~50 KB**

### High Priority - Dead MCP Tools (Never Registered)
These files implement MCP tools that are unreachable to users. They exist only in `tools/` but are never imported by `server.py`:

1. **`tools/sizing.py`** (6.8 KB)
   - Outdated blocking implementation, replaced by Background Job Pattern
   - Would break if accidentally imported (conflicts with server.py)
   - **Action: DELETE**

2. **`tools/simulation.py`** (7.9 KB)
   - Outdated CLI instruction wrapper, replaced by Background Job Pattern
   - Would block event loop for 2-5 minutes if reactivated
   - **Action: DELETE**

3. **`tools/process_health.py`** (12 KB)
   - "Optional analysis tool" never activated
   - No @mcp.tool() decorator, no imports in server.py
   - **Action: DELETE**

4. **`tools/stream_details.py`** (8.1 KB)
   - "Optional analysis tool" never activated
   - No @mcp.tool() decorator, no imports in server.py
   - **Action: DELETE**

5. **`tools/sulfur_balance.py`** (12 KB)
   - "Optional analysis tool" never activated
   - No @mcp.tool() decorator, no imports in server.py
   - **Action: DELETE**

### High Priority - Broken Test
6. **`tests/test_regression_catastrophe.py`** (2-3 KB)
   - Line 21: Imports from non-existent `utils.watertap_simulation_modified`
   - Test is marked @pytest.mark.xfail (expected failure)
   - **Action: DELETE** (or fix if regression test is needed)

---

## Quick Commands to Clean Up

```bash
# Remove all dead tool files
rm tools/sizing.py tools/simulation.py tools/process_health.py tools/stream_details.py tools/sulfur_balance.py

# Remove broken test (or keep if fixing)
rm tests/test_regression_catastrophe.py
```

## Impact Assessment

**Safe to remove:** YES
- No other modules import these files
- No references in server.py, CLI scripts, or other utils
- Removing them has zero impact on production code
- The Background Job Pattern they tried to implement is already better-implemented elsewhere

---

## Architecture Note

These tools represent an incomplete refactoring:
- Old approach: Implement tools as async functions that do heavy computation
- New approach: Implement tools as async wrappers that launch subprocess via JobManager
- Result: Old files were never updated, but their implementations remain in codebase

The Background Job Pattern is the **correct** architecture for this use case:
- ✓ Prevents event loop blocking (solves WSL2 timeout issue)
- ✓ Enables 2-5 minute simulations without client timeout
- ✓ Provides immediate response with job_id for status polling

---

## Files to Keep

All other files are part of the production system:
- ✓ `tools/basis_of_design.py` - USED (elicit_basis_of_design)
- ✓ `tools/state_management.py` - USED (get/reset design state)
- ✓ `tools/validation.py` - USED (check_strong_ion_balance)
- ✓ `tools/chemical_dosing.py` - USED (estimate_chemical_dosing)
- ✓ `tests/test_qsdsan_simulation_basic.py` - WORKING smoke test
- ✓ All `utils/*_cli.py` - Essential for job execution
- ✓ All other `utils/*.py` - Core calculation logic

---

## Optional Future Work

**If you want optional analysis tools:**

Instead of having dead files, consider:
1. Consolidate into single file: `tools/analysis.py`
2. Register with @mcp.tool() decorators in server.py
3. Add to main workflow documentation
4. Make available as secondary analysis tools

**For now:** Remove them to clean up technical debt.
