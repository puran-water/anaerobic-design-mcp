# Claude Integration Guide for Anaerobic Digester Design MCP

## Overview

This project provides two MCP servers that work together:
1. **anaerobic-design**: Main server for anaerobic digester design workflow
2. **ADM1-State-Variable-Estimator**: Codex-based server for intelligent feedstock characterization

## When to Use Each Server

### anaerobic-design Server Tools

Use the main anaerobic-design server for:
- `elicit_basis_of_design`: Collecting design parameters (flow rate, COD, temperature, etc.)
- `heuristic_sizing_ad`: Performing heuristic sizing calculations for digesters and MBR systems
- `get_design_state`: Retrieving the current design state
- `reset_design`: Clearing the design state for a new project
- `characterize_feedstock`: Initial tool that may call Codex MCP when `use_codex=true`

### ADM1-State-Variable-Estimator (Codex MCP)

Use the ADM1-State-Variable-Estimator server (`mcp__ADM1-State-Variable-Estimator__codex`) when:
- The `characterize_feedstock` tool is called with `use_codex=true`
- You need accurate ADM1 state variable estimation based on feedstock descriptions
- Converting natural language feedstock descriptions to numerical ADM1 parameters

## How to Call the Codex MCP Server

When the `characterize_feedstock` tool needs Codex assistance:

1. **Prepare the prompt** with feedstock information:
```python
prompt = f"""
Generate ADM1 state variables for the following feedstock:
{feedstock_description}

Measured parameters:
- COD: {cod_mg_l} mg/L
- TSS: {tss_mg_l} mg/L
- pH: {ph}

[Rest of prompt with JSON structure requirements]
"""
```

2. **Call the ADM1-State-Variable-Estimator tool**:
```python
result = await mcp_client.call_tool("mcp__ADM1-State-Variable-Estimator__codex", {
    "prompt": prompt,
    "cwd": "/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp"
})
```

3. **Read the output file**:
```python
with open("./adm1_state.json", "r") as f:
    adm1_state = json.load(f)
```

## Workflow Example

1. **Start with basis of design**:
   - Call `elicit_basis_of_design` to set flow rate, COD, temperature

2. **Characterize the feedstock**:
   - Call `characterize_feedstock` with feedstock description
   - If `use_codex=true`, this internally uses Codex MCP for intelligent estimation
   - ADM1 state variables are stored in the design state

3. **Perform heuristic sizing**:
   - Call `heuristic_sizing_ad` to size digesters and auxiliary equipment
   - Uses the stored ADM1 state for calculations

4. **Continue to simulation and economic analysis**:
   - Future tools will use the complete design state
   - WaterTAP simulation will use ADM1 state variables
   - Economic analysis will use sizing results

## Important Notes

- The Codex MCP server uses GPT-5 with high reasoning effort
- Output is written to `./adm1_state.json` in the current directory
- The `.codex/AGENTS.md` file contains the system prompt for ADM1 expertise
- Sandbox mode is set to `workspace-write` to allow file creation

## Error Handling

If Codex MCP is unavailable or fails:
- The `characterize_feedstock` tool falls back to pattern-based estimation
- Default ADM1 states are generated based on feedstock type keywords
- A warning is logged indicating the fallback method was used

## Configuration

The Codex MCP server configuration is in:
- `.mcp.json`: Server launch configuration
- `.codex/config.toml`: Model and sandbox settings
- `.codex/AGENTS.md`: System prompt for ADM1 expertise

## Testing

To test Codex integration:
1. Run `test_milestone3.py` for full workflow testing
2. Run `test_codex_integration.py` for standalone Codex testing
3. Check `./adm1_state.json` for output verification