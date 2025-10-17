"""
H2S Speciation for Anaerobic Digestion.

Reuses PHREEQC-based speciation from degasser-design-mcp following DRY principle.

This module provides pH-dependent H2S/HS⁻ speciation calculations and
gas-liquid distribution estimates for anaerobic digester design.
"""
import sys
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Add degasser-design-mcp to path for module reuse (DRY principle)
degasser_path = Path(__file__).parent.parent.parent / "degasser-design-mcp"
if str(degasser_path) not in sys.path:
    sys.path.insert(0, str(degasser_path))

try:
    from utils.speciation import strippable_fraction, effective_inlet_concentration
    PHREEQC_AVAILABLE = True
    logger.info("Successfully imported PHREEQC-based speciation from degasser-design-mcp")
except ImportError as e:
    PHREEQC_AVAILABLE = False
    logger.warning(f"Could not import degasser speciation module: {e}")
    logger.warning("Falling back to Henderson-Hasselbalch approximation")

# Re-export for local use
__all__ = ['strippable_fraction', 'effective_inlet_concentration',
           'calculate_h2s_distribution', 'PHREEQC_AVAILABLE']


def calculate_h2s_distribution(
    S_IS_total_kg_m3: float,
    pH: float,
    temp_c: float = 35.0,
    gas_transfer_fraction: float = 0.7
) -> dict:
    """
    Calculate H2S distribution between aqueous and gas phases.

    Uses degasser-design-mcp speciation module for pH-dependent H2S/HS⁻ split
    (PHREEQC-based if available, Henderson-Hasselbalch fallback),
    then applies gas transfer for biogas estimation.

    Args:
        S_IS_total_kg_m3: Total dissolved sulfide (kg S/m³)
        pH: Effluent pH
        temp_c: Temperature (°C), default 35°C for mesophilic digestion
        gas_transfer_fraction: Fraction of H2S(aq) that transfers to biogas (default 0.7)

    Returns:
        Dictionary with:
        - S_IS_total_mg_l: Total sulfide (mg S/L)
        - S_H2S_aq_mg_l: Aqueous H2S concentration (mg S/L)
        - S_HS_mg_l: Bisulfide concentration (mg S/L)
        - fraction_H2S: Fraction as H2S(aq) (0-1)
        - H2S_biogas_ppm_estimate: Rough biogas H2S estimate (ppm)
        - warning: Corrosion warning if >1000 ppm
        - method: Calculation method used

    Example:
        >>> dist = calculate_h2s_distribution(S_IS_total_kg_m3=0.05, pH=7.2, temp_c=35.0)
        >>> print(f"Biogas H2S: {dist['H2S_biogas_ppm_estimate']:.0f} ppm")
    """
    # Convert to mg/L
    S_IS_total_mg_l = S_IS_total_kg_m3 * 1000

    if PHREEQC_AVAILABLE:
        try:
            # Use PHREEQC-based speciation (DRY - reuse degasser code)
            fraction_H2S = strippable_fraction(
                solute="H2S",
                ph=pH,
                temp_c=temp_c,
                total_mg_l=S_IS_total_mg_l
            )
            method = "PHREEQC (degasser-design-mcp)"
        except Exception as e:
            logger.warning(f"PHREEQC calculation failed: {e}, using Henderson-Hasselbalch")
            fraction_H2S = _henderson_hasselbalch_h2s(pH, temp_c)
            method = "Henderson-Hasselbalch (fallback)"
    else:
        # Fallback to Henderson-Hasselbalch
        fraction_H2S = _henderson_hasselbalch_h2s(pH, temp_c)
        method = "Henderson-Hasselbalch (PHREEQC not available)"

    # Calculate species concentrations
    S_H2S_aq_mg_l = S_IS_total_mg_l * fraction_H2S
    S_HS_mg_l = S_IS_total_mg_l * (1 - fraction_H2S)

    # Estimate gas transfer (simplified)
    H2S_transferred = S_H2S_aq_mg_l * gas_transfer_fraction

    # Very rough biogas H2S estimate (ppm)
    # Rule of thumb: 1 mg/L H2S in liquid ≈ 10-15 ppm in biogas at typical biogas production rates
    # Using 12.5 as middle value
    H2S_biogas_ppm_estimate = H2S_transferred * 12.5

    # Generate warnings
    warning = None
    if H2S_biogas_ppm_estimate > 5000:
        warning = f"CRITICAL: Very high biogas H2S ({H2S_biogas_ppm_estimate:.0f} ppm) - severe corrosion risk"
    elif H2S_biogas_ppm_estimate > 1000:
        warning = f"WARNING: High biogas H2S ({H2S_biogas_ppm_estimate:.0f} ppm) - corrosion risk, treatment needed"
    elif H2S_biogas_ppm_estimate > 500:
        warning = f"CAUTION: Moderate biogas H2S ({H2S_biogas_ppm_estimate:.0f} ppm) - biogas upgrading recommended"

    return {
        'S_IS_total_mg_l': S_IS_total_mg_l,
        'S_H2S_aq_mg_l': S_H2S_aq_mg_l,
        'S_HS_mg_l': S_HS_mg_l,
        'pH': pH,
        'temp_c': temp_c,
        'fraction_H2S': fraction_H2S,
        'fraction_HS': 1 - fraction_H2S,
        'gas_transfer_fraction': gas_transfer_fraction,
        'H2S_biogas_ppm_estimate': H2S_biogas_ppm_estimate,
        'warning': warning,
        'method': method
    }


