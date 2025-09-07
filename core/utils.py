"""Utility functions for anaerobic digester design."""

import json
from typing import Any, Dict, Optional, Union


def to_float(value: Union[float, int, str, None]) -> Optional[float]:
    """
    Convert value to float with robust error handling.
    
    Args:
        value: Input value to convert
        
    Returns:
        Float value or None if conversion fails
    """
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def coerce_to_dict(value: Optional[Any]) -> Optional[Dict[str, Any]]:
    """Coerce tool inputs to a plain dict.

    Supports:
    - dict
    - JSON string
    - Pydantic RootModel with `.root`
    - Fallback BaseModel with `.data`
    """
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return None
    # Pydantic v2 RootModel
    if hasattr(value, "root") and isinstance(getattr(value, "root"), dict):
        return getattr(value, "root")
    # Fallback BaseModel with `data`
    if hasattr(value, "data") and isinstance(getattr(value, "data"), dict):
        return getattr(value, "data")
    return None