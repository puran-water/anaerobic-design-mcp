# Anaerobic Design MCP Server

Production-ready MCP (Model Context Protocol) server for anaerobic digester design using the complete mADM1 (Modified ADM1) process model with 63 components (62 state variables + H2O).

## Overview

This server provides an end-to-end workflow for designing anaerobic digesters treating high-strength wastewater, from feedstock characterization through dynamic simulation. It leverages QSDsan's production-grade mADM1 model with phosphorus/sulfur/iron extensions for comprehensive nutrient recovery and biogas production modeling.

**Status**: Production-Ready + Background Job Pattern (2025-11-22)

## Key Features

### Core Process Model
- **Complete mADM1 Model (63 Components)**: Full Modified ADM1 with P/S/Fe extensions
  - 27 core ADM1 components (sugars, amino acids, VFAs, biomass)
  - 3 EBPR components (X_PHA, X_PP, X_PAO)
  - 7 sulfur species (SO4, H2S, 4 SRB types, S0)
  - 9 iron species (Fe3+, Fe2+, 7 HFO variants)
  - 13 mineral precipitates (struvite, HAP, FeS, etc.)
  - 4 additional cations (K, Mg, Ca, Al)
  - 1 solvent (H2O as component index 62)

- **AI-Powered ADM1 State Generation**: Codex MCP server converts feedstock descriptions into complete 63-component states

- **Thermodynamically Rigorous pH Solver**: Production charge balance with all ionic species

- **Dynamic Simulation**: QSDsan's AnaerobicCSTR reactor with 4-component biogas tracking (H2, CH4, CO2, H2S)

### Enhanced Design Tools (Week 1-2 Implementation)
- **Mixing Module** (`utils/mixing_calculations.py`): Physics-based power calculations for mechanical and pumped mixing
  - Eductor/jet pump support with `fluids.jet_pump` integration (prevents 5× pump oversizing)
  - Non-Newtonian rheology corrections (Metzner-Otto method)
  - Multiple impeller types (pitched blade, Rushton, marine propeller)

- **Rheology Module** (`utils/rheology.py`): TSS-dependent viscosity for accurate mixing power
  - WEF MOP-8 validated correlations
  - Power-law parameters (Baudez et al. 2011)
  - Temperature corrections

- **Substrate-Aware Biomass Yield** (`utils/heuristic_sizing.py:80-267`): Complete ADM1 pathway analysis
  - Accounts for multi-step metabolism (not just first-step yields)
  - Cascading yields: substrate → intermediates → acetate/H₂ → CH₄
  - Substrate-specific yields: carbs (0.116), proteins (0.106), lipids (0.073-0.078) kg TSS/kg COD
  - Based on ADM1 stoichiometry and product split fractions
  - **Known Limitation**: Does not account for SRT-dependent endogenous decay (under investigation)

- **Thermal Integration**: Direct MCP access to heat-transfer-mcp server
  - Feedstock heating load calculations
  - Tank heat loss (insulated vessels, weather data integration)
  - Heat exchanger sizing (plate, shell-tube, coil)

- **Complete Workflow**: Parameters → ADM1 generation → Validation → **Sizing + Mixing + Thermal** → Simulation

## Quick Start

### Installation

```bash
# Clone repository
cd /path/to/mcp-servers/anaerobic-design-mcp

# Install dependencies (requires Python 3.10+)
pip install -r requirements.txt

# Install QSDsan
pip install qsdsan

# Add to Claude Desktop MCP configuration
# Edit: %APPDATA%/Claude/claude_desktop_config.json (Windows)
#   or: ~/Library/Application Support/Claude/claude_desktop_config.json (macOS)
```

**MCP Configuration**:

```json
{
  "mcpServers": {
    "anaerobic-design": {
      "command": "C:/path/to/venv/Scripts/python.exe",
      "args": [
        "-m",
        "server"
      ],
      "cwd": "C:/path/to/mcp-servers/anaerobic-design-mcp"
    }
  }
}
```

### Basic Usage

**Step 1: Reset and collect parameters**

