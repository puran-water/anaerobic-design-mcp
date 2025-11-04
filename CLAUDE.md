# AI Agent Instructions - Anaerobic Digester Design Workflow

## MCP Tools Available

- **anaerobic-design MCP**: Main server (basis of design, sizing, simulation)
- **ADM1-State-Variable-Estimator MCP**: Codex server for mADM1 state generation (GPT-5)
- **heat-transfer-mcp**: Thermal analysis server (heat duty, tank heat loss, heat exchanger design)
- **aerobic-treatment-kb**: Semantic search through Metcalf & Eddy knowledge base

## Background Job Pattern (IMPORTANT)

**Four computationally-heavy tools run as background jobs:**
- `heuristic_sizing_ad` - Digester sizing with mixing/thermal analysis
- `simulate_ad_system_tool` - QSDsan ADM1+sulfur simulation (2-5 minutes)
- `validate_adm1_state` - Bulk composite validation
- `compute_bulk_composites` - COD/TSS/VSS/TKN/TP calculation

**These tools return immediately** (< 1 second) with a `job_id`. Use job management tools to monitor:

```python
# Tool returns job_id immediately
result = mcp__anaerobic-design__heuristic_sizing_ad(...)
job_id = result["job_id"]

# Check status
mcp__anaerobic-design__get_job_status(job_id=job_id)
# Returns: {"status": "running", "elapsed_time_seconds": 15.2, ...}

# Get results when completed
mcp__anaerobic-design__get_job_results(job_id=job_id)
# Returns: {"status": "completed", "results": {...}, ...}

# List all jobs
mcp__anaerobic-design__list_jobs(status_filter="running", limit=10)

# Terminate a running job (if needed)
mcp__anaerobic-design__terminate_job(job_id=job_id)

# Get time series data separately (excluded from get_job_results)
mcp__anaerobic-design__get_timeseries_data(job_id=job_id)
```

**Job Statuses:**
- `running` - Job is executing in background subprocess
- `completed` - Job finished successfully, results available
- `failed` - Job encountered error (check stderr.log in results)

**Important:** DO NOT wait for heavy tools to return results. Always use the Background Job Pattern with `get_job_status()` and `get_job_results()`.

**Token Efficiency:**
- `get_job_results()` automatically excludes time_series data (~22K tokens) to stay under MCP's 25K token limit
- Use `get_timeseries_data(job_id)` only if you specifically need time series for plotting/analysis
- Large time series may still exceed limits - if so, read directly from `jobs/{job_id}/simulation_results.json`

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

### Step 4: Size (Background Job)

**IMPORTANT:** This tool runs as a background job. It returns job_id immediately.

```python
# Start sizing job
result = mcp__anaerobic-design__heuristic_sizing_ad(
    use_current_basis=True,
    target_srt_days=20,
    # Tank configuration
    tank_material="concrete",  # or "steel_bolted"
    height_to_diameter_ratio=1.2,
    # Mixing configuration
    mixing_type="mechanical",  # "pumped", "mechanical", or "hybrid"
    mixing_power_target_w_m3=7.0,  # W/m³ (default for mesophilic)
    impeller_type="pitched_blade_turbine",  # "rushton_turbine", "marine_propeller"
    pumped_recirculation_turnovers_per_hour=3.0,
    # Eductor/jet mixer configuration (for pumped mixing only)
    mixing_mode="simple",  # "simple" or "eductor" (default: "simple")
    entrainment_ratio=5.0,  # Total flow : motive flow ratio (for eductor mode)
    use_eductor_physics=True,  # Use fluids.jet_pump model (default: True)
    # Biogas handling
    biogas_application="storage",  # "direct_utilization", "upgrading"
    biogas_discharge_pressure_kpa=25.0,
    # Thermal analysis
    calculate_thermal_load=True,
    feedstock_inlet_temp_c=10.0,
    insulation_R_value_si=1.76  # m²K/W (SI units)
)

job_id = result["job_id"]  # Extract job ID

# Monitor progress
mcp__anaerobic-design__get_job_status(job_id=job_id)

# Retrieve results when completed
sizing_results = mcp__anaerobic-design__get_job_results(job_id=job_id)
```

**Eductor vs. Simple Pumped Mixing:**
- **Simple pumped**: Pump flow = recirculation flow (e.g., 3000 m³/h for 3 turnovers/h on 1000 m³ tank)
- **Eductor mode**: Pump flow = recirculation flow / entrainment_ratio (e.g., 600 m³/h motive flow creates 3000 m³/h total educted flow)
  - Uses high-velocity nozzle (15-30 m/s) to entrain additional liquid
  - Higher pump TDH (includes velocity head: v²/2g)
  - CRITICAL: Prevents 5× pump oversizing error (pump sized for motive flow, NOT total flow)
  - Physics-based modeling via `fluids.jet_pump.liquid_jet_pump()`

**Sizing Output includes:**
- Tank dimensions (diameter, height, volume)
- Mixing system details (power, impeller speed, Reynolds number)
- Biogas blower preliminary sizing
- **Thermal analysis request structure** (for use with heat-transfer-mcp)

### Step 4a: Thermal Analysis (OPTIONAL)

Use heat-transfer-mcp tools to perform detailed thermal calculations based on the heuristic sizing output.

