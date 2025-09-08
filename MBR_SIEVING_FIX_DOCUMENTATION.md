# MBR Sieving Coefficient Fix Documentation

## Date: 2025-01-07

## Problem Identified

The original MBR split logic in `watertap_simulation_modified.py` contained a structural mathematical inconsistency that caused convergence failures:

### Original Problematic Logic (Lines 837-865)
```python
# Soluble components (S_*): split_fraction = 0.999999 (~100% to permeate)
# Particulates (X_*): split_fraction = 0.001 (~0.1% to permeate)
# Water (H2O): unfixed, determined by volumetric recovery constraint
# Volumetric recovery: mbr_recovery = 0.2 (20% of inlet volume to permeate)
```

### The Mathematical Impossibility
With volumetric recovery at 20% but soluble mass split at ~100%, this forced:
- Permeate soluble concentrations to be **5× the feed concentration**
- Retentate to be nearly solute-free
- Violation of fundamental MBR physics where membranes pass dissolved species with minimal rejection

This created conflicting constraints that caused:
- Sequential Decomposition oscillation
- Solver divergence or convergence to infeasible states
- Numerical instability from extreme split values (0.999999)

## Solution Implemented

### Sieving Coefficient Approach
Replaced the fixed split fractions with a physically consistent sieving coefficient model:

```python
split_fraction[permeate, j] = σ_j × mbr_recovery
```

Where:
- `σ_j` is the sieving coefficient for component j (ratio C_permeate/C_feed)
- `mbr_recovery` is the volumetric recovery fraction

### Implementation Details (Lines 837-880)

1. **Sieving Coefficient Parameters**:
   - `σ_soluble = 1.0`: Solubles pass through freely (no concentration change)
   - `σ_particulate = 1e-4`: Particulates are rejected (>99.9% removal)
   - `σ_h2o = 1.0`: Water follows volumetric recovery

2. **Key Changes**:
   - Created Pyomo Parameter `m.fs.mbr_sigma` for each component
   - Unfixed all split fractions (made them Variables)
   - Added constraint: `eq_mbr_split` linking splits to recovery
   - Maintained existing volumetric constraints

3. **Configuration Options**:
   Users can now tune membrane behavior via `heuristic_config['mbr']`:
   ```python
   "mbr": {
       "sigma_soluble": 1.0,      # Range: 0.95-1.0 for slight rejection
       "sigma_particulate": 1e-4,  # Range: 1e-5 to 1e-3
       "sigma_h2o": 1.0           # Keep at 1.0
   }
   ```

## Benefits of the Fix

1. **Physical Consistency**: 
   - Maintains C_permeate ≈ C_feed for solubles
   - Ensures proper particulate rejection
   - Aligns mass and volume balances

2. **Numerical Stability**:
   - Eliminates extreme split values (0.999999)
   - Improves conditioning of the constraint matrix
   - Reduces oscillation in Sequential Decomposition

3. **Flexibility**:
   - User-tunable parameters for different membrane types
   - Automatic adjustment if recovery changes during solving
   - Compatible with existing recycle/translator topology

## Testing

A test script `test_mbr_sieving_fix.py` has been created with:
- Pause point for MCP server reconnection
- Full simulation test with the new sieving approach
- Validation of convergence and physical consistency

## Files Modified

1. `/utils/watertap_simulation_modified.py` (Lines 837-880)
   - Replaced fixed split logic with sieving coefficient approach
   
2. Created `/test_mbr_sieving_fix.py`
   - Test script with pause point for MCP reconnection
   
3. Created `/MBR_SIEVING_FIX_DOCUMENTATION.md`
   - This documentation file

## Verification Checklist

After implementation, verify:
- [ ] DOF = 0 after arc expansion
- [ ] C_permeate/C_feed ≈ 1 for soluble components
- [ ] Particulate rejection > 99%
- [ ] Sequential Decomposition converges monotonically
- [ ] No solver warnings about badly scaled variables
- [ ] MBR permeate flow matches expected value (~1000 m³/d for 1000 m³/d feed)

## References

The fix was based on:
1. Standard MBR membrane physics where sieving coefficients determine separation
2. WaterTAP best practices for membrane modeling (recovery/rejection relationships)
3. Numerical optimization principles for constraint-based modeling

## Next Steps

1. Run `test_mbr_sieving_fix.py` to validate the fix
2. Monitor convergence behavior with different feedstock types
3. Consider extending to include slight solute rejection (σ = 0.95-0.98) for specific applications