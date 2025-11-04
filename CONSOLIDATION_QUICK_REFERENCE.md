# Documentation Consolidation - Quick Reference

## Key Findings Summary

### Current State
- **Total documentation**: ~2,400 lines across 7 files (fragmented)
- **Audience clarity**: Mixed (users, AI agents, developers)
- **Navigation**: No index, scattered information
- **Public release readiness**: 4/10

### Main Issues
1. **README.md (301 lines)** - Mixed user + AI instructions (should be installation only)
2. **CLAUDE.md (397 lines)** - Good, but undiscoverable for human users
3. **IMPLEMENTATION_PLAN.md (1,177 lines)** - Too detailed, internal development notes
4. **Background Job Pattern** - Critical but not highlighted in README
5. **No troubleshooting guide** - Users will be frustrated

---

## Quick Wins (High Impact, Low Effort)

### 1. Create docs/INDEX.md (30 min)
**Impact**: Enables navigation, clarifies audience
**Content**: Simple categorization (Users | AI Agents | Developers | Reference)

### 2. Update README.md Quick Start (20 min)
**Current**: 4 incomplete workflow steps (lines 82-162)
**New**: "See [CLAUDE.md](CLAUDE.md) for complete workflow"
**Impact**: Removes confusion, points to correct document

### 3. Add CLAUDE.md link to README (5 min)
**Current**: README mentions CLAUDE.md but doesn't emphasize it
**New**: Add prominent "For AI Agent Workflows" section
**Impact**: AI agents will find complete instructions

---

## Medium Effort Projects (Required for Public Release)

### 4. Create docs/BACKGROUND_JOB_PATTERN.md (60 min)
**Why**: Users don't understand why tools return immediately
**Content**: Explanation + examples + troubleshooting
**Reference from**: README, API_REFERENCE, TROUBLESHOOTING

### 5. Create docs/USER_GUIDE.md (60 min)
**Why**: Humans need step-by-step, not Python API calls
**Content**: Installation → Example → Results → Troubleshooting
**Reference from**: README (simplified)

### 6. Create docs/API_REFERENCE.md (90 min)
**Why**: No specification of MCP tool parameters
**Content**: 13 tools with parameters, examples, runtime expectations
**Note**: Requires adding docstrings to server.py first

### 7. Create docs/TROUBLESHOOTING.md (90 min)
**Why**: No guidance for failed jobs, validation errors, etc.
**Content**: 5 sections (jobs, validation, simulation, install, performance)

---

## File Organization Plan

### High Priority
```
README.md               ← Refactor (180 lines, no workflow)
docs/
├── INDEX.md           ← NEW (navigation hub)
├── USER_GUIDE.md      ← NEW (step-by-step for humans)
├── BACKGROUND_JOB_PATTERN.md ← NEW (critical explanation)
├── API_REFERENCE.md   ← NEW (tool specifications)
└── TROUBLESHOOTING.md ← NEW (common issues)
```

### Medium Priority (Nice to Have)
```
docs/
├── DESIGN_PARAMETERS.md ← NEW (explain mixing/thermal params)
├── CHANGELOG.md        ← NEW (version history)
├── DEVELOPMENT.md      ← NEW (contributing guide)
├── KNOWN_LIMITATIONS.md ← NEW (TODO items documented)
└── REFERENCES.md       ← NEW (consolidated citations)
```

### Archive
```
DEVELOPMENT_HISTORY.md ← Archive IMPLEMENTATION_PLAN.md
```

---

## Specific Content Movement

