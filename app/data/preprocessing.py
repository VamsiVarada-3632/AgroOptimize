"""
Turns the OFFICIAL datasets into the structured, query-ready objects the rest of the
pipeline (fuzzy engine + NSGA-II + TOPSIS) consumes.

Stage 1 & 2 of the reference paper (Section III-B): gathers soil, rainfall, crop and
water-availability data for a given (district, season) and normalises it into a single
RegionSeasonProfile. Every input comes from the official database (app/datasets); quantities
the official data does not provide are None / NaN and the features needing them are reported
as unavailable - nothing is estimated and there is no synthetic fallback (the archived
synthetic data lives in legacy/ and is never imported here).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd

from app import config
from app.data.loader import load_all
from app.datasets import reference as ref
from app.datasets import service as svc

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CropCandidate:
    """One candidate crop for a (district, season). Official fields only; None = not published."""
    name: str
    crop_type: Optional[str]
    yield_kg_ha: float                       # official district yield (Season & Crop Report 2024-25)
    water_req_mm: Optional[float]            # not published numerically by TNAU -> None
    fert_n_kg_ha: float                      # TNAU Crop Production Guide blanket dose
    fert_p_kg_ha: float
    fert_k_kg_ha: float
    pesticide_cost_rs_ha: Optional[float]    # no official source -> None
    labor_days_ha: Optional[float]           # no official source -> None
    msp_rs_qtl: float                        # CACP/MSP notification KMS 2024-25
    revenue_rs_lakh_hist: float              # district area x yield x MSP (potential revenue at MSP, Rs lakh)
    crop_duration_days: Optional[int]        # not published numerically -> None
    sowing_month: Optional[str]
    harvest_month: Optional[str]
    irrigation_type: str                     # "Irrigated"/"Rainfed"/"Mixed" from the official irrigated area split
    rainfall_dependency: str                 # "<x>% rainfed" (unirrigated area share, official)
    # ---- official quantities added by the migration ----
    cost_rs_qtl: float = float("nan")        # CACP projected cost of cultivation (A2+FL), Rs/quintal
    rainfed_share: float = float("nan")      # unirrigated area / total area of this crop in the district (0-1)
    irrigated_share: float = float("nan")    # 1 - rainfed_share
    area_ha: float = float("nan")            # official district area under the crop
    revenue_rs_ha: float = float("nan")      # yield (q/ha) x MSP
    cost_rs_ha: float = float("nan")         # yield (q/ha) x CACP cost per quintal
    dose_rule: str = ""
    sources: dict = field(default_factory=dict)


@dataclass
class SoilProfile:
    """Soil Health Card derived. avg_ph/organic carbon values are not published (only class counts)."""
    soil_type: Optional[str]
    avg_ph: Optional[float]
    organic_carbon_percent: Optional[float]
    n_status: Optional[str]                  # dominant class among tested samples
    p_status: Optional[str]
    k_status: Optional[str]
    irrigation_percent: Optional[float]      # irrigated share of the district's cropped area (official)
    fertility_index: Optional[float]         # 0-100, share-weighted class score of N/P/K/OC (documented rule)
    samples_tested: Optional[int] = None
    shares: dict = field(default_factory=dict)


@dataclass
class RainfallProfile:
    avg_monthly_rainfall_mm: float
    avg_deviation_percent: float             # (sum actual - sum normal) / sum normal over the season's months
    avg_humidity_percent: Optional[float]    # not in the official rainfall dataset -> None
    avg_max_temp_c: Optional[float]
    avg_min_temp_c: Optional[float]
    months_used: List[str]
    effective_rainfall_mm: Optional[float]   # needs a utilisation factor: no official source -> None
    season_actual_mm: float = float("nan")
    season_normal_mm: float = float("nan")


@dataclass
class WaterProfile:
    avg_storage_percent: Optional[float]     # reservoir storage of mapped reservoirs; None if none mapped
    groundwater_status: Optional[str]
    avg_deficit_surplus_mcm: Optional[float]
    groundwater_level_m_bgl: Optional[float] = None
    reservoirs: List[str] = field(default_factory=list)


@dataclass
class RegionSeasonProfile:
    location: str
    year: int
    season: str
    soil: SoilProfile
    rainfall: RainfallProfile
    water: WaterProfile
    candidate_crops: List[CropCandidate] = field(default_factory=list)
    data_year_estimated: bool = False        # official data carries no "Estimated" rows
    excluded_crops: List[dict] = field(default_factory=list)   # [{crop, reasons}] - why a crop is not a candidate
    fuzzy_available: bool = True
    fuzzy_unavailable_reason: Optional[str] = None
    notes: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


from app.datasets.units import UNIT_BASIS_MISMATCH  # noqa: E402


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def canonical_choice(value: str, options: List[str], kind: str) -> str:
    """Case/whitespace-insensitive match of `value` against `options`,
    returning the canonical spelling (e.g. "coimbatore" -> "Coimbatore").
    Raises ValueError (mapped to HTTP 400 by the API) if nothing matches."""
    wanted = str(value).strip().lower()
    for option in options:
        if option.lower() == wanted:
            return option
    raise ValueError(f"Unknown {kind} '{value}'. Choose one of {options}.")


def observed_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Official frames contain observations only (no carried-forward estimates), so this is the identity;
    kept so callers written against the old data layer keep working."""
    return df


