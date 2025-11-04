"""
Runtime Patches for Library Compatibility Issues

This module provides runtime patches for known compatibility issues in dependencies.
Import and call patches at the top of CLI entry points BEFORE importing QSDsan/biosteam.
"""

def ensure_py37_flag():
    """
    Patch fluids.numerics.PY37 attribute for compatibility with thermo<=0.4.2.

    Issue: fluids>=1.2 removed the PY37 flag, but thermo<=0.4.2 (QSDsan dependency)
    still checks for it. This causes AttributeError during QSDsan imports.

    Solution: Inject the flag at runtime before any QSDsan/biosteam imports.

    References:
    - CalebBell/fluids: Removed PY37 in v1.2
    - CalebBell/thermo: Still uses numerics.PY37 check in v0.4.2
    """
    import fluids.numerics

    if not hasattr(fluids.numerics, "PY37"):
        # Python ≥3.7 satisfies the original intent (we're on 3.12)
        fluids.numerics.PY37 = True


def apply_all_patches():
    """
    Apply all runtime patches.

    Call this function at the top of CLI entry points before importing
    any heavy dependencies (QSDsan, biosteam, thermosteam, etc.)
    """
    ensure_py37_flag()
