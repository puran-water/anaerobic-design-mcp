# Background Job Pattern: FAQ and Common Questions

---

## General Questions

### Q: Why is my MCP server timing out?

**A:** Long-running tools that:
1. Import heavy libraries (scipy, tensorflow, qsdsan, pandas)
2. Perform heavy computation (>30 seconds)
3. Print verbose output to stdout

...all block the MCP STDIO channel. The agent gives up waiting after 30-60 seconds.

**Solution:** Use the Background Job Pattern to run these in isolated subprocesses.

### Q: What's the difference between this and asyncio?

**A:** 
- **asyncio alone**: Doesn't help if your code imports scipy. Heavy imports still happen in main process.
- **Background Job Pattern**: Launches subprocess, heavy imports happen there (not main process), main process stays responsive.

Think of it as:
- **asyncio**: Non-blocking I/O
- **Background Job Pattern**: Non-blocking heavy imports + computation

### Q: Can I use this with FastAPI/Flask?

**A:** Yes! The pattern works with any Python framework:
- FastAPI: Return job_id immediately, agent polls `/status/{job_id}`
- Flask: Same approach with HTTP endpoints
- MCP: This guide focuses on MCP, but adapts to any framework

### Q: Does this require Docker/Kubernetes?

**A:** No. Works with just Python:
- Single machine: Jobs run as subprocesses
- Distributed: You can adapt to queue-based system (Celery, RQ, etc.), but not required

---

## Technical Questions

### Q: Why not just use asyncio.sleep()?

**A:** Doesn't help. Example:

```python
# This still blocks STDIO
@mcp.tool()
async def slow_tool():
    await asyncio.sleep(0)  # Yield control
    
    # But now import scipy (18 seconds, synchronous)
    import scipy  # BLOCKS HERE
    
    # STDIO still blocked during import
    return scipy.compute()
```

**Solution:** Move scipy import to subprocess:

```python
@mcp.tool()
async def slow_tool():
    # Returns immediately
    job = await JobManager().execute(["python", "cli.py"])
    return {"job_id": job["id"]}

# cli.py (subprocess):
import scipy  # Import here (doesn't block parent STDIO)
results = scipy.compute()
```

### Q: Why write results to JSON files instead of returning?

**A:** Because:
1. **Subprocess isolation**: Parent and child have separate memory spaces
2. **Large data**: JSON files handle gigabytes; memory passing doesn't
3. **Crash recovery**: Results persist on disk even if server crashes
4. **Debugging**: Can inspect results without rerunning job

### Q: What if my job_id collides with another job?

**A:** Can't happen. `JobManager.execute()`:

```python
if job_id is None:
    job_id = str(uuid.uuid4())[:8]  # 8-char UUID (essentially unique)
else:
    if job_id in self.jobs:  # Check collision
        raise ValueError(f"Job ID {job_id} already exists")
    if not job_dir.exists():  # Check directory exists
        raise ValueError(f"Job directory missing")
```

### Q: Does the subprocess see changes to parent state?

**A:** No. Subprocess is isolated:

```python
# Parent process
design_state.config = {"value": 1}

# Start job
job = await manager.execute(["python", "cli.py"])

# Parent changes state
design_state.config = {"value": 2}

# Subprocess still sees {"value": 1} (unless it re-reads from file)
```

**Solution:** Subprocess should read inputs from JSON files, not parent memory.

### Q: Can I pass state to subprocess via environment variables?

**A:** Technically yes, practically no:

```python
# WORKS but fragile
cmd = ["python", "cli.py"]
env = {"STATE": json.dumps(huge_dict)}  # Fragile, max ~100KB
proc = await asyncio.create_subprocess_exec(*cmd, env=env)

# BETTER - use files
with open(job_dir / "state.json", "w") as f:
    json.dump(huge_dict, f)  # Unlimited size, readable, persistent
cmd = ["python", "cli.py", "--input-dir", str(job_dir)]
```

Use JSON files for anything >1KB.

### Q: What if my subprocess crashes?

**A:** JobManager detects and reports:

```python
# After subprocess exits with error code
job["status"] = "failed"
job["exit_code"] = 1
job["error"] = stderr_output[:500]

# Agent can check:
status = await get_job_status(job_id)
# Returns: {"status": "failed", "error": "...", "exit_code": 1}
```

Logs are saved to files:
```
jobs/abc123/stderr.log  # Captured stderr
jobs/abc123/stdout.log  # Captured stdout
```

### Q: Can jobs run in parallel?

**A:** Yes, limited by `max_concurrent_jobs`:

```python
manager = JobManager(max_concurrent_jobs=3)

# Job 1 starts
job1 = await manager.execute(cmd1)

# Job 2 starts (parallel, different subprocess)
job2 = await manager.execute(cmd2)

# Job 3 starts (parallel)
job3 = await manager.execute(cmd3)

# Job 4 waits (max_concurrent_jobs=3 limit hit)
job4 = await manager.execute(cmd4)  # Blocks until 1, 2, or 3 finishes
```

This prevents resource exhaustion (each job = 500MB-1GB memory).

### Q: How do I know when a job is done?

**A:** Poll `get_job_status()`:

```python
import asyncio

job_id = (await tool.start_job())["job_id"]

# Poll until done
while True:
    status = await tool.get_job_status(job_id)
    print(f"{status['status']}: {status['elapsed_time_seconds']}s")
    
    if status['status'] == 'completed':
        results = await tool.get_job_results(job_id)
        return results
    
    await asyncio.sleep(5)  # Poll every 5 seconds
```

Or subscribe to webhooks if using async server.

---

## Performance Questions

### Q: Why is there 18 seconds of overhead?

**A:** Heavy module imports:

```
Tool invocation:                 ~50ms
Subprocess creation:             ~1-2s
Python interpreter startup:      ~0.5s
scipy import:                    ~5s
qsdsan import:                   ~8s
biosteam import:                 ~2s
QSDsan initialization:           ~2s
───────────────────────────────
Total overhead:                  ~18s

(One-time per subprocess)
```

### Q: Can I reduce overhead?

**A:** Yes:

1. **Reuse processes**: Keep subprocess alive for multiple jobs (complex, not recommended)
2. **Pre-import modules**: Start a "warm" process on server startup
3. **Lazy imports**: Only import needed modules
4. **Cache imports**: Share subprocess across related jobs (uncommon)

For most use cases, 18s overhead is acceptable compared to 150+ second total job time.

### Q: How much memory does each subprocess use?

**A:** ~500MB-1GB:

```
Base Python:                   ~50MB
scipy + numpy:                 ~150MB
qsdsan + biosteam:            ~300MB
Job data in memory:           ~50-400MB
───────────────────────────
Per subprocess:               ~500MB-1GB
```

With `max_concurrent_jobs=3`: Peak ~1.5-3GB

**Mitigation:**
- Lower `max_concurrent_jobs` if constrained
- Run on larger server
- Clean up old jobs: `rm -rf jobs/old_job_id`

### Q: How long should my agent wait before polling?

**A:** Depends on expected job duration:

```python
# Fast job (< 1 minute)
await asyncio.sleep(1)  # Poll every 1s

# Medium job (1-10 minutes)
await asyncio.sleep(5)  # Poll every 5s

# Long job (> 10 minutes)
await asyncio.sleep(30)  # Poll every 30s
```

**Formula**: `wait_time = expected_job_duration / 10` (check 10 times before done)

---

## Debugging Questions

### Q: How do I check what's wrong with a job?

**A:** Check these files in order:

1. **Check metadata**:
```bash
cat jobs/abc123/job.json | jq
# Look for: status, error, exit_code, pid
```

2. **Check subprocess output**:
```bash
cat jobs/abc123/stdout.log
cat jobs/abc123/stderr.log
```

3. **Check results**:
```bash
cat jobs/abc123/results.json
```

4. **Check state**:
```bash
cat state/my_results.json  # If state patch applied
```

### Q: How do I manually kill a job?

**A:**

```bash
# Option 1: Use MCP tool
await terminate_job("abc123")

# Option 2: Manual kill
pid=$(jq .pid jobs/abc123/job.json)
kill -9 $pid

# Then update status
# (next get_job_status() will detect process is gone)
```