```python
# Reset design state
mcp__anaerobic-design__reset_design()

# Collect basis of design parameters
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

**Step 2: Generate ADM1 state using Codex** (CRITICAL - Do not skip!)

```python
# Call Codex MCP to generate complete 63-component mADM1 state
mcp__ADM1-State-Variable-Estimator__codex(
    prompt="""
Generate complete mADM1 state variables for:

Feedstock: High-strength municipal wastewater sludge
COD: 50,000 mg/L | TSS: 35,000 mg/L | VSS: 28,000 mg/L
TKN: 2,500 mg-N/L | TP: 500 mg-P/L | pH: 7.0

Save to: ./adm1_state.json (all 63 components in kg/m³)
""",
    cwd="/path/to/anaerobic-design-mcp"
)

# Load generated state
mcp__anaerobic-design__load_adm1_state(file_path="./adm1_state.json")
```

**Step 3: Validate and size**

```bash
# Validate ADM1 state against measured parameters
python utils/validate_cli.py validate \
    --adm1-state adm1_state.json \
    --user-params '{"cod_mg_l": 50000, "tss_mg_l": 35000}' \
    --tolerance 0.15

# Run heuristic sizing
mcp__anaerobic-design__heuristic_sizing_ad(
    use_current_basis=True,
    target_srt_days=20
)
```

**Step 4: Run QSDsan simulation**

```bash
# Execute simulation (300-600 seconds to reach TRUE steady state)
python utils/simulate_cli.py --basis simulation_basis.json --adm1-state adm1_state.json --heuristic-config simulation_heuristic_config.json --hrt-variation 0.2

# Parse results (token-efficient: 7 KB vs 159 KB full file)
python utils/parse_simulation_results.py
```

**Output**: Three comprehensive tables showing:
1. Performance metrics (COD removal, methane yield, biomass yields)
2. Inhibition analysis (pH, ammonia, H2, H2S effects)
3. Precipitation metrics (struvite, HAP, FeS, etc.)

**Optional chemical dosing** (if needed for pH control):
```bash
python utils/simulate_cli.py --basis simulation_basis.json --adm1-state adm1_state.json --heuristic-config simulation_heuristic_config.json --hrt-variation 0.2 --naoh-dose 2840 --fecl3-dose 100
```

## Available MCP Tools

**Core Workflow**:
- `elicit_basis_of_design` - Collect design parameters
- `load_adm1_state` - Load Codex-generated ADM1 state
- `validate_adm1_state` - Verify state matches targets
- `heuristic_sizing_ad` - Size digester and MBR
- `simulate_ad_system_tool` - Run QSDsan dynamic simulation

**State Management**:
- `get_design_state` - Check workflow progress
- `reset_design` - Start new project

**Optional Analysis**:
- `compute_bulk_composites` - Calculate COD/TSS/VSS/TKN/TP from state
- `check_strong_ion_balance` - Verify charge balance
- `analyze_stream_details` - Component-level analysis
- `assess_process_health` - Inhibition factors
- `evaluate_sulfur_balance` - H2S pathways

## Architecture

```
anaerobic-design-mcp/
├── server.py                        # FastMCP server (13 tools)
├── tools/                           # MCP tool implementations
│   ├── basis_of_design.py          # Parameter collection
│   ├── validation.py               # ADM1 state validation
│   ├── sizing.py                   # Heuristic sizing
│   └── simulation.py               # QSDsan integration
├── utils/
│   ├── qsdsan_madm1.py             # 63-component mADM1 model
│   ├── qsdsan_reactor_madm1.py     # Custom AnaerobicCSTR
│   ├── qsdsan_simulation_sulfur.py # Simulation engine
│   ├── inoculum_generator.py       # Enhanced inoculum (6× methanogen boost) ⭐
│   ├── parse_simulation_results.py # Token-efficient result parser ⭐
│   ├── validate_cli.py             # CLI validation tools
│   └── simulate_cli.py             # CLI simulation wrapper
├── core/
│   └── state.py                    # Design state management
└── docs/                           # Complete documentation
    ├── INDEX.md                    # Navigation hub
    ├── architecture/               # System design
    ├── bugs/                       # Bug tracking
    ├── development/                # Refactoring history
    └── diagnostics/                # Analysis guides
