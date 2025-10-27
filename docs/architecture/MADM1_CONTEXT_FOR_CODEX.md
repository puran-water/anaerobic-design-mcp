# mADM1 Model Implementation Context - Comprehensive Summary

## Executive Summary

The anaerobic-design-mcp project implements a complete mADM1 (Modified ADM1) system with 62 state variables (63 components including H2O) for anaerobic digestion design. The model extends standard ADM1 with phosphorus (P), sulfur (S), and iron (Fe) biogeochemistry extensions, includes explicit mineral precipitation tracking, and uses QSDsan's Production-grade PCM (pH/Carbonate/Ammonia) solver for thermodynamic equilibrium calculations.

---

## 1. COMPLETE 62-COMPONENT STATE VECTOR

### Core ADM1 Components (0-12: Soluble; 13-23: Particulate)

**Soluble organic substrates (0-7):**
- 0: S_su - Monosaccharides (simple sugars, carbohydrate hydrolysis products)
- 1: S_aa - Amino acids (from protein hydrolysis)
- 2: S_fa - Long-chain fatty acids (LCFA, from lipid hydrolysis)
- 3: S_va - Valerate (C5 VFA)
- 4: S_bu - Butyrate (C4 VFA)
- 5: S_pro - Propionate (C3 VFA)
- 6: S_ac - Acetate (C2 VFA)
- 7: S_h2 - Dissolved hydrogen gas

**Soluble inorganic components (8-12):**
- 8: S_ch4 - Dissolved methane gas
- 9: S_IC - Inorganic carbon (kg C/m³, includes CO2 + HCO3⁻ + CO3²⁻)
- 10: S_IN - Inorganic nitrogen (kg N/m³, NH4⁺/NH3)
- 11: S_IP - Inorganic orthophosphate (kg P/m³, phosphate ions)
- 12: S_I - Soluble inerts (non-biodegradable soluble organics)

**Particulate substrate (13-15):**
- 13: X_ch - Carbohydrates (complex sugars, starch, cellulose)
- 14: X_pr - Proteins (slowly degradable nitrogenous organics)
- 15: X_li - Lipids (fats, oils, grease)

**Biomass (16-22):**
- 16: X_su - Sugar degraders (monosaccharide-fermenting bacteria)
- 17: X_aa - Amino acid degraders (amino acid-fermenting bacteria)
- 18: X_fa - LCFA degraders (fatty acid-degrading bacteria)
- 19: X_c4 - Valerate/butyrate degraders (butyrate/valerate-fermenting bacteria)
- 20: X_pro - Propionate degraders (propionate-degrading bacteria)
- 21: X_ac - Acetoclastic methanogens (Methanosaeta/Methanosarcina)
- 22: X_h2 - Hydrogenotrophic methanogens (Methanobacterium/Methanobrevibacter)

**Particulate inerts (23):**
- 23: X_I - Particulate inerts (non-biodegradable particulate organics)

### EBPR Extension Components (24-26: ASM2d-based)

- 24: X_PHA - Polyhydroxyalkanoates (internal storage polymers in PAOs)
- 25: X_PP - Polyphosphate (internal phosphorus storage in PAOs)
- 26: X_PAO - Phosphorus accumulating organisms (EBPR biomass)

### Metal Cation Components (27-28, 45-46, 60-61)

**Soluble metal ions (measured on element basis):**
- 27: S_K - Potassium ion (kg K/m³)
- 28: S_Mg - Magnesium ion (kg Mg/m³)
- 45: S_Ca - Calcium ion (kg Ca/m³)
- 46: S_Al - Aluminum ion (kg Al/m³, for alum dosing)
- 60: S_Na - Sodium ion (kg Na/m³)
- 61: S_Cl - Chloride ion (kg Cl/m³)

### Sulfur Extension Components (29-35)

**Soluble sulfur species (measured on S basis):**
- 29: S_SO4 - Sulfate (kg S/m³, electron acceptor for sulfate reduction)
- 30: S_IS - Inorganic sulfide (kg S/m³, total H2S + HS⁻ + S²⁻)
- 35: S_S0 - Elemental sulfur (kg S/m³, intermediate in sulfur cycling)

**Sulfate-reducing bacteria (SRB) - 4 species (31-34):**
- 31: X_hSRB - Hydrogenotrophic SRB (H2 utilizers)
- 32: X_aSRB - Acetotrophic SRB (acetate utilizers)
- 33: X_pSRB - Propionotrophic SRB (propionate utilizers)
- 34: X_c4SRB - Butyrate/valerate-utilizing SRB

