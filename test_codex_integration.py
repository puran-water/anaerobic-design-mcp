#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script to demonstrate Codex MCP integration for ADM1 state estimation.

This script shows how to call the Codex MCP server directly using the mcp__codex__codex tool.
"""

import json
import asyncio
from typing import Dict, Any


async def test_codex_adm1_estimation():
    """Test Codex MCP for ADM1 state variable estimation."""
    
    print("=" * 60)
    print("CODEX MCP INTEGRATION TEST")
    print("=" * 60)
    
    # Define test feedstocks
    test_cases = [
        {
            "name": "Dairy Wastewater",
            "description": "High-strength dairy wastewater from cheese production with high protein and lipid content",
            "cod_mg_l": 80000,
            "ph": 6.8
        },
        {
            "name": "Brewery Wastewater",
            "description": "Brewery wastewater with high carbohydrate content from beer production",
            "cod_mg_l": 50000,
            "tss_mg_l": 15000
        },
        {
            "name": "Municipal Wastewater",
            "description": "Typical municipal wastewater with balanced nutrients",
            "cod_mg_l": 30000
        }
    ]
    
    for test_case in test_cases:
        print(f"\n{'='*50}")
        print(f"TEST: {test_case['name']}")
        print(f"{'='*50}")
        
        # Build the prompt for Codex
        prompt = f"""You are an expert in anaerobic digestion and ADM1 modeling.

Generate ADM1 state variables for the following feedstock:
{test_case['description']}

Measured parameters:
- COD: {test_case.get('cod_mg_l', 'Not specified')} mg/L
{f"- TSS: {test_case['tss_mg_l']} mg/L" if 'tss_mg_l' in test_case else ""}
{f"- pH: {test_case['ph']}" if 'ph' in test_case else ""}

Return a JSON object with all 27 ADM1 state variables (all values in kg/m³ except S_IC, S_IN, S_cat, S_an which are in kmol/m³):

{{
    "S_su": 0.0,  // Monosaccharides
    "S_aa": 0.0,  // Amino acids
    "S_fa": 0.0,  // Long chain fatty acids
    "S_va": 0.0,  // Total valerate
    "S_bu": 0.0,  // Total butyrate
    "S_pro": 0.0, // Total propionate
    "S_ac": 0.0,  // Total acetate
    "S_h2": 0.0,  // Hydrogen gas
    "S_ch4": 0.0, // Methane gas
    "S_IC": 0.0,  // Inorganic carbon (kmol/m³)
    "S_IN": 0.0,  // Inorganic nitrogen (kmol/m³)
    "S_I": 0.0,   // Soluble inerts
    "S_cat": 0.0, // Total cation equivalents (kmol/m³)
    "S_an": 0.0,  // Total anion equivalents (kmol/m³)
    "S_co2": 0.0, // Carbon dioxide
    "X_c": 0.0,   // Composites
    "X_ch": 0.0,  // Carbohydrates
    "X_pr": 0.0,  // Proteins
    "X_li": 0.0,  // Lipids
    "X_su": 0.0,  // Sugar degraders
    "X_aa": 0.0,  // Amino acid degraders
    "X_fa": 0.0,  // LCFA degraders
    "X_c4": 0.0,  // Valerate and butyrate degraders
    "X_pro": 0.0, // Propionate degraders
    "X_ac": 0.0,  // Acetate degraders
    "X_h2": 0.0,  // Hydrogen degraders
    "X_I": 0.0    // Particulate inerts
}}

Guidelines:
- For inlet streams, biomass concentrations (X_su through X_h2) should be very low (0.01-0.05 kg/m³)
- Ensure S_cat and S_an are balanced for charge neutrality
- Scale values to match measured COD
- Return ONLY the JSON object, no additional text
"""
        
        print(f"Description: {test_case['description']}")
        print(f"COD: {test_case.get('cod_mg_l', 'Not specified')} mg/L")
        
        # Note: This is where you would call the Codex MCP server
        # In actual use with MCP client:
        # result = await mcp_client.call_tool("mcp__codex__codex", {
        #     "prompt": prompt,
        #     "profile": "adm1-estimation"
        # })
        
        print("\nPrompt prepared for Codex MCP.")
        print("In production, this would call: mcp__codex__codex")
        print("Expected output: JSON with 27 ADM1 state variables")
        
        # Show what pattern matching would generate as a comparison
        if "dairy" in test_case['name'].lower():
            print("\nPattern-based estimation (for comparison):")
            print("  High protein/lipid profile expected")
            print("  X_pr (Proteins): ~25 kg/m³")
            print("  X_li (Lipids): ~20 kg/m³")
        elif "brewery" in test_case['name'].lower():
            print("\nPattern-based estimation (for comparison):")
            print("  High carbohydrate profile expected")
            print("  X_ch (Carbohydrates): ~30 kg/m³")
            print("  S_su (Sugars): ~5 kg/m³")
        else:
            print("\nPattern-based estimation (for comparison):")
            print("  Balanced nutrient profile expected")
            print("  X_ch: ~25%, X_pr: ~20%, X_li: ~10% of COD")
    
    print("\n" + "=" * 60)
    print("CODEX MCP INTEGRATION TEST COMPLETE")
    print("=" * 60)
    print("\nNotes:")
    print("1. Codex MCP server should be configured in .mcp.json")
    print("2. CODEX_HOME should point to .codex/ with config.toml and AGENTS.md")
    print("3. Uses gpt-5 model with high reasoning effort")
    print("4. Returns structured JSON for direct use in WaterTAP simulation")


if __name__ == "__main__":
    asyncio.run(test_codex_adm1_estimation())