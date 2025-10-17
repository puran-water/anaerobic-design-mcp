# Component Mapping: WaterTAP Modified ADM1 to QSDsan ADM1p

## Overview
This document maps WaterTAP Modified ADM1 state variables to QSDsan ADM1p components for the migration.

## Component Mapping Table

### Soluble Components

| WaterTAP Modified ADM1 | QSDsan ADM1p | Units | Conversion Notes |
|------------------------|--------------|-------|------------------|
| S_su | S_su | kg/m³ | Direct mapping |
| S_aa | S_aa | kg/m³ | Direct mapping |
| S_fa | S_fa | kg/m³ | Direct mapping |
| S_va | S_va | kg/m³ | Direct mapping |
| S_bu | S_bu | kg/m³ | Direct mapping |
| S_pro | S_pro | kg/m³ | Direct mapping |
| S_ac | S_ac | kg/m³ | Direct mapping |
| S_h2 | S_h2 | kg/m³ | Direct mapping |
| S_ch4 | S_ch4 | kg/m³ | Direct mapping |
| S_IC | S_IC | kg C/m³ | Direct mapping |
| S_IN | S_IN | kg N/m³ | Direct mapping |
| S_I | S_I | kg/m³ | Direct mapping |
| S_cat | S_cat* | kmol/m³ | Excludes K+, Mg2+ in ADM1p |
| S_an | S_an* | kmol/m³ | Excludes specific anions |
| S_co2 | (calculated) | kg/m³ | From S_IC equilibrium |

### Phosphorus Species (Modified ADM1 → ADM1p)

| WaterTAP Modified ADM1 | QSDsan ADM1p | Units | Conversion Notes |
|------------------------|--------------|-------|------------------|
| S_IP | S_IP | kg P/m³ | Direct mapping |
| S_K | S_K | kg/m³ | Direct mapping |
| S_Mg | S_Mg | kg/m³ | Direct mapping |
| - | S_Ca | kg/m³ | Add for precipitation |
| - | S_Na | kg/m³ | Add for ionic strength |
| - | S_Cl | kg/m³ | Add for ionic strength |

### Particulate Components

| WaterTAP Modified ADM1 | QSDsan ADM1p | Units | Conversion Notes |
|------------------------|--------------|-------|------------------|
| X_c | - | kg/m³ | Removed in Modified ADM1 |
| X_ch | X_ch | kg/m³ | Direct mapping |
| X_pr | X_pr | kg/m³ | Direct mapping |
| X_li | X_li | kg/m³ | Direct mapping |
| X_su | X_su | kg/m³ | Direct mapping |
| X_aa | X_aa | kg/m³ | Direct mapping |
| X_fa | X_fa | kg/m³ | Direct mapping |
| X_c4 | X_c4 | kg/m³ | Direct mapping |
| X_pro | X_pro | kg/m³ | Direct mapping |
| X_ac | X_ac | kg/m³ | Direct mapping |
| X_h2 | X_h2 | kg/m³ | Direct mapping |
| X_I | X_I | kg/m³ | Direct mapping |

### Phosphorus Biomass (Modified ADM1 → ADM1p)

| WaterTAP Modified ADM1 | QSDsan ADM1p | Units | Conversion Notes |
|------------------------|--------------|-------|------------------|
| X_PAO | X_PAO | kg/m³ | Direct mapping |
| X_PHA | X_PHA | kg/m³ | Direct mapping |
| X_PP | X_PP | kg P/m³ | Direct mapping |

### Precipitates (New in ADM1p)

| WaterTAP Modified ADM1 | QSDsan ADM1p | Units | Conversion Notes |
|------------------------|--------------|-------|------------------|
| - | X_CaCO3 | kg/m³ | Calcium carbonate |
| - | X_struv | kg/m³ | Struvite (MgNH4PO4) |
| - | X_newb | kg/m³ | Newberyite |
| - | X_ACP | kg/m³ | Amorphous calcium phosphate |
| - | X_MgCO3 | kg/m³ | Magnesium carbonate |
| - | X_AlOH | kg/m³ | Aluminum hydroxide |
| - | X_AlPO4 | kg/m³ | Aluminum phosphate |
| - | X_FeOH | kg/m³ | Iron hydroxide |
| - | X_FePO4 | kg/m³ | Iron phosphate |

## Important Conversion Notes

