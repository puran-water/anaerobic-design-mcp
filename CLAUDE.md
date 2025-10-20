# Claude Code System Prompt - Anaerobic Digester Design MCP

## CRITICAL INSTRUCTIONS - MUST FOLLOW

### PAUSE POINT REQUIREMENTS
**YOU MUST PAUSE before testing MCP tools after ANY of the following:**
1. Refactoring or modifying MCP tool implementations
2. Changing tool function signatures or parameters
3. Modifying validation logic or state handling
4. Implementing fixes that affect tool behavior
5. Making changes to the MCP server code

**How to PAUSE correctly:**
```python
print("\n" + "="*80)
print("PAUSE POINT - MCP Tool Testing")
print("="*80)
print("Changes made:")
print("  - [List each change]")
print("\nReady to test MCP tool: [tool_name]")
print("Press Enter to continue...")
input()  # WAIT for user confirmation
```

**NEVER skip the pause - the user may need to:**
- Restart the MCP server
- Review changes before testing
- Prepare monitoring/logging
- Ensure the environment is ready

## MCP Servers Available

Two MCP servers work together in this project:
1. **anaerobic-design**: Main server with tools for basis of design, sizing, simulation
2. **ADM1-State-Variable-Estimator**: Codex-based server for mADM1 state generation (GPT-5, high reasoning effort)

## COMPLETE WORKFLOW - MUST FOLLOW ALL STEPS

**CRITICAL**: When testing the full anaerobic digester design workflow, you MUST follow ALL steps in order. Do NOT skip Step 2 (Codex ADM1 generation) - this is the core innovation of the system.

### Step 0: Reset Design State
```python
mcp__anaerobic-design__reset_design()
```

### Step 1: Collect Basis of Design Parameters
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

### Step 2: Generate ADM1 State Using Codex MCP ⚠️ CRITICAL STEP

**This is the most important step - do NOT skip it!**

Call the Codex MCP server to generate all 62 mADM1 state variables from feedstock description:

```python
mcp__ADM1-State-Variable-Estimator__codex(
    prompt=f"""
Generate complete mADM1 (Modified ADM1) state variables for the following feedstock.

## Feedstock Description
Type: High-strength municipal wastewater sludge
Source: Primary and waste activated sludge blend
Characteristics: Thick, particle-rich suspension

## Measured Bulk Parameters
- Flow rate: 1000 m³/d
- COD: 50,000 mg/L
- TSS: 35,000 mg/L
- VSS: 28,000 mg/L (VSS/TSS = 0.80)
- TKN: 2,500 mg-N/L
- TP: 500 mg-P/L
- pH: 7.0
- Alkalinity: 50 meq/L
- Temperature: 35°C

## Required Output

Generate a complete JSON file with ALL 62 mADM1 state variables (indexes 0-61) as specified in your training.

Save the output to: ./adm1_state.json

Format as:
{{
  "S_su": value_in_kg_m3,
  "S_aa": value_in_kg_m3,
  ...all 62 components...
  "S_Cl": value_in_kg_m3
}}

Ensure the state vector:
1. Matches the measured bulk parameters (COD, TSS, VSS, TKN, TP)
2. Represents realistic high-strength sludge composition
3. Includes all P/S/Fe extension components
4. Has proper charge balance (cations vs anions)
""",
    cwd="/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp"
)
```

**After Codex completes**, the ADM1 state will be in `./adm1_state.json`. Load it:

```python
mcp__anaerobic-design__load_adm1_state(file_path="./adm1_state.json")
```

### Step 3: Validate ADM1 State

Run validation to ensure Codex-generated state matches targets:

```bash
python utils/validate_cli.py validate \
    --adm1-state adm1_state.json \
    --user-params '{"cod_mg_l": 50000, "tss_mg_l": 35000, "vss_mg_l": 28000, "tkn_mg_l": 2500, "tp_mg_l": 500, "ph": 7}' \
    --tolerance 0.15
```

### Step 4: Heuristic Sizing

```python
mcp__anaerobic-design__heuristic_sizing_ad(
    use_current_basis=True,
    target_srt_days=20
)
```

### Step 5: Run QSDsan Simulation ⚠️ REQUIRED

**CRITICAL**: The simulation MUST be run as part of the complete workflow test. This validates that the Codex-generated ADM1 state works correctly with QSDsan's mADM1 process model.

