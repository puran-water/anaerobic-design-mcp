# mADM1 Quick Reference Card

## Essential Facts

**Total Components:** 63 (62 state variables + H2O)
**File:** `/utils/qsdsan_madm1.py`
**Function:** `create_madm1_cmps()` and `ModifiedADM1` class

---

## 62 State Variables Breakdown

```
Core ADM1 (27):
  Soluble organic: S_su, S_aa, S_fa, S_va, S_bu, S_pro, S_ac, S_h2 (0-7)
  Soluble inorganic: S_ch4, S_IC, S_IN, S_IP, S_I (8-12)
  Particulates: X_ch, X_pr, X_li, X_su, X_aa, X_fa, X_c4, X_pro, X_ac, X_h2, X_I (13-23)

EBPR (3):
  X_PHA, X_PP, X_PAO (24-26)

Metals (6):
  S_K(27), S_Mg(28), S_Ca(45), S_Al(46), S_Na(60), S_Cl(61)

Sulfur (7):
  S_SO4(29), S_IS(30), S_S0(35), X_hSRB(31), X_aSRB(32), X_pSRB(33), X_c4SRB(34)

Iron (7):
  S_Fe3(36), S_Fe2(37), X_HFO_H(38), X_HFO_L(39), X_HFO_old(40), 
  X_HFO_HP(41), X_HFO_LP(42), X_HFO_HP_old(43), X_HFO_LP_old(44) → 9 total

Minerals (13):
  Ca-P: X_CCM(47), X_ACC(48), X_ACP(49), X_HAP(50), X_DCPD(51), X_OCP(52)
  Mg: X_struv(53), X_newb(54), X_magn(55), X_kstruv(56)
  Fe/Al: X_FeS(57), X_Fe3PO42(58), X_AlPO4(59)

Water (1):
  H2O(62)
```

---

## 13 Mineral Precipitates

| Index | ID | Chemical | Formula | Type |
|-------|----|----|--------|------|
| 47 | X_CCM | Calcite | CaCO3 | Ca-CO3 |
| 48 | X_ACC | Aragonite | CaCO3 | Ca-CO3 |
| 49 | X_ACP | Amorph Ca-P | Ca3(PO4)2 | Ca-P |
| 50 | X_HAP | Hydroxylapatite | Ca5(PO4)3OH | Ca-P |
| 51 | X_DCPD | Dicalc phosphate | CaHPO4·2H2O | Ca-P |
| 52 | X_OCP | Octacalc phosphate | Ca4H(PO4)3 | Ca-P |
| 53 | X_struv | Struvite | MgNH4PO4·6H2O | Mg-P |
| 54 | X_newb | Newberyite | MgHPO4·3H2O | Mg-P |
| 55 | X_magn | Magnesite | MgCO3 | Mg-CO3 |
| 56 | X_kstruv | K-struvite | MgKPO4·6H2O | Mg-P |
| 57 | X_FeS | Iron sulfide | FeS | Fe-S |
| 58 | X_Fe3PO42 | Ferrous phosphate | Fe3(PO4)2 | Fe-P |
| 59 | X_AlPO4 | Aluminum phosphate | AlPO4 | Al-P |

---

## 7 HFO Variants (Iron Extension)

**Two base types differ by active site factor (ASF):**
- X_HFO_H: High affinity, ASF=1.2, stronger but fewer P sites
- X_HFO_L: Low affinity, ASF=0.31, weaker but more P sites

**Three forms each:**
1. Base form: X_HFO_H, X_HFO_L (free P binding sites)
2. P-loaded: X_HFO_HP, X_HFO_LP (P occupies active sites)
3. Aged: X_HFO_H_old, X_HFO_L_old (deactivated, less reactive)

**Total HFO in state vector:** 7 components (indices 38-44)

---

## PCM Solver Key Info

**Location:** `utils/qsdsan_madm1.py:432-623`

**Inputs:**
- state_arr: 62+ component concentrations (kg/m³)
- params: dict with Ka_base, Ka_dH, T_base, T_op, components

**Returns:**
- pH: computed from charge balance
- nh3: ammonia concentration (kmol-N/m³)
- co2: CO2 concentration (kmol-C/m³)
- activities: ionic activities for precipitation (placeholder)

**Solver Method:**
- Root-finding: scipy.optimize.brenth (Brent's method)
- Equation: Electroneutrality (charge balance)
- Temperature correction: Van't Hoff for Ka values

**Key Equation:**
```
Cations: H+ + NH4+ + 2*Mg2+ + 2*Ca2+ + 2*Fe2+ + 3*Fe3+ + 3*Al3+ + Na+ + K+
= 
Anions: OH- + HCO3- + CO32- + Ac- + Pro- + Bu- + Va- + HPO42- + 2*SO42- + HS- + Cl-
```

---

## Critical Unit Info

**State variable units:** kg/m³
**Molar conversion:** `mass2mol_conversion(cmps)` → converts to mol/L
**Gas constant:** R = 8.314 J/(mol·K)

**Measured_as field determines chemical basis:**
- 'COD': kg/m³ on COD basis (most organics)
- 'S': kg/m³ on sulfur basis (S_SO4, S_IS, S_S0)
- 'Fe', 'P', 'N': kg/m³ on element basis
- 'K', 'Mg', 'Ca', 'Na', 'Cl', 'Al': kg/m³ on element basis

---

## Component Access in Code

```python
from utils.qsdsan_madm1 import create_madm1_cmps, ModifiedADM1

cmps = create_madm1_cmps()  # Get component set

# Access by name
idx_ac = cmps.index('S_ac')
idx_hap = cmps.index('X_HAP')

# Get properties
MW = cmps.chem_MW[idx]
i_mass = cmps.i_mass[idx]
i_COD = cmps.i_COD[idx]
```

---

## Process Count

**Total processes:** 63
- 38 biological (ADM1 + SRB)
- 8 iron-phosphorus coupling
- 13 mineral precipitation
- 4 gas transfer (CH4, CO2, H2, H2S)

---

## File Locations

| What | Where |
|------|-------|
| Component definitions | `utils/qsdsan_madm1.py:45-280` |
| PCM solver | `utils/qsdsan_madm1.py:432-623` |
| HFO chemistry | `utils/qsdsan_madm1.py:176-196` |
| Minerals | `utils/qsdsan_madm1.py:197-209` |
| Stoichiometry matrix | `data/_madm1.tsv` |
| Reactor ODE | `utils/qsdsan_reactor_madm1.py` |
| Simulation | `utils/qsdsan_simulation_sulfur.py` |
| Codex prompt | `.codex/AGENTS.md` |

---

## For Codex Integration

**Key functions to know:**

1. `create_madm1_cmps(ASF_L=0.31, ASF_H=1.2)` → Returns mADM1 component set
2. `ModifiedADM1(components=cmps)` → Creates process model
3. `pcm(state_arr, params)` → Computes pH from charge balance
4. `calc_biogas(state_arr, params, pH)` → H2S speciation

**Most important:** All 62 components are in the state vector returned by pcm(). Use dynamic indexing: `cmps.index('component_id')` not hardcoded values.

---

Generated: 2025-10-27
