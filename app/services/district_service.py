"""
District Intelligence: everything the project knows about one district,
assembled into a single structured payload (overview, climate, soil, water,
crop history, crop suitability, historical prices, insights, summary).

Rules
-----
* Only observed rows feed statistics and trends; rows flagged "Estimated"
  in `data_source` are counted in the coverage section and nothing else.
* No value is estimated. Anything the dataset does not contain is returned
  as `None` with a `note`, and the UI shows "Data not available".
* Existing calculations are reused, not re-implemented:
    - soil fertility index        -> preprocessing.compute_soil_fertility_index
    - region/season profiles      -> preprocessing.get_region_season_profile
    - fuzzy assessment and labels -> fuzzy.engine
    - per-crop yield/cost/water/environmental values
                                  -> FarmPlanProblem's own objective function,
                                     evaluated for one-crop, one-hectare plans
    - min-max goodness            -> ranking.topsis_scores
    - statement format            -> explanation_service.make_item
* Thresholds that turn numbers into words are named constants below and
  documented in docs/handbook/DISTRICT_INTELLIGENCE.md.

The payload is a pure function of the CSVs, so it is cached per district.
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


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def _coverage(location: str, data: Dict[str, pd.DataFrame]) -> dict:
    files, all_years, obs_years = [], set(), set()
    for kind, df in data.items():
        d = _slice(df, location)
        o = pp.observed_rows(d)
        all_years |= set(int(y) for y in d["Year"].unique())
        obs_years |= set(int(y) for y in o["Year"].unique())
        files.append({"kind": kind, "rows": int(len(d)), "observed_rows": int(len(o))})
    mtimes = []
    for kind in config.DATASET_KINDS:
        path = config.RAW_DATA_DIR / f"{location.lower()}_{kind}.csv"
        if path.exists():
            mtimes.append(path.stat().st_mtime)
    crop = pp.observed_rows(_slice(data["crop"], location))
    seasons = {s: sorted(int(y) for y in crop.loc[crop["Season"] == s, "Year"].unique()) for s in config.AG_SEASONS}
    monthly_expected = 12 * len(obs_years)
    monthly_present = {k: int(len(pp.observed_rows(_slice(data[k], location)))) for k in ("rainfall", "water")}
    sources = sorted(set(_slice(data["crop"], location)["data_source"].astype(str))) if "data_source" in data["crop"] else []
    return {
        "observed_years": sorted(obs_years),
        "estimated_years": sorted(all_years - obs_years),
        "seasons_available": seasons,
        "files": files,
        "monthly_completeness_pct": {k: _f(100 * v / monthly_expected, 1) if monthly_expected else None
                                     for k, v in monthly_present.items()},
        "last_dataset_update": _dt.datetime.fromtimestamp(max(mtimes)).date().isoformat() if mtimes else None,
        "last_dataset_update_basis": "Most recent modification date of this district's CSV files.",
        "provenance": sources,
    }


def _climate(location: str, data) -> dict:
    rain = pp.observed_rows(_slice(data["rainfall"], location)).copy()
    rain["Mean_Temp_C"] = (rain["Max_Temp_C"] + rain["Min_Temp_C"]) / 2
    annual = rain.groupby("Year").agg(
        total_mm=("Monthly_Rainfall_mm", "sum"), normal_mm=("Normal_Rainfall_mm", "sum"),
        rainy_days=("Rainy_Days", "sum"), mean_temp_c=("Mean_Temp_C", "mean"),
        max_temp_c=("Max_Temp_C", "max"), min_temp_c=("Min_Temp_C", "min"), humidity_pct=("Humidity_Percent", "mean"),
    ).reset_index()
    annual["deviation_pct"] = (annual["total_mm"] - annual["normal_mm"]) / annual["normal_mm"] * 100
    years = annual["Year"].astype(int).tolist()
    annual_rows = [{"year": int(r.Year), "total_mm": _f(r.total_mm, 1), "normal_mm": _f(r.normal_mm, 1),
                    "deviation_pct": _f(r.deviation_pct, 1), "rainy_days": int(r.rainy_days),
                    "mean_temp_c": _f(r.mean_temp_c), "max_temp_c": _f(r.max_temp_c, 1), "min_temp_c": _f(r.min_temp_c, 1),
                    "humidity_pct": _f(r.humidity_pct, 1)} for r in annual.itertuples()]
    monthly = [{"year": int(r.Year), "month": r.Month, "month_index": MONTHS.index(r.Month) + 1,
                "rainfall_mm": _f(r.Monthly_Rainfall_mm, 1), "normal_mm": _f(r.Normal_Rainfall_mm, 1),
                "max_temp_c": _f(r.Max_Temp_C, 1), "min_temp_c": _f(r.Min_Temp_C, 1), "humidity_pct": _f(r.Humidity_Percent, 1),
                "met_season": r.Season}
               for r in rain.sort_values(["Year", "Month"], key=lambda c: c.map(MONTHS.index) if c.name == "Month" else c).itertuples()]
    total = rain["Monthly_Rainfall_mm"].sum()
    met = [{"season": s, "share_pct": _f(100 * g["Monthly_Rainfall_mm"].sum() / total, 1),
            "mean_mm_per_year": _f(g["Monthly_Rainfall_mm"].sum() / max(1, len(years)), 1)}
           for s, g in rain.groupby("Season")] if total else []
    met.sort(key=lambda m: -(m["share_pct"] or 0))
    agri = []
    for season, months in config.SEASON_MONTH_MAP.items():
        per_year = rain[rain["Month"].isin(months)].groupby("Year")["Monthly_Rainfall_mm"].sum()
        t = trend(per_year.index.tolist(), per_year.tolist())
        agri.append({"season": season, "months": months, "mean_total_mm": _f(per_year.mean(), 1),
                     "by_year": {int(y): _f(v, 1) for y, v in per_year.items()}, "trend": t})
    normals = rain.groupby("Year")["Annual_Normal_mm"].first() if "Annual_Normal_mm" in rain else pd.Series(dtype=float)
    return {
        "annual": annual_rows, "monthly": monthly, "met_season_share": met, "agri_seasons": agri,
        "stated_annual_normal_mm": _f(normals.iloc[0], 1) if len(normals) else None,
        "trends": {"rainfall": trend(years, annual["total_mm"].tolist()),
                   "temperature": trend(years, annual["mean_temp_c"].tolist()),
                   "humidity": trend(years, annual["humidity_pct"].tolist()),
                   "rainy_days": trend(years, annual["rainy_days"].tolist())},
    }


def _soil(location: str, data) -> dict:
    land = pp.observed_rows(_slice(data["land"], location))
    records = []
    for r in land.sort_values(["Year", "Season"]).itertuples():
        fi = pp.compute_soil_fertility_index(r.Avg_Soil_pH, r.Organic_Carbon_Percent, r.N_Status, r.P_Status, r.K_Status)
        records.append({"year": int(r.Year), "season": r.Season, "soil_type": r.Soil_Type, "ph": _f(r.Avg_Soil_pH, 2),
                        "organic_carbon_pct": _f(r.Organic_Carbon_Percent, 2), "n_status": r.N_Status,
                        "p_status": r.P_Status, "k_status": r.K_Status, "fertility_index": fi})
    if not records:
        return {"available": False, "note": NOT_AVAILABLE}
    latest_year = max(r["year"] for r in records)
    latest = [r for r in records if r["year"] == latest_year]
    fert_mean = float(np.mean([r["fertility_index"] for r in latest]))
    memberships = fz.input_memberships(0, 50, fert_mean)["soil_fert"]
    label = max(memberships, key=memberships.get)
    first_year = min(r["year"] for r in records)
    first = [r for r in records if r["year"] == first_year]
    years = sorted({r["year"] for r in records})
    by_year = {y: [r for r in records if r["year"] == y] for y in years}
    ph_t = trend(years, [np.mean([r["ph"] for r in by_year[y]]) for y in years])
    oc_t = trend(years, [np.mean([r["organic_carbon_pct"] for r in by_year[y]]) for y in years])
    fi_t = trend(years, [np.mean([r["fertility_index"] for r in by_year[y]]) for y in years])

    limitations, characteristics = [], []
    for nutrient, key in (("Nitrogen", "n_status"), ("Phosphorus", "p_status"), ("Potassium", "k_status")):
        a, b = first[0][key], latest[0][key]
        characteristics.append(make_item(f"soil-{key}", f"{nutrient} status",
                                         f"{nutrient} status was {a} in {first_year} and {b} in {latest_year} (Kharif records).",
                                         "dataset", {"first": a, "latest": b}))
        if b == "Low":
            limitations.append(make_item(f"limit-{key}", f"Low {nutrient.lower()}",
                                         f"{nutrient} status is Low in the latest observed year ({latest_year}).",
                                         "dataset", {"status": b, "year": latest_year}))
    ph = latest[0]["ph"]
    characteristics.append(make_item("soil-ph", "Soil reaction (pH)", _describe_trend("Average soil pH", ph_t, digits=2), "dataset", {"trend": ph_t}))
    characteristics.append(make_item("soil-oc", "Organic carbon", _describe_trend("Organic carbon", oc_t, "%", digits=2), "dataset", {"trend": oc_t}))
    if latest[0]["organic_carbon_pct"] < 1.0:
        limitations.append(make_item("limit-oc", "Organic carbon below 1%",
                                     f"Organic carbon is {latest[0]['organic_carbon_pct']}% in {latest_year}; the fertility index "
                                     f"treats 1.0% as the level that earns a full organic-carbon score.",
                                     "dataset + fertility index", {"organic_carbon_pct": latest[0]["organic_carbon_pct"]}))

    crop = pp.observed_rows(_slice(data["crop"], location))
    types = crop.groupby("Crop_Type")["Crop_Name"].unique()
    grown = [{"crop_type": t, "crops": sorted(map(str, names))} for t, names in types.items()]
    return {
        "available": True, "soil_types": sorted({r["soil_type"] for r in records}), "records": records,
        "latest_year": latest_year,
        "latest": {"ph": ph, "organic_carbon_pct": latest[0]["organic_carbon_pct"], "n_status": latest[0]["n_status"],
                   "p_status": latest[0]["p_status"], "k_status": latest[0]["k_status"],
                   "fertility_index_mean": _f(fert_mean, 1), "fuzzy_set": label, "fuzzy_membership": memberships},
        "trends": {"ph": ph_t, "organic_carbon": oc_t, "fertility_index": fi_t},
        "characteristics": characteristics, "limitations": limitations,
        "crop_categories_grown": grown,
        "crop_categories_basis": "Crop types recorded for this district in crop.csv (observed years). The dataset has no "
                                 "soil-to-crop suitability table, so categories are what is grown here, not an agronomic "
                                 "recommendation; see Crop suitability for the computed ranking.",
    }


def _water(location: str, data) -> dict:
    w = pp.observed_rows(_slice(data["water"], location)).copy()
    land = pp.observed_rows(_slice(data["land"], location))
    if w.empty:
        return {"available": False, "note": NOT_AVAILABLE}
    years = sorted(int(y) for y in w["Year"].unique())
    yearly = w.groupby("Year").agg(
        irrigation_mcm=("Irrigation_Water_MCM", "sum"), drinking_mcm=("Drinking_Water_MCM", "sum"),
        industrial_mcm=("Industrial_Water_MCM", "sum"), total_demand_mcm=("Total_Demand_MCM", "sum"),
        inflow_mcm=("River_Inflow_MCM", "sum"), storage_pct=("Storage_Percent", "mean"),
        groundwater_mbgl=("Groundwater_Level_mbgl", "mean"), deficit_mcm=("Deficit_Surplus_MCM", "sum"),
    ).reset_index()
    yearly["irrigation_share_pct"] = yearly["irrigation_mcm"] / yearly["total_demand_mcm"] * 100
    monthly_storage = w.groupby("Month")["Storage_Percent"].agg(["mean", "nunique"])
    storage_by_month = [{"month": m, "storage_pct": _f(monthly_storage.loc[m, "mean"], 1),
                         "varies_between_years": bool(monthly_storage.loc[m, "nunique"] > 1)}
                        for m in MONTHS if m in monthly_storage.index]
    storage_identical = all(not s["varies_between_years"] for s in storage_by_month)
    by_season = []
    for season, months in config.SEASON_MONTH_MAP.items():
        pct = float(w[w["Month"].isin(months)]["Storage_Percent"].mean())
        mem = fz.input_memberships(0, pct, 50)["water_storage"]
        by_season.append({"season": season, "storage_pct": _f(pct, 1), "fuzzy_set": max(mem, key=mem.get),
                          "below_action_threshold": pct < LOW_STORAGE_PCT})
    status_counts = w["Groundwater_Status"].value_counts()
    irrigation_dep = (land.groupby("Year")
                      .apply(lambda g: g["Irrigated_Land_Ha"].sum() / g["Agricultural_Land_Ha"].sum() * 100, include_groups=False)
                      if not land.empty else pd.Series(dtype=float))
    stress = []
    low = [s for s in by_season if s["below_action_threshold"]]
    stress.append(make_item("storage-low-season", "Seasonal storage",
                            (f"Mean reservoir storage falls below {LOW_STORAGE_PCT:.0f}% in "
                             f"{', '.join(s['season'] for s in low)}." if low else
                             f"Mean reservoir storage stays at or above {LOW_STORAGE_PCT:.0f}% in every season "
                             f"(lowest: {min(by_season, key=lambda s: s['storage_pct'])['season']} at "
                             f"{min(s['storage_pct'] for s in by_season)}%)."), "dataset",
                            {"by_season": by_season, "threshold_pct": LOW_STORAGE_PCT}))
    share_t = trend(years, yearly["irrigation_share_pct"].tolist())
    stress.append(make_item("irrigation-share", "Irrigation share of water demand",
                            _describe_trend("Irrigation's share of total water demand", share_t, "%"), "dataset", {"trend": share_t}))
    if (yearly["deficit_mcm"] == 0).all():
        stress.append(make_item("deficit-zero", "Supply-demand balance",
                                "Deficit/surplus is recorded as 0 MCM in every month: the dataset sets demand equal to canal "
                                "release, so it carries no shortage signal.", "dataset", {"deficit_mcm_total": 0.0}))
    sources = w["Primary_Source"].value_counts()
    return {
        "available": True,
        "yearly": [{"year": int(r.Year), "irrigation_mcm": _f(r.irrigation_mcm, 1), "drinking_mcm": _f(r.drinking_mcm, 1),
                    "industrial_mcm": _f(r.industrial_mcm, 1), "total_demand_mcm": _f(r.total_demand_mcm, 1),
                    "inflow_mcm": _f(r.inflow_mcm, 1), "storage_pct": _f(r.storage_pct, 1),
                    "groundwater_mbgl": _f(r.groundwater_mbgl, 1), "irrigation_share_pct": _f(r.irrigation_share_pct, 1)}
                   for r in yearly.itertuples()],
        "storage_by_month": storage_by_month, "storage_identical_every_year": storage_identical,
        "storage_by_season": by_season,
        "reservoir_capacity_mcm": _f(w["Reservoir_Capacity_MCM"].max(), 1),
        "primary_sources": [{"source": s, "share_of_months_pct": _f(100 * n / len(w), 1)} for s, n in sources.items()],
        "groundwater": {
            "level_mbgl_by_year": {int(r.Year): _f(r.groundwater_mbgl, 1) for r in yearly.itertuples()},
            "level_varies": bool(w["Groundwater_Level_mbgl"].nunique() > 1),
            "status_distribution": [{"status": s, "months": int(n), "share_pct": _f(100 * n / len(w), 1)}
                                    for s, n in status_counts.items()],
            "most_common_status": str(status_counts.index[0]),
        },
        "irrigation_dependency": {"irrigated_pct_by_year": {int(y): _f(v, 1) for y, v in irrigation_dep.items()},
                                  "trend": trend(list(irrigation_dep.index), list(irrigation_dep.values))},
        "trends": {"inflow": trend(years, yearly["inflow_mcm"].tolist()),
                   "irrigation_demand": trend(years, yearly["irrigation_mcm"].tolist()),
                   "irrigation_share": share_t},
        "stress_indicators": stress,
        "glossary": {
            "storage_pct": "Reservoir storage as % of capacity; the fuzzy model's water input.",
            "irrigation_share_pct": "Irrigation's share of total water demand (irrigation + drinking + industrial).",
            "groundwater_mbgl": "Groundwater depth in metres below ground level (deeper = scarcer).",
            "irrigated_pct": "Irrigated land as % of agricultural land.",
            "inflow_mcm": "River inflow summed over the year, million cubic metres.",
        },
    }


def _crops(location: str, data) -> dict:
    crop = pp.observed_rows(_slice(data["crop"], location)).copy()
    if crop.empty:
        return {"available": False, "note": NOT_AVAILABLE, "records": [], "trends": []}
    season_area = crop.groupby(["Year", "Season"])["Area_Sown_Ha"].transform("sum")
    crop["area_share_pct"] = crop["Area_Sown_Ha"] / season_area * 100
    records = [{"year": int(r.Year), "season": r.Season, "crop": r.Crop_Name, "crop_type": r.Crop_Type,
                "area_ha": _f(r.Area_Sown_Ha, 0), "area_share_pct": _f(r.area_share_pct, 1),
                "production_t": _f(r.Production_Tonnes, 0), "yield_t_ha": _f(r.Yield_Kg_Ha / 1000, 3),
                "price_rs_qtl": _f(r.MSP_Rs_Qtl, 2), "revenue_rs_lakh": _f(r.Revenue_Rs_Lakh, 0)}
               for r in crop.sort_values(["Season", "Crop_Name", "Year"]).itertuples()]
    trends = []
    for (season, name), g in crop.groupby(["Season", "Crop_Name"]):
        ys = g["Year"].astype(int).tolist()
        trends.append({"season": season, "crop": name,
                       "mean_area_ha": _f(g["Area_Sown_Ha"].mean(), 0), "mean_area_share_pct": _f(g["area_share_pct"].mean(), 1),
                       "mean_yield_t_ha": _f(g["Yield_Kg_Ha"].mean() / 1000, 3),
                       "production": trend(ys, g["Production_Tonnes"].tolist()),
                       "area": trend(ys, g["Area_Sown_Ha"].tolist()),
                       "yield": trend(ys, (g["Yield_Kg_Ha"] / 1000).tolist())})
    trends.sort(key=lambda t: -(t["mean_area_ha"] or 0))
    return {"available": True, "records": records, "trends": trends,
            "filters": {"seasons": sorted(crop["Season"].unique().tolist()), "crops": sorted(crop["Crop_Name"].unique().tolist()),
                        "years": sorted(int(y) for y in crop["Year"].unique())}}


def _suitability(location: str, crops: dict) -> dict:
    """Score every crop the district grows, per season, from five components
    (each 0-1, equal weights). Per-hectare yield, cost, water and
    environmental values come from FarmPlanProblem's own objective function
    for a one-crop, one-hectare plan with baseline input levels."""
    crop_df = pp.observed_rows(_slice(load_all()["crop"], location))
    if crop_df.empty:
        return {"available": False, "note": NOT_AVAILABLE, "rankings": []}
    year = int(crop_df["Year"].max())
    trend_by = {(t["season"], t["crop"]): t for t in crops["trends"]}
    rows = []
    for season in config.AG_SEASONS:
        try:
            profile = pp.get_region_season_profile(location, season, year=year, max_candidate_crops=12)
        except ValueError:
            continue
        assessment = fz.evaluate_uncertainty(profile.rainfall.avg_deviation_percent,
                                             profile.water.avg_storage_percent, profile.soil.fertility_index)
        problem = FarmPlanProblem(profile, assessment, total_land_ha=1.0)
        n = problem.n_crops
        X = np.hstack([np.eye(n), np.ones((n, n)), np.ones((n, n))])   # one crop, full land, baseline inputs
        F = problem.evaluate(X, return_as_dictionary=True)["F"]
        yields, costs, waters, envs = -F[:, 0], F[:, 1], F[:, 2], F[:, 3]
        _, goodness = ranking.topsis_scores(yields, costs, waters, envs, ranking.preference_weights("balanced"))
        max_share = max((trend_by.get((season, c.name), {}).get("mean_area_share_pct") or 0) for c in profile.candidate_crops) or 1.0
        eff = profile.rainfall.effective_rainfall_mm
        for i, c in enumerate(profile.candidate_crops):
            t = trend_by.get((season, c.name), {})
            yield_cv = (t.get("yield") or {}).get("cv")
            comps = {
                "climate_soil": float(problem.crop_vec.crop_yield_confidence[i]),
                "rainfall_fit": min(1.0, eff / c.water_req_mm) if c.water_req_mm else None,
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
                "water_req_mm": c.water_req_mm, "irrigation_need_l_ha": round(float(waters[i]), 0),
                "cost_rs_ha": round(float(costs[i]), 0), "env_impact_per_ha": round(float(envs[i]), 2),
                "rainfall_dependency": c.rainfall_dependency, "duration_days": c.crop_duration_days,
                "mean_area_share_pct": t.get("mean_area_share_pct"),
                "production_trend": (t.get("production") or {}).get("direction"),
            })
    rows.sort(key=lambda r: (-r["score"], r["crop"]))
    for rank, r in enumerate(rows, start=1):
        r["rank"] = rank
    for season in config.AG_SEASONS:
        for rank, r in enumerate([r for r in rows if r["season"] == season], start=1):
            r["season_rank"] = rank
    return {
        "available": True, "year_basis": year, "rankings": rows,
        "method": ("Score = mean of five 0–1 components, ×100: climate & soil (fuzzy crop confidence for the season), "
                   "rainfall fit (effective rainfall ÷ crop water requirement, capped at 1), prominence (mean share of the "
                   "season's sown area, relative to the most widely grown crop), yield stability (1 − coefficient of "
                   "variation of observed yields) and resource efficiency (mean min–max goodness of cost, irrigation and "
                   "environmental impact per hectare among the season's crops). Yield, cost, water and impact per hectare "
                   "come from the optimiser's objective function for a one-crop, one-hectare plan at baseline input levels. "
                   "Tonnage is shown but not scored, because tonnes of different crops are not comparable."),
    }


def _market(crops: dict) -> dict:
    by_crop: Dict[str, Dict[int, float]] = {}
    for r in crops["records"]:
        if r["price_rs_qtl"] is not None:
            by_crop.setdefault(r["crop"], {})[r["year"]] = r["price_rs_qtl"]
    items = []
    for name, series in sorted(by_crop.items()):
        ys = sorted(series)
        t = trend(ys, [series[y] for y in ys])
        items.append({"crop": name, "prices_by_year": {y: series[y] for y in ys},
                      "mean_rs_qtl": _f(np.mean(list(series.values())), 1), "trend": t})
    ranked = [i for i in items if i["trend"] and i["trend"]["change_pct"] is not None]
    ranked.sort(key=lambda i: -i["trend"]["change_pct"])
    return {
        "available": bool(items), "is_live": False,
        "note": ("Historical prices from the dataset's MSP_Rs_Qtl column (observed years only), not live market data. "
                 "Several crops listed have no government-notified MSP and the values have not been validated."),
        "crops": items,
        "strongest_price_growth": [{"crop": i["crop"], "change_pct": i["trend"]["change_pct"]} for i in ranked[:3]],
        "weakest_price_growth": [{"crop": i["crop"], "change_pct": i["trend"]["change_pct"]} for i in ranked[-3:][::-1]],
    }


def _overview(location: str, data, coverage: dict, climate: dict, soil: dict, water: dict, crops: dict) -> dict:
    land = pp.observed_rows(_slice(data["land"], location))
    latest = int(land["Year"].max()) if not land.empty else None
    ly = land[land["Year"] == latest] if latest else land
    annual = climate["annual"]
    mean_temp = float(np.mean([a["mean_temp_c"] for a in annual])) if annual else None
    major = [{"crop": t["crop"], "season": t["season"], "mean_area_ha": t["mean_area_ha"],
              "mean_area_share_pct": t["mean_area_share_pct"]} for t in crops["trends"][:MAJOR_CROPS]]
    return {
        "district": location,
        "coordinates": dict(zip(("lat", "lon"), config.DISTRICT_COORDINATES[location])) if location in config.DISTRICT_COORDINATES else None,
        "agricultural_zone": None,
        "agricultural_zone_note": "The dataset has no agro-climatic zone field.",
        "agricultural_area_ha": _f(ly["Agricultural_Land_Ha"].mean(), 0) if not ly.empty else None,
        "total_area_ha": _f(ly["Total_Land_Ha"].mean(), 0) if not ly.empty else None,
        "irrigated_pct": _f(ly["Irrigated_Land_Ha"].sum() / ly["Agricultural_Land_Ha"].sum() * 100, 1) if not ly.empty else None,
        "land_year_basis": latest, "land_basis": "Mean of the season records for the latest observed year.",
        "soil_types": soil.get("soil_types", []),
        "average_annual_rainfall_mm": _f(np.mean([a["total_mm"] for a in annual]), 1) if annual else None,
        "stated_annual_normal_mm": climate["stated_annual_normal_mm"],
        "average_temperature_c": _f(mean_temp, 1),
        "average_humidity_pct": _f(np.mean([a["humidity_pct"] for a in annual]), 1) if annual else None,
        "primary_irrigation_sources": water.get("primary_sources", []),
        "major_crops": major,
        "seasons_available": coverage["seasons_available"],
        "observed_years": coverage["observed_years"], "estimated_years": coverage["estimated_years"],
        "last_dataset_update": coverage["last_dataset_update"],
    }


def _insights(location, climate, soil, water, crops, market, suitability) -> List[dict]:
    out = []
    rt = climate["trends"]["rainfall"]
    out.append(make_item("rainfall-trend", "Annual rainfall", _describe_trend("Annual rainfall", rt, " mm", 0), "dataset", {"trend": rt}))
    annual = climate["annual"]
    normal = climate["stated_annual_normal_mm"]
    if annual and normal:
        mean = float(np.mean([a["total_mm"] for a in annual]))
        diff = (mean - normal) / normal * 100
        out.append(make_item("rainfall-normal", "Rainfall against the stated normal",
                             f"Observed annual rainfall averages {mean:.0f} mm, {abs(diff):.0f}% {'above' if diff >= 0 else 'below'} "
                             f"the {normal:.0f} mm annual normal recorded in the dataset.", "dataset",
                             {"mean_annual_mm": round(mean, 1), "stated_normal_mm": normal, "difference_pct": round(diff, 1)}))
    if climate["met_season_share"]:
        top = climate["met_season_share"][0]
        out.append(make_item("rainfall-season", "When the rain falls",
                             f"The {top['season']} brings {top['share_pct']:.0f}% of annual rainfall "
                             f"(≈{top['mean_mm_per_year']:.0f} mm a year); "
                             + ", ".join(f"{m['season']} {m['share_pct']:.0f}%" for m in climate["met_season_share"][1:]) + ".",
                             "dataset", {"shares": climate["met_season_share"]}))
    tt = climate["trends"]["temperature"]
    if tt:
        out.append(make_item("temperature", "Temperature", _describe_trend("Mean annual temperature", tt, " °C"), "dataset", {"trend": tt}))

    trends = [t for t in crops["trends"] if t["production"]]
    if trends:
        best = max(trends, key=lambda t: t["production"]["change_pct"] or -1e9)
        worst = min(trends, key=lambda t: t["production"]["change_pct"] or 1e9)
        for tag, t in (("fastest", best), ("slowest", worst)):
            area, yld = t["area"], t["yield"]
            driver = ("almost entirely from more area, with yield per hectare essentially flat"
                      if yld and abs(yld["change_pct"] or 0) < STABLE_CHANGE_PCT and area and abs(area["change_pct"] or 0) >= STABLE_CHANGE_PCT
                      else f"area {area['change_pct']:+.1f}%, yield {yld['change_pct']:+.1f}%" if area and yld else "")
            out.append(make_item(f"production-{tag}", f"{'Fastest' if tag == 'fastest' else 'Slowest'} production growth",
                                 f"{t['crop']} ({t['season']}) production changed {t['production']['change_pct']:+.1f}% between "
                                 f"{t['production']['first_year']} and {t['production']['last_year']}"
                                 + (f" — {driver}." if driver else "."), "dataset",
                                 {"production": t["production"], "area": area, "yield": yld}))
        yields = [t for t in crops["trends"] if t["yield"] and t["yield"]["cv"] is not None]
        if yields:
            steady = min(yields, key=lambda t: t["yield"]["cv"])
            volatile = max(yields, key=lambda t: t["yield"]["cv"])
            out.append(make_item("yield-variability", "Yield consistency",
                                 f"Most consistent yield: {steady['crop']} ({steady['season']}, CV {steady['yield']['cv']:.3f}); "
                                 f"most variable: {volatile['crop']} ({volatile['season']}, CV {volatile['yield']['cv']:.3f}).",
                                 "dataset", {"most_consistent": steady["crop"], "most_variable": volatile["crop"]}))
        flat = [t for t in yields if t["yield"]["direction"] in ("unchanged", "stable")]
        if len(flat) == len(yields):
            out.append(make_item("yield-flat", "Yields per hectare",
                                 f"Yield per hectare is stable or unchanged for all {len(yields)} crop-season series in the observed "
                                 f"years, so production changes reflect changes in sown area.", "dataset", {"series": len(yields)}))

    for season in config.AG_SEASONS:
        shares = [t for t in crops["trends"] if t["season"] == season]
        if shares:
            top = max(shares, key=lambda t: t["mean_area_share_pct"] or 0)
            out.append(make_item(f"concentration-{season}", f"{season} cropping pattern",
                                 f"{top['crop']} holds the largest share of {season} sown area ({top['mean_area_share_pct']:.0f}%) "
                                 f"among {len(shares)} crops — "
                                 + ("a concentrated pattern." if (top["mean_area_share_pct"] or 0) >= CONCENTRATED_SHARE_PCT else "a diversified pattern."),
                                 "dataset", {"crop": top["crop"], "share_pct": top["mean_area_share_pct"], "crops": len(shares)}))

    if water.get("available"):
        dep = water["irrigation_dependency"]["trend"]
        if dep:
            out.append(make_item("irrigation-dependency", "Irrigation dependency",
                                 _describe_trend("Irrigated share of agricultural land", dep, "%"), "dataset", {"trend": dep}))
        if water["storage_identical_every_year"]:
            out.append(make_item("storage-static", "Reservoir records",
                                 "Reservoir storage percentages are identical in every observed year for each month, so the data "
                                 "shows a seasonal pattern but no year-to-year change.", "dataset", {}))
        gw = water["groundwater"]
        if not gw["level_varies"]:
            out.append(make_item("groundwater-static", "Groundwater records",
                                 f"Groundwater depth is recorded as {next(iter(gw['level_mbgl_by_year'].values()))} m below ground "
                                 f"in every month, while the status label varies (most often '{gw['most_common_status']}'); treat "
                                 f"the status as indicative.", "dataset", {"status_distribution": gw["status_distribution"]}))
    if soil.get("available"):
        fi = soil["trends"]["fertility_index"]
        out.append(make_item("soil-fertility", "Soil fertility index", _describe_trend("Soil fertility index", fi, "", 1),
                             "dataset + fertility index", {"trend": fi}))
    if market["strongest_price_growth"]:
        g = market["strongest_price_growth"][0]
        out.append(make_item("price-growth", "Historical price growth",
                             f"{g['crop']} recorded the largest historical price rise in the dataset ({g['change_pct']:+.1f}%, "
                             f"unvalidated prices, not live market data).", "dataset", {"top": market["strongest_price_growth"]}))
    if suitability.get("rankings"):
        top = suitability["rankings"][0]
        out.append(make_item("suitability-top", "Highest suitability score",
                             f"{top['crop']} ({top['season']}) has the highest suitability score, {top['score']:.0f}/100.",
                             "fuzzy + nsga2 objectives + dataset", {"crop": top["crop"], "score": top["score"]}))
    return out


def _summary(location, overview, climate, soil, water, crops, suitability, coverage) -> dict:
    sentences = []
    obs = coverage["observed_years"]
    span = f"{obs[0]}–{obs[-1]}" if obs else "no observed years"
    if overview["major_crops"]:
        top = overview["major_crops"][:3]
        sentences.append(f"{location} grows {len(crops['filters']['crops'])} crops across {sum(1 for s in coverage['seasons_available'].values() if s)} "
                         f"seasons; the largest by sown area are " + ", ".join(f"{c['crop']} ({c['season']})" for c in top)
                         + f" (observed {span}).")
    if suitability.get("rankings"):
        best = suitability["rankings"][:3]
        sentences.append("The highest crop-suitability scores are " + ", ".join(f"{r['crop']} in {r['season']} ({r['score']:.0f})" for r in best) + ".")
    rt = climate["trends"]["rainfall"]
    if rt and overview["average_annual_rainfall_mm"]:
        sentences.append(f"Annual rainfall averaged {overview['average_annual_rainfall_mm']:.0f} mm and was "
                         f"{'unchanged' if rt['direction'] == 'unchanged' else rt['direction']} over the observed years, "
                         f"with {rt['variability']} variability"
                         + (f"; the {climate['met_season_share'][0]['season']} brings {climate['met_season_share'][0]['share_pct']:.0f}% of it."
                            if climate["met_season_share"] else "."))
    if water.get("available"):
        lowest = min(water["storage_by_season"], key=lambda s: s["storage_pct"])
        sentences.append(f"Reservoir storage is lowest in {lowest['season']} ({lowest['storage_pct']:.0f}%, fuzzy set '{lowest['fuzzy_set']}'); "
                         f"groundwater status is most often '{water['groundwater']['most_common_status']}'.")
    if soil.get("available"):
        s = soil["latest"]
        sentences.append(f"Soils are {', '.join(soil['soil_types'])} with pH {s['ph']} and a fertility index of "
                         f"{s['fertility_index_mean']} (fuzzy set '{s['fuzzy_set']}') in {soil['latest_year']}.")
    if coverage["estimated_years"]:
        sentences.append(f"Figures exclude {', '.join(map(str, coverage['estimated_years']))}, whose rows are estimates.")
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
            "water": water, "crops": crops, "suitability": suitability, "market": market,
            "insights": insights, "summary": summary}


def get_district_intelligence(location: str) -> dict:
    """Full District Intelligence payload for one district (case-insensitive).
    Raises ValueError for an unknown district."""
    return _build(pp.canonical_choice(location, config.LOCATIONS, "district"))


def clear_cache() -> None:
    _build.cache_clear()
