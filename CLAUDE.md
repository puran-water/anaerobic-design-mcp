# AI Agent Instructions - Anaerobic Digester Design Workflow

## MCP Tools Available

- **anaerobic-design MCP**: Main server (basis of design, sizing, simulation)
- **ADM1-State-Variable-Estimator MCP**: Codex server for mADM1 state generation (GPT-5)

## Complete Workflow (DO NOT SKIP STEPS)

### Step 0: Reset
```python
mcp__anaerobic-design__reset_design()
```

### Step 1: Collect Parameters
```python
mcp__anaerobic-design__elicit_basis_of_design(
    parameter_group="all",
    current_values={
        "Q": 1000,           # m3/d
        "Temp": 35,          # °C
        "cod_mg_l": 50000,   # mg/L
        "tss_mg_l": 35000,   # mg/L
        "vss_mg_l": 28000,   # mg/L
        "tkn_mg_l": 2500,    # mg-N/L
        "tp_mg_l": 500,      # mg-P/L
        "pH": 7,
        "alkalinity_meq_l": 50
    }
)
```

### Step 2: Generate ADM1 State via Codex (CRITICAL - DO NOT SKIP)
```python
mcp__ADM1-State-Variable-Estimator__codex(
    prompt="Generate complete mADM1 (Modified ADM1) state variables...",
    cwd="/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp"
)
```

#### For Multi-Turn Codex Conversations (ONLY after ADM1-State-Variable-Estimator responds):
If you need to reply to the Codex agent, follow this procedure to find the conversation ID:

