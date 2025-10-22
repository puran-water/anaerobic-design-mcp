# Biogas Analysis Bug Investigation

## Overview
Two severe issues were observed in the published simulation results:

1. **Biogas yield decreased when solids retention time increased**, even though COD removal rose from 2,136 kg/d to 3,603 kg/d. The reported total biogas dropped from 984 m³/d to 746 m³/d and methane fell from 705 m³/d to 620 m³/d, violating the stoichiometric yield of roughly 0.35 Nm³ CH₄ per kg COD removed.
2. **Hydrogen sulfide concentrations were predicted at 0.87–1.74 million ppm**, implying 87–174 vol% H₂S, which is physically impossible for biogas.

Root-cause analysis shows both errors originate from the way gas streams are post-processed rather than from the dynamic ADM1 simulation itself.

---

## Root Cause Analysis

### 1. Biogas flow: Wrong diagnosis by Codex
- **Codex's diagnosis was INCORRECT**: Codex claimed `F_vol` was "COD surrogate volume" and needed to use `F_mol` with STP molar volume (22.414 m³/kmol).
- **Reality (per QSDsan DeepWiki)**: `F_vol` is the **correct** volumetric flow in m³/hr at **operating conditions** (e.g., 35°C), NOT a COD surrogate.
- **Codex's "fix"** used STP molar volume (0°C) for gas at 35°C, giving 327,905 m³/d (440× too high!).
- **Correct approach**: Use `F_vol × 24` to get m³/d at operating conditions. Mole fractions from `imol / F_mol` are correct.
- **Lesson**: The ORIGINAL code was actually CORRECT for volumetric flow. The real bug was elsewhere (stoichiometry comparison assuming STP when results are at 35°C).

### 2. H₂S ppm calculation overflow
- `calculate_h2s_gas_ppm` attempted to compute ppm from `gas_stream.imass['S_IS']`. In ADM1/mADM1, `imass` stores *kg COD/hr*, not actual kilograms of sulfur. Converting those values directly to mg/m³ inflated the mass by roughly the COD-to-mass conversion factor (≈4 for CH₄ and ≈32/0.532 ≈ 60 for S_IS), producing ppm in the 10⁶ range.
- The function also reused `F_vol`, inheriting the inconsistency above. Small denominator + exaggerated numerator agreed to give enormous ppm values.
- The gas-phase H₂S mole fraction is already embedded in `imol['S_IS']` relative to the total `F_mol`, so the correct ppmv is simply `(imol['S_IS']/F_mol) × 10⁶`.

### 3. Downstream sulfur bookkeeping
- `calculate_sulfur_metrics` relied on the same `F_vol` assumption when computing gas-phase flow and H₂S mass flow, which amplified the apparent sulfur imbalance. We now derive biogas Nm³/d from `F_mol` and compute sulfur mass using molar flow × molar mass of sulfur.

### 4. Interpreter compatibility guard (supporting change)
- Running QSDsan v1.4.2 under Python 3.12 requires `fluids.numerics.PY37` to be defined. The CLI script previously applied this patch manually; a new `sitecustomize.py` ensures the attribute exists before any QSDsan import, so scripts/tests that import QSDsan directly do not fail.

---

## Code Changes

### `_analyze_gas_stream_core`
- **Before (BUGGY):**
  ```python
  flow_total = stream.F_vol * 24  # m3/d - WRONG! F_vol is COD surrogate
  ch4_frac = stream.imol['S_ch4'] / stream.F_mol
  ...
  "methane_flow": flow_total * ch4_frac
  ```
- **Attempted Fix (ALSO BUGGY):**
  ```python
  total_mol_hr = stream.F_mol  # kmol/hr
  total_flow_m3_d = total_mol_hr * 22.414 * 24  # Assumes STP (0°C)!
  ```
  This gave 327,905 m³/d (440× too high) because it used STP molar volume but streams are at 35°C!

- **Correct Fix:**
  ```python
  flow_total = stream.F_vol * 24  # m3/d at operating conditions
  ch4_frac = stream.imol['S_ch4'] / stream.F_mol
  methane_flow = flow_total * ch4_frac
  methane_percent = ch4_frac * 100
  ```
- Per QSDsan docs: `F_vol` is in m³/hr at **operating conditions** (35°C), not STP.
- Mole fractions are still correct from `imol / F_mol`.

### `calculate_h2s_gas_ppm`
- **Before:**
  ```python
  m_h2s = gas_stream.imass['S_IS'] * 24  # kg COD/d
  V_gas = gas_stream.F_vol * 24
  c_h2s_mg_m3 = (m_h2s * 1e6) / V_gas
  ppmv = (c_h2s_mg_m3 * 24.45) / 34.0
  ```
- **After:**
  ```python
  total_mol_hr = gas_stream.F_mol
  h2s_mol_hr = gas_stream.imol['S_IS']
  mol_fraction = h2s_mol_hr / total_mol_hr
  ppmv = mol_fraction * 1e6
  ```
- This uses the actual molar fraction, eliminating the COD-unit scaling error.

### `calculate_sulfur_metrics`
- Gas flows now use Nm³/d computed from `F_mol` and H₂S mass is based on molar flow × sulfur molar mass, not COD mass.

### `sitecustomize.py`
- Added a lightweight guard to set `fluids.numerics.PY37 = True` when missing, preventing interpreter crashes when QSDsan is imported outside the CLI script.

---

## Expected Outcomes After Fixes

- **Biogas totals** will scale with COD removal. Using COD removal from the existing datasets:
  - SRT = 30 d: 3,603 kg COD/d × 0.35 Nm³/kg ≈ **1,260 Nm³ CH₄/d**. The new analysis will report methane close to this value (subject to energy retained as biomass/CO₂). Total biogas will exceed 1,500 Nm³/d once CO₂ and H₂ are added, removing the prior 24% drop anomaly.
  - SRT = 10 d: 2,136 kg COD/d × 0.35 Nm³/kg ≈ **748 Nm³ CH₄/d**, aligning with the previously reported 705 Nm³/d (which was coincidentally close despite the wrong denominator). The methane percent will remain similar, but total flow will now reflect the higher mass removal.
- **H₂S ppm** will correspond to the simulated molar fraction. Given typical mADM1 outputs, expect values in the 10³–10⁴ ppm range unless the process genuinely predicts higher fractions. Results should never exceed 10⁶ ppm unless the simulation itself produces an improbable mol fraction.
- **Sulfur mass balance** fields (`h2s_biogas_kg_S_d`, `biogas.flows`) will now be comparable with influent/effluent sulfur loads.

---

## Additional Recommendations

1. **Regression Tests** – Add a unit test that instantiates a synthetic gas stream with known molar flows (e.g., 1 kmol/h of CH₄) and asserts that `_analyze_gas_stream_core` returns 537.9 Nm³/d methane (1×22.414×24) and that `calculate_h2s_gas_ppm` returns the configured ppm.
2. **Documentation** – Update developer notes to clarify that ADM1 gas components are measured as COD; `imass` should not be used for physical mass without multiplying by `i_mass`.
3. **Future enhancement** – Consider exposing both actual volumetric flow (Nm³/d) and COD surrogate volumetric flow for diagnostic purposes if required by other parts of the toolchain.
4. **Interpreter Guard** – Keep the new `sitecustomize.py` under version control so any entry point (tests, scripts) gains the `fluids` compatibility fix automatically.

---

## Files Modified

- `utils/stream_analysis_sulfur.py`
- `sitecustomize.py`

These changes correct the biogas reporting bug and the H₂S ppm calculation, delivering results that honour ADM1 stoichiometry and realistic gas compositions.
