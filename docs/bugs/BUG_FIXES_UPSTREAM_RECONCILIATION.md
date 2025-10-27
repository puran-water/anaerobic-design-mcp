# Bug Fixes and Upstream Reconciliation

## Date: 2025-10-24

## Summary

Two critical bugs were identified by Codex that caused 99.94%+ biogas production failure. Both bugs have been fixed and the implementation is now reconciled with upstream QSD-Group/QSDsan repository.

## Bug #1: Wrong Gas Constant (100× Error)

### Problem
The gas constant R was set to `8.314 J/(mol·K)` which is the standard thermodynamic value, but ADM1 headspace calculations require R in bar-based units.

**Impact**: Partial pressures were 100× too large, causing methane and CO2 to dissolve back into the liquid phase instead of evolving as biogas.

### Root Cause
```python
# WRONG (original code)
R = 8.314  # J/(mol·K) - standard thermodynamic units
biogas_p = R * T_op * state_arr[63:67]  # Gives pressure in wrong units
```

When used in the ideal gas law with kmol/m³ concentrations, this gives pressures in units incompatible with ADM1's bar-based Henry's law constants.

### Fix Applied
```python
# CORRECT (fixed in utils/qsdsan_madm1.py:431)
# CRITICAL: ADM1 uses bar-based units for headspace, so R must be in bar·m³/(kmol·K)
R = 8.3145e-2  # bar·m³/(kmol·K) - NOT 8.314 J/(mol·K)
```

### Upstream Verification
From `qsdsan/processes/__init__.py` line 39 (commit d5316d9b by Joy Zhang, 2024-06-13):
```python
R = 8.3145e-2 # Universal gas constant, [bar/M/K]
```

**Status**: ✅ RECONCILED with upstream

---

## Bug #2: Dimensional Mismatch in Gas Transfer

### Problem
The gas transfer calculation attempted to convert biogas_S to kmol/m³ then back to kg/m³, creating a dimensional mismatch in Henry's law.

**Impact**: The term `(biogas_S - KH * biogas_p)` had inconsistent units:
- `KH * biogas_p`: kg/m³ (from KH already in kg/m³/bar)
- `biogas_S`: kmol/m³ (after incorrect conversion)
- Result: Subtraction of incompatible units, wrong driving force for gas transfer

### Root Cause (First Attempt)
```python
# WRONG - my initial fix attempt
biogas_S = state_arr[[7,8,9,30]] * unit_conversion[[7,8,9,30]]  # kg/m³ → kmol/m³
biogas_S[2] = co2  # kmol/m³
biogas_S[3] = Z_h2s  # kmol/m³
biogas_p = R * T_op * state_arr[63:67]  # bar
rhos[-4:] = kLa * (biogas_S - KH * biogas_p) / unit_conversion[[7,8,9,30]]
# Problem: [kmol/m³] - [kg/m³/bar × bar] = [kmol/m³] - [kg/m³] → dimensional error
```

### Fix Applied
```python
# CORRECT (fixed in utils/qsdsan_madm1.py:873-887)
# Henry's law: rhos = kLa * (biogas_S - KH * biogas_p)
# CRITICAL: Keep everything in kg/m³ (mass units) to match KH which is already kg/m³/bar

biogas_S = state_arr[[7,8,9,30]].copy()  # Start with kg/m³ from state
# Replace totals with dissolved species from PCM/calc_biogas (convert from kmol/m³ to kg/m³)
biogas_S[2] = co2 / unit_conversion[9]  # CO2 from PCM: kmol/m³ → kg/m³
biogas_S[3] = Z_h2s / unit_conversion[30]  # H2S from calc_biogas: kmol/m³ → kg/m³

# Partial pressures in bar (R is in bar·m³/(kmol·K), state[63:67] is kmol/m³)
biogas_p = R * T_op * state_arr[63:67]  # bar

# Gas transfer rate in kg/m³/d (all terms in consistent mass units)
rhos[-4:] = kLa * (biogas_S - KH * biogas_p)  # kg/m³/d
```

**Key insight**: KH is already in mass units (kg/m³/bar) from line 834:
```python
KH = KHb * T_correction_factor(T_base, T_op, KH_dH) / unit_conversion[[7,8,9,30]]
```

### Upstream Verification
From `qsdsan/processes/_adm1_p_extension.py` function `_rhos_adm1_p_extension`:
```python
biogas_S = state_arr[7:10].copy()
# ...
co2 = state_arr[9] * h / (Ka[3] + h)
biogas_S[-1] = co2
# ...
rhos[-3:] = kLa * (biogas_S - KH * biogas_p)
```

Note: Upstream handles CO2 differently (uses `co2` directly from mass balance, not from PCM), but the unit consistency pattern is identical - `biogas_S` stays in kg/m³.

**Status**: ✅ RECONCILED with upstream

---

## Implementation Comparison Table