**Calculate Feedstock Heating Load:**
```python
mcp__heat-transfer-mcp__calculate_heat_duty(
    calculation_method="sensible_heat",
    fluid_name="water",  # or appropriate feedstock fluid
    flow_rate=11.57,  # kg/s (from Q_m3d / 86400 * density)
    inlet_temp=283.15,  # K (10°C)
    outlet_temp=308.15,  # K (35°C)
    fluid_pressure=101325.0  # Pa
)
```

**Calculate Tank Heat Loss:**
```python
mcp__heat-transfer-mcp__tank_heat_loss(
    geometry="vertical_cylinder_tank",
    dimensions={"diameter": 23.13, "height": 27.76},  # m (from sizing)
    contents_temperature=308.15,  # K (35°C)
    fluid_name_internal="water",
    fluid_name_external="air",
    # Headspace modeling (for digesters with biogas space)
    headspace_height_m=2.0,  # m (gas space above liquid)
    headspace_fluid="biogas",
    # Insulation specification
    insulation_R_value_si=1.76,  # m²K/W (from sizing)
    assumed_insulation_k_w_mk=0.035,  # W/m·K (typical foam insulation)
    # Ambient conditions (direct specification)
    ambient_air_temperature=263.15,  # K (-10°C design condition)
    wind_speed=5.0,  # m/s
    # OR use weather data (percentile-based design)
    # latitude=40.7128, longitude=-74.0060,  # NYC
    # start_date="2020-01-01", end_date="2024-12-31",
    # design_percentile=0.99,  # 99th percentile cold (1% exceedance)
    # time_resolution="daily",
    # Surface properties
    surface_emissivity=0.85,
    # Ground contact (auto-enabled for vertical tanks)
    include_ground_contact=True,
    average_external_air_temperature=283.15  # K (10°C annual average)
)
```

**Size Heat Exchanger (for feedstock pre-heating):**
```python
mcp__heat-transfer-mcp__heat_exchanger_design(
    # Process heating
    process_fluid="water",
    process_mass_flow_kg_s=11.57,  # kg/s
    process_inlet_temp_K=283.15,  # K (10°C)
    process_target_temp_K=308.15,  # K (35°C)
    # Heating medium (hot water from biogas CHP)
    heating_fluid="hot_water",
    heating_inlet_temp_K=363.15,  # K (90°C)
    heating_outlet_temp_K=333.15,  # K (60°C)
    # Heat exchanger configuration
    overall_U_W_m2K=1000.0,  # W/m²K (typical for plate HX)
    hx_type="shell_tube",  # "plate", "coil", "double_pipe"
    flow_arrangement="counterflow",
    # Optional: include tank heat loss in total duty
    include_tank_loss=True,
    tank_params={
        "geometry": "vertical_cylinder_tank",
        "dimensions": {"diameter": 23.13, "height": 27.76},
        "contents_temperature": 308.15,
        "insulation_R_value_si": 1.76,
        "ambient_air_temperature": 263.15,
        "wind_speed": 5.0
    },
    estimate_physical=True  # Get shell/tube dimensions
)
```

**Key Thermal Outputs:**
- Feedstock heating: Q [kW], required heat input to raise inlet to digester temp
- Tank heat loss: Q [kW], continuous heat loss through walls/roof/floor
- Heat exchanger: Area [m²], shell/tube dimensions, LMTD [K]
- **Total heat load**: Feedstock + Tank loss [kW]

### Step 5: Simulate (Background Job - REQUIRED)

**IMPORTANT:** This tool runs as a background job and can take 2-5 minutes. It returns job_id immediately.

```python
# Start simulation job
result = mcp__anaerobic-design__simulate_ad_system_tool(
    use_current_state=True,
    validate_hrt=True,
    hrt_variation=0.2,
    fecl3_dose_mg_L=0,    # Optional: FeCl3 dosing
    naoh_dose_mg_L=0,     # Optional: NaOH dosing
    na2co3_dose_mg_L=0    # Optional: Na2CO3 dosing
)

job_id = result["job_id"]  # Extract job ID

# Monitor progress (check every 30-60 seconds)
mcp__anaerobic-design__get_job_status(job_id=job_id)
# Returns: {"status": "running", "elapsed_time_seconds": 45, ...}

# Retrieve results when completed (status = "completed")
sim_results = mcp__anaerobic-design__get_job_results(job_id=job_id)
```

**Note:** The simulation automatically creates files with enhanced inoculum (6× methanogen boost) for stable startup.

**IMPORTANT - Time Series Data:**
- `get_job_results()` automatically **excludes time_series data** to avoid MCP token limits
- The full results include time_series_available: true flag
- To retrieve time series data (if needed for plotting/analysis):
  ```python
  # Time series data is large (~22K+ tokens), so it's excluded by default
  # Use this separate tool only if you specifically need it:
  mcp__anaerobic-design__get_timeseries_data(job_id=job_id)

  # Note: Large time series may still exceed token limits
  # In that case, read directly from file:
  # jobs/{job_id}/simulation_results.json
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

- Focus on directional improvements in simulation outputs, not exact values
- TAN accumulation, biomass washout indicate failure
- Simulation convergence may vary depending on initial conditions
