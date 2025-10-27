# Documentation Index - Anaerobic Design MCP Server

**Last Updated**: 2025-10-26

Welcome to the complete documentation for the Anaerobic Design MCP Server. This index provides navigation to all documentation, organized by category.

---

## Getting Started

### New Users Start Here

1. **[README.md](../README.md)** - Overview, installation, and quick start guide
2. **[CLAUDE.md](../CLAUDE.md)** - Complete workflow instructions for Claude Code
3. **[Architecture Overview](architecture/OVERVIEW.md)** - System design and independence from parent ADM1 server

### Quick Reference

- **Model**: mADM1 (Modified ADM1) with 62 state variables + H2O
- **Simulation**: QSDsan AnaerobicCSTR with 4-component biogas (H2, CH4, CO2, H2S)
- **Status**: Production-Ready (validated to 97.4% theoretical methane yield)
- **MCP Tools**: 13 tools for complete design workflow

---

## Architecture

Comprehensive system design documentation.

### Core Documents

- **[OVERVIEW.md](architecture/OVERVIEW.md)** - Design principles and independence from parent server
  - Complete independence from ADM1 MCP server
  - 62-component mADM1 vs 27-component ADM1
  - Native QSDsan implementations
  - Migration path and future development

- **[COMPONENT_MODEL.md](architecture/COMPONENT_MODEL.md)** - Complete mADM1 component specification
  - All 62 state variables + H2O
  - P/S/Fe extensions
  - Mineral precipitation (13 types)
  - EBPR components

- **[FASTMCP_QSDSAN.md](architecture/FASTMCP_QSDSAN.md)** - Integration architecture
  - FastMCP server structure
  - QSDsan lazy loading
  - MCP tool implementations
  - Lifespan management

### Key Architectural Decisions

1. **No cross-server dependencies**: Standalone implementation
2. **62-component mADM1**: Full P/S/Fe extensions
3. **Native implementations**: Purpose-built for sulfur chemistry
4. **Codex integration**: AI-powered ADM1 state generation

---

## Development

Development history, refactoring notes, and testing documentation.

### Refactoring & History

- **[REFACTORING_HISTORY.md](development/REFACTORING_HISTORY.md)** - Complete development timeline
  - Major milestones
  - Architecture evolution
  - Dependency changes
  - Performance improvements

- **[STEADY_STATE_REFACTORING.md](development/STEADY_STATE_REFACTORING.md)** - Simulation methodology changes
  - Time-limited vs true steady-state
  - Convergence criteria
  - Performance impact

- **[VALIDATION_CLEANUP_SUMMARY.md](development/VALIDATION_CLEANUP_SUMMARY.md)** - Validation tool consolidation
  - QSDsan native validation (<100ms)
  - CLI validation tools
  - Component verification

### Testing

- **[TEST_ANALYSIS.md](development/TEST_ANALYSIS.md)** - Regression test suite
  - test_qsdsan_simulation_basic.py
  - test_regression_catastrophe.py (non-deterministic)
  - test_madm1_validation.py
  - Coverage and known issues

---

## Bugs & Fixes

Critical bug tracking and workflow testing documentation.

### Current Bug Documentation

- **[CRITICAL_FIXES.md](bugs/CRITICAL_FIXES.md)** - Consolidated critical fix documentation ⭐ **START HERE**
  - Critical Fix #1: pH Solver Bugs (10^29× Ka error)
  - Critical Fix #2: Production PCM Solver (9 Codex-reviewed fixes)
  - Critical Fix #3: 1000× Unit Conversion Error
  - Critical Fix #4: QSDsan Convention Alignment
  - Impact summary and lessons learned

### Detailed Bug Tracking

- **[BUG_TRACKING.md](bugs/BUG_TRACKING.md)** - Detailed bug investigation notes
  - Initial WaterTAP workflow issues (2025-01-07)
  - QSDsan workflow integration (2025-10-18)
  - mADM1 integration bugs (2025-10-18)
  - Codex technical reviews

- **[BUG_FIXES_SUMMARY.md](bugs/BUG_FIXES_SUMMARY.md)** - Bug fix summaries by date
  - Pre-consolidation documentation
  - Individual fix descriptions
  - Test results

- **[BUG_FIXES_UPSTREAM_RECONCILIATION.md](bugs/BUG_FIXES_UPSTREAM_RECONCILIATION.md)** - QSDsan alignment
  - Unit conversion conventions
  - Biogas species assignment
  - Phosphate charge balance
  - Mathematical equivalence proofs

### Workflow Testing