def _henderson_hasselbalch_h2s(pH: float, temp_c: float = 35.0) -> float:
    """
    Fallback Henderson-Hasselbalch calculation for H2S speciation.

    Used when PHREEQC is not available.

    Args:
        pH: Water pH
        temp_c: Temperature (°C)

    Returns:
        Fraction of total sulfide as H2S(aq) (0-1)

    Note:
        pKa1 for H2S ⇌ HS⁻ + H⁺ is temperature-dependent:
        - 25°C: pKa1 ≈ 7.0
        - 35°C: pKa1 ≈ 6.95 (slight decrease with temperature)
    """
    # Temperature-corrected pKa1 (simplified linear approximation)
    # pKa decreases by ~0.005 per °C above 25°C
    pKa1_25C = 7.0
    pKa1 = pKa1_25C - 0.005 * (temp_c - 25.0)

    # Henderson-Hasselbalch: fraction_H2S = 1 / (1 + 10^(pH - pKa))
    fraction_H2S = 1.0 / (1.0 + 10**(pH - pKa1))

    return fraction_H2S


if __name__ == "__main__":
    # Test the module
    logging.basicConfig(level=logging.INFO)

    print("=== H2S Speciation Module Test ===\n")

    print("1. H2S Distribution at Different pH Values (35°C):")
    print(f"   {'pH':<5} {'H2S(aq)%':<10} {'HS⁻%':<10} {'Biogas ppm':<12} {'Warning'}")
    print("   " + "-"*70)

    for ph in [6.0, 6.5, 7.0, 7.5, 8.0, 8.5]:
        dist = calculate_h2s_distribution(
            S_IS_total_kg_m3=0.05,  # 50 mg S/L
            pH=ph,
            temp_c=35.0
        )
        print(f"   {ph:<5.1f} {dist['fraction_H2S']*100:<10.1f} "
              f"{dist['fraction_HS']*100:<10.1f} {dist['H2S_biogas_ppm_estimate']:<12.0f} "
              f"{dist['warning'] if dist['warning'] else 'OK'}")

    print("\n2. High Sulfide Case (100 mg S/L at pH 7.2):")
    dist_high = calculate_h2s_distribution(
        S_IS_total_kg_m3=0.1,  # 100 mg S/L
        pH=7.2,
        temp_c=35.0
    )
    print(f"   Total sulfide: {dist_high['S_IS_total_mg_l']:.0f} mg S/L")
    print(f"   H2S(aq): {dist_high['S_H2S_aq_mg_l']:.1f} mg S/L ({dist_high['fraction_H2S']*100:.1f}%)")
    print(f"   HS⁻: {dist_high['S_HS_mg_l']:.1f} mg S/L ({dist_high['fraction_HS']*100:.1f}%)")
    print(f"   Estimated biogas H2S: {dist_high['H2S_biogas_ppm_estimate']:.0f} ppm")
    print(f"   Method: {dist_high['method']}")
    if dist_high['warning']:
        print(f"   ⚠️  {dist_high['warning']}")