### Iron Extension Components (36-44)

**Soluble iron species (measured on Fe basis):**
- 36: S_Fe3 - Ferric iron (Fe³⁺, oxidized form, for iron dosing)
- 37: S_Fe2 - Ferrous iron (Fe²⁺, reduced form, precipitates with sulfide)

**Hydrous ferric oxide (HFO) variants - Iron phosphorus adsorption (38-44):**
- 38: X_HFO_H - HFO with high number of active P adsorption sites
- 39: X_HFO_L - HFO with low number of active P adsorption sites
- 40: X_HFO_old - Aged/inactive HFO (sites blocked, less reactive)
- 41: X_HFO_HP - X_HFO_H with phosphorus-bounded adsorption sites
- 42: X_HFO_LP - X_HFO_L with phosphorus-bounded adsorption sites
- 43: X_HFO_HP_old - Aged X_HFO_H with phosphorus bounded
- 44: X_HFO_LP_old - Aged X_HFO_L with phosphorus bounded

**Note on HFO design:**
- X_HFO_H and X_HFO_L differ by active site factor (ASF): ASF_H=1.2, ASF_L=0.31 (mol P sites/mol Fe)
- High-affinity sites (H) bind P more strongly but capacity limited
- Low-affinity sites (L) bind P weakly but higher total capacity
- Aging process: H/L → HP/LP → HP_old/LP_old as sites get occupied and deactivated

---

## 2. MINERAL PRECIPITATION COMPONENTS (13 Total)

The mADM1 explicitly tracks 13 mineral precipitate species:

### Calcium Phosphate Precipitates (6 components: indices 47-52)

- 47: **X_CCM** - Calcite (CaCO3, calcium carbonate)
- 48: **X_ACC** - Aragonite (CaCO3 polymorph, calcium carbonate)
- 49: **X_ACP** - Amorphous calcium phosphate (Ca3(PO4)2)
- 50: **X_HAP** - Hydroxylapatite (Ca5(PO4)3OH, most stable Ca-P mineral at neutral pH)
- 51: **X_DCPD** - Dicalcium phosphate (CaHPO4·2H2O)
- 52: **X_OCP** - Octacalcium phosphate (Ca4H(PO4)3)

### Magnesium-based Precipitates (4 components: indices 53-56)

- 53: **X_struv** - Struvite (MgNH4PO4·6H2O, magnesium ammonium phosphate)
- 54: **X_newb** - Newberyite (MgHPO4·3H2O, magnesium phosphate)
- 55: **X_magn** - Magnesite (MgCO3, magnesium carbonate)
- 56: **X_kstruv** - K-struvite (MgKPO4·6H2O, potassium-substituted struvite)

### Iron and Aluminum Precipitates (3 components: indices 57-59)

- 57: **X_FeS** - Iron sulfide (FeS, Fe²⁺ + H2S precipitation)
- 58: **X_Fe3PO42** - Ferrous phosphate (Fe3(PO4)2)
- 59: **X_AlPO4** - Aluminum phosphate (AlPO4, from alum coagulation)

**Total mineral species:** 13

**Stoichiometry for precipitation:** sum_stoichios = [2, 2, 5, 9, 3, 8, 3, 3, 2, 3, 2, 2, 2]
- Index order follows _precipitates tuple: CCM, ACC, ACP, HAP, DCPD, OCP, struv, newb, magn, kstruv, FeS, Fe3PO42, AlPO4

---

## 3. COMPLETE COMPONENT ORDERING IN QSDSAN

The mADM1 components in create_madm1_cmps() are ordered as:

