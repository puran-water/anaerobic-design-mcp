# Bug Tracker - Anaerobic Design MCP Workflow
## Date: 2025-01-07

## Bugs Encountered

### 1. MCP Tool Parameter Format Issue
- **Tool**: `mcp__anaerobic-design__elicit_basis_of_design`
- **Issue**: The `current_values` parameter does not accept a dictionary/object format despite documentation suggesting it should
- **Error**: "Input validation error: '...' is not valid under any of the given schemas"
- **Workaround**: Omit the `current_values` parameter and use default prompts
- **Status**: Active

### 2. Unicode Encoding Issue (FIXED)
- **Tool**: Test script output
- **Issue**: Unicode character σ (sigma) caused encoding error in Windows console
- **Error**: "UnicodeEncodeError: 'charmap' codec can't encode character '\u03c3'"
- **Fix**: Replaced σ with ASCII "sigma" in output strings
- **Status**: Fixed

### 3. ADM1 State Validation Deviations
- **Tool**: `mcp__anaerobic-design__validate_adm1_state`
- **Issue**: Large deviations between calculated and target parameters
  - COD: 69,648 mg/L vs 50,000 mg/L (39.3% deviation)
  - TSS: 42,500 mg/L vs 35,000 mg/L (21.4% deviation)
  - VSS: 37,500 mg/L vs 28,000 mg/L (33.9% deviation)
  - TKN: 3,027 mg/L vs 2,500 mg/L (21.1% deviation)
  - TP: 0 mg/L vs 500 mg/L (100% deviation - not modeled in ADM1)
- **Root Cause**: The ADM1 state from Codex uses array format [value, unit, description] but validation extracts wrong values
- **Status**: Active - state was stored despite validation failure

### 4. WaterTAP Simulation TypeError (FIXED)
- **Tool**: `mcp__anaerobic-design__simulate_ad_system_tool`
- **Issue**: regularize_adm1_state_for_initialization() got unexpected keyword argument 'target_alkalinity_meq_l'
- **Context**: Occurs when running simulation with use_current_state=true
- **Fix**: Changed call to pass basis_of_design instead of individual parameters
- **Status**: Fixed

### 5. Model Over-Specification (DOF = -1) (FIXED)
- **Tool**: `mcp__anaerobic-design__simulate_ad_system_tool`
- **Issue**: Model is over-specified with DOF = -1 after MBR sieving coefficient fix
- **Context**: Occurs in low_tss_mbr flowsheet after adding eq_mbr_split constraints
- **Fix**: Excluded last component from constraints to avoid over-specification
- **Status**: Fixed

### 6. Simulation Convergence Failure (PARTIALLY FIXED)
- **Tool**: `mcp__anaerobic-design__simulate_ad_system_tool`
- **Issue**: Simulation reaches max iterations without converging
- **Initial Symptoms**:
  - Biogas production: 5.26e-6 m³/d (essentially zero)
  - MBR permeate: 282 m³/d (should be ~1000 m³/d)
  - Methane fraction: 5% (should be ~65%)
- **After Water-Anchored Fix**:
  - ✅ MBR permeate: 999.86 m³/d (FIXED!)
  - ❌ Biogas: 0.19 m³/d (still too low)
  - ❌ Methane: 4.8% (still too low)
  - ❌ Sludge: 0.14 m³/d (should be 333)
- **Root Cause**: AD biology not functioning - needs phased initialization
- **Status**: Partially Fixed - MBR flows correct, AD biology needs initialization fix

## Current Workflow Status
- ✅ Design state reset
- ✅ Basis of design parameters set (9 parameters collected)
- ✅ ADM1 state estimation via Codex (completed with JSON file)
- ⚠️ ADM1 validation (failed with deviations but stored)
- ✅ Heuristic sizing (completed - low_tss_mbr selected)
- ❌ WaterTAP simulation (convergence failure)

## Summary of Critical Bugs

1. **MCP Tool Input Validation**: The elicit_basis_of_design tool doesn't accept current_values parameter as documented
2. **ADM1 Array Format Issue**: Validation tool incorrectly processes array-formatted ADM1 states from Codex
3. **Function Signature Mismatch**: regularize_adm1_state_for_initialization called with wrong arguments
4. **DOF Over-specification**: MBR sieving constraints created DOF = -1 issue
5. **Convergence Failure**: Simulation fails to converge, producing physically impossible results

