"""
Job State Reconciler - Automatic Design State Hydration

This module provides automatic loading of background job results into the
server's in-memory design_state after job completion. This solves the problem
where background jobs run in isolated subprocesses and cannot directly update
the parent process's state.

Architecture:
1. Tools register a `state_patch` in job metadata (field name, result file)
2. JobManager calls reconciler after job completion
3. Reconciler loads result file and updates design_state
4. State is also persisted to disk for crash recovery
5. On server restart, missed updates are replayed

Usage:
    # In server.py tool:
    state_patch = {
        "field": "heuristic_config",
        "result_file": "results.json",
        "json_pointer": None  # Optional: JSONPath to extract subset
    }

    # In JobManager._monitor_job():
    if job["status"] == "completed" and "state_patch" in job:
        reconciler = JobStateReconciler()
        reconciler.apply(job)
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class JobStateReconciler:
    """
    Reconciles background job results with server's in-memory design_state.

    This class handles automatic state updates after job completion, providing:
    - Crash recovery (replay missed updates on restart)
    - Disk persistence (mirror state to state/*.json files)
    - Idempotency (safe to apply same update multiple times)
    """

    def __init__(self, state_dir: Path = None):
        """
        Initialize reconciler.

        Args:
            state_dir: Directory for persisted state files (default: ./state)
        """
        self.state_dir = state_dir or Path("state")
        self.state_dir.mkdir(exist_ok=True)

    def apply(self, job: Dict[str, Any]) -> bool:
        """
        Apply state patch from completed job to design_state.

        Args:
            job: Job metadata dict with "state_patch" key

        Returns:
            True if state was updated, False if skipped/failed
        """
        # Check if already applied
        if job.get("state_applied"):
            logger.debug(f"State patch already applied for job {job['id']}")
            return False

        # Extract state patch metadata
        state_patch = job.get("state_patch")
        if not state_patch:
            logger.debug(f"No state patch for job {job['id']}")
            return False

        field = state_patch.get("field")
        result_file = state_patch.get("result_file")
        json_pointer = state_patch.get("json_pointer")

        if not field or not result_file:
            logger.error(f"Invalid state_patch for job {job['id']}: missing field or result_file")
            return False

        # Load result file from job directory
        job_dir = Path(job["job_dir"])
        result_path = job_dir / result_file

        if not result_path.exists():
            logger.error(f"Result file not found: {result_path}")
            return False

        try:
            with open(result_path, 'r') as f:
                result_data = json.load(f)

            # Extract subset using JSON pointer if specified
            if json_pointer:
                result_data = self._extract_json_pointer(result_data, json_pointer)

            # Update design_state
            from core.state import design_state
            setattr(design_state, field, result_data)

            # Persist to disk
            state_file = self.state_dir / f"{field}.json"
            with open(state_file, 'w') as f:
                json.dump(result_data, f, indent=2, allow_nan=False)

            logger.info(f"Applied state patch for job {job['id']}: {field} <- {result_path.name}")
            return True

        except Exception as e:
            logger.error(f"Failed to apply state patch for job {job['id']}: {e}", exc_info=True)
            return False

    def replay_missed_updates(self, jobs: Dict[str, Dict[str, Any]]) -> int:
        """
        Replay state patches for completed jobs that were missed (e.g., after crash).

        This is called on server startup to restore state from completed jobs
        whose results were never loaded into design_state.

        Args:
            jobs: Dict of job_id -> job metadata

        Returns:
            Number of state patches successfully replayed
        """
        count = 0
        for job_id, job in jobs.items():
            if job.get("status") == "completed" and job.get("state_patch") and not job.get("state_applied"):
                logger.info(f"Replaying missed state update for job {job_id}")
                if self.apply(job):
                    count += 1

        if count > 0:
            logger.info(f"Replayed {count} missed state updates")

        return count

    def _extract_json_pointer(self, data: Any, pointer: str) -> Any:
        """
        Extract value from JSON using JSON Pointer (RFC 6901).

        Examples:
            pointer="/results/digester" extracts data["results"]["digester"]
            pointer="/0" extracts data[0]

        Args:
            data: JSON data
            pointer: JSON Pointer string (e.g., "/results/metrics")

        Returns:
            Extracted value
        """
        if not pointer or pointer == "/":
            return data

        parts = pointer.lstrip('/').split('/')
        current = data

        for part in parts:
            # Handle array indices
            if isinstance(current, list):
                try:
                    current = current[int(part)]
                except (ValueError, IndexError) as e:
                    raise ValueError(f"Invalid JSON pointer '{pointer}': {e}")
            # Handle dict keys
            elif isinstance(current, dict):
                if part not in current:
                    raise ValueError(f"JSON pointer '{pointer}' not found: key '{part}' missing")
                current = current[part]
            else:
                raise ValueError(f"JSON pointer '{pointer}' invalid: cannot traverse {type(current)}")

        return current

    def refresh_field_from_disk(self, field: str) -> bool:
        """
        Load a field from disk into design_state (fallback/recovery mechanism).

        This provides a self-healing path when design_state is empty but
        persisted state exists on disk.

        Args:
            field: Field name (e.g., "heuristic_config")

        Returns:
            True if loaded successfully, False otherwise
        """
        state_file = self.state_dir / f"{field}.json"

        if not state_file.exists():
            logger.debug(f"No persisted state for field: {field}")
            return False

        try:
            with open(state_file, 'r') as f:
                data = json.load(f)

            from core.state import design_state
            setattr(design_state, field, data)

            logger.info(f"Refreshed {field} from disk: {state_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to refresh {field} from disk: {e}", exc_info=True)
            return False