#### Option A: Using MCP Tool (Returns CLI Command)

```python
mcp__anaerobic-design__simulate_ad_system_tool(
    use_current_state=True,
    validate_hrt=True
)
```

**Note**: This MCP tool returns a CLI command that must be executed manually due to long execution time (50-150 seconds) and STDIO timeout issues.

#### Option B: Direct CLI Execution (Recommended)

Run the simulation directly via CLI:

```bash
/mnt/c/Users/hvksh/mcp-servers/venv312/Scripts/python.exe utils/simulate_cli.py \
    --basis simulation_basis.json \
    --adm1-state adm1_state.json \
    --heuristic-config simulation_heuristic_config.json \
    --hrt-variation 0.2
```

**What the simulation does**:
1. Loads QSDsan components (~18 seconds)
2. Creates mADM1 process model with production PCM solver
3. Builds flowsheet (AnMBR with digester + MBR)
4. Runs dynamic simulation (~50-150 seconds)
5. Analyzes results (biogas production, effluent quality, sulfur balance)
6. Saves results to `simulation_results.json`

**Expected outputs**:
- Methane production (m³/d, kg/d)
- Biogas composition (CH₄, CO₂, H₂S percentages)
- Effluent quality (COD, TSS, VSS, TKN, TP)
- Sulfur mass balance (influent SO₄ → effluent H₂S)
- Performance metrics (COD removal %, VSS destruction %)
- HRT validation results (if `--hrt-variation` specified)

**After simulation completes**:

```bash
# View results
cat simulation_results.json | jq '.'

# Or view specific metrics
cat simulation_results.json | jq '.performance_metrics'
cat simulation_results.json | jq '.biogas'
cat simulation_results.json | jq '.sulfur_analysis'
```

**Why this step is critical**:
1. Validates that Codex-generated state is physically realistic
2. Confirms mADM1 process model converges with the state
3. Verifies biogas production matches theoretical yields
4. Demonstrates complete end-to-end workflow
5. Provides actual design outputs (not just heuristics)

**DO NOT skip this step** - the simulation is the ultimate validation that the entire workflow (parameters → Codex ADM1 generation → sizing → simulation) works correctly.

## Why Step 2 (Codex Generation) is Critical

1. **Core Innovation**: The Codex MCP server uses the complete mADM1 specification in `.codex/AGENTS.md` to intelligently generate all 62 state variables
2. **Intelligent Estimation**: Goes beyond simple heuristics - uses feedstock characteristics to determine realistic distributions
3. **Complete Component Set**: Generates P/S/Fe extension components that simple tools cannot estimate
4. **Charge Balance**: Ensures ionic species are properly balanced
5. **Production-Ready**: Uses the same process that will be used in production systems

**DO NOT bypass this step by loading pre-existing JSON files** - that defeats the purpose of the workflow test.

## Regression Testing - Important Note

### test_regression_catastrophe.py Non-Determinism

The regression test in `tests/test_regression_catastrophe.py` is **NOT deterministic** due to solver convergence issues with the catastrophic failure case. Different runs may produce varying magnitudes of failure:

- **Observed TAN range**: 10,000 - 77,000 mg-N/L (both are severe failures, normal is ~40 mg-N/L)
- **pH range**: 4.0 - 7.0 (depending on convergence path)
- **VFA accumulation**: 6 - 47 kg/m³ (both indicate process failure)

#### What the test DOES reliably show:
1. **TAN accumulation bug** - Always shows ammonia accumulation (>10,000 mg-N/L vs normal 40 mg-N/L)
2. **Biomass washout bug** - Consistently shows TSS < 10 mg/L (complete biomass loss)
3. **Severe methanogenic inhibition** - I_nh3 < 0.1 (>90% inhibition)

#### How to use this test:
- Use it to ensure **directional improvement** - fixes should reduce TAN and increase biomass
- Do NOT expect exact reproducibility of specific values
- The xfail assertions are set conservatively (TAN > 50,000) but may need adjustment
- Focus on order-of-magnitude improvements rather than precise values

#### Why non-determinism occurs:
- Solver finds different local minima when the model is infeasible
- Sequential decomposition initialization varies
- MLSS constraints and other fixes alter the failure mode
- Numerical precision differences across environments