## Recommendations
1. Fix the array extraction logic in ADM1 validation
2. Improve initial guesses for recycle streams
3. Review MBR sieving coefficient implementation for proper constraint formulation
4. Add better scaling for extreme component values (S_H at 1e-7 kmol/m³)

---

# QSDsan Simulation Workflow Testing
## Date: 2025-10-18

## Bugs Encountered in QSDsan Workflow

### 7. Component Initialization Bug (FIXED)
- **Tool**: `mcp__anaerobic-design__simulate_ad_system_tool`
- **Issue**: Global `ADM1_SULFUR_CMPS` component set was None when simulation started
- **Error**: `AttributeError: 'NoneType' object has no attribute 'tuple'` at `utils/qsdsan_sulfur_kinetics.py:413`
- **Location**: `base_cmps_tuple = ADM1_SULFUR_CMPS.tuple[:27]`
- **Root Cause**: Simulation functions called via `anyio.to_thread.run_sync()` without first loading components using `get_qsdsan_components()`
- **Symptoms**:
  - Tool appeared to hang (ran for 567+ seconds)
  - Error logged to stderr but tool didn't return error to user
  - Not a FastMCP blocking issue - genuine code bug
- **Fix**: Added component loading step in simulation tool before calling simulation functions:
  ```python
  from utils.qsdsan_loader import get_qsdsan_components
  components = await get_qsdsan_components()
  ```
- **Status**: Fixed
- **Commit**: Pending

## Current Workflow Status (QSDsan)
- ✅ Design state reset
- ✅ Basis of design parameters set (essential params collected)
- ✅ ADM1 state estimation via Codex (30 components with self-validation)
  - COD: 0.02% deviation ✓
  - TSS: 17.87% deviation (QSDsan component mapping limitation)
  - VSS: 22.02% deviation (QSDsan component mapping limitation)
  - TKN: 0.72% deviation ✓
  - TP: 6.36% deviation ✓
- ✅ ADM1 state loaded (30 components)
- ✅ Heuristic sizing (10000 m³ digester + MBR)
- ✅ QSDsan simulation tool (CLI instruction mode working)

### 8. MCP STDIO Connection Timeout During QSDsan Loading (FIXED - Architecture Change)
- **Tool**: `mcp__anaerobic-design__simulate_ad_system_tool`
- **Issue**: MCP STDIO connection drops during QSDsan component loading (~18 seconds)
- **Error**: "STDIO connection dropped after 253s uptime", "Connection error: Received a response for an unknown message ID"
- **Root Cause**: FastMCP ping/pong mechanism doesn't keep connection alive during long synchronous imports in `anyio.to_thread.run_sync()`
- **Attempted Fix #1**: Added `await get_qsdsan_components()` before simulation - FAILED (connection still timed out)
- **Diagnosis**:
  - 13:58:20.705: Simulation started
  - 13:58:20.726 (0.02s later): "STDIO connection dropped"
  - 13:58:20.729: "Connection error: Received a response for an unknown message ID"
  - MCP client disconnected while component loading was in progress
- **Solution**: Changed architecture to CLI instruction mode (like validation tools)
  - Tool now returns CLI command for manual execution
  - Saves input files: `simulation_basis.json`, `simulation_adm1_state.json`, `simulation_heuristic_config.json`
  - User runs: `/mnt/c/Users/hvksh/mcp-servers/venv312/Scripts/python.exe utils/simulate_cli.py ...`
  - Results saved to `simulation_results.json`
- **Files Created**:
  - `utils/simulate_cli.py`: Standalone CLI script for simulation
  - Modified `tools/simulation.py`: Now returns CLI instructions instead of executing
- **Status**: Fixed via architecture change
- **Commit**: Pending

## Summary of QSDsan Workflow Bugs
1. **Component Initialization**: Simulation failed because QSDsan components weren't loaded before simulation - FIXED by adding component loading step
2. **MCP STDIO Timeout**: FastMCP connection drops during long QSDsan imports - FIXED by converting to CLI instruction mode