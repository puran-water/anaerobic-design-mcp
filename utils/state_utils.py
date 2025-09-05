#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Utilities to sanitize and normalize ADM1 state inputs.

Supports values provided either as plain numerics or as
Codex-style triplets: [value, unit, explanation].

These helpers avoid unit-multiplication errors in Pyomo by
coercing inputs to native floats before applying units.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple
import math

logger = logging.getLogger(__name__)


def _to_float_maybe(x: Any) -> Optional[float]:
    """Attempt to coerce a value to float, returning None on failure."""
    if x is None:
        return None
    # Fast path for numeric types
    if isinstance(x, (int, float)):
        return float(x)
    # Strings: try direct and then regex (e.g., "0.5 kg/m3")
    if isinstance(x, str):
        try:
            return float(x)
        except Exception:
            match = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", x)
            if match:
                try:
                    return float(match.group(0))
                except Exception:
                    return None
            return None
    # Dicts with a typical numeric payload
    if isinstance(x, dict):
        for key in ("value", "val", "amount", "number"):
            if key in x:
                return _to_float_maybe(x[key])
        return None
    # Sequences: take first element as numeric if present
    if isinstance(x, (list, tuple)):
        if len(x) == 0:
            return None
        return _to_float_maybe(x[0])
    return None


def extract_numeric(value: Any, key: str = "") -> Optional[float]:
    """
    Extract a numeric float from a value that may be:
    - float/int
    - string (possibly with units text)
    - dict with a numeric under a common key (value/val/amount)
    - list/tuple like [value, unit, explanation]

    Returns None if a numeric cannot be obtained.
    """
    out = _to_float_maybe(value)
    if out is None:
        # Log at debug with the raw value; warn with the key for visibility
        logger.debug("extract_numeric: could not coerce value for %s: %r", key, value)
    return out


def clean_adm1_state(adm1_state: Dict[str, Any]) -> Tuple[Dict[str, float], List[str]]:
    """
    Normalize an ADM1 state mapping to numeric floats.

    - Accepts values as numerics or [value, unit, explanation]
    - Silently ignores units text and explanations (logging a debug note)
    - Returns (clean_state, warnings)
    """
    clean: Dict[str, float] = {}
    warnings: List[str] = []

    for comp, raw in (adm1_state or {}).items():
        num = extract_numeric(raw, key=comp)
        if num is None:
            msg = f"ADM1 component '{comp}' has non-numeric value {raw!r}; skipping."
            logger.warning(msg)
            warnings.append(msg)
            continue
        clean[comp] = float(num)

    return clean, warnings


def _carbonate_alpha_fractions(ph: float) -> Tuple[float, float, float]:
    """Return alpha0, alpha1, alpha2 for CO2 system at given pH.

    Uses pKa1 = 6.35, pKa2 = 10.33 at 25-35 C typical of AD.
    """
    # Convert pH to H+ concentration (mol/L)
    h = 10 ** (-ph)
    ka1 = 10 ** (-6.35)
    ka2 = 10 ** (-10.33)
    denom = h * h + h * ka1 + ka1 * ka2
    if denom <= 0:
        return 1.0, 0.0, 0.0
    alpha0 = (h * h) / denom
    alpha1 = (h * ka1) / denom
    alpha2 = (ka1 * ka2) / denom
    return alpha0, alpha1, alpha2


