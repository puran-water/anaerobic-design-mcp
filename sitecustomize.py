"""Project-specific interpreter customizations.

Ensures legacy versions of `fluids` expose the `PY37` attribute expected by
`thermo`/`thermosteam` when running under Python ≥3.7. This mirrors upstream
behaviour and prevents import errors during simulations.
"""

try:  # pragma: no cover - defensive import hook
    import fluids.numerics as _fluids_numerics

    if not hasattr(_fluids_numerics, "PY37"):
        _fluids_numerics.PY37 = True
except Exception:
    # Silently ignore so that unrelated imports are unaffected.
    pass

