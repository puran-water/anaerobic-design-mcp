import json
import sys
sys.path.insert(0, '/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp')

from core.state import design_state

# Load ADM1 state from Codex-generated file
with open('./adm1_state.json', 'r') as f:
    adm1_data = json.load(f)

# Store in design state
design_state.adm1_state = adm1_data
print(f"ADM1 state loaded: {len(adm1_data)} components")
print(f"First component: {list(adm1_data.keys())[0]} = {adm1_data[list(adm1_data.keys())[0]]}")