- **[WORKFLOW_TESTING.md](bugs/WORKFLOW_TESTING.md)** - End-to-end workflow validation
  - Complete workflow steps (0-5)
  - Codex ADM1 generation testing
  - Simulation validation
  - Known issues and workarounds

### Historical Bug Tracking

- **[../BUG_TRACKER.md](../BUG_TRACKER.md)** - Original chronological bug log
  - Historical reference (superseded by CRITICAL_FIXES.md)
  - Early WaterTAP issues
  - Initial QSDsan integration problems

---

## Diagnostics

System diagnosis guides and analysis methodologies.

### Performance Analysis

- **[BIOGAS_ANALYSIS.md](diagnostics/BIOGAS_ANALYSIS.md)** - Biogas production diagnostics
  - Methane yield validation
  - Biogas composition analysis
  - H2S concentration assessment
  - Gas transfer troubleshooting

- **[COD_BALANCE.md](diagnostics/COD_BALANCE.md)** - COD mass balance verification
  - Influent COD tracking
  - Effluent COD calculation
  - Biogas COD accounting
  - Gap analysis (<5% target)

- **[DIGESTER_DIAGNOSIS.md](diagnostics/DIGESTER_DIAGNOSIS.md)** - Process health assessment
  - pH range validation (6.5-7.5)
  - VFA accumulation detection
  - Alkalinity monitoring
  - Inhibition factor analysis

### System Behavior

- **[DETERMINISM.md](diagnostics/DETERMINISM.md)** - Non-deterministic behavior analysis
  - Solver convergence issues
  - Regression test variability
  - TAN accumulation ranges (10,000-77,000 mg-N/L)
  - When to use directional vs absolute assertions

---

## Operations

Operational guides and production deployment documentation.

### Production Deployment

- **[BIOMASS_YIELD_MAR.md](operations/BIOMASS_YIELD_MAR.md)** - Biomass yield management
  - Y_obs calculation
  - SRT impact on yield
  - MAR (Measured Anaerobic Respiration) validation
  - Typical yield ranges (0.05-0.15 kg VSS/kg COD)

### Future Operations Docs

- Economic analysis workflow (planned)
- Multi-stage digester design (planned)
- Nutrient recovery optimization (planned)

---

## External Analysis

External validation and comparison documentation.

### Codex Reviews

- **[CODEX_ANALYSIS.md](external/CODEX_ANALYSIS.md)** - Codex MCP server investigations
  - GitHub CLI QSDsan source analysis
  - DeepWiki ADM1/mADM1 model reviews
  - PCM thermodynamic validation
  - Unit conversion verification

### Upstream Comparisons

- **[WATERTAP_REMOVAL.md](external/WATERTAP_REMOVAL.md)** - Transition from WaterTAP
  - Why QSDsan replaced WaterTAP
  - Performance comparison
  - Architecture benefits
  - Migration notes

---

## Archived Documentation

Historical documentation retained for reference.

### Obsolete/Superseded Docs

- **[archived/DIAGNOSTIC_DATA_STATUS.md](archived/DIAGNOSTIC_DATA_STATUS.md)** - Early diagnostic attempts
- **[archived/PUSH_SUMMARY.md](archived/PUSH_SUMMARY.md)** - Historical commit summaries
- **[archived/WATERTAP_VALIDATION_UPGRADE.md](archived/WATERTAP_VALIDATION_UPGRADE.md)** - WaterTAP validation efforts
- **[archived/WORKFLOW_TEST_SUMMARY.md](archived/WORKFLOW_TEST_SUMMARY.md)** - Early workflow testing
- **[archived/component_mapping.md](archived/component_mapping.md)** - 30→62 component mapping notes

**Note**: These documents are retained for historical context but are superseded by current documentation.

---

## Quick Reference Tables

### Bugs by Number

| Bug # | Title | Impact | Status | Document |
|-------|-------|--------|--------|----------|
| Fix #1 | pH Solver Bugs (R units, unit conversion) | CATASTROPHIC | ✅ Fixed | [CRITICAL_FIXES.md](bugs/CRITICAL_FIXES.md#critical-fix-1-ph-solver-unit-bugs-date-2025-10-21) |
| Fix #2 | Production PCM Solver (9 sub-fixes) | CRITICAL | ✅ Fixed | [CRITICAL_FIXES.md](bugs/CRITICAL_FIXES.md#critical-fix-2-complete-production-pcm-solver-date-2025-10-18) |
| Fix #3 | 1000× Unit Conversion Error | CATASTROPHIC | ✅ Fixed | [CRITICAL_FIXES.md](bugs/CRITICAL_FIXES.md#critical-fix-3-1000-unit-conversion-error-date-2025-10-21) |
| Fix #4 | QSDsan Convention Alignment | HIGH | ✅ Fixed | [CRITICAL_FIXES.md](bugs/CRITICAL_FIXES.md#critical-fix-4-qsdsan-convention-alignment-date-2025-10-22) |

