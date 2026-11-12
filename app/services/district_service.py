"""
District Intelligence: everything the project knows about one district,
assembled into a single structured payload (overview, climate, soil, water,
crop history, crop suitability, historical prices, insights, summary).

Rules
-----
* Every figure comes from the official government datasets (see /api/datasets). District data is a single
  report year (TN Season & Crop Report 2024-25); multi-year context comes only from the official state-level
  series (1965-2024). Nothing is estimated.
* No value is estimated. Anything the dataset does not contain is returned
  as `None` with a `note`, and the UI shows "Data not available".
* Existing calculations are reused, not re-implemented:
    - soil fertility index        -> Soil Health Card class shares (datasets.service / official_view)
    - region/season profiles      -> preprocessing.get_region_season_profile
    - fuzzy assessment and labels -> fuzzy.engine
    - per-crop yield/cost/water/environmental values
                                  -> FarmPlanProblem's own objective function,
                                     evaluated for one-crop, one-hectare plans
    - min-max goodness            -> ranking.topsis_scores
    - statement format            -> explanation_service.make_item
* Thresholds that turn numbers into words are named constants below and
  documented in docs/handbook/DISTRICT_INTELLIGENCE.md.

The payload is a pure function of the official database, so it is cached per district.
"""

from __future__ import annotations

import datetime as _dt
from functools import lru_cache
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from app import config
from app.data import preprocessing as pp
from app.data.loader import load_all
from app.decision import ranking
from app.fuzzy import engine as fz
from app.optimization.problem import FarmPlanProblem
from app.services.explanation_service import make_item

# ---------------------------------------------------------------------------
# Wording thresholds (documented in DISTRICT_INTELLIGENCE.md)
# ---------------------------------------------------------------------------
STABLE_CHANGE_PCT = 5.0      # |first -> last observed change| below this reads "stable"
LOW_CV = 0.10                # coefficient of variation below this = low variability
HIGH_CV = 0.25               # at or above this = high variability
MAJOR_CROPS = 5              # how many crops the overview lists
LOW_STORAGE_PCT = 40.0       # same threshold the dashboard uses for its irrigation action
CONCENTRATED_SHARE_PCT = 50  # one crop holding this share of a season's area = concentrated

MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]
NOT_AVAILABLE = "Data not available"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _f(x, digits=2) -> Optional[float]:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return round(float(x), digits)


def trend(years: List[int], values: List[float]) -> Optional[dict]:
    """Change between the first and last observed year, least-squares slope
    per year, and coefficient of variation, with a direction label."""
    pairs = [(int(y), float(v)) for y, v in zip(years, values) if v is not None and not np.isnan(v)]
    if len(pairs) < 2:
        return None
    pairs.sort()
    ys, vs = np.array([p[0] for p in pairs]), np.array([p[1] for p in pairs])
    first, last = vs[0], vs[-1]
    change = None if abs(first) < 1e-12 else (last - first) / abs(first) * 100
    mean = vs.mean()
    cv = float(vs.std(ddof=1) / abs(mean)) if abs(mean) > 1e-12 else None
    if np.allclose(vs, vs[0]):
        direction = "unchanged"
    elif change is not None and abs(change) < STABLE_CHANGE_PCT:
        direction = "stable"
    else:
        direction = "increasing" if last > first else "decreasing"
    return {
        "first_year": int(ys[0]), "last_year": int(ys[-1]), "first": _f(first, 3), "last": _f(last, 3),
        "change_pct": _f(change, 1), "slope_per_year": _f(np.polyfit(ys, vs, 1)[0], 3),
        "cv": _f(cv, 3), "variability": variability_label(cv), "direction": direction, "n_years": len(pairs),
    }


def variability_label(cv: Optional[float]) -> Optional[str]:
    if cv is None:
        return None
    return "low" if cv < LOW_CV else "moderate" if cv < HIGH_CV else "high"


def _describe_trend(name: str, t: Optional[dict], unit: str = "", digits: int = 1) -> str:
    if t is None:
        return f"{name}: not enough observed years to describe a trend."
    if t["direction"] == "unchanged":
        return f"{name} is identical in every observed year ({t['first']:.{digits}f}{unit}, {t['first_year']}–{t['last_year']})."
    word = {"stable": "has remained stable", "increasing": "has increased", "decreasing": "has decreased"}[t["direction"]]
    return (f"{name} {word}: {t['first']:.{digits}f}{unit} in {t['first_year']} to {t['last']:.{digits}f}{unit} in "
            f"{t['last_year']} ({t['change_pct']:+.1f}%), with {t['variability']} year-to-year variability (CV {t['cv']:.3f}).")