def is_estimated_year(location: str, year: int) -> bool:
    return False


def _none_if_nan(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else x


def _resolve_year(year: Optional[int]) -> int:
    years = sorted(int(y) for y in load_all()["crop"]["Year"].unique())
    if year is None:
        return years[-1]
    # reports are labelled 2024-25: accept the start year (2024)
    if int(year) not in years:
        raise ValueError(f"No official data for year={year}. Available years: {years} (report year {years[0]}-{str(years[0] + 1)[-2:]}).")
    return int(year)


TALUK_NOTES = {
    "pollachi": "Pollachi is a taluk of Coimbatore district. The official datasets are published per district, so "
                "taluk data is not available; use 'Coimbatore'.",
}


def resolve_location(location: str) -> str:
    key = str(location).strip().lower()
    if key in TALUK_NOTES:
        raise ValueError(TALUK_NOTES[key])
    return canonical_choice(location, config.LOCATIONS, "location")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_catalog() -> dict:
    """Discovery payload: what districts/years/seasons/crops exist in the official data."""
    crop_df = load_all()["crop"]
    ok = _candidate_mask(crop_df)
    return {
        "locations": config.LOCATIONS,
        "seasons": config.AG_SEASONS,
        "years": sorted(int(y) for y in crop_df["Year"].unique()),
        "crops_by_season": {
            season: sorted(crop_df.loc[(crop_df["Season"] == season) & ok, "Crop_Name"].unique().tolist())
            for season in config.AG_SEASONS
        },
        "taluk_notes": TALUK_NOTES,
        "data_sources": [{"dataset": r["name"], "file": r["filename"], "report_year": r["report_year"]} for r in svc.provenance()],
    }


def _candidate_mask(df: pd.DataFrame) -> pd.Series:
    need = ["Yield_Kg_Ha", "Fertilizer_N_Kg_Ha", "Fertilizer_P_Kg_Ha", "Fertilizer_K_Kg_Ha", "MSP_Rs_Qtl", "Cost_Rs_Qtl", "Irrigated_Share"]
    basis_ok = ~df["Crop_Name"].astype(str).str.lower().isin(UNIT_BASIS_MISMATCH)
    return df[need].notna().all(axis=1) & basis_ok


def _exclusion_reasons(r: pd.Series) -> List[str]:
    why = []
    basis = UNIT_BASIS_MISMATCH.get(str(r.Crop_Name).lower())
    if basis:
        why.append("price/yield unit basis differs and no official conversion factor is loaded: " + basis)
    if pd.isna(r.Yield_Kg_Ha):
        why.append(f"yield is not a mass unit ({r.Yield_Unit}); cannot be priced per quintal")
    if any(pd.isna(r[c]) for c in ("Fertilizer_N_Kg_Ha", "Fertilizer_P_Kg_Ha", "Fertilizer_K_Kg_Ha")):
        why.append("no complete TNAU fertiliser recommendation (" + str(r.Dose_Rule) + ")")
    if pd.isna(r.MSP_Rs_Qtl):
        why.append("no MSP for the report year in the official MSP notifications")
    elif pd.isna(r.Cost_Rs_Qtl):
        why.append("no CACP cost of cultivation for the report year")
    if pd.isna(r.Irrigated_Share):
        why.append("irrigated/unirrigated area not reported")
    return why or ["incomplete official data"]


def _season_months(season: str) -> List[str]:
    return list(config.SEASON_MONTH_MAP[season])


def get_region_season_profile(
    location: str,
    season: str,
    year: Optional[int] = None,
    max_candidate_crops: Optional[int] = None,
    rainfall_factor: float = 1.0,
    storage_override_pct: Optional[float] = None,
) -> RegionSeasonProfile:
    """Build the profile for one district/season from the official data.

    Scenario hooks (unchanged semantics):
    * `rainfall_factor` scales every monthly rainfall record; the season deviation is recomputed
      against the official normal.
    * `storage_override_pct` replaces the season's mean reservoir storage % (the fuzzy water input).
    """
    location = resolve_location(location)
    season = canonical_choice(season, config.AG_SEASONS, "season")
    resolved_year = _resolve_year(year)
    data = load_all()
    crop_df, land_df, rain_df, water_df = data["crop"], data["land"], data["rainfall"], data["water"]
    notes: List[str] = []
    unavailable: List[str] = []

    # ---- Soil (Soil Health Card) ----
    land_rows = land_df[(land_df["Location"] == location) & (land_df["Season"] == season)]
    if land_rows.empty:
        raise ValueError(f"No land data for {location}/{season}.")
    lr = land_rows.iloc[0]
    fert = _none_if_nan(lr.get("Soil_Fertility_Index"))
    soil_summary_ = svc.soil_health(location)
    from app.data import official_view as ov
    ss = ov.soil_summary(location)
    soil = SoilProfile(
        soil_type=None, avg_ph=None, organic_carbon_percent=None,
        n_status=_none_if_nan(lr.get("N_Status")), p_status=_none_if_nan(lr.get("P_Status")), k_status=_none_if_nan(lr.get("K_Status")),
        irrigation_percent=_none_if_nan(lr.get("Irrigation_Percent")), fertility_index=fert,
        samples_tested=None if ss is None else ss["samples_tested"],
        shares={} if ss is None else {k: ss[k] for k in ("n_shares", "p_shares", "k_shares", "oc_shares", "ph_shares")},
    )
    if fert is None:
        unavailable.append(f"no Soil Health Card data for {location}")

    # ---- Rainfall (IMD) over the season's months ----
    months = _season_months(season)
    rr = rain_df[(rain_df["Location"] == location) & (rain_df["Month"].isin(months))]
    if rr.empty:
        raise ValueError(f"No official rainfall data for {location}/season={season}.")
    actual = rr["Monthly_Rainfall_mm"].astype(float) * float(rainfall_factor)
    normal = rr["Normal_Rainfall_mm"].astype(float)
    dev = float((actual.sum() - normal.sum()) / normal.sum() * 100.0) if normal.sum() else float("nan")
    rainfall = RainfallProfile(
        avg_monthly_rainfall_mm=round(float(actual.mean()), 2), avg_deviation_percent=round(dev, 2),
        avg_humidity_percent=None, avg_max_temp_c=None, avg_min_temp_c=None, months_used=months,
        effective_rainfall_mm=None, season_actual_mm=round(float(actual.sum()), 1), season_normal_mm=round(float(normal.sum()), 1))
    if math.isnan(dev):
        unavailable.append("no official normal rainfall")

    # ---- Water (reservoirs mapped to the district; groundwater) ----
    wr = water_df[(water_df["Location"] == location) & (water_df["Month"].isin(months))]
    storage = wr["Storage_Percent"].dropna()
    gw = wr["Groundwater_Level_m_bgl"].dropna()
    res = svc.reservoirs_for(location)
    mean_storage = None if storage.empty else round(float(storage.mean()), 2)
    if storage_override_pct is not None:
        mean_storage = round(float(storage_override_pct), 2)
    water = WaterProfile(
        avg_storage_percent=mean_storage, groundwater_status=None, avg_deficit_surplus_mcm=None,
        groundwater_level_m_bgl=None if gw.empty else round(float(gw.mean()), 2),
        reservoirs=[] if res.empty else list(res.name))
    if 0 < len(storage) < len(months):
        notes.append(f"Reservoir storage covers {len(storage)} of the season's {len(months)} months (the official daily reservoir "
                     f"record starts 2025-01-01).")
    if mean_storage is None:
        unavailable.append("no official reservoir storage for this district and season (needs a mapped reservoir with readings inside the report year)")

    # ---- Candidate crops ----
    rows = crop_df[(crop_df["Location"] == location) & (crop_df["Season"] == season)]
    if rows.empty:
        raise ValueError(f"No official crop statistics for {location}/{season}.")
    ok = _candidate_mask(rows)
    cand_rows = rows[ok].sort_values("Revenue_Rs_Lakh", ascending=False)   # district-level potential revenue at MSP, as in the published method
    excluded = [{"crop": r.Crop_Name, "reasons": _exclusion_reasons(r)} for _, r in rows[~ok].iterrows()]
    top_n = max_candidate_crops or config.DEFAULT_MAX_CANDIDATE_CROPS
    cand_rows = cand_rows.head(max(top_n, config.MIN_CANDIDATE_CROPS))
    candidates = []
    for _, r in cand_rows.iterrows():
        rainfed = 1.0 - float(r.Irrigated_Share)
        candidates.append(CropCandidate(
            name=str(r.Crop_Name), crop_type=_none_if_nan(r.Crop_Type), yield_kg_ha=float(r.Yield_Kg_Ha), water_req_mm=None,
            fert_n_kg_ha=float(r.Fertilizer_N_Kg_Ha), fert_p_kg_ha=float(r.Fertilizer_P_Kg_Ha), fert_k_kg_ha=float(r.Fertilizer_K_Kg_Ha),
            pesticide_cost_rs_ha=None, labor_days_ha=None, msp_rs_qtl=float(r.MSP_Rs_Qtl),
            revenue_rs_lakh_hist=float(r.Revenue_Rs_Lakh), crop_duration_days=None, sowing_month=None, harvest_month=None,
            irrigation_type="Irrigated" if rainfed <= 0.2 else ("Rainfed" if rainfed >= 0.8 else "Mixed"),
            rainfall_dependency=f"{rainfed:.0%} rainfed", cost_rs_qtl=float(r.Cost_Rs_Qtl), rainfed_share=round(rainfed, 4),
            irrigated_share=round(float(r.Irrigated_Share), 4), area_ha=float(r.Area_Ha), revenue_rs_ha=float(r.Revenue_Rs_Ha),
            cost_rs_ha=float(r.Cost_Rs_Ha), dose_rule=str(r.Dose_Rule),
            sources={"agronomy": r.Dose_Source, "price": r.Price_Source, "crop_statistics": "TN Season & Crop Report 2024-25"}))
    if len(candidates) < config.MIN_CANDIDATE_CROPS:
        raise ValueError(
            f"Only {len(candidates)} crop(s) in {location}/{season} have complete official data (yield, TNAU dose, MSP and "
            f"CACP cost); need at least {config.MIN_CANDIDATE_CROPS}. Excluded: "
            + "; ".join(f"{e['crop']} ({e['reasons'][0]})" for e in excluded[:6]))
    notes.append("Seasons follow the official reports (Kharif/Rabi); rice uses Kar/Kuruvai/Sornavari for Kharif and Samba/Thaladi/Pishanam for Rabi.")
    return RegionSeasonProfile(
        location=location, year=resolved_year, season=season, soil=soil, rainfall=rainfall, water=water,
        candidate_crops=candidates, data_year_estimated=False, excluded_crops=excluded,
        fuzzy_available=not unavailable, fuzzy_unavailable_reason="; ".join(unavailable) or None, notes=notes)


# Reference ranges used to produce a human-readable [0,1] snapshot of the raw inputs for API
# transparency. Rainfall is scaled to the official distribution of monthly rainfall; the deviation
# range is the +/-60 % universe of the fuzzy rainfall variable; storage is a percentage.
def _ranges() -> dict:
    rain = load_all()["rainfall"]["Monthly_Rainfall_mm"]
    return {"avg_monthly_rainfall_mm": (0.0, float(rain.max())), "avg_deviation_percent": (-60.0, 60.0), "avg_storage_percent": (0.0, 100.0)}


def _minmax(value, key: str):
    if value is None:
        return None
    lo, hi = _ranges()[key]
    return round(max(0.0, min(1.0, (value - lo) / (hi - lo))), 3) if hi != lo else 0.5


def normalized_snapshot(profile: RegionSeasonProfile) -> dict:
    fi = profile.soil.fertility_index
    return {
        "rainfall_norm": _minmax(profile.rainfall.avg_monthly_rainfall_mm, "avg_monthly_rainfall_mm"),
        "rainfall_deviation_norm": _minmax(profile.rainfall.avg_deviation_percent, "avg_deviation_percent"),
        "water_storage_norm": _minmax(profile.water.avg_storage_percent, "avg_storage_percent"),
        "soil_fertility_index_norm": None if fi is None else round(fi / 100.0, 3),
    }