def regularize_adm1_state_for_initialization(
    clean_state: Dict[str, float],
    target_alkalinity_meq_l: Optional[float] = None,
    ph: float = 7.0,
) -> Tuple[Dict[str, float], List[str]]:
    """
    Produce a safe, self-consistent ADM1 state for AD initialization.

    Strategy:
    - Cap extreme VFAs and gases that destabilize acid-base system.
    - If a target alkalinity is provided, adjust VFAs and S_IC such that
      carbonate alkalinity + VFA alkalinity approximately matches target.
    - Ensure tiny but positive dissolved gases for numerical stability.
    - Set cations/anions to balanced defaults if wildly imbalanced.

    Returns (init_state, warnings).
    """
    warnings: List[str] = []
    state = dict(clean_state)  # shallow copy

    # Helper: get value or 0
    gv = lambda k, d=0.0: float(state.get(k, d) or 0.0)

    # 1) Cap dissolved gases to small positive values
    for comp, cap in ("S_h2", 1e-6), ("S_ch4", 1e-6):
        val = gv(comp)
        if val <= 0.0 or val > cap:
            state[comp] = min(max(val, 1e-9), cap)
            if val > cap:
                warnings.append(f"Capped {comp} from {val:g} to {state[comp]:g} kg/m3 for stability")

    # 2) Cap dissolved CO2 in liquid to modest value for init
    if gv("S_co2") > 0.01:
        warnings.append(f"Capped S_co2 from {gv('S_co2'):g} to 1e-3 kg/m3 for initialization")
    state["S_co2"] = min(max(gv("S_co2"), 1e-6), 1e-3)

    # 3) Cap VFAs to conservative initialization maxima (kg/m3)
    # Aggressive caps reduce acid-base stress and help AD find a feasible init point
    vfa_caps = {"S_ac": 0.1, "S_pro": 0.05, "S_bu": 0.05, "S_va": 0.03}
    for comp, cap in vfa_caps.items():
        val = gv(comp)
        if val > cap:
            state[comp] = cap
            warnings.append(f"Capped {comp} from {val:g} to {cap:g} kg/m3 for initialization")

    # 4) If target alkalinity is provided, tune VFAs and S_IC to match
    if target_alkalinity_meq_l is not None and target_alkalinity_meq_l > 0:
        # Compute current VFA alkalinity (mol/m3 ~= meq/L for monovalent)
        # Use COD -> mol conversions typical for ADM1 species
        acetate_mol = gv("S_ac") / 0.064  # 64 g COD/mol acetate
        propionate_mol = gv("S_pro") / 0.112
        butyrate_mol = gv("S_bu") / 0.160
        vfa_alk = acetate_mol + propionate_mol + butyrate_mol  # mol/m3 ~ meq/L

        # If VFA alkalinity already exceeds target, scale VFAs down
        if vfa_alk > 0.8 * target_alkalinity_meq_l:
            if vfa_alk > 0:
                scale = max(0.1, 0.5 * target_alkalinity_meq_l / vfa_alk)
                for comp in ("S_ac", "S_pro", "S_bu"):
                    original = gv(comp)
                    state[comp] = original * scale
                warnings.append(
                    f"Scaled VFAs by {scale:.3g} to reduce alkalinity from {vfa_alk:.1f} to"
                    f" <= ~{0.5*target_alkalinity_meq_l:.1f} meq/L for initialization"
                )
                # Recompute VFA alkalinity after scaling
                acetate_mol = gv("S_ac") / 0.064
                propionate_mol = gv("S_pro") / 0.112
                butyrate_mol = gv("S_bu") / 0.160
                vfa_alk = acetate_mol + propionate_mol + butyrate_mol

        # Set S_IC such that carbonate alkalinity ~ (target - vfa_alk)
        alpha0, alpha1, alpha2 = _carbonate_alpha_fractions(ph)
        rem_alk = max(target_alkalinity_meq_l - vfa_alk, 0.0)
        # At typical pH ~7, alkalinity ~ HCO3- + 2*CO3--, but alpha2 is tiny
        # Approximate CT (mol/m3) from HCO3- fraction
        if alpha1 <= 1e-6:
            ct_mol_m3 = rem_alk  # fallback
        else:
            ct_mol_m3 = rem_alk / max(alpha1, 1e-6)
        s_ic_kg_m3 = ct_mol_m3 * 0.012  # kg C/m3
        # Clip to conservative range for initialization
        s_ic_kg_m3 = float(min(max(s_ic_kg_m3, 0.01), 0.3))
        if abs(gv("S_IC") - s_ic_kg_m3) / max(s_ic_kg_m3, 1e-6) > 0.2:
            warnings.append(
                f"Adjusted S_IC from {gv('S_IC'):g} to {s_ic_kg_m3:g} kg C/m3 for alkalinity consistency"
            )
        state["S_IC"] = s_ic_kg_m3

    else:
        # Without an alkalinity target, just clip S_IC to a safe window
        s_ic_val = gv("S_IC", 0.05)
        if s_ic_val < 0.005 or s_ic_val > 0.5:
            new_val = float(min(max(s_ic_val, 0.01), 0.3))
            if new_val != s_ic_val:
                warnings.append(f"Clipped S_IC from {s_ic_val:g} to {new_val:g} kg C/m3 for initialization")
            state["S_IC"] = new_val

    # 5) Balance strong ions: set cations/anions to matched, moderate values
    s_cat = gv("S_cat")
    s_an = gv("S_an")
    if s_cat <= 0 or s_an <= 0 or abs(s_cat - s_an) > 0.02:
        state["S_cat"] = 0.04
        state["S_an"] = 0.04
        warnings.append("Set S_cat and S_an to 0.04 kmol/m3 for electroneutrality in initialization")

    return state, warnings
