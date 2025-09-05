# Anaerobic Digester Design MCP Server

An MCP server for anaerobic digester design using the WaterTAP framework, following the proven architecture of the RO-design-mcp server.

## Installation

```bash
# Clone the repository
cd /mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp

# Install dependencies
pip install -e .

# For full WaterTAP simulation capabilities
pip install -e ".[watertap]"
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

### 📋 Milestone 3: Codex Integration
- [ ] Codex MCP adapter
- [ ] Feed characterization tool
- [ ] ADM1 state estimation

### 🔬 Milestone 4: WaterTAP Simulation
- [ ] ADM1 simulation wrapper
- [ ] SRT iteration logic
- [ ] Performance metrics extraction

### 💰 Milestone 5: Economic Analysis
- [ ] WaterTAPCostingDetailed integration
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
├── server.py              # Main MCP server
├── utils/                 # Utility modules (to be added)
│   ├── heuristic_sizing.py
│   ├── codex_adapter.py
│   ├── ad_simulation.py
│   └── economic_analysis.py
└── tests/                 # Test suite (to be added)
```

## Testing

```bash
# Install test dependencies
pip install -e ".[test]"

# Run tests
pytest tests/
```