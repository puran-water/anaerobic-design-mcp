"""Pydantic models and data structures for anaerobic digester design."""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

try:
    from pydantic import RootModel
except ImportError:
    RootModel = None


class BasisOfDesign(BaseModel):
    """Basic design parameters for anaerobic digester."""
    feed_flow_m3d: float = Field(description="Feed flow rate in m³/day")
    cod_mg_l: float = Field(description="COD concentration in mg/L")
    tss_mg_l: Optional[float] = Field(None, description="TSS concentration in mg/L")
    vss_mg_l: Optional[float] = Field(None, description="VSS concentration in mg/L")
    temperature_c: float = Field(35.0, description="Operating temperature in °C")
    tkn_mg_l: Optional[float] = Field(None, description="TKN concentration in mg/L")
    tp_mg_l: Optional[float] = Field(None, description="TP concentration in mg/L")
    alkalinity_meq_l: Optional[float] = Field(None, description="Alkalinity in meq/L")
    ph: Optional[float] = Field(None, description="pH value")


# Free-form dictionary type for FastMCP tool parameters
if RootModel is not None:
    class AnyDict(RootModel[Dict[str, Any]]):
        pass
else:
    # Fallback for environments without Pydantic v2
    class AnyDict(BaseModel):
        data: Dict[str, Any] = Field(default_factory=dict)