### 1. Charge Balance (S_cat/S_an)
- **WaterTAP Modified ADM1**: S_cat and S_an include all cations/anions
- **QSDsan ADM1p**: S_cat and S_an represent "other" ions only
  - K+, Mg2+, Ca2+, Na+ are tracked separately as S_K, S_Mg, S_Ca, S_Na
  - Must recalculate S_cat/S_an to exclude these specific ions

### 2. Composite Variable (X_c)
- **WaterTAP Modified ADM1**: X_c removed (direct breakdown to X_ch, X_pr, X_li)
- **QSDsan ADM1p**: No X_c component
- **Conversion**: Sum of X_ch + X_pr + X_li replaces X_c functionality

### 3. Precipitation Species
- **WaterTAP Modified ADM1**: No explicit precipitates
- **QSDsan ADM1p**: 9 precipitate species for mineral precipitation
- **Initialization**: Set all precipitates to 0.0 initially, let simulation calculate

### 4. Additional Ions
- **WaterTAP Modified ADM1**: Limited ion tracking
- **QSDsan ADM1p**: Comprehensive ionic species (Ca, Na, Cl)
- **Default Values**: 
  - S_Ca: 0.01 kg/m³ (typical for wastewater)
  - S_Na: 0.05 kg/m³ (typical for wastewater)
  - S_Cl: 0.03 kg/m³ (typical for wastewater)

## State Generation Strategy

### From Codex MCP (ADM1-State-Variable-Estimator)
1. Update AGENTS.md to generate all 42 ADM1p components
2. Include precipitate species (initialized to 0)
3. Add missing ionic species (Ca, Na, Cl)
4. Adjust S_cat/S_an calculation for "other ions" only

### Validation Considerations
1. COD balance: Ensure total COD matches measured values
2. TSS/VSS: Account for precipitates in TSS calculation
3. Charge balance: Properly separate specific ions from S_cat/S_an
4. P-balance: Track phosphorus in S_IP, X_PP, X_PAO, precipitates

## QSDsan ADM1p State Dictionary Format

```python
adm1p_state = {
    # Soluble components (kg/m³)
    'S_su': 1.0,
    'S_aa': 1.5,
    'S_fa': 2.5,
    'S_va': 0.001,
    'S_bu': 0.001,
    'S_pro': 0.002,
    'S_ac': 2.5,
    'S_h2': 0.0001,
    'S_ch4': 0.0001,
    'S_IC': 0.05,  # kg C/m³
    'S_IN': 0.03,  # kg N/m³
    'S_IP': 0.005, # kg P/m³
    'S_I': 2.5,
    'S_K': 0.01,
    'S_Mg': 0.005,
    'S_Ca': 0.01,
    'S_Na': 0.05,
    'S_Cl': 0.03,
    'S_cat': 0.02,  # Other cations only (kmol/m³)
    'S_an': 0.02,   # Other anions only (kmol/m³)
    
    # Particulate components (kg/m³)
    'X_ch': 12.5,
    'X_pr': 10.0,
    'X_li': 5.0,
    'X_su': 0.01,
    'X_aa': 0.01,
    'X_fa': 0.005,
    'X_c4': 0.005,
    'X_pro': 0.005,
    'X_ac': 0.01,
    'X_h2': 0.005,
    'X_I': 2.5,
    
    # P-biomass (kg/m³)
    'X_PAO': 0.01,
    'X_PHA': 0.001,
    'X_PP': 0.1,  # kg P/m³
    
    # Precipitates (kg/m³) - initialized to 0
    'X_CaCO3': 0.0,
    'X_struv': 0.0,
    'X_newb': 0.0,
    'X_ACP': 0.0,
    'X_MgCO3': 0.0,
    'X_AlOH': 0.0,
    'X_AlPO4': 0.0,
    'X_FeOH': 0.0,
    'X_FePO4': 0.0,
    
    # Water (kg/m³)
    'H2O': 994.0  # Remainder to make ~1000 kg/m³
}
```

## Migration Implementation Order

1. **Update Codex MCP AGENTS.md** to generate QSDsan ADM1p format
2. **Create state converter** for existing WaterTAP states (backwards compatibility)
3. **Update validation tools** to use QSDsan component properties
4. **Implement QSDsan simulation** with ADM1p model
5. **Add TEA calculations** using QSDsan framework

## References
- QSDsan ADM1p: `qsdsan/processes/_adm1_p_extension.py`
- WaterTAP Modified ADM1: `watertap/property_models/unit_specific/anaerobic_digestion/modified_adm1_properties.py`
- Working ADM1 server: `/mnt/c/Users/hvksh/mcp-servers/adm1_mcp_server/`