### What Stays Where
✓ **CLAUDE.md** - Keep all 397 lines (it's excellent for AI agents)
✓ **.codex/AGENTS.md** - Keep all 548 lines (system prompt for Codex)
✓ **docs/architecture/** - Keep all 3 files (well-organized)

### What Moves
→ **README.md lines 107-162** (workflow steps) → **docs/USER_GUIDE.md** + **CLAUDE.md**
→ **IMPLEMENTATION_PLAN.md lines 21-87** (Background Job) → **docs/BACKGROUND_JOB_PATTERN.md**
→ **IMPLEMENTATION_PLAN.md lines 399-483** (Parameters) → **docs/DESIGN_PARAMETERS.md**
→ **IMPLEMENTATION_PLAN.md all** (development notes) → **DEVELOPMENT_HISTORY.md** (archive)

### What's New
+ **docs/INDEX.md** - Navigation hub (30 lines)
+ **docs/USER_GUIDE.md** - Human-friendly workflow (150 lines)
+ **docs/BACKGROUND_JOB_PATTERN.md** - Job pattern explanation (120 lines)
+ **docs/API_REFERENCE.md** - Tool specifications (200 lines)
+ **docs/TROUBLESHOOTING.md** - Common issues (150 lines)
+ **DEVELOPMENT_HISTORY.md** - Archived development notes (1,177 lines)

---

## Estimated Timeline

### Day 1 (3 hours)
- Create docs/INDEX.md
- Refactor README.md Quick Start
- Enhance CLAUDE.md (add link from README)
- **Result**: Navigation in place, audience clarity

### Day 2 (4 hours)
- Create docs/USER_GUIDE.md
- Create docs/BACKGROUND_JOB_PATTERN.md
- Create docs/TROUBLESHOOTING.md
- **Result**: Users have complete guidance

### Day 3 (3 hours)
- Create docs/API_REFERENCE.md (requires server.py docstrings)
- Create docs/CHANGELOG.md
- Archive IMPLEMENTATION_PLAN.md
- **Result**: Professional documentation structure

### Optional (2 hours)
- Create docs/DESIGN_PARAMETERS.md
- Create docs/FAQ.md
- Create docs/REFERENCES.md (consolidated)

**Total**: ~10 hours → Professional documentation ready for public release

---

## Critical Content Priorities

### 1. Background Job Pattern (HIGHEST PRIORITY)
**Why**: Users won't understand tool behavior without it
**Currently**: Explained in CLAUDE.md but not discoverable for human users
**Location**: docs/BACKGROUND_JOB_PATTERN.md (NEW)
**Sections needed**:
- What is the background job pattern?
- Why is it needed? (MCP STDIO blocking explanation)
- Which tools use it? (4 specific tools listed)
- How to monitor jobs? (get_job_status, get_job_results)
- Troubleshooting failed jobs (how to read stderr.log)

### 2. API Reference (HIGH PRIORITY)
**Why**: No specification of MCP tool parameters
**Currently**: Inline comments in server.py, scattered documentation
**Location**: docs/API_REFERENCE.md (NEW)
**Sections needed**:
- Each of 13 MCP tools (parameters, returns, example, runtime)
- Cross-references (e.g., heuristic_sizing_ad → get_job_results)
- Job workspace structure (jobs/{job_id}/)
- Output files location

### 3. User Guide (HIGH PRIORITY)
**Why**: Humans don't want to read AI workflow documentation
**Currently**: Mixed in README.md with feature overview
**Location**: docs/USER_GUIDE.md (NEW)
**Sections needed**:
- Installation verification
- Real example (sizing 100 m³ digester)
- Understanding output files
- Common parameters explained
- When to adjust settings
- FAQ + troubleshooting

### 4. Troubleshooting (MEDIUM PRIORITY)
**Why**: No guidance for common issues
**Currently**: Scattered notes in IMPLEMENTATION_PLAN.md
**Location**: docs/TROUBLESHOOTING.md (NEW)
**Sections needed**:
- Job timeouts/failures (how to debug)
- Validation deviations (what they mean)
- Simulation divergence (what to adjust)
- Installation issues (dependencies)
- Performance tuning (job limits)

---

## Success Criteria (Post-Consolidation)

### User Experience
- ✓ README.md is clear, concise entry point
- ✓ Users find docs/USER_GUIDE.md instead of being confused by code examples
- ✓ AI agents find CLAUDE.md easily
- ✓ Developers find docs/ARCHITECTURE.md and docs/DEVELOPMENT.md
- ✓ docs/INDEX.md helps everyone navigate

### Documentation Coverage
- ✓ Installation: 100%
- ✓ Workflow: 100% (all 6 steps documented)
- ✓ API Reference: 100% (all 13 tools specified)
- ✓ Troubleshooting: 100% (common issues covered)
- ✓ Architecture: 100% (design decisions documented)

### Public Release Readiness
- ✓ No hardcoded absolute paths
- ✓ No development notes in public docs
- ✓ Clear audience segmentation
- ✓ Navigation hub (docs/INDEX.md)
- ✓ Professional structure
- **Rating**: 4/10 → 9/10

---

## Files to Create

1. **docs/INDEX.md** (30 lines)
   - Navigation hub with 3 audiences

2. **docs/USER_GUIDE.md** (150 lines)
   - Human-friendly step-by-step

3. **docs/BACKGROUND_JOB_PATTERN.md** (120 lines)
   - Job execution explanation

4. **docs/API_REFERENCE.md** (200 lines)
   - MCP tool specifications

5. **docs/TROUBLESHOOTING.md** (150 lines)
   - Common issues and solutions

6. **docs/DESIGN_PARAMETERS.md** (150 lines) [Optional]
   - Explain mixing/thermal parameters

7. **docs/CHANGELOG.md** (150 lines) [Optional]
   - Version history and fixes

8. **DEVELOPMENT_HISTORY.md** (1,177 lines) [Archive]
   - Move IMPLEMENTATION_PLAN.md content

---

## Modified Files

1. **README.md** (Refactor)
   - Remove workflow steps (move to USER_GUIDE.md)
   - Add docs/INDEX.md link
   - Simplify Quick Start section

2. **CLAUDE.md** (Enhance)
   - Add troubleshooting section
   - Replace hardcoded paths
   - Add reference to docs/BACKGROUND_JOB_PATTERN.md

3. **server.py** (Prerequisite)
   - Add docstrings to MCP tools (required for API_REFERENCE.md)
   - Document all 13 parameters for each tool

---

## Expected Impact

### Current State
- 2,400 lines of documentation (fragmented)
- Mixed audiences (confusing)
- No navigation (hard to find info)
- Workflow scattered (incomplete in README, complete in CLAUDE.md)
- No troubleshooting (frustrating for users)

### Post-Consolidation
- 2,400+ lines (same content + new structure)
- Clear audience separation (users | AI agents | developers)
- Navigation hub (docs/INDEX.md)
- Workflow: README → docs/USER_GUIDE.md OR CLAUDE.md (clear choice)
- Complete troubleshooting guide (docs/TROUBLESHOOTING.md)
- Professional structure (ready for public release)

### Metrics
- Navigation clarity: 2/10 → 9/10
- Completeness: 70% → 100%
- Audience clarity: 3/10 → 9/10
- Public release readiness: 4/10 → 9/10

---

## Next Steps

1. **Review this report** - Ensure approach aligns with your vision
2. **Priority ranking** - Decide what's critical vs. nice-to-have
3. **Timeline** - Choose whether to do all at once or phased
4. **Assignment** - Decide who creates each file
5. **Review process** - Plan how to review/approve new docs

**Recommendation**: Start with High Priority items (Quick Wins + Medium Effort) for public release readiness, then add optional files based on user feedback.