```

## Production Readiness

### Validated Features

- **Thermodynamic Rigor**: Production charge balance solver with all 63 components
- **Biogas Tracking**: 4-component biogas (H2, CH4, CO2, H2S) with Henry's law equilibrium
- **Methane Yield**: 97.4% match to theoretical (validation against COD mass balance)
- **pH Accuracy**: 6.5-7.5 range for typical digesters (fixed critical R units bug)
- **Unit Consistency**: Aligned with QSDsan conventions (fixed 1000× gas production bug)

### Critical Fixes Applied

1. **Enhanced Inoculum (6× Methanogen Boost)** (2025-10-29): CRITICAL FIX for pH collapse during startup
   - Doubled methanogen boost factor from 3× → 6× in `utils/inoculum_generator.py`
   - Prevents VFA accumulation and pH drop from 7.0 → 4.8
   - Enables stable operation WITHOUT chemical supplementation (NaOH, Na2CO3)
   - Validated through comparative simulations: 3× boost = FAILED, 6× boost = SUCCESS
2. **pH Solver Bugs** (2025-10-21): Fixed 10^29× error in Ka values, restored pH to 6.7-7.5 range
3. **Production PCM** (2025-10-18): 9 fixes for complete charge balance with all ionic species
4. **1000× Unit Error** (2025-10-21): Fixed gas transfer units, restored methane production
5. **QSDsan Alignment** (2025-10-22): Eliminated divergence from upstream conventions

See [docs/bugs/CRITICAL_FIXES.md](docs/bugs/CRITICAL_FIXES.md) for details.

### Known Limitations

- **Non-deterministic regression tests**: Catastrophic failure case shows variable TAN (10,000-77,000 mg-N/L)
- **Reactor maintenance burden**: Custom AnaerobicCSTR class requires manual sync with QSDsan updates
- **Simplified precipitation**: Unity activity coefficients (Davies equation not yet implemented)

## Documentation

- **[CLAUDE.md](CLAUDE.md)** - System prompt for Claude Code (workflow instructions)

### Quick Links

- [mADM1 Component Indices (63 components)](docs/architecture/MADM1_COMPONENT_INDICES.md)
- [mADM1 Quick Reference](docs/architecture/MADM1_QUICK_REFERENCE.md)
- [FastMCP-QSDsan Integration](docs/architecture/FASTMCP_QSDSAN.md)

## Requirements

- **Python**: 3.10+
- **QSDsan**: 1.3+ (includes mADM1 process model)
- **FastMCP**: 0.1.0+
- **NumPy**: 1.24+
- **Pandas**: 2.0+

See [pyproject.toml](pyproject.toml) for complete dependencies.

## License

MIT License (see LICENSE file)

## Support

- **Issues**: Submit via GitHub Issues
- **Documentation**: See docs/architecture/ directory for technical references

## Citation

If you use this server in research, please cite:

- QSDsan framework: [https://github.com/QSD-Group/QSDsan](https://github.com/QSD-Group/QSDsan)
- ADM1 model: Batstone et al. (2002) "The IWA Anaerobic Digestion Model No. 1 (ADM1)"

## Development Status

**Current Version**: 0.1.0 (Production-Ready)

**Recent Updates**:
- 2025-11-22: Pre-release cleanup (removed obsolete docs and dead code)
- 2025-11-04: Background Job Pattern implementation (prevents STDIO blocking)
- 2025-10-29: Enhanced inoculum (6× methanogen boost) - CRITICAL FIX for startup stability
- 2025-10-29: Token-efficient result parser (95% reduction: 7 KB vs 159 KB)
- 2025-10-26: Comprehensive documentation consolidation
- 2025-10-22: QSDsan convention alignment
- 2025-10-21: Critical pH and unit conversion fixes
- 2025-10-18: Production PCM solver implementation
- 2025-10-18: Full mADM1 (63 components) integration


---

**Last Updated**: 2025-11-22
