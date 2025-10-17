"""State management for anaerobic digester design."""

from typing import Dict, Any


class ADDesignState:
    """Manages state across tools for anaerobic digester design."""

    def __init__(self):
        self.basis_of_design = {}
        self.adm1_state = {}
        self.heuristic_config = {}
        self.simulation_results = {}
        self.economic_results = {}
        self.last_simulation = None  # Cache for optional analysis tools

    def reset(self):
        """Reset all state."""
        self.__init__()

    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary."""
        result = {
            "basis_of_design": self.basis_of_design,
            "adm1_state": self.adm1_state,
            "heuristic_config": self.heuristic_config,
            "simulation_results": self.simulation_results,
            "economic_results": self.economic_results
        }

        # Add lightweight simulation summary if available
        if self.last_simulation:
            result["last_simulation_summary"] = {
                "timestamp": str(self.last_simulation.get("timestamp", "N/A")),
                "status": self.last_simulation.get("status", "N/A"),
                "converged_at": self.last_simulation.get("converged_at", "N/A")
            }

        return result


# Global state instance
design_state = ADDesignState()