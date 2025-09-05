"""
Child process entrypoint for running AD simulations.

Reads JSON input from stdin, runs the simulation, and writes JSON to stdout.
All logging is routed to stderr to keep stdout strictly JSON-only.
"""

import sys
import json
import logging
from typing import Any, Dict


def _configure_child_logging() -> None:
    """Route logs to stderr in the child process to protect parent STDIO."""
    # Basic configuration: INFO level, stderr stream
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="[%(levelname)s] %(name)s: %(message)s")
    # Quiet extremely noisy loggers if needed
    for noisy in ("pyomo", "idaes", "watertap"):
        try:
            logging.getLogger(noisy).setLevel(logging.INFO)
        except Exception:
            pass


def main() -> int:
    _configure_child_logging()

    try:
        raw = sys.stdin.read()
        payload: Dict[str, Any] = json.loads(raw) if raw else {}
    except Exception as e:
        err = {"status": "error", "message": f"Invalid JSON input: {e}"}
        print(json.dumps(err), end="")
        return 1

    try:
        from .watertap_simulation_modified import simulate_ad_system

        basis_of_design = payload.get("basis_of_design") or {}
        adm1_state = payload.get("adm1_state") or {}
        heuristic_config = payload.get("heuristic_config") or {}
        costing_method = payload.get("costing_method", "WaterTAPCosting")
        initialize_only = bool(payload.get("initialize_only", False))
        tee = bool(payload.get("tee", False))

        results = simulate_ad_system(
            basis_of_design=basis_of_design,
            adm1_state=adm1_state,
            heuristic_config=heuristic_config,
            costing_method=costing_method,
            initialize_only=initialize_only,
            tee=tee,
        )

        print(json.dumps(results), end="")
        return 0
    except Exception as e:
        err = {"status": "error", "message": f"Simulation failed: {e}"}
        print(json.dumps(err), end="")
        return 2


if __name__ == "__main__":
    sys.exit(main())

