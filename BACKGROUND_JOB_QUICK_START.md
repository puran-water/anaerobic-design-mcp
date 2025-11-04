# Background Job Pattern: Quick Start Guide

**TL;DR - Get Background Jobs working in 10 minutes**

---

## The Problem (30 seconds)

Your MCP server blocks when running tools that import heavy libraries (scipy, qsdsan, tensorflow) or perform long computations (>30 seconds). The agent times out waiting for a response.

## The Solution (1 line)

Launch computations in **background subprocesses** instead of the main MCP process. Return immediately with a `job_id`, let the agent poll for results.

---

## Quick Start: 5 Steps

### Step 1: Copy JobManager (2 minutes)

Copy this file to your project:
```
utils/job_manager.py
```

This singleton manages background subprocess execution with crash recovery and concurrency control.

### Step 2: Copy JobStateReconciler (1 minute)

Copy this file:
```
utils/job_state_reconciler.py
```

This automatically loads results into your server's state after jobs complete.

### Step 3: Create a CLI Wrapper (3 minutes)

For each heavy operation, create a standalone script:

```python
#!/usr/bin/env python3
# utils/my_operation_cli.py

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    
    try:
        # Load inputs from JSON
        with open(Path(args.input_dir) / "input.json") as f:
            inputs = json.load(f)
        
        # Import heavy modules HERE (subprocess-isolated)
        from my_heavy_module import compute
        
        # Run computation
        results = compute(inputs)
        
        # Write results to JSON
        with open(Path(args.output_dir) / "results.json", "w") as f:
            json.dump(results, f, indent=2)
        
        sys.exit(0)
    except Exception as e:
        sys.exit(1)

if __name__ == "__main__":
    main()
```

Key points:
- Read inputs from JSON files (not parent memory)
- Import heavy libraries inside subprocess
- Write results to JSON files
- Exit with status code

### Step 4: Update Your Tool (2 minutes)

In `server.py`, replace blocking tool with job-launching version:

```python
@mcp.tool()
async def my_heavy_operation(param1: str):
    """Heavy operation that would normally block"""
    from utils.job_manager import JobManager
    import json, uuid, sys
    from pathlib import Path
    
    # Validate state
    if not design_state.required_data:
        return {"error": "Missing state"}
    
    # Pre-create job directory
    job_id = str(uuid.uuid4())[:8]
    job_dir = Path("jobs") / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    
    # Serialize state to JSON
    with open(job_dir / "input.json", "w") as f:
        json.dump(design_state.required_data, f)
    
    # Build subprocess command
    cmd = [
        sys.executable,
        "utils/my_operation_cli.py",
        "--input-dir", str(job_dir),
        "--output-dir", str(job_dir)
    ]
    
    # Register state patch for auto-hydration
    state_patch = {
        "field": "my_results",
        "result_file": "results.json"
    }
    
    # Execute job (returns immediately)
    manager = JobManager()
    job = await manager.execute(cmd=cmd, cwd=".", job_id=job_id)
    job["state_patch"] = state_patch
    manager._save_job_metadata(job)
    
    # Return job_id immediately
    return {
        "job_id": job["id"],
        "status": "starting",
        "message": "Job started"
    }
```

### Step 5: Add Monitoring Tools (1 minute)

Add these tools to your MCP server:

```python
@mcp.tool()
async def get_job_status(job_id: str):
    """Check job status"""
    return await JobManager().get_status(job_id)

@mcp.tool()
async def get_job_results(job_id: str):
    """Get job results"""
    return await JobManager().get_results(job_id)
```

---

## Agent Workflow

```python
# 1. Start job
response = await tools.my_heavy_operation(param1="value")
job_id = response["job_id"]

# 2. Poll for completion
while True:
    status = await tools.get_job_status(job_id)
    if status['status'] == 'completed':
        break
    await asyncio.sleep(5)

# 3. Get results
results = await tools.get_job_results(job_id)
print(results)
```

---

## Common Pitfalls

### ❌ Don't: Import heavy modules in main process
```python
# WRONG - blocks STDIO
import scipy
@mcp.tool()
async def my_tool():
    return scipy.compute()
```

