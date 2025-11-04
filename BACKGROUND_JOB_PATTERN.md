# The Background Job Pattern: Solving MCP STDIO Blocking for Long-Running Operations

**A comprehensive guide to implementing non-blocking asynchronous task execution in MCP servers**

---

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [Root Cause Analysis](#root-cause-analysis)
3. [Solution Overview](#solution-overview)
4. [Architecture](#architecture)
5. [Implementation Guide](#implementation-guide)
6. [Code Examples](#code-examples)
7. [Key Patterns](#key-patterns)
8. [Trade-offs and Considerations](#trade-offs-and-considerations)
9. [Production Deployment](#production-deployment)

---

## Problem Statement

### The STDIO Blocking Issue

MCP servers communicate with AI agents via STDIO (stdin/stdout). When a long-running operation (>30 seconds) that performs heavy computation writes to stdout or stderr, it can block the entire MCP communication channel, causing:

- **Tool timeout failures** - Agent calls timeout waiting for a response
- **Connection drops** - STDIO pipe fills up, MCP protocol breaks
- **Resource exhaustion** - Python process blocks on I/O, unable to handle new requests
- **Cascading failures** - One slow tool blocks all other concurrent requests

### Why This Happens

```
MCP Protocol (STDIO-based):
┌─────────────────────────────────────────────────────┐
│ Agent              MCP Server Process               │
│  │                 ┌──────────────────────┐        │
│  ├─→ JSON request ─→ stdin buffer         │        │
│  │                 │ (limited capacity)   │        │
│  ←─ JSON response ←─ stdout buffer        │        │
│  │                 └──────────────────────┘        │
│  │                                                  │
│  │              ⚠️ PROBLEM:                        │
│  │  Unbuffered stdout from heavy operations       │
│  │  fills pipe faster than agent can read,        │
│  │  causing blocking and timeouts                 │
│  └─────────────────────────────────────────────────┘
```

### Real-World Example: The Scipy Import Problem

```python
# Traditional approach (blocks STDIO for 18+ seconds)
@mcp.tool()
async def simulate_system():
    # This import takes 18 seconds and prints to stdout
    import scipy
    import qsdsan
    # ... now the MCP connection is blocked ...
    return results
```

The agent's request sits unanswered for 18+ seconds while heavy modules load, printing debug output, version information, and progress messages directly to stdout—all unbuffered and blocking MCP STDIO.

---

## Root Cause Analysis

### The STDIO Buffer Problem

MCP uses synchronous STDIO communication:

```
1. Agent writes JSON request to stdin
2. MCP server reads from stdin (blocking)
3. Tool processes request (prints to stdout/stderr unbuffered)
4. Tool returns result
5. MCP writes result to stdout
6. Agent reads result from stdout

PROBLEM: Step 3 can take 30+ seconds AND fill the stdout pipe,
         preventing step 5 from completing.
```

### Why Subprocess Isolation Works

When a subprocess runs independently:

```
Main MCP Process:
  ├─ Continues reading/writing STDIO to agent ✓
  ├─ Returns job_id immediately ✓
  └─ Remains responsive ✓

Background Subprocess:
  ├─ Loads heavy modules (scipy, qsdsan, biosteam)
  ├─ Prints debug output to captured files (not STDIO)
  ├─ Performs long computation (18-300 seconds)
  ├─ Writes results to JSON files
  └─ Exits gracefully
```

The key insight: **Subprocess output is redirected to files, NOT to parent STDIO**.

---

## Solution Overview

The **Background Job Pattern** solves this by:

1. **Immediate Response**: Return `job_id` immediately without waiting for computation
2. **Subprocess Isolation**: Launch heavy work in an independent asyncio subprocess
3. **Output Redirection**: Capture subprocess stdout/stderr to files, not parent STDIO
4. **State Hydration**: Automatically load results into server state after completion
5. **Async Management**: Use asyncio for non-blocking job monitoring
6. **Crash Recovery**: Persist job metadata to disk for restart resilience

### Success Criteria

```
BEFORE (Blocking):
  Agent request
  │
  ├─ Wait 30+ seconds ⏳
  │
  └─ Response timeout ❌

AFTER (Job Pattern):
  Agent request
  │
  ├─ Immediate response: {job_id: "abc123"} ✓
  │
  └─ Agent polls status (via get_job_status)
     │
     ├─ Poll 1: {status: "running", elapsed: 15s} ✓
     │
     ├─ Poll 2: {status: "completed", elapsed: 45s} ✓
     │
     └─ Get results (via get_job_results) ✓
```

---

## Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     MCP Server                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  MCP Tool Handler (server.py)                        │   │
│  │  ✓ Validates inputs                                 │   │
│  │  ✓ Serializes state to JSON files                   │   │
│  │  ✓ Pre-creates job directory                        │   │
│  │  ✓ Returns job_id immediately                       │   │
│  └──────────────────────────────────────────────────────┘   │
│                          │                                  │
│                          ▼                                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  JobManager (utils/job_manager.py)                   │   │
│  │  ✓ Async subprocess launcher                         │   │
│  │  ✓ Concurrency control (semaphore)                   │   │
│  │  ✓ Job metadata persistence                          │   │
│  │  ✓ Background monitoring                             │   │
│  │  ✓ Crash recovery                                    │   │
│  └──────────────────────────────────────────────────────┘   │
│                          │                                  │
│                          ├─→ jobs/abc123/job.json (metadata)
│                          │                                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  JobStateReconciler (utils/job_state_reconciler.py)  │   │
│  │  ✓ Loads result files into design_state             │   │
│  │  ✓ Persists state to disk                           │   │
│  │  ✓ Replays missed updates on restart                │   │
│  └──────────────────────────────────────────────────────┘   │
│                          │                                  │
│                          ├─→ state/field_name.json         │
│                          │                                  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────┐
        │   Background Subprocess               │
        │   (utils/script_cli.py)               │
        │                                       │
        │  ✓ Loads heavy modules in subprocess │
        │  ✓ Reads inputs from JSON files      │
        │  ✓ Performs computation              │
        │  ✓ Writes results to JSON files      │
        │  ✓ Writes logs to .log files         │
        │                                       │
        │  jobs/abc123/                        │
        │  ├─ basis.json (input)              │
        │  ├─ results.json (output)           │
        │  ├─ stdout.log (captured output)    │
        │  └─ stderr.log (captured errors)    │
        │                                       │
        │  CRITICAL: Does NOT write to parent  │
        │            process STDIO             │
        └───────────────────────────────────────┘
```

### Data Flow

```
1. TOOL INVOCATION (server.py)
   Agent → MCP Server Tool Handler
   │
   ├─ Validate inputs
   ├─ Check design_state has required data
   └─ Serialize to JSON files in job directory

2. JOB SUBMISSION (JobManager)
   Tool Handler → JobManager.execute()
   │
   ├─ Generate or validate job_id
   ├─ Create job directory: jobs/{job_id}/
   ├─ Write job metadata: jobs/{job_id}/job.json
   ├─ Launch subprocess: utils/script_cli.py
   │  (subprocess reads from jobs/{job_id}/*.json)
   ├─ Return job_id immediately
   └─ Register state patch for auto-hydration

3. SUBPROCESS EXECUTION (utils/script_cli.py)
   JobManager → Background Subprocess
   │
   ├─ Read inputs from JSON files (NOT from parent memory)
   ├─ Load heavy modules (scipy, qsdsan, etc.)
   ├─ Perform computation
   ├─ Write results to JSON files
   ├─ Capture stdout/stderr to .log files
   └─ Exit with status code

4. BACKGROUND MONITORING (JobManager._monitor_job)
   Subprocess Exit → JobManager
   │
   ├─ Collect stdout/stderr from subprocess
   ├─ Update job status (completed/failed)
   ├─ Trigger state reconciliation
   └─ Save job metadata to disk

5. STATE HYDRATION (JobStateReconciler)
   Job Completion → State Update
   │
   ├─ Load result JSON from job directory
   ├─ Apply state patch to design_state
   ├─ Persist state to disk (state/{field}.json)
   └─ Mark state_applied in job metadata

6. RESULT RETRIEVAL (get_job_results)
   Agent → JobManager.get_results()
   │
   ├─ Check job status
   ├─ Load results.json from job directory
   ├─ Return parsed results to agent
   └─ Agent proceeds with next step
```

---

## Implementation Guide

### Step 1: Create the JobManager Class

The `JobManager` is the heart of the pattern. It handles:
- Async subprocess execution
- Job metadata persistence
- Concurrency control
- Crash recovery

**Key features:**

```python
class JobManager:
    """Singleton job manager for background task execution"""
    
    def __init__(self, max_concurrent_jobs: int = 3):
        """Initialize with concurrency control"""
        self.semaphore = asyncio.Semaphore(max_concurrent_jobs)
        self.jobs_dir = Path("jobs")
        self.jobs = {}  # In-memory job registry
        self._load_existing_jobs()  # Crash recovery
    
    async def execute(
        self, 
        cmd: List[str], 
        cwd: str = ".",
        job_id: Optional[str] = None
    ) -> dict:
        """
        Execute subprocess and return immediately with job_id
        
        Args:
            cmd: Command as list (e.g., ["python", "script.py", "--arg", "value"])
            cwd: Working directory
            job_id: Optional pre-determined job ID
        
        Returns:
            Job metadata with status="starting" and job_id
        """
        # ... implementation ...
```

**Critical implementation details:**

1. **Subprocess Redirection**: Use `asyncio.subprocess.PIPE` for stdout/stderr
2. **Semaphore**: Limit concurrent jobs to prevent resource exhaustion
3. **Job Directory**: Pre-create `jobs/{job_id}/` before launching subprocess
4. **Metadata Persistence**: Save job.json before and after execution
5. **Non-blocking monitoring**: Use `asyncio.create_task()` to monitor in background

### Step 2: Create CLI Wrapper Scripts

For each heavy operation, create a standalone CLI script that:
- Accepts command-line arguments (not parent memory)
- Reads inputs from JSON files (not design_state)
- Loads heavy modules in subprocess (not main process)
- Writes results to JSON files
- Captures stdout/stderr

**Example structure:**

```python
#!/usr/bin/env python3
"""CLI Wrapper for Heavy Operation"""

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Apply patches BEFORE importing heavy modules
from utils.runtime_patches import apply_all_patches
apply_all_patches()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    # ... other arguments ...
    
    args = parser.parse_args()
    
    try:
        # Load inputs from JSON files (NOT from parent memory)
        with open(Path(args.input_dir) / "basis.json") as f:
            basis = json.load(f)
        
        # Import heavy modules here (subprocess-isolated)
        from utils.heavy_module import perform_computation
        
        # Run computation
        results = perform_computation(basis)
        
        # Write results to JSON file
        with open(Path(args.output_dir) / "results.json", "w") as f:
            json.dump(results, f, indent=2)
        
        sys.exit(0)
    
    except Exception as e:
        # Log error and exit with failure code
        sys.exit(1)

if __name__ == "__main__":
    main()
```

### Step 3: Create State Reconciler

The `JobStateReconciler` automatically loads results into server state:

```python
class JobStateReconciler:
    """Automatic state hydration from job results"""
    
    def apply(self, job: Dict[str, Any]) -> bool:
        """
        Load result from job directory into design_state
        
        Extracts state_patch metadata from job:
            - field: design_state attribute name
            - result_file: JSON file to load
            - json_pointer: Optional path to nested value
        """
        # Load result file
        result_path = Path(job["job_dir"]) / job["state_patch"]["result_file"]
        with open(result_path) as f:
            result_data = json.load(f)
        
        # Update design_state
        from core.state import design_state
        field = job["state_patch"]["field"]
        setattr(design_state, field, result_data)
        
        # Persist to disk for crash recovery
        state_file = self.state_dir / f"{field}.json"
        with open(state_file, 'w') as f:
            json.dump(result_data, f, indent=2)
        
        return True
    
    def replay_missed_updates(self, jobs: Dict) -> int:
        """On server restart, replay state updates for completed jobs"""
        count = 0
        for job_id, job in jobs.items():
            if job.get("status") == "completed" and not job.get("state_applied"):
                if self.apply(job):
                    count += 1
        return count
```

### Step 4: Integrate in MCP Tool Handler

In your MCP server (server.py), create a tool that:
1. Validates inputs
2. Serializes design_state to JSON files
3. Pre-creates job directory
4. Returns job_id immediately

```python
@mcp.tool()
async def my_heavy_tool(param1: str, param2: float):
    """Heavy operation that would normally block STDIO"""
    from utils.job_manager import JobManager
    from core.state import design_state
    from pathlib import Path
    import json
    import uuid
    
    # Validate design_state
    if not design_state.some_required_field:
        return {"error": "Missing required state"}
    
    # Pre-create job directory
    job_id = str(uuid.uuid4())[:8]
    job_dir = Path("jobs") / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    
    # Serialize state to JSON
    try:
        with open(job_dir / "input_state.json", "w") as f:
            json.dump(design_state.some_field, f, indent=2)
    except (TypeError, ValueError) as e:
        job_dir.rmdir()  # Clean up
        return {"error": f"Serialization failed: {e}"}
    
    # Build subprocess command
    cmd = [
        sys.executable,
        "utils/my_heavy_cli.py",
        "--input-dir", str(job_dir),
        "--output-dir", str(job_dir),
        "--param1", param1,
        "--param2", str(param2)
    ]
    
    # Register state patch for auto-hydration
    state_patch = {
        "field": "my_results",           # design_state.my_results
        "result_file": "results.json",   # jobs/{job_id}/results.json
        "json_pointer": None             # Load entire file
    }
    
    # Execute job
    manager = JobManager()
    job = await manager.execute(cmd=cmd, cwd=".", job_id=job_id)
    
    # Add state patch to job metadata
    job["state_patch"] = state_patch
    manager._save_job_metadata(job)
    
    # Return immediately with job_id
    return {
        "job_id": job["id"],
        "status": job["status"],
        "message": "Job started. Use get_job_status() to monitor.",
        "next_steps": [
            f"Check status: get_job_status('{job['id']}')",
            f"Get results: get_job_results('{job['id']}')"
        ]
    }
```

### Step 5: Add Job Management Tools

Provide agent with tools to monitor and retrieve results:

```python
@mcp.tool()
async def get_job_status(job_id: str):
    """Check status of a background job"""
    manager = JobManager()
    return await manager.get_status(job_id)

@mcp.tool()
async def get_job_results(job_id: str):
    """Retrieve results from completed job"""
    manager = JobManager()
    return await manager.get_results(job_id)

@mcp.tool()
async def list_jobs(status_filter: str = None, limit: int = 20):
    """List all jobs with optional status filter"""
    manager = JobManager()
    return await manager.list_jobs(status_filter=status_filter, limit=limit)

@mcp.tool()
async def terminate_job(job_id: str):
    """Terminate a running job"""
    manager = JobManager()
    return await manager.terminate_job(job_id)
```

---

## Code Examples

### Example 1: Before (Blocking Implementation)

```python
# ❌ BLOCKS STDIO FOR 30+ SECONDS
@mcp.tool()
async def simulate_system(feedstock_cod: float):
    """Simulate anaerobic digester"""
    
    # Heavy imports run in main process, blocking STDIO
    from utils.heavy_simulation import run_simulation  # Takes 18 seconds
    import scipy  # Takes 5 seconds
    import qsdsan  # Takes 8 seconds
    
    # At this point, 30+ seconds have passed, MCP STDIO is blocked
    
    # Now run computation (takes another 120 seconds)
    results = run_simulation(feedstock_cod)
    
    # Total time: 150+ seconds, entire time blocking STDIO
    return results

# Agent experiences:
# - Tool call made
# - 150+ seconds of silence
# - MCP connection timeout
# - Tool call fails
```

### Example 2: After (Non-Blocking Implementation)

```python
# ✅ RETURNS IMMEDIATELY (< 100ms)
@mcp.tool()
async def simulate_system(feedstock_cod: float):
    """Simulate anaerobic digester"""
    from utils.job_manager import JobManager
    from core.state import design_state
    import json, uuid, sys
    from pathlib import Path
    
    # Validate state quickly
    if not design_state.basis_of_design:
        return {"error": "Call elicit_basis_of_design first"}
    
    # Pre-create job directory
    job_id = str(uuid.uuid4())[:8]
    job_dir = Path("jobs") / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    
    # Serialize state (fast, no heavy imports)
    with open(job_dir / "basis.json", "w") as f:
        json.dump(design_state.basis_of_design, f)
    
    # Build subprocess command
    cmd = [sys.executable, "utils/simulate_cli.py",
           "--input-dir", str(job_dir),
           "--output-dir", str(job_dir),
           "--feedstock-cod", str(feedstock_cod)]
    
    # Launch job (doesn't wait for completion)
    manager = JobManager()
    job = await manager.execute(cmd=cmd, cwd=".", job_id=job_id)
    
    # Register state patch
    job["state_patch"] = {
        "field": "simulation_results",
        "result_file": "results.json"
    }
    manager._save_job_metadata(job)
    
    # Return immediately (< 100ms)
    return {
        "job_id": job["id"],
        "status": "starting",
        "message": "Simulation job started",
        "next_steps": [
            f"Check status: get_job_status('{job['id']}')",
            f"Get results: get_job_results('{job['id']}')"
        ]
    }

# Agent experience:
# - Tool call made
# - Immediate response: {job_id: "abc123", status: "starting"}
# - Agent polls: get_job_status("abc123")
#   Response 1: {status: "running", elapsed: 30s}
#   Response 2: {status: "running", elapsed: 80s}
#   Response 3: {status: "completed", elapsed: 150s}
# - Agent retrieves: get_job_results("abc123")
# - Gets full results without blocking
```

### Example 3: CLI Wrapper Script

```python
#!/usr/bin/env python3
"""
CLI wrapper for simulation (utils/simulate_cli.py)

Runs as background subprocess, isolated from main MCP STDIO
"""

import argparse
import json
import sys
import logging
from pathlib import Path

# Setup
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.runtime_patches import apply_all_patches
apply_all_patches()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--feedstock-cod", type=float, required=True)
    
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    
    try:
        # Load inputs from JSON (not from parent memory)
        logger.info("Loading inputs...")
        with open(Path(args.input_dir) / "basis.json") as f:
            basis = json.load(f)
        
        # Import heavy modules (subprocess-isolated)
        logger.info("Loading scipy (18 seconds)...")
        import scipy
        
        logger.info("Loading qsdsan...")
        from utils.qsdsan_simulation_sulfur import run_simulation
        
        # Run computation
        logger.info(f"Running simulation with COD={args.feedstock_cod}")
        results = run_simulation(
            basis=basis,
            feedstock_cod=args.feedstock_cod
        )
        
        # Write results to JSON
        with open(output_dir / "results.json", "w") as f:
            json.dump(results, f, indent=2)
        
        logger.info("Simulation complete")
        sys.exit(0)
    
    except Exception as e:
        logger.error(f"Simulation failed: {e}", exc_info=True)
        with open(output_dir / "error.json", "w") as f:
            json.dump({"error": str(e)}, f)
        sys.exit(1)

if __name__ == "__main__":
    main()
```

### Example 4: Agent Workflow

```python
# Agent script using the Background Job Pattern

# Step 1: Start sizing job
sizing_response = await tools.heuristic_sizing_ad(
    use_current_basis=True,
    target_srt_days=20
)
sizing_job_id = sizing_response["job_id"]
print(f"Sizing job started: {sizing_job_id}")

# Step 2: Poll for completion (doesn't block agent)
while True:
    status = await tools.get_job_status(sizing_job_id)
    print(f"Status: {status['status']} (elapsed: {status['elapsed_time_seconds']}s)")
    
    if status['status'] == 'completed':
        break
    
    # Wait before polling again (avoid busy-wait)
    await asyncio.sleep(5)

# Step 3: Get results
results = await tools.get_job_results(sizing_job_id)
print(f"Sizing results: {results['results']}")

# Step 4: Start simulation job
sim_response = await tools.simulate_ad_system_tool(
    use_current_state=True,
    validate_hrt=True
)
sim_job_id = sim_response["job_id"]

# Step 5: Poll for simulation (in parallel with other work)
while True:
    status = await tools.get_job_status(sim_job_id)
    
    if status['status'] == 'completed':
        break
    
    # Could do other work here
    await asyncio.sleep(10)

# Step 6: Get simulation results
results = await tools.get_job_results(sim_job_id)
print(f"Simulation complete: {results['results']}")
```

---

## Key Patterns

### Pattern 1: Pre-Created Job Directories

```python
# CRITICAL: Create job directory BEFORE launching subprocess
job_id = str(uuid.uuid4())[:8]
job_dir = Path("jobs") / job_id
job_dir.mkdir(parents=True, exist_ok=True)  # Create directory

# Serialize inputs to JSON
with open(job_dir / "input.json", "w") as f:
    json.dump(input_data, f)

# Now subprocess can access files
cmd = ["python", "cli.py", "--input-dir", str(job_dir)]
await manager.execute(cmd, job_id=job_id)
```

**Why?** JobManager validates that job_dir exists before launching subprocess. This prevents race conditions.

### Pattern 2: JSON File Communication

```
Don't:  Pass state as environment variables or arguments (too large)
        Import parent modules in subprocess (memory duplication)

Do:     Serialize state to JSON files
        Subprocess reads JSON files via argparse
        Subprocess writes results to JSON files
        Parent reads results from JSON files
```

**Example:**

```python
# Parent: serialize state
with open(job_dir / "adm1_state.json", "w") as f:
    json.dump(design_state.adm1_state, f)

# Child (CLI script): load state
with open(args.input_dir + "/adm1_state.json") as f:
    adm1_state = json.load(f)

# Child: write results
with open(args.output_dir + "/results.json", "w") as f:
    json.dump(results, f)

# Parent: load results
with open(job_dir / "results.json") as f:
    results = json.load(f)
```

### Pattern 3: State Patches for Automatic Hydration

```python
# Define state patch metadata
state_patch = {
    "field": "heuristic_config",           # design_state attribute
    "result_file": "results.json",         # file to load from
    "json_pointer": "/digester/volume"     # optional: extract subset
}

# JobManager applies patch after job completion
# This automatically loads results into design_state
# And persists to disk for crash recovery
```

**Benefits:**
- Eliminates manual result loading
- Provides crash recovery (results not lost if server crashes)
- Automatic persistence for agent continuity

### Pattern 4: Concurrency Control with Semaphore

```python
# Initialize JobManager with max concurrent jobs
manager = JobManager(max_concurrent_jobs=3)

# Internally uses semaphore to limit concurrent jobs
async with self.semaphore:  # Max 3 concurrent
    proc = await asyncio.create_subprocess_exec(...)
    await self._monitor_job(job_id, proc)
```

**Why limit?** 
- Prevent resource exhaustion (scipy + qsdsan per process = 500MB-1GB)
- Prevent system overload (spawn too many heavy processes)
- Ensure predictable performance

### Pattern 5: Crash Recovery with Metadata Persistence

```python
class JobManager:
    def _load_existing_jobs(self):
        """On server startup, recover job state from disk"""
        for job_file in self.jobs_dir.glob("*/job.json"):
            with open(job_file) as f:
                job = json.load(f)
            
            # Check if process still running
            if self._is_process_alive(job["pid"]):
                job["status"] = "running"  # Resume monitoring
            else:
                job["status"] = "failed"   # Mark as failed
            
            self.jobs[job["id"]] = job
        
        # Replay missed state updates
        self._reconciler.replay_missed_updates(self.jobs)
```

**Benefits:**
- Jobs survive server restart
- State hydration resumes where it left off
- No duplicate work if job completed but state not applied

### Pattern 6: Output Capture Without STDIO Blocking

```python
# Create subprocess with pipe redirection
proc = await asyncio.create_subprocess_exec(
    *cmd,
    stdout=asyncio.subprocess.PIPE,  # Capture, don't inherit
    stderr=asyncio.subprocess.PIPE,
    cwd=cwd
)

# In background, collect output to files (doesn't block)
async def _monitor_job(self, job_id, proc):
    stdout_data, stderr_data = await proc.communicate()
    
    # Write to files AFTER process completes
    with open(job_dir / "stdout.log", "wb") as f:
        f.write(stdout_data)
    with open(job_dir / "stderr.log", "wb") as f:
        f.write(stderr_data)
```

**Critical:** 
- Set `stdout=PIPE` and `stderr=PIPE` (don't inherit parent's STDIO)
- Use `await proc.communicate()` (collects all output without blocking)
- Write logs AFTER process exits

---

## Trade-offs and Considerations

### Advantages

| Advantage | Benefit |
|-----------|---------|
| **Non-blocking** | MCP STDIO always responsive, no timeouts |
| **Scalable** | Handle multiple long-running jobs concurrently |
| **Resilient** | Jobs survive server restarts, crash recovery |
| **Observable** | Agent can poll progress, check status, retrieve logs |
| **Isolated** | Heavy imports don't impact main process |
| **Persistent** | Results stored on disk, not lost if connection drops |

### Disadvantages

| Disadvantage | Mitigation |
|--------------|-----------|
| **Complexity** | Use this guide and reference implementation |
| **Latency** | Subprocess startup (2-5 seconds) + heavy imports (10-30 seconds) |
| **Disk I/O** | JSON serialization overhead (typically <100ms) |
| **Memory** | Each subprocess costs 500MB-1GB for scipy/qsdsan |
| **Job limit** | Concurrency control prevents spawning unlimited processes |

### When to Use This Pattern

**Use Job Pattern When:**
- Tool takes > 10 seconds
- Tool imports heavy libraries (scipy, pandas, tensorflow, qsdsan)
- Tool's stdout/stderr is verbose
- Tool might be called by multiple users concurrently
- Tool involves network I/O (API calls, database queries)

**Don't Use When:**
- Tool completes in < 1 second
- Tool is a simple lookup/calculation
- Tool doesn't import heavy libraries
- Tool is never called concurrently
- Tool is already async and non-blocking

### Performance Considerations

**Typical timings for anaerobic digester simulator:**

```
Tool invocation (validation, serialization):    ~50ms
Subprocess startup:                              ~1-2s
Python interpreter loading:                      ~0.5s
Heavy module imports (scipy, qsdsan, biosteam): ~18s
QSDsan system initialization:                    ~5s
ADM1 model convergence simulation:              ~120-300s
Result serialization:                            ~2-5s
State hydration:                                 ~50ms
───────────────────────────────────────────────────────
Total time:                                     ~150-330s

BUT: MCP STDIO is responsive after ~50ms!
     Agent can poll status and continue working.
```

### Resource Consumption

**Per subprocess (scipy + qsdsan):**
- Memory: 500MB - 1GB
- CPU cores: 1 (single-threaded)
- Disk: ~100MB for modules, ~1MB per job directory

**With max_concurrent_jobs=3:**
- Peak memory: 1.5GB - 3GB
- Peak CPU: 3 cores
- Disk: ~300MB per concurrently running job

**Mitigation strategies:**
- Set `max_concurrent_jobs` based on available resources
- Monitor system load with `psutil`
- Clean up old jobs: `rm -rf jobs/job_id`
- Consider containerization with resource limits

---

## Production Deployment

### Recommended Configuration

```python
# server.py initialization
def initialize_job_manager():
    """Setup background job infrastructure"""
    import psutil
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Auto-detect max concurrent jobs based on CPU count
    cpu_count = psutil.cpu_count(logical=True)
    max_jobs = max(2, cpu_count // 2)  # Conservative: 50% of CPUs
    
    logger.info(f"Initializing JobManager: max_concurrent_jobs={max_jobs}")
    
    manager = JobManager(max_concurrent_jobs=max_jobs)
    
    # Setup periodic cleanup of old jobs (older than 7 days)
    asyncio.create_task(periodic_job_cleanup())
    
    return manager

async def periodic_job_cleanup(days_old: int = 7):
    """Clean up old job directories periodically"""
    import time
    from pathlib import Path
    
    while True:
        await asyncio.sleep(3600)  # Every hour
        
        jobs_dir = Path("jobs")
        cutoff_time = time.time() - (days_old * 86400)
        
        for job_dir in jobs_dir.iterdir():
            if job_dir.is_dir():
                job_time = job_dir.stat().st_mtime
                if job_time < cutoff_time:
                    # Clean up old job
                    shutil.rmtree(job_dir)
```

### Logging and Monitoring

```python
# Setup detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('mcp_server.log'),
        logging.StreamHandler()
    ]
)

# Monitor long-running jobs
@mcp.tool()
async def get_system_status():
    """Get system status and running jobs"""
    manager = JobManager()
    jobs = await manager.list_jobs(status_filter="running")
    
    return {
        "running_jobs": len(jobs["jobs"]),
        "max_concurrent": jobs["max_concurrent"],
        "jobs": jobs["jobs"],
        "system": {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_mb": psutil.virtual_memory().used / 1024 / 1024
        }
    }
```

### Error Handling and Graceful Degradation

```python
# Tool-level error handling
@mcp.tool()
async def heavy_operation():
    """Heavy operation with robust error handling"""
    
    try:
        manager = JobManager()
        
        # Check system resources before launching
        mem = psutil.virtual_memory()
        if mem.percent > 90:
            return {
                "error": "Insufficient memory (>90% used)",
                "message": "Wait for running jobs to complete",
                "running_jobs": await manager.list_jobs()
            }
        
        # Execute job
        job = await manager.execute(cmd, job_id=job_id)
        
        return {
            "job_id": job["id"],
            "status": job["status"]
        }
    
    except Exception as e:
        logger.error(f"Job submission failed: {e}", exc_info=True)
        return {
            "error": "Job submission failed",
            "message": str(e)
        }
```

### Testing the Pattern

```python
# Test 1: Verify STDIO remains responsive
async def test_stdio_responsiveness():
    """Verify main process stays responsive during job"""
    
    # Start long job
    job_id = (await simulate_ad_system_tool())["job_id"]
    
    # Poll status repeatedly (should be fast)
    for i in range(5):
        start = time.time()
        status = await get_job_status(job_id)
        elapsed = time.time() - start
        
        assert elapsed < 0.1, f"Status check took {elapsed}s (should be <0.1s)"
        print(f"Poll {i}: {elapsed*1000:.1f}ms")

# Test 2: Verify results are complete
async def test_result_completeness():
    """Verify all results loaded into design_state"""
    
    job_id = (await heuristic_sizing_ad())["job_id"]
    
    # Wait for completion
    while True:
        status = await get_job_status(job_id)
        if status['status'] == 'completed':
            break
        await asyncio.sleep(2)
    
    # Check design_state has results
    assert design_state.heuristic_config is not None
    assert "digester" in design_state.heuristic_config
    assert "mixing" in design_state.heuristic_config

# Test 3: Verify crash recovery
async def test_crash_recovery():
    """Verify jobs survive server restart"""
    
    # Start job
    job_id = (await heuristic_sizing_ad())["job_id"]
    
    # Simulate server crash by creating new manager
    # (in production, server process restarts)
    del manager
    manager = JobManager()  # Loads jobs from disk
    
    # Job should still be in registry
    assert job_id in manager.jobs
    assert manager.jobs[job_id]["status"] in ["running", "completed"]
```

---

## Summary: The Pattern at a Glance

```
┌─────────────────────────────────────────────────────────────┐
│           THE BACKGROUND JOB PATTERN                        │
└─────────────────────────────────────────────────────────────┘

PROBLEM:   Long-running tools block MCP STDIO, causing timeouts

SOLUTION:  
  1. Tool returns job_id immediately (< 100ms)
  2. Subprocess runs in background (isolated)
  3. Subprocess output captured to files (not STDIO)
  4. Agent polls job status via get_job_status(job_id)
  5. Agent retrieves results via get_job_results(job_id)
  6. State automatically hydrated into design_state

KEY COMPONENTS:
  • JobManager: Launches and monitors subprocesses
  • CLI Wrappers: Standalone scripts that subprocess runs
  • JobStateReconciler: Loads results into server state
  • Job Metadata: Persisted on disk for crash recovery

BENEFITS:
  ✓ Non-blocking STDIO (no timeouts)
  ✓ Concurrent job execution (with limits)
  ✓ Crash recovery (jobs survive restart)
  ✓ Observable progress (agent can poll)
  ✓ Persistent results (no data loss)

IMPLEMENTATION:
  1. Create JobManager class with subprocess execution
  2. Create CLI wrapper for each heavy operation
  3. Create JobStateReconciler for auto-hydration
  4. Integrate into MCP tool handlers
  5. Provide get_job_status/results tools for agent
  6. Test crash recovery and resource limits

COMPLEXITY: High initial setup, but reusable across all tools
BENEFIT: Eliminates STDIO blocking forever
```

---

## References and Further Reading

- **MCP Protocol**: https://modelcontextprotocol.io/
- **Python asyncio**: https://docs.python.org/3/library/asyncio.html
- **JSON Pointer (RFC 6901)**: https://tools.ietf.org/html/rfc6901
- **Model Context Protocol GitHub Issues**:
  - #262: STDIO buffer size limiting
  - #1333: WSL2 blocking issues
  - #1141: Buffer management

---

## Appendix: Complete Reference Implementation

### File Structure

```
your-mcp-server/
├── server.py                          # Main MCP server with tool handlers
├── core/
│   └── state.py                       # Global design_state object
├── utils/
│   ├── job_manager.py                 # JobManager class
│   ├── job_state_reconciler.py        # State hydration
│   ├── runtime_patches.py             # Heavy module patches
│   ├── heuristic_sizing_cli.py        # Subprocess entry point
│   ├── simulate_cli.py                # Subprocess entry point
│   └── validate_cli.py                # Subprocess entry point
├── jobs/                              # Job directories created here
│   └── abc123/
│       ├── job.json                   # Job metadata
│       ├── basis.json                 # Input
│       ├── results.json               # Output
│       ├── stdout.log                 # Subprocess stdout
│       └── stderr.log                 # Subprocess stderr
└── state/                             # Persistent design_state backups
    ├── heuristic_config.json
    ├── simulation_results.json
    └── ...
```

### Critical Files for Copy-Paste

See the implementation files at:
- `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/utils/job_manager.py`
- `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/utils/job_state_reconciler.py`
- `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/utils/heuristic_sizing_cli.py`
- `/mnt/c/Users/hvksh/mcp-servers/anaerobic-design-mcp/utils/simulate_cli.py`

These are production-tested implementations ready for adaptation.

