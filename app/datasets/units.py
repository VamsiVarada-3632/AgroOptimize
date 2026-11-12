"""Unit normalisation. Base units: area ha; production tonne; yield kg_per_ha.
Counts (coconut nuts) stay in nuts: they are NOT convertible to mass without an official nut weight,
so they are flagged unit_std='nuts' / 'nuts_per_ha' and the optimiser treats them as 'no mass yield'."""
from __future__ import annotations

BALE_KG_LINT = 170.0          # a bale of lint is 170 kg (stated in the unit label itself)
NUTS_PER_LAKH = 100_000.0

def to_std(measure: str, unit: str, value):
    """-> (unit_std, value_std). value may be None."""
    if value is None or value != value:
        return _std_name(measure, unit), None
    u = str(unit).strip().lower()
    if measure == "area":
        return "ha", float(value)
    if measure == "production":
        if u.startswith("tonnes"):
            return "tonne", float(value)                       # incl. "tonnes of cane", "tonnes (cured nuts)", "tonnes of gur"
        if u.startswith("bales of 170 kg lint"):
            return "tonne", float(value) * BALE_KG_LINT / 1000.0
        if u == "lakh nuts":
            return "nuts", float(value) * NUTS_PER_LAKH
    if measure == "yield":
        if u in ("kg / ha", "kg / ha (cured nuts)", "kg lint / ha", "kg of gur / ha"):
            return "kg_per_ha", float(value)
        if u in ("tonnes / ha", "tonnes of cane / ha"):
            return "kg_per_ha", float(value) * 1000.0
        if u == "nuts / ha":
            return "nuts_per_ha", float(value)
    raise ValueError(f"Unsupported unit {unit!r} for measure {measure!r}")

def _std_name(measure, unit):
    try:
        return to_std(measure, unit, 0.0)[0]
    except ValueError:
        return None

MCFT_TO_MCM = 0.0283168466     # 1 million cubic feet in million cubic metres
CUSEC_TO_M3S = 0.0283168466


# Crops whose official yield is NOT on the same basis as the official MSP / CACP cost (both per quintal of the
# harvested produce). No official conversion factor (ginning outturn, milling outturn) is loaded, so these crops are
# excluded from optimisation rather than converted with an assumed factor. Re-enable by loading the official factor.
UNIT_BASIS_MISMATCH = {
    "cotton": "official yield is kg of lint/ha; MSP and CACP cost are per quintal of kapas (seed cotton)",
    "rice": "official production/yield is in terms of rice; MSP and CACP cost are per quintal of paddy",
}
