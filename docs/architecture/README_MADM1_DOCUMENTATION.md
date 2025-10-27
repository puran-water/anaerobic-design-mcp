# mADM1 Documentation Index

This directory contains comprehensive documentation about the mADM1 (Modified ADM1) implementation for anaerobic digestion design with 62 state variables.

## Documentation Files

### 1. MADM1_CONTEXT_FOR_CODEX.md (494 lines, 20 KB)
**Comprehensive reference for detailed understanding**

Best for:
- Understanding the complete component model
- Learning about PCM solver implementation
- Understanding mineral precipitation framework
- Detailed iron extension chemistry
- Deep dives into thermodynamic modeling

Contents:
- Complete 62-component state vector with descriptions
- All 13 mineral precipitate components
- Iron extension components (HFO variants)
- PCM solver implementation details (lines 432-623)
- Current precipitation handling status
- Component mapping vs standard ADM1
- Unit conventions and critical notes
- Testing resources and non-determinism issues

Start here if: You need deep understanding of how the system works

### 2. MADM1_QUICK_REFERENCE.md (177 lines, 5 KB)
**One-page cheat sheet for quick lookups**

Best for:
- Quick reference during development
- Component breakdown at a glance
- PCM solver key info
- File locations
- Process count breakdown

Contents:
- Essential facts summary
- Component breakdown (27 → 62 mapping)
- 13 minerals with chemical formulas
- 7 HFO variants with active site factors
- PCM solver signature and features
- Unit conventions
- Code access patterns
- Process count (63 total)
- Key functions to know

Start here if: You need quick facts during coding

### 3. MADM1_COMPONENT_INDICES.md (169 lines, 8 KB)
**Complete lookup table for all 62 components**

Best for:
- Finding component by index or ID
- Understanding unit conventions
- Code access patterns
- Component grouping
- Looking up specific mineral properties

Contents:
- All 62 components (indices 0-61) + H2O (62)
- Column table: Index, ID, Name, Type, Units, Notes
- Grouped by category
- Unit conventions by component group
- Component access code examples
- Fast lookup tables
- Charge valencies for PCM solver

Start here if: You need exact component indices or properties

## Quick Navigation

### By Task

**"I need to understand the whole system"**
→ Read MADM1_CONTEXT_FOR_CODEX.md section by section

**"I need to implement something fast"**
→ Check MADM1_QUICK_REFERENCE.md or MADM1_COMPONENT_INDICES.md

**"I need the index for component X"**
→ Search MADM1_COMPONENT_INDICES.md table

**"I need to understand mineral precipitation"**
→ MADM1_CONTEXT_FOR_CODEX.md section 2 & 6

**"I need to understand PCM solver"**
→ MADM1_CONTEXT_FOR_CODEX.md section 5

**"I need iron extension details"**
→ MADM1_CONTEXT_FOR_CODEX.md section 4

### By Component Group

**ADM1 Core (27):** All three documents

**EBPR (3):** MADM1_QUICK_REFERENCE.md, MADM1_COMPONENT_INDICES.md

**Minerals (13):** MADM1_CONTEXT_FOR_CODEX.md section 2, MADM1_QUICK_REFERENCE.md, MADM1_COMPONENT_INDICES.md

**Iron (9):** MADM1_CONTEXT_FOR_CODEX.md section 4, MADM1_QUICK_REFERENCE.md

**Sulfur (7):** MADM1_CONTEXT_FOR_CODEX.md

**Metals (6):** MADM1_COMPONENT_INDICES.md

## Key Sections Reference

### Component Overview
- **Full list with descriptions:** MADM1_CONTEXT_FOR_CODEX.md section 1
- **Index table:** MADM1_COMPONENT_INDICES.md full table
- **Quick summary:** MADM1_QUICK_REFERENCE.md "62 State Variables Breakdown"

### Mineral Precipitation (13 components)
- **Detailed chemistry:** MADM1_CONTEXT_FOR_CODEX.md section 2
- **Quick table:** MADM1_QUICK_REFERENCE.md "13 Mineral Precipitates"
- **Index reference:** MADM1_COMPONENT_INDICES.md indices 47-59
- **Status & roadmap:** MADM1_CONTEXT_FOR_CODEX.md section 6

### Iron Extension (9 components)
- **Detailed HFO chemistry:** MADM1_CONTEXT_FOR_CODEX.md section 4
- **HFO variants:** MADM1_QUICK_REFERENCE.md "7 HFO Variants"
- **Index reference:** MADM1_COMPONENT_INDICES.md indices 36-44
- **ASF values:** All three documents