def _slice(df: pd.DataFrame, location: str) -> pd.DataFrame:
    return df[df["Location"] == location]


def _nan(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else x


def _na(note: str) -> dict:
    return {"available": False, "note": note}


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def _coverage(location: str, data: Dict[str, pd.DataFrame]) -> dict:
    from app.datasets import service as svc
    files = []
    for kind, df in data.items():
        d = _slice(df, location)
        files.append({"kind": kind, "rows": int(len(d)), "observed_rows": int(len(d))})
    prov = svc.provenance()
    crop = _slice(data["crop"], location)
    seasons = {s: sorted(int(y) for y in crop.loc[crop["Season"] == s, "Year"].unique()) for s in config.AG_SEASONS}
    years = sorted({int(y) for y in crop["Year"].unique()})
    rain = _slice(data["rainfall"], location)
    water = _slice(data["water"], location)
    return {
        "observed_years": years, "estimated_years": [], "seasons_available": seasons, "files": files,
        "monthly_completeness_pct": {
            "rainfall": _f(100 * rain["Monthly_Rainfall_mm"].notna().sum() / 12, 1),
            "water": _f(100 * water["Storage_Percent"].notna().sum() / 12, 1)},
        "last_dataset_update": max((p["imported_at"] for p in prov), default=None) and max(p["imported_at"] for p in prov)[:10],
        "last_dataset_update_basis": "Most recent import of the official datasets into the local database.",
        "provenance": [f"{p['name']} ({p['filename']}, report year {p['report_year']}, sha256 {p['sha256'][:12]})" for p in prov],
        "report_year": "2024-25",
        "note": "District data is one report year; there is no district-level history in the official files supplied.",
    }


def _climate(location: str, data) -> dict:
    rain = _slice(data["rainfall"], location).copy()
    if rain.empty or rain["Monthly_Rainfall_mm"].notna().sum() == 0:
        return {**_na(NOT_AVAILABLE), "annual": [], "monthly": [], "met_season_share": [], "agri_seasons": [],
                "stated_annual_normal_mm": None, "trends": {"rainfall": None, "temperature": None, "humidity": None, "rainy_days": None}}
    rain["mi"] = rain["Month"].map(MONTHS.index)
    rain = rain.sort_values(["Year", "mi"])
    year = int(rain["Year"].max())
    tot, nor = rain["Monthly_Rainfall_mm"].sum(), rain["Normal_Rainfall_mm"].sum()
    annual = [{"year": year, "total_mm": _f(tot, 1), "normal_mm": _f(nor, 1), "deviation_pct": _f((tot - nor) / nor * 100, 1) if nor else None,
               "rainy_days": None, "mean_temp_c": None, "max_temp_c": None, "min_temp_c": None, "humidity_pct": None}]
    monthly = [{"year": int(r.Year), "month": r.Month, "month_index": MONTHS.index(r.Month) + 1,
                "rainfall_mm": _f(r.Monthly_Rainfall_mm, 1), "normal_mm": _f(r.Normal_Rainfall_mm, 1),
                "max_temp_c": None, "min_temp_c": None, "humidity_pct": None, "met_season": r.IMD_Season}
               for r in rain.itertuples()]
    met = [{"season": s, "share_pct": _f(100 * g["Monthly_Rainfall_mm"].sum() / tot, 1), "mean_mm_per_year": _f(g["Monthly_Rainfall_mm"].sum(), 1)}
           for s, g in rain.groupby("IMD_Season")] if tot else []
    met.sort(key=lambda m: -(m["share_pct"] or 0))
    agri = []
    for season, months in config.SEASON_MONTH_MAP.items():
        g = rain[rain["Month"].isin(months)]
        agri.append({"season": season, "months": months, "mean_total_mm": _f(g["Monthly_Rainfall_mm"].sum(), 1),
                     "normal_mm": _f(g["Normal_Rainfall_mm"].sum(), 1), "by_year": {year: _f(g["Monthly_Rainfall_mm"].sum(), 1)}, "trend": None})
    return {"available": True, "annual": annual, "monthly": monthly, "met_season_share": met, "agri_seasons": agri,
            "stated_annual_normal_mm": _f(nor, 1),
            "trends": {"rainfall": None, "temperature": None, "humidity": None, "rainy_days": None},
            "note": "IMD district rainfall for the report year. Temperature, humidity and rainy days are not in the official datasets supplied."}


def _soil(location: str, data) -> dict:
    land = _slice(data["land"], location)
    if land.empty or land["Soil_Fertility_Index"].isna().all():
        return _na("Soil Health Card data not available for this district.")
    r = land.iloc[0]
    fi = float(r.Soil_Fertility_Index)
    mem = fz.input_memberships(0, 50, fi)["soil_fert"]
    label = max(mem, key=mem.get)
    year = int(r.Year)
    rec = {"year": year, "season": "All", "soil_type": None, "ph": None, "organic_carbon_pct": None,
           "n_status": r.N_Status, "p_status": r.P_Status, "k_status": r.K_Status, "oc_status": r.OC_Status, "fertility_index": _f(fi, 1)}
    from app.datasets import service as svc
    shc = svc.soil_health(location) or {}
    def share(k):
        t = sum(shc.get(f"{k}_{c}", 0) for c in ("low", "medium", "high")) or None
        return None if not t else {c: _f(100 * shc[f"{k}_{c}"] / t, 1) for c in ("low", "medium", "high")}
    shares = {k: share(k) for k in ("n", "p", "k", "oc")}
    limitations, characteristics = [], []
    for nutrient, key in (("Nitrogen", "n_status"), ("Phosphorus", "p_status"), ("Potassium", "k_status"), ("Organic carbon", "oc_status")):
        b = rec[key]
        k = key.split("_")[0]
        characteristics.append(make_item(f"soil-{key}", f"{nutrient} status",
                                         f"Most tested samples in {location} are {b} in {nutrient.lower()} ({shares[k]}).",
                                         "Soil Health Card", {"dominant": b, "shares_pct": shares[k]}))
        if b == "Low":
            limitations.append(make_item(f"limit-{key}", f"Low {nutrient.lower()}", f"{nutrient} is Low in the largest share of samples.",
                                         "Soil Health Card", {"status": b, "shares_pct": shares[k]}))
    crop = _slice(data["crop"], location)
    grown = [{"crop_type": t, "crops": sorted(map(str, names))} for t, names in crop.groupby("Crop_Type")["Crop_Name"].unique().items()]
    return {"available": True, "soil_types": [], "records": [rec], "latest_year": year,
            "latest": {"ph": None, "organic_carbon_pct": None, "n_status": r.N_Status, "p_status": r.P_Status, "k_status": r.K_Status,
                       "oc_status": r.OC_Status, "fertility_index_mean": _f(fi, 1), "fuzzy_set": label, "fuzzy_membership": mem,
                       "samples_tested": _nan(r.Soil_Samples_Tested), "class_shares_pct": shares,
                       "ph_class_counts": {k: shc.get(k) for k in ("ph_acidic", "ph_neutral", "ph_alkaline")}},
            "trends": {"ph": None, "organic_carbon": None, "fertility_index": None},
            "characteristics": characteristics, "limitations": limitations, "crop_categories_grown": grown,
            "crop_categories_basis": "Crop types recorded for this district in the official Season & Crop Report. There is no official "
                                     "soil-to-crop suitability table; see Crop suitability for the computed ranking.",
            "note": "Soil Health Card publishes class counts (Low/Medium/High), not pH or organic-carbon values."}


def _water(location: str, data) -> dict:
    w = _slice(data["water"], location).copy()
    land = _slice(data["land"], location)
    if w.empty or (w["Storage_Percent"].isna().all() and w["Groundwater_Level_m_bgl"].isna().all()):
        return _na("Water data not available for this district.")
    w["mi"] = w["Month"].map(MONTHS.index)
    w = w.sort_values("mi")
    year = int(w["Year"].max())
    sto = w.dropna(subset=["Storage_Percent"])
    storage_by_month = [{"month": r.Month, "storage_pct": _f(r.Storage_Percent, 1), "varies_between_years": False} for r in sto.itertuples()]
    by_season = []
    for season, months in config.SEASON_MONTH_MAP.items():
        g = sto[sto["Month"].isin(months)]
        if g.empty:
            by_season.append({"season": season, "storage_pct": None, "fuzzy_set": None, "below_action_threshold": None,
                              "note": "No official reservoir record for this season."})
            continue
        pct = float(g["Storage_Percent"].mean())
        by_season.append({"season": season, "storage_pct": _f(pct, 1), "fuzzy_set": _water_set(pct), "below_action_threshold": pct < LOW_STORAGE_PCT,
                          "months_covered": int(len(g))})
    gw = w.dropna(subset=["Groundwater_Level_m_bgl"])
    irrig = _nan(land["Irrigation_Percent"].iloc[0]) if not land.empty else None
    stress = []
    have = [s for s in by_season if s["storage_pct"] is not None]
    if have:
        low = [s for s in have if s["below_action_threshold"]]
        stress.append(make_item("storage-low-season", "Seasonal storage",
                                (f"Mean reservoir storage falls below {LOW_STORAGE_PCT:.0f}% in {', '.join(s['season'] for s in low)}." if low else
                                 f"Mean reservoir storage stays at or above {LOW_STORAGE_PCT:.0f}% in every season with records."),
                                "TN Water Resources Dept", {"by_season": by_season, "threshold_pct": LOW_STORAGE_PCT}))
    else:
        stress.append(make_item("storage-none", "Reservoir storage", "No official reservoir storage is mapped to this district for the report year.",
                                "TN Water Resources Dept", {}))
    gwl = [{"month": r.Month, "level_mbgl": _f(r.Groundwater_Level_m_bgl, 2)} for r in gw.itertuples()]
    return {"available": True,
            "yearly": [{"year": year, "irrigation_mcm": None, "drinking_mcm": None, "industrial_mcm": None, "total_demand_mcm": None,
                        "inflow_mcm": None, "storage_pct": _f(sto["Storage_Percent"].mean(), 1) if len(sto) else None,
                        "groundwater_mbgl": _f(gw["Groundwater_Level_m_bgl"].mean(), 2) if len(gw) else None, "irrigation_share_pct": None}],
            "storage_by_month": storage_by_month, "storage_identical_every_year": False, "storage_by_season": by_season,
            "reservoir_capacity_mcm": None, "primary_sources": [],
            "groundwater": {"level_mbgl_by_year": {year: _f(gw["Groundwater_Level_m_bgl"].mean(), 2)} if len(gw) else {},
                            "level_by_month": gwl, "level_varies": len(gw) > 1, "status_distribution": [], "most_common_status": None},
            "irrigation_dependency": {"irrigated_pct_by_year": {year: _f(irrig, 1)} if irrig is not None else {}, "trend": None},
            "trends": {"inflow": None, "irrigation_demand": None, "irrigation_share": None},
            "stress_indicators": stress,
            "glossary": {"storage_pct": "Reservoir storage as % of capacity (daily levels averaged by month); the fuzzy model's water input.",
                         "groundwater_mbgl": "Groundwater depth in metres below ground level (deeper = scarcer).",
                         "irrigated_pct": "Irrigated area as % of the district's cropped area (Season & Crop Report)."},
            "note": "Official reservoir daily data starts 2025-01-01, so storage exists only for Jan-Feb of the Rabi window and only for districts "
                    "with a mapped reservoir. Water demand, inflow and capacity are not in the official files supplied."}


def _water_set(pct: float) -> str:
    return max(fz.input_memberships(0, pct, 50)["water_storage"].items(), key=lambda kv: kv[1])[0]


def _crops(location: str, data) -> dict:
    crop = _slice(data["crop"], location).copy()
    if crop.empty:
        return {"available": False, "note": NOT_AVAILABLE, "records": [], "trends": []}
    season_area = crop.groupby(["Year", "Season"])["Area_Ha"].transform("sum")
    crop["area_share_pct"] = crop["Area_Ha"] / season_area * 100
    records = [{"year": int(r.Year), "season": r.Season, "crop": r.Crop_Name, "crop_type": r.Crop_Type,
                "area_ha": _f(r.Area_Ha, 0), "area_share_pct": _f(r.area_share_pct, 1), "production_t": _f(r.Production_Tonnes, 0),
                "yield_t_ha": _f(r.Yield_Kg_Ha / 1000, 3), "price_rs_qtl": _f(r.MSP_Rs_Qtl, 2), "cost_rs_qtl": _f(r.Cost_Rs_Qtl, 2),
                "revenue_rs_lakh": _f(r.Revenue_Rs_Lakh, 0)}
               for r in crop.sort_values(["Season", "Crop_Name", "Year"]).itertuples()]
    from app.datasets import service as svc
    trends = []
    for (season, name), g in crop.groupby(["Season", "Crop_Name"]):
        ser = svc.state_series(name, "yield")
        yt = trend(ser.year_start.tolist(), (ser.value_std / 1000).tolist()) if len(ser) else None
        trends.append({"season": season, "crop": name, "mean_area_ha": _f(g["Area_Ha"].mean(), 0),
                       "mean_area_share_pct": _f(g["area_share_pct"].mean(), 1), "mean_yield_t_ha": _f(g["Yield_Kg_Ha"].mean() / 1000, 3),
                       "production": None, "area": None, "yield": yt, "yield_trend_basis": "Tamil Nadu state series 1965-2024 (official)"})
    trends.sort(key=lambda t: -(t["mean_area_ha"] or 0))
    return {"available": True, "records": records, "trends": trends,
            "filters": {"seasons": sorted(crop["Season"].unique().tolist()), "crops": sorted(crop["Crop_Name"].unique().tolist()),
                        "years": sorted(int(y) for y in crop["Year"].unique())}}


def _suitability(location: str, crops: dict) -> dict:
    """Score every candidate crop, per season, from the components the official data supports (each 0-1, equal weights).
    Per-hectare yield, cost, irrigated and fertiliser quantities come from FarmPlanProblem's own objective function."""
    if not crops.get("records"):
        return {"available": False, "note": NOT_AVAILABLE, "rankings": []}
    trend_by = {(t["season"], t["crop"]): t for t in crops["trends"]}
    rows = []
    year = None
    for season in config.AG_SEASONS:
        try:
            profile = pp.get_region_season_profile(location, season, max_candidate_crops=12)
        except ValueError:
            continue
        year = profile.year
        assessment = fz.assess_profile(profile)
        problem = FarmPlanProblem(profile, assessment, total_land_ha=1.0)
        metrics = problem.single_crop_metrics()
        yields = np.array([m["yield_t_ha"] for m in metrics]); costs = np.array([m["cost_rs_ha"] for m in metrics])
        irr = np.array([m["irrigated_ha_per_ha"] for m in metrics]); envs = np.array([m["env_per_ha"] for m in metrics])
        _, goodness = ranking.topsis_scores(yields, costs, irr, envs, ranking.preference_weights("balanced"))
        max_share = max((trend_by.get((season, c.name), {}).get("mean_area_share_pct") or 0) for c in profile.candidate_crops) or 1.0
        for i, c in enumerate(profile.candidate_crops):
            t = trend_by.get((season, c.name), {})
            yield_cv = (t.get("yield") or {}).get("cv")
            comps = {
                "climate_soil": float(problem.crop_vec.crop_yield_confidence[i]) if assessment is not None else None,
                "rainfall_fit": None,   # crop water requirement (mm) is not published numerically
                "prominence": (t.get("mean_area_share_pct") or 0) / max_share,
                "yield_stability": 1 - min(1.0, yield_cv) if yield_cv is not None else None,
                "resource_efficiency": float(np.mean([goodness[1][i], goodness[2][i], goodness[3][i]])),
            }
            scored = [v for v in comps.values() if v is not None]
            rows.append({
                "crop": c.name, "season": season, "crop_type": c.crop_type, "year_basis": year,
                "score": round(100 * float(np.mean(scored)), 1),
                "components": {k: None if v is None else round(v, 3) for k, v in comps.items()},
                "expected_yield_t_ha": round(float(yields[i]), 2), "historical_mean_yield_t_ha": t.get("mean_yield_t_ha"),
                "water_req_mm": c.water_req_mm, "irrigated_share": _f(c.irrigated_share, 3), "irrigation_need_l_ha": None,
                "cost_rs_ha": round(float(costs[i]), 0), "env_impact_per_ha": round(float(envs[i]), 2),
                "rainfall_dependency": c.rainfall_dependency, "duration_days": c.crop_duration_days,
                "mean_area_share_pct": t.get("mean_area_share_pct"), "production_trend": None,
                "fuzzy_applied": assessment is not None,
            })
    rows.sort(key=lambda r: (-r["score"], r["crop"]))
    for rank, r in enumerate(rows, start=1):
        r["rank"] = rank
    for season in config.AG_SEASONS:
        for rank, r in enumerate([r for r in rows if r["season"] == season], start=1):
            r["season_rank"] = rank
    return {"available": bool(rows), "year_basis": year, "rankings": rows,
            "method": ("Score = mean of the available 0-1 components, x100: climate & soil (fuzzy crop confidence, when official reservoir data "
                       "exists for the season), prominence (share of the season's area relative to the most widely grown crop), yield "
                       "stability (1 - coefficient of variation of the official state yield series 1965-2024) and resource efficiency "
                       "(min-max goodness of cost, irrigated area and fertiliser use per hectare). Rainfall fit is not scored because crop "
                       "water requirement in mm is not published in the official data. Per-hectare values come from the optimiser's "
                       "objective function for a one-crop, one-hectare plan at baseline input levels.")}


def _market(crops: dict) -> dict:
    items = []
    seen = set()
    for r in crops["records"]:
        if r["price_rs_qtl"] is None or r["crop"] in seen:
            continue
        seen.add(r["crop"])
        items.append({"crop": r["crop"], "prices_by_year": {r["year"]: r["price_rs_qtl"]}, "mean_rs_qtl": r["price_rs_qtl"],
                      "cost_rs_qtl": r["cost_rs_qtl"], "trend": None})
    items.sort(key=lambda i: i["crop"])
    return {"available": bool(items), "is_live": False,
            "note": "Official MSP (KMS 2024-25, CACP notification) and CACP projected cost of cultivation (A2+FL). Not live market prices; "
                    "Agmarknet mandi prices are not in the datasets supplied.",
            "crops": items, "strongest_price_growth": [], "weakest_price_growth": []}


def _overview(location: str, data, coverage: dict, climate: dict, soil: dict, water: dict, crops: dict) -> dict:
    from app.datasets import service as svc
    land = _slice(data["land"], location)
    lu = svc.land_use(location) or {}
    ly = land.iloc[0] if not land.empty else None
    annual = climate.get("annual") or []
    major = [{"crop": t["crop"], "season": t["season"], "mean_area_ha": t["mean_area_ha"], "mean_area_share_pct": t["mean_area_share_pct"]}
             for t in crops["trends"][:MAJOR_CROPS]]
    return {"district": location, "coordinates": None,
            "coordinates_note": "District coordinates are not in the official datasets supplied.",
            "agricultural_zone": None, "agricultural_zone_note": "No agro-climatic zone field in the official datasets supplied.",
            "agricultural_area_ha": _f(lu.get("Net area sown"), 0), "total_area_ha": _f(lu.get("Total geographical area"), 0),
            "gross_area_sown_ha": _f(lu.get("Gross area sown"), 0),
            "irrigated_pct": _f(ly.Irrigation_Percent, 1) if ly is not None else None,
            "land_year_basis": coverage["observed_years"][-1] if coverage["observed_years"] else None,
            "land_basis": "Season & Crop Report 2024-25 land-use classification.",
            "soil_types": soil.get("soil_types", []),
            "average_annual_rainfall_mm": annual[0]["total_mm"] if annual else None,
            "stated_annual_normal_mm": climate.get("stated_annual_normal_mm"),
            "average_temperature_c": None, "average_humidity_pct": None,
            "primary_irrigation_sources": [], "major_crops": major, "seasons_available": coverage["seasons_available"],
            "observed_years": coverage["observed_years"], "estimated_years": [], "last_dataset_update": coverage["last_dataset_update"],
            "taluk_note": "Pollachi is a taluk of Coimbatore; taluk-level data is not available." if location == "Coimbatore" else None}


def _insights(location, climate, soil, water, crops, market, suitability) -> List[dict]:
    out = []
    annual = climate.get("annual") or []
    if annual and annual[0]["normal_mm"]:
        a = annual[0]
        out.append(make_item("rainfall-normal", "Rainfall against the IMD normal",
                             f"{a['year']} rainfall was {a['total_mm']:.0f} mm, {abs(a['deviation_pct']):.0f}% "
                             f"{'above' if a['deviation_pct'] >= 0 else 'below'} the {a['normal_mm']:.0f} mm normal.", "IMD", a))
    if climate.get("met_season_share"):
        top = climate["met_season_share"][0]
        out.append(make_item("rainfall-season", "When the rain falls", f"The {top['season']} brings {top['share_pct']:.0f}% of the year's rainfall; "
                             + ", ".join(f"{m['season']} {m['share_pct']:.0f}%" for m in climate["met_season_share"][1:]) + ".", "IMD",
                             {"shares": climate["met_season_share"]}))
    for season in config.AG_SEASONS:
        shares = [t for t in crops["trends"] if t["season"] == season]
        if shares:
            top = max(shares, key=lambda t: t["mean_area_share_pct"] or 0)
            out.append(make_item(f"concentration-{season}", f"{season} cropping pattern",
                                 f"{top['crop']} holds the largest share of {season} sown area ({top['mean_area_share_pct']:.0f}%) among "
                                 f"{len(shares)} crops - " + ("a concentrated pattern." if (top["mean_area_share_pct"] or 0) >= CONCENTRATED_SHARE_PCT
                                                              else "a diversified pattern."), "Season & Crop Report",
                                 {"crop": top["crop"], "share_pct": top["mean_area_share_pct"], "crops": len(shares)}))
    if water.get("available"):
        out.extend(water["stress_indicators"])
    if soil.get("available"):
        s = soil["latest"]
        out.append(make_item("soil-fertility", "Soil fertility index",
                             f"Fertility index {s['fertility_index_mean']}/100 from {s['samples_tested']} Soil Health Card samples (fuzzy set '{s['fuzzy_set']}').",
                             "Soil Health Card", {"index": s["fertility_index_mean"]}))
        out.extend(soil["limitations"])
    if suitability.get("rankings"):
        top = suitability["rankings"][0]
        out.append(make_item("suitability-top", "Highest suitability score", f"{top['crop']} ({top['season']}) has the highest suitability score, {top['score']:.0f}/100.",
                             "official data + fuzzy + objectives", {"crop": top["crop"], "score": top["score"]}))
    return out


def _summary(location, overview, climate, soil, water, crops, suitability, coverage) -> dict:
    sentences = []
    if overview["major_crops"]:
        top = overview["major_crops"][:3]
        sentences.append(f"{location} grows {len(crops['filters']['crops'])} crops in the official 2024-25 report; the largest by sown area are "
                         + ", ".join(f"{c['crop']} ({c['season']})" for c in top) + ".")
    if suitability.get("rankings"):
        sentences.append("The highest crop-suitability scores are " + ", ".join(f"{r['crop']} in {r['season']} ({r['score']:.0f})" for r in suitability["rankings"][:3]) + ".")
    ann = climate.get("annual") or []
    if ann:
        sentences.append(f"Rainfall was {ann[0]['total_mm']:.0f} mm against a {ann[0]['normal_mm']:.0f} mm IMD normal ({ann[0]['deviation_pct']:+.0f}%).")
    if water.get("available"):
        have = [s for s in water["storage_by_season"] if s["storage_pct"] is not None]
        sentences.append((f"Reservoir storage averaged {have[0]['storage_pct']:.0f}% in {have[0]['season']} (fuzzy set '{have[0]['fuzzy_set']}')."
                          if have else "No official reservoir storage is mapped to this district."))
    if soil.get("available"):
        s = soil["latest"]
        sentences.append(f"Soil Health Card fertility index is {s['fertility_index_mean']}/100 (fuzzy set '{s['fuzzy_set']}'); N is {s['n_status']}, P {s['p_status']}, K {s['k_status']}.")
    return {"sentences": sentences, "text": " ".join(sentences)}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@lru_cache(maxsize=8)
def _build(location: str) -> dict:
    data = load_all()
    coverage = _coverage(location, data)
    climate = _climate(location, data)
    soil = _soil(location, data)
    water = _water(location, data)
    crops = _crops(location, data)
    suitability = _suitability(location, crops)
    market = _market(crops)
    overview = _overview(location, data, coverage, climate, soil, water, crops)
    insights = _insights(location, climate, soil, water, crops, market, suitability)
    summary = _summary(location, overview, climate, soil, water, crops, suitability, coverage)
    return {"district": location, "overview": overview, "coverage": coverage, "climate": climate, "soil": soil,
            "water": water, "crops": crops, "suitability": suitability, "market": market, "insights": insights, "summary": summary}


def get_district_intelligence(location: str) -> dict:
    """Full District Intelligence payload for one district (case-insensitive). Raises ValueError for an unknown district."""
    return _build(pp.canonical_choice(location, config.LOCATIONS, "district"))


def clear_cache() -> None:
    _build.cache_clear()