### Bugs by Date

| Date | Fix | Impact | Symptom |
|------|-----|--------|---------|
| 2025-10-18 | Production PCM (9 fixes) | CRITICAL | pH=7.0 constant, no charge balance |
| 2025-10-21 | pH solver bugs | CATASTROPHIC | pH=9.3, 13-20% COD gap |
| 2025-10-21 | 1000× unit error | CATASTROPHIC | Methane: 0.73 m³/d (expected 724) |
| 2025-10-22 | QSDsan alignment | HIGH | Divergence from upstream |

### Bugs by Topic

| Topic | Bugs | Status | Reference |
|-------|------|--------|-----------|
| **pH Calculation** | R units, unit conversion, charge balance | ✅ Fixed | [CRITICAL_FIXES.md](bugs/CRITICAL_FIXES.md) |
| **Unit Conversion** | 1000× gas error, molar conversion | ✅ Fixed | [CRITICAL_FIXES.md](bugs/CRITICAL_FIXES.md) |
| **Thermodynamics** | PCM solver, Ka temperature correction | ✅ Fixed | [CRITICAL_FIXES.md](bugs/CRITICAL_FIXES.md) |
| **QSDsan Alignment** | Compensating factors, conventions | ✅ Fixed | [BUG_FIXES_UPSTREAM_RECONCILIATION.md](bugs/BUG_FIXES_UPSTREAM_RECONCILIATION.md) |
| **Non-determinism** | Regression test variability | ⚠️ Known | [DETERMINISM.md](diagnostics/DETERMINISM.md) |

---

## Documentation by Audience

### For New Users

1. [README.md](../README.md) - Start here!
2. [CLAUDE.md](../CLAUDE.md) - Complete workflow
3. [Architecture OVERVIEW.md](architecture/OVERVIEW.md) - Understand the system

### For Developers

1. [CRITICAL_FIXES.md](bugs/CRITICAL_FIXES.md) - Understand past issues
2. [REFACTORING_HISTORY.md](development/REFACTORING_HISTORY.md) - Development timeline
3. [TEST_ANALYSIS.md](development/TEST_ANALYSIS.md) - Regression testing
4. [Architecture docs](architecture/) - System design

### For Researchers

1. [COMPONENT_MODEL.md](architecture/COMPONENT_MODEL.md) - mADM1 specification
2. [CODEX_ANALYSIS.md](external/CODEX_ANALYSIS.md) - Thermodynamic validation
3. [BIOGAS_ANALYSIS.md](diagnostics/BIOGAS_ANALYSIS.md) - Validation methodology
4. [BIOMASS_YIELD_MAR.md](operations/BIOMASS_YIELD_MAR.md) - Yield calculations

### For Production Deployment

1. [CRITICAL_FIXES.md](bugs/CRITICAL_FIXES.md) - Known issues resolved
2. [WORKFLOW_TESTING.md](bugs/WORKFLOW_TESTING.md) - Complete workflow validation
3. [DETERMINISM.md](diagnostics/DETERMINISM.md) - Expected behavior ranges
4. [Production Readiness section in README](../README.md#production-readiness)

---

## Document Status Legend

- ⭐ **Primary Reference** - Most important/current documentation
- ✅ **Complete** - Documentation is comprehensive and current
- 🔄 **In Progress** - Actively being updated
- 📚 **Reference** - Historical or supplementary material
- 🗄️ **Archived** - Superseded but retained for reference

---

## Contributing to Documentation

### Documentation Standards

1. **Keep INDEX.md current** - Update this file when adding/removing docs
2. **Use relative links** - Enable offline browsing
3. **Include dates** - Track when docs were created/updated
4. **Cross-reference** - Link related documents
5. **Status markers** - Use legend symbols for clarity

### New Document Checklist

- [ ] Add entry to this INDEX.md
- [ ] Include "Last Updated" date
- [ ] Add cross-references to related docs
- [ ] Update README.md if user-facing
- [ ] Archive superseded documentation

---

## Contact & Support

- **Issues**: Submit via GitHub Issues
- **Questions**: See [README.md](../README.md) support section
- **Codex Integration**: [.codex/AGENTS.md](../.codex/AGENTS.md)

---

**Navigation**: [← Back to README](../README.md) | [Architecture →](architecture/OVERVIEW.md) | [Critical Fixes →](bugs/CRITICAL_FIXES.md)

**Last Updated**: 2025-10-26