### PCM Solver
- **Implementation details:** MADM1_CONTEXT_FOR_CODEX.md section 5
- **Key functions:** MADM1_QUICK_REFERENCE.md "PCM Solver Key Info"
- **Codex fixes:** MADM1_CONTEXT_FOR_CODEX.md section 5 table
- **Code location:** All documents reference utils/qsdsan_madm1.py:432-623

### Unit Conventions
- **Complete reference:** MADM1_CONTEXT_FOR_CODEX.md section 9
- **Quick summary:** MADM1_QUICK_REFERENCE.md "Critical Unit Info"
- **By component group:** MADM1_COMPONENT_INDICES.md "Unit Conventions"

## Code References

### Main Implementation
- **Component creation:** utils/qsdsan_madm1.py:45-280
- **PCM solver:** utils/qsdsan_madm1.py:432-623
- **HFO chemistry:** utils/qsdsan_madm1.py:176-196
- **Minerals:** utils/qsdsan_madm1.py:197-209
- **Stoichiometry:** data/_madm1.tsv
- **Reactor ODE:** utils/qsdsan_reactor_madm1.py
- **Simulation:** utils/qsdsan_simulation_sulfur.py
- **Codex prompt:** .codex/AGENTS.md

## Critical Patterns

### Always use dynamic indexing
```python
# CORRECT
idx = cmps.index('S_ac')
value = state_arr[idx]

# WRONG
value = state_arr[6]  # Hardcoded!
```

### Temperature corrections are essential
```python
# Van't Hoff for Ka values
Ka_corrected = Ka_base * exp((ΔH/R) * (1/T_base - 1/T_op))
# R = 8.314 J/(mol·K)  [NOT bar·m³/(kmol·K)]
```

### Unit conversion for PCM solver
```python
# Convert kg/m³ to mol/L
mass_kg_m3 = state_arr[idx]
unit_conv = mass2mol_conversion(cmps)[idx]
molar_conc = mass_kg_m3 * unit_conv
```

### Ion aggregation for charge balance
```python
# Divalent: Mg²⁺ + Ca²⁺ + Fe²⁺ (all ×2 charge)
# Trivalent: Fe³⁺ + Al³⁺ (all ×3 charge)
# NOT just Mg²⁺!
```

## Document Maintenance

These documents were generated: **2025-10-27**

Generated from:
- `data/_madm1.tsv` - Component and stoichiometry definitions
- `utils/qsdsan_madm1.py` - PCM solver implementation
- `utils/qsdsan_reactor_madm1.py` - Reactor ODE
- `.codex/AGENTS.md` - Codex agent prompt

### If you update the model:
1. Update component definitions in utils/qsdsan_madm1.py
2. Regenerate MADM1_COMPONENT_INDICES.md with new indices
3. Update MADM1_CONTEXT_FOR_CODEX.md with new chemistry details
4. Update MADM1_QUICK_REFERENCE.md with new process counts if applicable

## Common Questions Answered

**Q: How many components are there?**
A: 62 state variables + H2O = 63 total components. See MADM1_COMPONENT_INDICES.md

**Q: Where are the minerals?**
A: Indices 47-59 (13 total). See MADM1_QUICK_REFERENCE.md table

**Q: What are the HFO variants?**
A: 7 components (indices 38-44). See MADM1_QUICK_REFERENCE.md "7 HFO Variants"

**Q: How does PCM solver work?**
A: Charge balance with Brent's method, temperature-corrected Ka values. See MADM1_CONTEXT_FOR_CODEX.md section 5

**Q: What units are state variables in?**
A: kg/m³ (with some on COD basis, some on element basis). See MADM1_CONTEXT_FOR_CODEX.md section 9

**Q: How do I access a component by name?**
A: Use `cmps.index('component_id')`. See MADM1_COMPONENT_INDICES.md "Component Access in Code"

**Q: What's the mineral precipitation status?**
A: Framework only - saturation index calculation exists but IAP/Ksp not implemented. See MADM1_CONTEXT_FOR_CODEX.md section 6

**Q: Which file should I read first?**
A: Start with MADM1_QUICK_REFERENCE.md for overview, then read MADM1_CONTEXT_FOR_CODEX.md for depth.

---

Last updated: 2025-10-27
For questions about this documentation, see the main project README or contact the development team.