```python
Components([
    # ADM1 base (0-23)
    S_su(0), S_aa(1), S_fa(2), S_va(3), S_bu(4), S_pro(5), S_ac(6), 
    S_h2(7), S_ch4(8), S_IC(9), S_IN(10), S_IP(11), S_I(12),
    X_ch(13), X_pr(14), X_li(15),
    X_su(16), X_aa(17), X_fa(18), X_c4(19), X_pro(20), X_ac(21), X_h2(22), X_I(23),
    
    # EBPR (24-26)
    X_PHA(24), X_PP(25), X_PAO(26),
    
    # Metal cations (27-28, 45-46, 60-61)
    S_K(27), S_Mg(28),
    S_SO4(29), S_IS(30),  # Sulfur soluble
    X_hSRB(31), X_aSRB(32), X_pSRB(33), X_c4SRB(34),  # SRB
    S_S0(35),  # Elemental sulfur
    S_Fe3(36), S_Fe2(37),  # Iron soluble
    X_HFO_H(38), X_HFO_L(39), X_HFO_old(40),
    X_HFO_HP(41), X_HFO_LP(42), X_HFO_HP_old(43), X_HFO_LP_old(44),  # HFO
    
    S_Ca(45), S_Al(46),  # More metal cations
    
    # Minerals (47-59)
    X_CCM(47), X_ACC(48), X_ACP(49), X_HAP(50), X_DCPD(51), X_OCP(52),
    X_struv(53), X_newb(54), X_magn(55), X_kstruv(56),
    X_FeS(57), X_Fe3PO42(58), X_AlPO4(59),
    
    # More ions
    S_Na(60), S_Cl(61),
    
    H2O(62)  # Water (not state variable)
])
```

**Total: 63 components (62 state variables + H2O)**

---

## 4. IRON EXTENSION COMPONENTS - DETAILED

### HFO Concept
Hydrous ferric oxide (HFO, FeO(OH)) is a colloidal iron(III) hydroxide that acts as a phosphorus adsorbent and is central to chemical P removal in wastewater treatment.

### HFO Active Site Factor (ASF)
- **ASF**: Molar ratio of phosphorus active sites to iron atoms [mol P sites/mol Fe]
- **X_HFO_H**: High affinity, ASF_H = 1.2 (default) → fewer but stronger binding sites
- **X_HFO_L**: Low affinity, ASF_L = 0.31 (default) → more sites but weaker binding

### HFO Aging Process
HFO ages through two pathways (used in PCM solver):
1. **Fast P binding**: X_HFO_H/L → X_HFO_HP/LP (phosphorus occupies active sites)
2. **Slow P sorption**: X_HFO_H/L → X_HFO_H_old/L_old (colloid ages, becomes less reactive)

### Parameterization in create_madm1_cmps()
```python
X_HFO_H = Component('X_HFO_H', formula='FeO(OH)',
                    description='HFO high-affinity sites',
                    measured_as='Fe', particle_size='Particulate')

X_HFO_HP = Component('X_HFO_HP', 
                     formula=f'FeO(OH)P{ASF_H}',  # ASF_H=1.2
                     description='X_HFO_H with P-bounded sites',
                     measured_as='Fe')
```

---

## 5. PCM (PRODUCTION pH/CARBONATE/AMMONIA) SOLVER IMPLEMENTATION