| Component | Upstream QSDsan | Our mADM1+S Implementation | Status |
|-----------|----------------|---------------------------|--------|
| Gas constant R | `8.3145e-2 [bar/M/K]` | `8.3145e-2` (line 431) | ✅ MATCH |
| biogas_S initialization | `state_arr[7:10].copy()` | `state_arr[[7,8,9,30]].copy()` | ✅ COMPATIBLE* |
| Dissolved CO2 | `state_arr[9] * h / (Ka[3] + h)` | `co2 / unit_conversion[9]` | ✅ EQUIVALENT** |
| KH conversion | `KHb / unit_conversion[7:10]` | `KHb * T_corr / unit_conversion[[7,8,9,30]]` | ✅ MATCH |
| biogas_p calculation | `R * T_op * state_arr[34:37]` | `R * T_op * state_arr[63:67]` | ✅ COMPATIBLE*** |
| Henry's law | `kLa * (biogas_S - KH * biogas_p)` | `kLa * (biogas_S - KH * biogas_p)` | ✅ MATCH |

**Notes**:
- \* Our implementation includes H2S (index 30) as 4th biogas species; upstream has 3 species (H2, CH4, CO2)
- \*\* Both compute dissolved CO2, our implementation uses PCM solver which returns same result
- \*\*\* Different state indices due to our 67-component mADM1+S vs upstream's 37-component ADM1-P

---

## Files Modified

### `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/utils/qsdsan_madm1.py`

**Line 431** - Fixed gas constant:
```python
R = 8.3145e-2  # bar·m³/(kmol·K) - NOT 8.314 J/(mol·K)
```

**Lines 873-887** - Fixed gas transfer unit consistency:
```python
biogas_S = state_arr[[7,8,9,30]].copy()  # kg/m³
biogas_S[2] = co2 / unit_conversion[9]  # kmol/m³ → kg/m³
biogas_S[3] = Z_h2s / unit_conversion[30]  # kmol/m³ → kg/m³
biogas_p = R * T_op * state_arr[63:67]  # bar
rhos[-4:] = kLa * (biogas_S - KH * biogas_p)  # kg/m³/d
```

---

## Expected Outcome

With both fixes applied, the simulation should show:

1. **Biogas production restored**: ~2500 m³/d total (~1265 m³/d CH4)
2. **Methane yield**: ~0.35 m³/kg COD (100% theoretical efficiency)
3. **COD mass balance closure**: CODin = CODout + CODmethane + CODsulfate + CODbiomass
4. **TOC mass balance closure**: Cin = Cout + Cmethane + Cco2

Previous runs showed catastrophic failure:
- Before fixes: 1.49 m³/d CH4 (99.94% failure)
- After Bug #1 fix only: Unknown (both fixes applied together)
- After both fixes: TO BE VERIFIED

---

## Upstream References

### QSD-Group/QSDsan Repository

**Commits referenced**:
- `d5316d9b` - Joy Zhang, 2024-06-13: Added R constant definition
- `cea2a3c0` - Joy Zhang, 2024-06-13: Added R import to _adm1_p_extension.py
- `2155dd84` - Joy Zhang, 2024-12-04: Updated biogas_p calculation
- `12f5622a` - Joy Zhang, 2024-06-03: Added _R to AnaerobicCSTR

**Files referenced**:
- `qsdsan/processes/__init__.py` - R constant definition
- `qsdsan/processes/_adm1_p_extension.py` - Gas transfer implementation
- `qsdsan/sanunits/_anaerobic_reactor.py` - Reactor ODE and gas evolution

---

## Verification Method

Used DeepWiki MCP server to query upstream QSDsan documentation:

1. **Query 1**: "What is the correct value and units for the gas constant R used in ADM1 headspace calculations?"
   - **Result**: Confirmed R = 8.3145e-2 [bar/M/K]

2. **Query 2**: "How is the gas transfer calculation implemented in _adm1_p_extension.py?"
   - **Result**: Confirmed biogas_S.copy() pattern and unit consistency

---

## Codex Diagnosis Reference

From conversation ID `019a1399-9238-7a40-a8df-2b5b09c45283`, Codex identified both bugs after reviewing:
- Our implementation in `utils/qsdsan_madm1.py`
- Upstream QSDsan models via DeepWiki
- GitHub repository via gh CLI tools

Codex's exact diagnosis (condensed):

> **Bug #1**: You have `R = 8.314`, but that's the "J/(mol·K)" constant. For headspace in bar, you need R = 8.3145e-2 bar·m³/(kmol·K).
>
> **Bug #2**: You're dividing by unit_conversion at the end, but KH was already converted to mass units earlier. This creates a dimensional mismatch.

Both bugs confirmed via upstream code review and now fixed.

---

## Status

- ✅ Bug #1 fixed and reconciled with upstream
- ✅ Bug #2 fixed and reconciled with upstream
- ⏳ Simulation running to verify fixes work
- ⏳ Mass balance closure verification pending

**Last updated**: 2025-10-24 16:10 UTC