### Q: How do I rerun a failed job?

**A:** Remove the job directory and resubmit:

```bash
# Clean up failed job
rm -rf jobs/abc123

# Resubmit
response = await tool.start_job()
```

Or implement a `retry_job(job_id)` tool.

### Q: Why aren't results loading into design_state?

**A:** Check state patch:

```bash
# 1. Was state_patch registered?
jq .state_patch jobs/abc123/job.json

# Should show:
# {
#   "field": "my_results",
#   "result_file": "results.json"
# }

# 2. Did job complete successfully?
jq .status jobs/abc123/job.json  # Should be "completed"

# 3. Does result file exist?
ls -la jobs/abc123/results.json

# 4. Was state_applied?
jq .state_applied jobs/abc123/job.json  # Should be true

# 5. Check persisted state
ls -la state/my_results.json
```

### Q: How do I see job progress?

**A:** JobManager parses progress from stdout:

```bash
# In subprocess (utils/my_cli.py)
print("Progress: 50%")  # Will be captured in stdout.log
print("Day 10/20")      # Detected by JobManager

# Parent can retrieve
status = await get_job_status(job_id)
# Returns: {"progress": {"percent": 50, "message": "..."}}
```

---

## Deployment Questions

### Q: Can I use this in production?

**A:** Yes, with considerations:

```
Safety:        ✓ (subprocess isolation, crash recovery)
Reliability:   ✓ (disk persistence, job metadata)
Scalability:   ⚠ (single machine only, not distributed)
Monitoring:    ✓ (job status, logs available)
```

For multi-machine deployment, consider:
- Kubernetes (Job Pattern as job pod)
- Celery (Background Job Pattern runs in worker)
- Cloud Functions (AWS Lambda, Google Cloud Functions)

### Q: How do I monitor jobs in production?

**A:** Implement monitoring:

```python
# Periodic job cleanup
async def cleanup_old_jobs(days=7):
    while True:
        await asyncio.sleep(3600)
        jobs_dir = Path("jobs")
        for job_dir in jobs_dir.iterdir():
            age = time.time() - job_dir.stat().st_mtime
            if age > days * 86400:
                shutil.rmtree(job_dir)

# Health check
@mcp.tool()
async def get_system_status():
    manager = JobManager()
    jobs = await manager.list_jobs()
    return {
        "running_jobs": sum(1 for j in jobs if j["status"] == "running"),
        "completed_jobs": sum(1 for j in jobs if j["status"] == "completed"),
        "failed_jobs": sum(1 for j in jobs if j["status"] == "failed"),
        "disk_usage_mb": sum(d.stat().st_size for d in Path("jobs").glob("**/*")) / 1024**2
    }
```

### Q: How do I handle resource limits?

**A:**

```python
import psutil

async def check_resources():
    """Check if system has capacity for new job"""
    mem = psutil.virtual_memory()
    if mem.percent > 85:
        return {"error": "Insufficient memory"}
    
    cpu = psutil.cpu_percent(interval=0.1)
    if cpu > 90:
        return {"error": "High CPU usage"}
    
    return {"ok": True}

# Before submitting job
if not await check_resources():
    return {"error": "System overloaded"}
```

### Q: Should I use tmpfs for jobs/?

**A:** Not recommended:

```
✓ Pros:   Fast I/O (RAM-based)
✗ Cons:   Data lost on restart (defeats crash recovery)
          Limited size (runs out of RAM)

Better:   Use regular disk (/jobs)
          Or SSD for faster I/O
```

---

## Advanced Questions

### Q: Can I chain jobs (output of job1 → input of job2)?

**A:** Yes:

```python
# Job 1 completes, results in jobs/abc123/results.json
results1 = await get_job_results("abc123")

# Job 2 reads results1 as input
with open(job_dir2 / "input.json", "w") as f:
    json.dump(results1["results"], f)

job2 = await manager.execute(cmd2, job_id=job_id2)
```

Or build a DAG:

```python
# Start jobs 1, 2, 3 in parallel
jobs = [
    await start_job1(),
    await start_job2(),
    await start_job3()
]

# Wait for all to complete
for job_id in jobs:
    while (await get_job_status(job_id))["status"] != "completed":
        await asyncio.sleep(1)

# Job 4 depends on 1, 2, 3
results = [await get_job_results(jid) for jid in jobs]
await start_job4(results)
```

### Q: Can I cancel a running job?

**A:** Yes:

```python
# Terminate job
await terminate_job(job_id)

# Verify termination
status = await get_job_status(job_id)
# Returns: {"status": "terminated"}
```

### Q: How do I implement progress reporting?

**A:** Subprocess writes progress to file:

```python
# utils/my_cli.py
with open(job_dir / "progress.json", "w") as f:
    json.dump({"percent": 25, "step": "Loading modules"}, f)

# Parent reads periodically
progress = json.load(open(f"jobs/{job_id}/progress.json"))
```

Or parse from stdout:

```python
# utils/my_cli.py
for i in range(100):
    print(f"Progress: {i}%")  # Captured by JobManager

# Parent reads via get_job_status()
status = await get_job_status(job_id)
# Returns: {"progress": {"percent": i, "message": "..."}}
```

---

## Migration Questions

### Q: How do I migrate existing blocking tools?

**A:** Follow this process:

1. **Identify blocking tool**: Runs > 10 seconds, imports heavy modules
2. **Extract computation**: Move into separate function
3. **Create CLI wrapper**: Wrap function as command-line script
4. **Update tool handler**: Return job_id instead of result
5. **Test**: Verify returns immediately and results load

Example:

```python
# Before
@mcp.tool()
async def my_tool():
    result = my_computation()
    return result

# After
async def my_tool():
    # Pre-create job directory
    job_dir = Path("jobs") / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    
    # Serialize input
    with open(job_dir / "input.json", "w") as f:
        json.dump(design_state.input, f)
    
    # Submit job
    cmd = ["python", "utils/my_cli.py", "--input-dir", str(job_dir)]
    job = await JobManager().execute(cmd=cmd, job_id=job_id)
    
    # Register state patch
    job["state_patch"] = {"field": "result", "result_file": "results.json"}
    JobManager()._save_job_metadata(job)
    
    return {"job_id": job["id"]}

# Create utils/my_cli.py:
# Load input → my_computation() → Write results.json
```

### Q: Can I gradually migrate tools?

**A:** Yes:

- Start with 1-2 heaviest tools
- Add monitoring (`get_job_status`, `get_job_results`)
- Test agent workflow
- Gradually migrate more tools
- Eventually all long-running tools are job-based

---

## Troubleshooting Decision Tree

```
Problem: Tool times out
  │
  ├─ Check: Tool returns immediately?
  │  └─ No  → Use Background Job Pattern
  │  └─ Yes → Skip, check next issue
  │
  ├─ Check: Job status says "running"?
  │  └─ No  → Job failed, check status details
  │  └─ Yes → Poll until completed
  │
  ├─ Check: Results file exists?
  │  └─ No  → Subprocess error, check logs
  │  └─ Yes → Check results loaded
  │
  ├─ Check: State patch applied?
  │  └─ No  → Check state_patch registered
  │  └─ Yes → Results should be in design_state
  │
  └─ Check: design_state.field has value?
     └─ No  → Check if state_applied=true in job.json
     └─ Yes → SUCCESS
```

---

## Quick Reference

| Issue | Solution |
|-------|----------|
| Tool times out | Use Background Job Pattern |
| Job stuck "running" | Check process alive: `ps {pid}` |
| Results not in state | Verify state_patch registered |
| Out of memory | Lower max_concurrent_jobs |
| Subprocess crash | Check stderr.log |
| Job takes too long | Check logs for bottleneck |
| Can't find results | Check jobs/{job_id}/results.json exists |

---

## Further Reading

- Full Guide: `BACKGROUND_JOB_PATTERN.md`
- Quick Start: `BACKGROUND_JOB_QUICK_START.md`
- Reference Implementation: `anaerobic-design-mcp/` directory
- MCP Docs: https://modelcontextprotocol.io/