### Location
- **Main implementation**: `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/utils/qsdsan_madm1.py:432-623`
- **Thermodynamic correction**: Van't Hoff equation for temperature-dependent Ka values
- **Root solver**: scipy.optimize.brenth (Brent's method)

### Function Signature
```python
def pcm(state_arr, params):
    """
    Production-grade pH/Carbonate/amMonia equilibrium model for mADM1.
    
    Parameters:
        state_arr : ndarray - State vector (62+ components)
        params : dict - Kinetic parameters (Ka_base, Ka_dH, T_base, T_op, components)
    
    Returns:
        tuple : (pH, nh3, co2, activities)
    """
```

### Key Features

**1. Temperature Correction (Van't Hoff):**
```
Ka(T_op) = Ka(T_base) * exp((ΔH_a/R) * (1/T_base - 1/T_op))
R = 8.314 J/(mol·K)  # CRITICAL: Not bar·m³/(kmol·K)
```

**2. Charge Balance Equation:**
The solver finds H⁺ by solving:
```
[H⁺] + [NH4⁺] + 2[Mg²⁺] + 2[Ca²⁺] + 2[Fe²⁺] + 3[Fe³⁺] + 3[Al³⁺] + [Na⁺] + [K⁺]
= [OH⁻] + [HCO3⁻] + [CO3²⁻] + [Ac⁻] + [Pro⁻] + [Bu⁻] + [Va⁻] + [HPO4²⁻] + [PO4³⁻] 
  + 2[SO4²⁻] + [HS⁻] + [Cl⁻]
```

**3. Weak Acid Speciation (Henderson-Hasselbalch):**
- Ammonia: `[NH3] = Ka_nh * [NH4⁺] / (Ka_nh + [H⁺])`
- CO2: `[CO2] = [H⁺] * [HCO3⁻] / (Ka_co2 + [H⁺])`
- VFAs: acetate, propionate, butyrate, valerate
- Sulfide: `[H2S] = Ka_h2s * [HS⁻] / (Ka_h2s + [H⁺])`

**4. Temperature-Corrected Ka Values:**
- Ka_h2s (H2S ⇌ HS⁻ + H⁺): pKa ≈ 7.0 at 25°C, ΔH = 14.3 kJ/mol
- Ka_nh (NH4⁺ ⇌ NH3 + H⁺): pKa ≈ 9.25 at 25°C
- Ka_co2 (H2CO3 ⇌ HCO3⁻ + H⁺): pKa ≈ 6.35 at 25°C
- VFA Ka values from ADM1 standard

**5. Lumped Ion Aggregation (Codex fixes #3, #4, #6):**
```python
S_cat = [Na⁺]  # From measured S_Na
S_divalent = [Mg²⁺] + [Ca²⁺] + [Fe²⁺]  # All contribute 2× charge
S_trivalent = [Fe³⁺] + [Al³⁺]  # All contribute 3× charge
S_an = [Cl⁻]  # From measured S_Cl
```

### Codex Fixes Applied

| Fix # | Issue | Fix | Impact |
|-------|-------|-----|--------|
| #1 | NH3 calc missing unit conversion | Added unit_conv_IN to numerator/denominator | Corrected NH3 inhibition magnitude |
| #2 | CO2 calc missing (Ka+h) denominator | Added (Ka+h) in denominator | Fixed CO2 kinetics in gas transfer |
| #3 | Charge balance using hardcoded S_cat/S_an | Use actual measured S_Na/S_Cl | Responds to influent salinity |
| #4 | Aggregating only Mg²⁺ for divalents | Add Ca²⁺ and Fe²⁺ | Handles iron dosing scenarios |
| #5 | No sulfur species in charge balance | Add SO4²⁻ (×2) and HS⁻ terms | Prevents pH bias in sulfur-rich AD |
| #6 | No trivalents in charge balance | Add Fe³⁺ (×3) and Al³⁺ (×3) | Handles iron/alum dosing |
| #7 | Ka_h2s hardcoded or temperature-incorrect | Compute Ka_h2s dynamically with Van't Hoff | Consistent with calc_biogas |

---

## 6. CURRENT PRECIPITATION HANDLING

### Status
- **Full precipitation mechanism**: NOT YET FULLY IMPLEMENTED
- **Available**: Saturation index calculation framework
- **Implemented**: Mineral precipitation process definitions in stoichiometry matrix

### Implemented Components

**1. Mineral Precipitation Processes (13 total):**
```python
_precipitates = (
    'X_CCM', 'X_ACC', 'X_ACP', 'X_HAP', 'X_DCPD', 'X_OCP',  # Ca-P
    'X_struv', 'X_newb', 'X_magn', 'X_kstruv',               # Mg-based
    'X_FeS', 'X_Fe3PO42', 'X_AlPO4'                          # Fe/Al
)
```

Each mineral has a process entry in the stoichiometry matrix (qsdsan/data/process_data/_madm1.tsv).

**2. Saturation Index Framework (Placeholder):**
```python
def saturation_index(acts, Ksp):
    """
    Calculate saturation indices for mineral precipitation.
    
    SI = IAP / Ksp
    SI > 1: Supersaturated (precipitation likely)
    SI = 1: At equilibrium
    SI < 1: Undersaturated (no precipitation)
    
    Currently returns SI = 1.0 for all minerals (placeholder).
    Future: Implement IAP calculation from ionic activities.
    """
```

**3. Activities Placeholder (in pcm()):**
```python
activities = np.ones(13)  # Placeholder - unity for all minerals
# Future: Add Davies or Pitzer activity model for ionic strength correction
```

### What Codex Should Implement
When working on precipitation kinetics, Codex should:

1. **Compute ionic activity products (IAP)** for each mineral:
   - Calcite: IAP = [Ca²⁺] * [CO3²⁻]
   - Struvite: IAP = [Mg²⁺] * [NH4⁺] * [PO4³⁻]
   - FeS: IAP = [Fe²⁺] * [S²⁻]
   - etc.

2. **Use solubility products (Ksp)** - temperature-dependent (Van't Hoff):
   - Each mineral has pKsp at 25°C and enthalpy of dissolution
   - Adjust with temperature using: Ksp(T) = Ksp(25°C) * exp(ΔH_diss * (1/298.15 - 1/T) / R)

3. **Implement kinetic precipitation rate:**
   - Rate ∝ (IAP/Ksp - 1)^n where n is precipitation order
   - Use saturation indices from pcm() to drive precipitation

4. **Update mineral state variables** based on precipitation:
   - Decrease soluble species (Ca²⁺, PO4³⁻, etc.)
   - Increase precipitate species (X_HAP, X_struv, etc.)

---

## 7. QSDSAN COMPONENT MAPPING

### How Our 62 Components Map to ADM1 Standard

**Original ADM1:** 27 components
- S_su through S_I (13 soluble)
- X_ch through X_I (10 particulate)
- Implicit ions for charge balance (S_cat, S_an)

**Extended to mADM1:** 62 components

| Extension | Components Added | Count | Notes |
|-----------|-----------------|-------|-------|
| Core ADM1 | S_su-S_I, X_ch-X_I | 23 | Standard IWA ADM1 |
| EBPR (ASM2d) | X_PHA, X_PP, X_PAO | 3 | Phosphorus dynamics |
| Explicit Cations | S_K, S_Mg, S_Ca, S_Na, S_Al | 5 | Replaces implicit S_cat |
| Explicit Anions | S_Cl | 1 | Replaces implicit S_an |
| Sulfur Extension | S_SO4, S_IS, S_S0, X_hSRB, X_aSRB, X_pSRB, X_c4SRB | 7 | Sulfate reduction & H2S |
| Iron Extension | S_Fe3, S_Fe2, X_HFO_H/L variants (7) | 9 | Chemical P removal & Fe dosing |
| Minerals | X_CCM, X_ACC, X_ACP, X_HAP, X_DCPD, X_OCP, X_struv, X_newb, X_magn, X_kstruv, X_FeS, X_Fe3PO42, X_AlPO4 | 13 | Explicit precipitation tracking |
| **TOTAL** | | **62** | Plus H2O makes 63 |

### Advantages Over Standard ADM1

| Feature | Standard ADM1 | Our mADM1 | Benefit |
|---------|--------------|----------|---------|
| P cycling | Implicit | Explicit X_PAO, X_PP, X_PHA + 6 Ca-P minerals | EBPR modeling, prediction of struvite loss |
| S chemistry | None | Explicit S_SO4, S_IS, 4 SRB + S0 | H2S control strategies |
| Fe dosing | None | S_Fe3, S_Fe2, 7 HFO variants | Chemical P removal, H2S precipitation |
| Charge balance | Hard-coded S_cat/S_an | Explicit Na⁺, K⁺, Cl⁻, Ca²⁺, Mg²⁺, Fe²⁺, Fe³⁺, Al³⁺ | pH responds to actual influent composition |
| Precipitation | None | 13 minerals with Ksp models | Recovery potential prediction (struvite, FeS) |

---

## 8. PCM SOLVER LOCATION AND STRUCTURE

### File Hierarchy
```
anaerobic-design-mcp/
├── utils/
│   ├── qsdsan_madm1.py (PCM solver main)
│   │   ├── def pcm() [line 432]
│   │   ├── def _compute_lumped_ions() [line 367]
│   │   ├── def acid_base_rxn() [line 550, nested]
│   │   ├── def saturation_index() [line 625]
│   │   └── def calc_biogas() [line 307]
│   ├── qsdsan_reactor_madm1.py (PCM integration in ODE)
│   │   ├── class AnaerobicCSTRmADM1
│   │   └── _compile_ODE() [calls pH_ctrl parameter]
│   └── qsdsan_simulation_sulfur.py (Simulation dispatcher)
│
├── data/
│   └── _madm1.tsv (Stoichiometry matrix for 13 minerals)
│
└── .codex/
    └── AGENTS.md (Codex prompt with all 62 components)
```

### Call Flow
1. **Simulation starts**: `qsdsan_simulation_sulfur.create_*()` 
2. **Each time step**: AnaerobicCSTRmADM1._compile_ODE() calls ODE function
3. **pH calculation**: Within dy_dt(), call pcm(QC, params) → returns (pH, nh3, co2, acts)
4. **Rate function**: rates = model.rate_function(state, params, h=pH) → uses pH for inhibition
5. **Precipitation**: saturation_index(acts, Ksp) → (not yet active)

---

## 9. KEY UNIT CONVENTIONS

### State Variables
- **All concentrations**: kg/m³ (or kg COD/m³ for COD-measured components)
- **Measured_as field**: Determines chemical basis
  - 'COD': kg/m³ on COD basis
  - 'S': kg/m³ on sulfur (element) basis
  - 'Fe', 'P', 'N': kg/m³ on element basis
  - 'K', 'Mg', 'Ca', 'Na', 'Cl', 'Al': kg/m³ on element basis

### Thermodynamic Units
- **Ka values**: Molar (mol/L)
- **Temperature**: Kelvin (K)
- **Gas constant R**: 8.314 J/(mol·K)

### PCM Solver Internals
- **Unit conversion**: `mass2mol_conversion(cmps)` → converts kg/m³ to mol/L
- **Ionic activity**: Molar concentrations (mol/L) × activity coefficient (placeholder: γ=1)
- **Saturation index**: Dimensionless ratio IAP/Ksp

---

## 10. CRITICAL IMPLEMENTATION NOTES FOR CODEX

### pH and Equilibrium
- PCM solver finds pH from electroneutrality (charge balance)
- Uses Brent's method (scipy.optimize.brenth) for robustness
- Temperature corrections via Van't Hoff for all Ka values
- No activity coefficient model yet (Davies/Pitzer coming)

### Mineral Equilibrium (Future Work)
- Current: Saturation index framework only (SI = 1.0 placeholder)
- Needed: IAP calculation from speciated ions + precipitation kinetics
- Ksp values must be temperature-dependent (Van't Hoff)
- Mineral stoichiometry already in _madm1.tsv matrix

### Gas Transfer (H2S)
- calc_biogas() function handles H2S speciation
- Uses temperature-corrected Ka_h2s (matches PCM)
- Returns dissolved H2S in kmol/m³ for gas transfer calculation
- Proper units critical: not COD-basis but molar sulfur basis

### Biomass Decay and Nutrient Cycling
- All decay processes yield inerts (S_I, X_I) + nutrients (S_IN, S_IP)
- P content: ~0.02 kg P / kg biomass COD
- N content: depends on component (typically 0.08-0.11 kg N / kg COD)
- i_NOD flags set to None for COD surrogates (prevents double-counting N)

---

## 11. TESTING AND VALIDATION RESOURCES

### Available Test Fixtures
- `.codex/AGENTS.md`: Complete Codex prompt with all 62 state descriptions
- `data/_madm1.tsv`: Stoichiometry matrix (48 rows = process rate equations)
- Tests verify:
  - 63 total components created
  - 62 state variables (plus H2O)
  - 38 biological + 8 iron P-removal + 13 mineral + 4 gas transfer processes
  - Dynamic component indexing (future-proof)

### Known Non-Determinism
- Catastrophic failure case: solver finds different local minima
- Expected: TAN > 10,000 mg-N/L (normal ~40), biomass < 10 mg/L, severe inhibition
- Do NOT expect exact reproducibility of specific failure values

---

## Summary Table: Component Overview

| Category | Count | Range | Description |
|----------|-------|-------|-------------|
| **Soluble organic** | 8 | 0-7 | S_su through S_h2 |
| **Soluble inorganic** | 5 | 8-12 | S_ch4, S_IC, S_IN, S_IP, S_I |
| **Particulate substrate** | 3 | 13-15 | X_ch, X_pr, X_li |
| **ADM1 Biomass** | 7 | 16-22 | X_su through X_h2 |
| **Particulate inerts** | 1 | 23 | X_I |
| **EBPR** | 3 | 24-26 | X_PHA, X_PP, X_PAO |
| **Metal cations** | 6 | 27-28,45-46,60-61 | K⁺, Mg²⁺, Ca²⁺, Fe²⁺, Fe³⁺, Al³⁺, Na⁺, Cl⁻ |
| **Sulfur species** | 7 | 29-35 | SO4²⁻, H2S, S⁰, 4 SRB types |
| **Iron extension** | 7 | 36-44 | Fe³⁺, Fe²⁺, 7 HFO variants |
| **Minerals** | 13 | 47-59 | 6 Ca-P + 4 Mg + 3 Fe/Al |
| **Water** | 1 | 62 | H2O (not state variable) |
| **TOTAL** | **63** | 0-62 | **62 state variables + H2O** |

---

Generated: 2025-10-27