### ✅ Do: Import in subprocess
```python
# CORRECT - subprocess-isolated
@mcp.tool()
async def my_tool():
    # CLI subprocess will import scipy
    job = await manager.execute(["python", "utils/cli.py"])
    return job["id"]
```

### ❌ Don't: Pass state as arguments
```python
# WRONG - state too large for command line
cmd = [sys.executable, "cli.py", "--state", json.dumps(huge_dict)]
```

### ✅ Do: Use JSON files
```python
# CORRECT - pass via files
with open(job_dir / "state.json", "w") as f:
    json.dump(huge_dict, f)
cmd = [sys.executable, "cli.py", "--input-dir", str(job_dir)]
```

### ❌ Don't: Print to stdout in subprocess
```python
# WRONG - output blocks STDIO
print("Progress: 50%")
```

### ✅ Do: Log to file
```python
# CORRECT - log to file
import logging
logger = logging.getLogger(__name__)
logger.info("Progress: 50%")  # Goes to file, not STDIO
```

---

## Real Example: Simulation Tool

**Before (Blocking):**
```python
@mcp.tool()
async def simulate_system():
    import scipy, qsdsan  # 30 seconds ⏳
    results = qsdsan.simulate()
    return results
# Agent times out ❌
```

**After (Non-blocking):**
```python
@mcp.tool()
async def simulate_system():
    """Returns immediately with job_id"""
    job_id = str(uuid.uuid4())[:8]
    job_dir = Path("jobs") / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    
    with open(job_dir / "config.json", "w") as f:
        json.dump(design_state.config, f)
    
    cmd = [sys.executable, "utils/simulate_cli.py",
           "--input-dir", str(job_dir),
           "--output-dir", str(job_dir)]
    
    job = await JobManager().execute(cmd=cmd, job_id=job_id)
    job["state_patch"] = {"field": "sim_results", "result_file": "results.json"}
    JobManager()._save_job_metadata(job)
    
    return {"job_id": job["id"]}
# Agent gets immediate response ✅
# Polls for results via get_job_status
# Job completes without blocking server
```

---

## Files to Copy

```
From reference implementation (anaerobic-design-mcp):
├── utils/job_manager.py             → Copy as-is
├── utils/job_state_reconciler.py    → Copy as-is
├── utils/heuristic_sizing_cli.py    → Use as template
├── utils/simulate_cli.py            → Use as template
└── BACKGROUND_JOB_PATTERN.md        → Read full guide
```

---

## Checklist

- [ ] Copied `utils/job_manager.py`
- [ ] Copied `utils/job_state_reconciler.py`
- [ ] Created CLI wrapper script(s)
- [ ] Updated tool handler to return job_id
- [ ] Added `get_job_status` tool
- [ ] Added `get_job_results` tool
- [ ] Tested: tool returns immediately
- [ ] Tested: status polling works
- [ ] Tested: results retrieved after completion
- [ ] Tested: crash recovery (restart server, jobs persist)

---

## Performance Expectations

```
Tool invocation:        ~50ms
Subprocess startup:     ~2s
Heavy imports:          ~18s (scipy, qsdsan)
Computation:            ~120-300s
Total:                  ~150-330s

But MCP STDIO responsive after 50ms ✓
Agent can poll during computation ✓
No timeouts ✓
```

---

## Debugging

**Job stuck in "running" state?**
```bash
# Check logs
cat jobs/abc123/stdout.log
cat jobs/abc123/stderr.log

# Manually terminate
# (get_job_status will show as running because process still alive)
kill $(cat jobs/abc123/job.json | jq .pid)
```

**Results not loaded into design_state?**
```bash
# Check if state_patch was registered
cat jobs/abc123/job.json | jq .state_patch

# Check if results file exists
ls -la jobs/abc123/results.json

# Check state file
ls -la state/my_results.json
```

**Out of memory?**
```python
# Reduce concurrent jobs
JobManager(max_concurrent_jobs=1)
```

---

## Next Steps

1. Read full guide: `BACKGROUND_JOB_PATTERN.md`
2. Copy reference implementation files
3. Adapt CLI wrappers for your tools
4. Test with small jobs first
5. Integrate into production workflow
6. Monitor resource usage

Questions? See detailed guide section on Trade-offs and Production Deployment.

