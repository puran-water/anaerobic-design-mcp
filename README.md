# Anaerobic Digester Design MCP Server

An MCP server for anaerobic digester design using QSDsan with the **mADM1 (Modified ADM1) model** featuring 62 state variables + H2O (63 total components), including phosphorus, sulfur, and iron extensions for comprehensive nutrient recovery modeling.

## Installation

```bash
# Clone the repository
cd /mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp

# Install dependencies
pip install -e .

# Core dependencies include:
# - QSDsan for native mADM1 simulation (63 components, <100ms validation)
# - FastMCP for MCP server framework
# - Codex MCP for intelligent feedstock characterization
```

## Running the Server

```bash
# Run directly
python server.py

# Or use as MCP server
# Add to your MCP client configuration
```

## Development Milestones

### ✅ Milestone 1: Basic Server with Parameter Elicitation
- [x] Basic MCP server structure
- [x] Parameter elicitation tool
- [x] State management
- [x] Design state retrieval

**Test with:**
```python
# Test parameter elicitation
await elicit_basis_of_design("essential")
await elicit_basis_of_design("all")
await get_design_state()
```

### 🔄 Milestone 2: Heuristic Sizing (Next)
- [ ] Implement heuristic sizing calculations
- [ ] Flowsheet selection logic (high TSS vs MBR)
- [ ] Volume calculations

### ✅ Milestone 3: Codex Integration (Complete)
- [x] Codex MCP adapter (.codex/AGENTS.md)
- [x] Feed characterization tool
- [x] mADM1 state estimation (62 components + H2O)
- [x] Complete P/S/Fe extension support

### ✅ Milestone 4: QSDsan Simulation (Complete)
- [x] mADM1 simulation with QSDsan (63 components)
- [x] Production PCM solver (9 Codex-reviewed fixes)
- [x] Sulfur dynamics (SO4 → H2S, 4 SRB types)
- [x] EBPR modeling (X_PHA, X_PP, X_PAO)
- [x] Iron chemistry (Fe3+/Fe2+, HFO adsorption)
- [x] Mineral precipitation (13 types)
- [x] Performance metrics extraction
- [x] Complete validation tools for mADM1

### 💰 Milestone 5: Economic Analysis (In Progress)
- [ ] QSDsan costing integration
- [ ] CAPEX/OPEX calculations
- [ ] LCOW analysis

## mADM1 Model Features

The server uses the **Modified ADM1 (mADM1)** model with comprehensive extensions:

### Core ADM1 (24 components)
- Soluble organics: Sugars, amino acids, fatty acids, VFAs (acetate, propionate, butyrate, valerate)
- Particulate organics: Carbohydrates, proteins, lipids
- Microbial biomass: 7 functional groups (sugar degraders, methanogens, etc.)
- Inorganic: S_IC, S_IN, S_IP

### EBPR Extension (3 components)
- **X_PHA**: Polyhydroxyalkanoates (PAO storage polymers)
- **X_PP**: Polyphosphate
- **X_PAO**: Phosphate-accumulating organisms

### Sulfur Extension (7 components)
- **S_SO4**: Sulfate (SO4²⁻)
- **S_IS**: Total dissolved sulfide (H2S + HS⁻ + S²⁻)
- **X_hSRB, X_aSRB, X_pSRB, X_c4SRB**: Four sulfate-reducing bacteria types
- **S_S0**: Elemental sulfur

### Iron Extension (9 components)
- **S_Fe3, S_Fe2**: Ferric and ferrous iron
- **X_HFO_***: Seven hydrous ferric oxide variants (high/low reactivity, P-loaded, aged)

### Mineral Precipitation (13 components)
- **Phosphates**: Struvite, HAP, ACP, DCPD, OCP, newberyite, K-struvite, Fe/Al phosphates
- **Carbonates**: Calcite, ACC, magnesite
- **Sulfides**: Iron sulfide (FeS)

### Additional Cations (4 components)
- **S_K, S_Mg, S_Ca, S_Al**: Complete ionic strength modeling

### Production PCM Solver
- **9 Codex-reviewed fixes** for thermodynamic accuracy
- Complete charge balance with all ionic species
- Temperature-corrected equilibrium constants
- Proper unit handling throughout

## Available Tools

### 1. `elicit_basis_of_design`
Collects design parameters in groups:
- `essential`: Flow, COD, temperature
- `solids`: TSS, VSS
- `nutrients`: TKN, TP
- `alkalinity`: pH, alkalinity
- `all`: Complete parameter set

### 2. `get_design_state`
Returns the current state of the design process including:
- Collected parameters
- Completion status
- Next recommended steps

### 3. `reset_design`
Clears all state to start a new design.

## Architecture

```
anaerobic-design-mcp/
├── server.py                           # Main MCP server (lazy imports)
├── tools/                              # MCP tool implementations
│   ├── basis_of_design.py             # Parameter elicitation
│   ├── validation.py                  # ADM1 state validation (QSDsan)
│   ├── sizing.py                      # Heuristic sizing
│   └── simulation.py                  # QSDsan simulation wrapper
├── utils/                              # Utility modules
│   ├── qsdsan_validation.py           # Fast QSDsan validation (<100ms)
│   ├── qsdsan_validation_sync.py      # Subprocess validation (mADM1)
│   ├── validate_cli.py                # CLI validation interface
│   ├── qsdsan_madm1.py                # mADM1 process model (63 components)
│   ├── qsdsan_simulation_madm1.py     # mADM1 simulation wrapper
│   ├── extract_qsdsan_sulfur_components.py  # mADM1 component loader
│   ├── qsdsan_sulfur_kinetics.py      # H2S inhibition kinetics
│   ├── h2s_speciation.py              # Gas-liquid equilibrium
│   ├── stream_analysis_sulfur.py      # Sulfur mass balance
│   ├── heuristic_sizing.py            # Sizing calculations
│   └── feedstock_characterization.py  # Feedstock handling
├── core/                               # State management
│   ├── state.py                       # Design state singleton
│   └── utils.py                       # Helper functions
├── .codex/                             # Codex MCP configuration
│   ├── AGENTS.md                      # mADM1 expert prompt (62 components)
│   └── config.toml                    # Codex settings
└── tests/                              # Regression test suite
    ├── test_qsdsan_simulation_basic.py
    └── test_regression_catastrophe.py
```

## Testing

```bash
# Install test dependencies
pip install -e ".[test]"

# Run tests
pytest tests/
```