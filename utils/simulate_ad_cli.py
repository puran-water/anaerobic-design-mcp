"""
Child process entrypoint for running AD simulations.

This module implements subprocess isolation for WaterTAP simulations to prevent
stdout/stderr contamination of the MCP server's STDIO communication channel.

Pattern:
1. Parent MCP server spawns this as a subprocess
2. Reads JSON input from stdin (simulation parameters)
3. Runs WaterTAP simulation with all logging routed to stderr
4. Writes JSON results to stdout
5. Parent parses JSON from stdout, ignoring any warnings on stderr

This isolation is critical because IDAES/Pyomo/WaterTAP can emit warnings
and solver output that would corrupt the MCP JSON protocol if mixed with
the response stream.
"""

import sys
import json
import logging
from typing import Any, Dict


def _configure_child_logging() -> None:
    """Route logs to stderr in the child process to protect parent STDIO."""
    # Basic configuration: INFO level, stderr stream
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="[%(levelname)s] %(name)s: %(message)s")
    
    # Configure IDAES logging to stderr and suppress warnings
    try:
        import idaes
        # Redirect IDAES console handler to stderr
        idaes.cfg["logging"]["handlers"]["console"]["stream"] = "ext://sys.stderr"
        # Set IDAES loggers to ERROR level to suppress warnings
        idaes.cfg["logging"]["loggers"]["idaes"]["level"] = "ERROR"
        idaes.cfg["logging"]["loggers"]["pyomo"]["level"] = "ERROR"
        idaes.cfg["logging"]["loggers"]["watertap"]["level"] = "ERROR"
        # Apply the configuration
        idaes.reconfig()
    except Exception:
        pass
    
    # Also set Python logging levels for these packages
    for noisy in ("pyomo", "idaes", "watertap"):
        try:
            logging.getLogger(noisy).setLevel(logging.ERROR)
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

