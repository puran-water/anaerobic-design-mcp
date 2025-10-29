#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Convert annotated mADM1 state (values as [value, unit, explanation])
to a numeric-only mapping for validators that expect raw floats.

Usage:
  /mnt/c/Users/hvksh/mcp-servers/venv312/Scripts/python.exe utils/convert_annotated_to_numeric.py \
      --input adm1_state.json --output adm1_state_numeric.json
"""
import json
import argparse

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True)
    p.add_argument('--output', required=True)
    args = p.parse_args()

    with open(args.input, 'r') as f:
        data = json.load(f)

    numeric = {}
    for k, v in data.items():
        if isinstance(v, (list, tuple)) and len(v) > 0:
            try:
                numeric[k] = float(v[0])
            except Exception:
                # Fall back to 0 for non-numeric values
                numeric[k] = 0.0
        else:
            try:
                numeric[k] = float(v)
            except Exception:
                numeric[k] = 0.0

    with open(args.output, 'w') as f:
        json.dump(numeric, f)

if __name__ == '__main__':
    main()

