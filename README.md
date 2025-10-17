# Anaerobic Digester Design MCP Server

An MCP server for anaerobic digester design using QSDsan with the ADM1+sulfur model (30 components), following the proven architecture of the RO-design-mcp server.

## Installation

```bash
# Clone the repository
cd /mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp

# Install dependencies
pip install -e .

# Core dependencies include:
# - QSDsan for native ADM1+sulfur simulation (<100ms validation)
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
- [x] ADM1+sulfur state estimation (30 components)

### ✅ Milestone 4: QSDsan Simulation (Complete)
- [x] ADM1+sulfur simulation with QSDsan
- [x] Sulfur dynamics (SO4 → H2S)
- [x] Performance metrics extraction
- [x] Stream analysis and sulfur balance

### 💰 Milestone 5: Economic Analysis (In Progress)
- [ ] QSDsan costing integration
- [ ] CAPEX/OPEX calculations
- [ ] LCOW analysis

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
│   ├── qsdsan_simulation_sulfur.py    # ADM1+sulfur simulation
│   ├── extract_qsdsan_sulfur_components.py  # Component definitions
│   ├── qsdsan_sulfur_kinetics.py      # H2S inhibition kinetics
│   ├── h2s_speciation.py              # Gas-liquid equilibrium
│   ├── stream_analysis_sulfur.py      # Sulfur mass balance
│   ├── heuristic_sizing.py            # Sizing calculations
│   └── feedstock_characterization.py  # Feedstock handling
├── core/                               # State management
│   ├── state.py                       # Design state singleton
│   └── utils.py                       # Helper functions
├── .codex/                             # Codex MCP configuration
│   ├── AGENTS.md                      # ADM1+sulfur expert prompt
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