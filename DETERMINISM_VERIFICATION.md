# mADM1 Determinism Verification

## Summary

The mADM1 (Modified Anaerobic Digestion Model 1) simulation model is **fully deterministic**. Identical inputs produce identical outputs.

## Verification Test Results

**Test**: `test_determinism.py` - Runs same simulation 3 times with identical inputs

| Metric | Run 1 | Run 2 | Run 3 | Status |
|--------|-------|-------|-------|--------|
| Actual pH (PCM solver) | 6.5344 | 6.5344 | 6.5344 | ✓ IDENTICAL |
| Stream pH (post-processed) | 4.4449 | 4.4449 | 4.4449 | ✓ IDENTICAL |
| VSS yield (kg/kg COD) | 0.074244 | 0.074244 | 0.074244 | ✓ IDENTICAL |
| TSS yield (kg/kg COD) | 0.085337 | 0.085337 | 0.085337 | ✓ IDENTICAL |
| COD removal (%) | 43.71 | 43.71 | 43.71 | ✓ IDENTICAL |
| Convergence time (days) | 200.0 | 200.0 | 200.0 | ✓ IDENTICAL |

**Conclusion**: Same inputs → Same outputs with machine precision. Model is deterministic.

## pH Calculation: Two Different Values

There are **two pH calculations** in the system:

### 1. Internal PCM pH (Actual Simulation pH)
- **Location**: `utils/qsdsan_madm1.py:452-545` (`pcm()` function)
- **When used**: During simulation for process rates and inhibition
- **Accounts for**: ALL ions (Fe³⁺, Cl⁻, Ca²⁺, Mg²⁺, NH₄⁺, VFAs, IC, etc.)
- **Stored in**: `root.data['pH']` and `diagnostics['speciation']['pH']`
- **Example**: pH = 6.53

### 2. Stream Property pH (Post-Processed)
- **Location**: `adm1_mcp_server/calculate_ph_and_alkalinity_fixed.py:200-283`
- **When calculated**: After simulation via `update_ph_and_alkalinity()`
- **Accounts for**: Only S_cat/S_an, inorganic C/N, and 4 VFAs
- **Stored in**: `stream.pH` property
- **Example**: pH = 4.44 (can be misleading!)

### Why They Differ

The stream pH calculation is **simplified** and does not account for:
- Fe³⁺, Fe²⁺ (iron cations)
- Cl⁻ (chloride anions)
- Ca²⁺, Mg²⁺ (divalent cations)
- Other mineral ions

When the base state has S_cat/S_an = 0 (as in our test files), the stream pH calculation "sees" VFA anions with no counter-cations and reports an artificially low pH.

## Implications

### For Users

**Always use the PCM pH** (actual simulation pH) when:
- Evaluating simulation results
- Comparing pH values
- Assessing process performance

**Extract the correct pH from diagnostics**:
```python
diagnostics = extract_diagnostics(system)
actual_pH = diagnostics['speciation']['pH']  # This is the real pH!
```

**Ignore stream.pH** unless:
- The ADM1 state properly sets S_cat/S_an
- You understand it uses simplified calculation

### For Developers

The stream pH should ideally be updated to use the PCM value:
```python
# After simulation
AD = system.flowsheet.unit.AD
effluent.pH = AD.model.rate_function.params['root'].data['pH']
```

This would eliminate confusion between the two pH values.

## Historical Context

This investigation was prompted by observations of "non-deterministic" pH behavior:
- Base case: pH 6.53
- High nutrients test: pH 5.14
- Iron addition test: pH 4.44

**Root cause**: Different input conditions + using simplified stream pH instead of actual PCM pH.

**Resolution**: Codex MCP analysis revealed the two pH calculations and confirmed determinism via repeated simulation tests.

## Testing Protocol

To verify determinism for future model changes:

1. Run `test_determinism.py` (runs same simulation 3 times)
2. All metrics must match within tolerance (< 1e-6 for pH, < 1e-8 for yields)
3. Check both PCM pH and stream pH for consistency

## References

- **PCM solver**: `utils/qsdsan_madm1.py:452-545`
- **Stream pH calculation**: `adm1_mcp_server/calculate_ph_and_alkalinity_fixed.py:200-283`
- **Diagnostic extraction**: `utils/stream_analysis_sulfur.py:1239-1325`
- **Determinism test**: `test_determinism.py`
- **Codex analysis**: Conversation ID `019a0b6a-43a1-7953-8066-5c46d524b490` (2025-10-22)
