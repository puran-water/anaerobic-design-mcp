# Diagnostic Data Status - mADM1 Simulation

## Currently Reported ✓

### 1. Performance Metrics
- **COD removal efficiency**: 43.7%
- **VSS yield**: 0 kg VSS/kg COD (CSTR at steady state)
- **TSS yield**: 0 kg TSS/kg COD (CSTR at steady state)

### 2. H2S Inhibition
- **Hydrogenotrophic methanogens**: 13.6% inhibition
- **Acetoclastic methanogens**: 12.1% inhibition  
- **H2S concentration**: 63.1 mg S/L
- **Inhibition constants** (KI): 0.4-0.46 kg S/m³

### 3. Stream Analysis
**Influent**:
- Flow, COD, TSS, VSS, TKN, TP, pH, alkalinity
- All 62 component concentrations

**Effluent**:
- Flow, COD, TSS, VSS, TKN, TP, pH, alkalinity
- All 62 component concentrations

**Biogas**:
- Total flow: 983.7 m³/d
- Methane: 705.4 m³/d (71.7%)
- CO2, H2 flows and percentages
- H2S ppm

### 4. Sulfur Balance
- Sulfate removal: 97.8%
- Sulfate in/out (mg/L and kg S/d)
- Dissolved sulfide (H2S, HS-)
- H2S speciation (fraction H2S vs HS-)
- SRB biomass

### 5. Convergence Data
- Status: max_time_reached
- Time: 200 days
- Runtime: 665 seconds

---

## Available But NOT Reported ✗

The following diagnostic data is **calculated** in `qsdsan_madm1.py:878-941` via `root.data` but **NOT extracted** and returned in simulation results:

### 1. Complete Inhibition Profile
```python
root.data = {
    'I_pH': {
        'acidogens': float,
        'acetoclastic': float,
        'hydrogenotrophic': float,
        'SRB_h2': float,
        'SRB_ac': float,
        'SRB_aa': float,
    },
    'I_h2': {
        'LCFA': float,
        'C4_valerate': float,
        'C4_butyrate': float,
        'propionate': float,
    },
    'I_h2s': {
        'C4_valerate': float,
        'C4_butyrate': float,
        'propionate': float,
        'acetate': float,
        'hydrogen': float,
        'SRB_h2': float,
        'SRB_ac': float,
        'SRB_prop': float,
        'SRB_bu': float,
        'SRB_va': float,
    },
    'I_nutrients': {
        'I_IN_lim': float,
        'I_IP_lim': float,
        'combined': float,
        'I_nh3': float,
    },
}
```

### 2. Biomass Concentrations
```python
'biomass_kg_m3': {
    'X_su': float,      # Sugar degraders
    'X_aa': float,      # Amino acid degraders
    'X_fa': float,      # LCFA degraders
    'X_c4': float,      # Valerate/butyrate degraders
    'X_pro': float,     # Propionate degraders
    'X_ac': float,      # Acetoclastic methanogens
    'X_h2': float,      # Hydrogenotrophic methanogens
    'X_PAO': float,     # Polyphosphate accumulating organisms
    'X_hSRB': float,    # H2-utilizing SRB
    'X_aSRB': float,    # Acetate-utilizing SRB
    'X_pSRB': float,    # Propionate-utilizing SRB
    'X_c4SRB': float,   # C4-utilizing SRB
}
```

### 3. Substrate Limitation (Monod Factors)
```python
'Monod': [
    float,  # S_su limitation
    float,  # S_aa limitation
    float,  # S_fa limitation
    float,  # S_va limitation
    float,  # S_bu limitation
    float,  # S_pro limitation
    float,  # S_ac limitation
    float,  # S_h2 limitation
]
```

### 4. Process Rates
```python
'process_rates': [
    # Array of 63 process rates (kg COD/m³/d)
    # Includes:
    # - Hydrolysis (3 processes)
    # - Acidogenesis (8 processes)
    # - Methanogenesis (3 processes)
    # - Decay (7 processes)
    # - P cycling (3 processes)
    # - Sulfate reduction (9 processes)
    # - Fe reactions (10 processes)
    # - Precipitation (13 processes)
    # - Gas transfer (4 processes)
]
```

### 5. Speciation Data
- pH, NH3 (M), CO2 (M), H2S (M)

### 6. Precipitation Rates
- All 13 mineral precipitation rates from `rhos[46:59]`
- Includes: struvite, calcium phosphates, iron sulfide, etc.

---

## Why This Data Is Important

1. **Process Diagnostics**: Identify which process is rate-limiting
2. **Troubleshooting**: Understand why performance is poor (e.g., which inhibition is dominant)
3. **Optimization**: Determine which parameter adjustments would help most
4. **Validation**: Compare biomass concentrations to literature values
5. **Resource Recovery**: Track precipitation of valuable minerals (struvite, HAP)

---

## Recommendation

Add diagnostic data extraction to `utils/qsdsan_simulation_sulfur.py` after simulation completion:

```python
# After simulation completes
if hasattr(madm1_model.rate_function, 'params'):
    root = madm1_model.rate_function.params.get('root')
    if root is not None and hasattr(root, 'data'):
        results['diagnostics'] = root.data
```

This would provide comprehensive process diagnostics for troubleshooting and optimization.
