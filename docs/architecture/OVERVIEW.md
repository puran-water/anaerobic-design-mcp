# Architecture: Anaerobic Design MCP Server

## Design Principles

### Complete Independence from ADM1 MCP Server

This server is a **standalone, improved implementation** that will eventually supplant the parent ADM1 MCP server. Key architectural decisions:

1. **No Cross-Server Dependencies**
   - This server does NOT import from or depend on the ADM1 MCP server
   - Both servers are completely separate MCP servers with independent implementations
   - This server is designed to be the successor, not an extension

2. **Different Model: ADM1+Sulfur (30 components)**
   - **Standard ADM1** (parent server): 27 components
   - **ADM1+Sulfur** (this server): 30 components
     - All 27 standard ADM1 components
     - Plus 3 sulfur-specific: `S_SO4`, `S_IS`, `X_SRB`
   - Different kinetic model with H2S inhibition on methanogens

3. **Native Implementations**
   - All stream analysis functions implemented natively for 30-component system
   - No fallback to parent server - clean, purpose-built implementations
   - Sulfur-aware from the ground up

## Key Differences from Parent Server

| Feature | ADM1 MCP Server | Anaerobic Design MCP (This) |
|---------|----------------|----------------------------|
| **Model** | Standard ADM1 (27 comp) | ADM1+Sulfur (30 comp) |
| **Simulation** | WaterTAP subprocess | Native QSDsan dynamic |
| **Sulfur** | ❌ Not modeled | ✅ Full sulfur cycle |
| **H2S Inhibition** | ❌ Not included | ✅ pH-dependent H2S/HS⁻ |
| **SRB** | ❌ Not modeled | ✅ Sulfate-reducing bacteria |
| **Workflow** | Simulation-focused | Full design workflow |

## Component Architecture

```
anaerobic-design-mcp/
├── server.py                          # FastMCP server (13 tools)
├── tools/
│   ├── basis_of_design.py            # Parameter elicitation
│   ├── validation.py                  # ADM1 state validation
│   ├── sizing.py                      # Heuristic sizing
│   ├── simulation.py                  # QSDsan simulation (native)
│   ├── stream_details.py             # Optional analysis
│   ├── process_health.py             # Optional diagnostics
│   └── sulfur_balance.py             # Optional sulfur analysis
├── utils/
│   ├── extract_qsdsan_sulfur_components.py  # 30-component setup
│   ├── qsdsan_sulfur_kinetics.py            # H2S inhibition kinetics
│   ├── qsdsan_simulation_sulfur.py          # Native simulation engine
│   └── stream_analysis_sulfur.py            # Native analysis (30 comp)
└── core/
    └── state.py                       # Design state management
```

## Why No Dependency on Parent Server?

1. **Incompatible Component Sets**
   - Parent expects 27 components
   - This server uses 30 components
   - Stream analysis functions would break with extra components

2. **Different Assumptions**
   - Parent assumes no sulfur chemistry
   - This server requires sulfur mass balance
   - H2S speciation is pH-dependent (not in parent)

3. **Evolution Path**
   - This is not a "fork" - it's a **replacement**
   - Cleaner to implement natively than to patch parent
   - Eliminates technical debt from the start

4. **Deployment Independence**
   - Each server can be deployed separately
   - No risk of version conflicts
   - Users can choose which server fits their needs

## Migration from ADM1 MCP Server

If migrating from the parent ADM1 MCP server:

1. **State Format**: ADM1 states are compatible (27 components)
   - This server adds 3 sulfur components with defaults
   - Existing 27-component states work but will have S_SO4=0.1, S_IS=0.001, X_SRB=0.01

2. **Workflow Changes**:
   - Old: Direct simulation with ADM1 state
   - New: Basis of design → Validation → Sizing → Simulation

3. **Output Structure**: Different (cleaner, more structured)
   - This server provides comprehensive sulfur analysis
   - H2S inhibition factors reported explicitly
   - Dual-HRT robustness validation included

## Future Development

This server will continue to evolve independently:
- Economic analysis tools
- Multi-stage digester design
- Advanced sulfur treatment options
- Integration with other wastewater unit operations

The parent ADM1 MCP server may remain for users who need standard 27-component ADM1 without sulfur chemistry, but this server represents the recommended path forward.