a. After making the initial codex call, retrieve the session ID from the Codex sessions directory
b. The sessions are stored in the MCP server project root: `.codex/sessions/YYYY/MM/DD/` (use today's date)
c. Find the most recent file by modification time:
   ```bash
   ls -lt .codex/sessions/YYYY/MM/DD/*.jsonl | head -1
   ```
d. Extract the session ID from the filename: The format is `rollout-YYYY-MM-DDTHH-MM-SS-[SESSION_ID].jsonl`
   - Example: `rollout-2025-09-10T12-35-31-670d90ae-4ff6-4a50-bcea-011d6ab64dbe.jsonl`
   - Session ID: `670d90ae-4ff6-4a50-bcea-011d6ab64dbe`
e. Verify it's the correct session by reading the file and checking for your initial prompt
f. Use codex-reply with parameter `conversationId` (NOT `session_id`) set to the extracted UUID:
   ```python
   mcp__ADM1-State-Variable-Estimator__codex-reply(
       conversationId="670d90ae-4ff6-4a50-bcea-011d6ab64dbe",
       prompt="Your follow-up message..."
   )
   ```

Then load:
```python
mcp__anaerobic-design__load_adm1_state(file_path="./adm1_state.json")
```

### Step 3: Validate
```bash
python utils/validate_cli.py validate \
    --adm1-state adm1_state.json \
    --user-params '{"cod_mg_l": 50000, "tss_mg_l": 35000, "tkn_mg_l": 2500}' \
    --tolerance 0.15
```

### Step 4: Size
```python
mcp__anaerobic-design__heuristic_sizing_ad(
    use_current_basis=True,
    target_srt_days=20
)
```

### Step 5: Simulate (REQUIRED)

**IMPORTANT:**
- Do NOT use a timeout parameter - simulations can take several minutes to reach steady state
- Do NOT use backslash line breaks in the command - run as a single line or the command will fail

```bash
/mnt/c/Users/hvksh/mcp-servers/venv312/Scripts/python.exe utils/simulate_cli.py --basis simulation_basis.json --adm1-state adm1_state.json --heuristic-config simulation_heuristic_config.json --hrt-variation 0.2
```

**Optional Chemical Dosing Parameters:**

Add chemical supplementation to the influent (specified as compound concentrations in mg/L):

```bash
# NaOH for alkalinity supplementation (mg/L as NaOH compound)
--naoh-dose 2840

# Na2CO3 for alkalinity supplementation (mg/L as Na2CO3 compound)
--na2co3-dose 5000

# FeCl3 for sulfide/phosphate removal (mg/L as FeCl3 compound)
--fecl3-dose 100

# Dynamic pH control (overrides fixed dosing)
--pH-ctrl 7.0
```

**Notes:**
- Dosages are specified as the **compound** (NaOH, Na2CO3, FeCl3), not as elements
- The simulation converts to elemental species (S_Na, S_Fe) automatically
- NaOH: 1 mg/L ≈ 0.025 meq/L alkalinity (MW = 40 g/mol)
- Na2CO3: 1 mg/L ≈ 0.019 meq/L alkalinity (MW = 106 g/mol)

Output Files:
- `simulation_results.json` - Full detailed results (159 KB)
- `simulation_performance.json` - Performance metrics (2 KB)
- `simulation_inhibition.json` - Inhibition analysis (2 KB)
- `simulation_precipitation.json` - Precipitation analysis (3 KB)

### Step 6: Present Results to User (REQUIRED)

After simulation completes, present results using the **token-efficient method**:

**MOST EFFICIENT:** Read only the small summary JSON files (total ~7 KB) instead of the full results (159 KB):

```python
import json

# Read compact summary files (saves 95% tokens)
with open('simulation_performance.json') as f:
    perf = json.load(f)
with open('simulation_inhibition.json') as f:
    inhib = json.load(f)
with open('simulation_precipitation.json') as f:
    precip = json.load(f)
```

**Present 3 tables to the user:**

1. **Performance Metrics Table:**
   - Influent/effluent characteristics (pH, COD, VSS, VFA, alkalinity)
   - Biogas production (total, CH₄, CO₂, H₂, H₂S)
   - **Specific methane yield** (m³/kg COD removed, L/kg COD removed)
   - **Net biomass yield** (kg VSS/kg COD removed, kg TSS/kg COD removed)
   - COD removal efficiency
   - Process stability (VFA/Alk ratios)

2. **Inhibition Metrics Table:**
   - Overall methanogen health (%)
   - Primary/secondary limiting factors
   - pH inhibition (acetoclastic, hydrogenotrophic)
   - Ammonia inhibition
   - Hydrogen inhibition (propionate, LCFA)
   - H₂S inhibition

3. **Precipitation Metrics Table:**
   - Total precipitation rate (kg/d)
   - Phosphorus/sulfur precipitated
   - Major minerals (struvite, K-struvite, HAP, calcite, FeS)
   - Formation rates and concentrations

4. **Overall Assessment:**
   - Critical issues (pH < 6.0, VFA > 1000 mg/L, methanogen health < 50%)
   - Warnings (low CH₄%, high H₂%)
   - Success criteria

**Token-Efficient Parsing Method:**

Use the dedicated parser script to read only the 7 KB summary files (not the 159 KB full results):

```bash
# Default usage (reads simulation_*.json from current directory)
python3 utils/parse_simulation_results.py

# Or specify custom files
python3 utils/parse_simulation_results.py \
    simulation_performance.json \
    simulation_inhibition.json \
    simulation_precipitation.json
```

This displays three formatted tables:
- **Table 1:** Performance metrics (influent/effluent, biogas, **specific methane yield**, **net biomass yield**)
- **Table 2:** Inhibition metrics (methanogen health, pH/NH3/H2/H2S inhibition)
- **Table 3:** Precipitation metrics (mineral formation rates and concentrations)
- **Overall Assessment:** Critical issues, warnings, and key findings summary

**Token Savings:** Reads 7 KB instead of 159 KB = **95% reduction in tokens**

## Critical Units (mADM1 vs QSDsan)

**mADM1 State Variables (in JSON files)**:
- All components in **kg/m³** (COD units)
- Biomass (X_*): kg COD/m³ (NOT kg VSS/m³)
- Convert to VSS: divide by 1.42

**QSDsan Time Series (`stream.scope.record`)**:
- All concentrations in **mg/L** (NOT kg/m³)
- NO conversion needed for time series data
- **DO NOT** multiply by 1000

## Key Files

- `utils/inoculum_generator.py`: Scales biomass + alkalinity for CSTR startup
- `utils/qsdsan_madm1.py`: mADM1 process model (62 components, P/S/Fe extensions)
- `utils/simulate_cli.py`: QSDsan simulation wrapper
- `utils/validate_cli.py`: Bulk composite validation (COD, TSS, pH, ion balance)

## Testing Notes

- `test_regression_catastrophe.py`: Non-deterministic (solver convergence varies)
- Focus on directional improvements, not exact values
- TAN accumulation, biomass washout indicate failure
