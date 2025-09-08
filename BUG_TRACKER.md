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