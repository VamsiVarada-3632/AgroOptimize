"""
Support logic for the frontend-facing dashboard endpoints (weather, KPI
summary, history, soil profile, Pareto plans, and A/B/C comparison).

Every value returned here is derived from the official database and the same
fuzzy/NSGA-II/TOPSIS pipeline the rest of the backend uses (see
app/fuzzy/engine.py, app/optimization/, app/decision/ranking.py) -- nothing
here is random or hardcoded. Where a metric has no single canonical
formula already defined elsewhere in the codebase (e.g. "water
utilization" as distinct from the already-used "water storage", or the
comparison view's 6-axis radar scores), the derivation is documented
inline so it's easy to challenge or retune later -- see
docs/SCORING_AND_RANKING.md (repository root) for the full list of these
choices in one place.
"""
from __future__ import annotations

import datetime as _dt
import logging
from functools import lru_cache
from typing import Optional

from app import config
from app.data import loader
from app.data import preprocessing as pp
from app.errors import FeatureUnavailable
from app.decision import ranking
from app.fuzzy import engine as fz
from app.optimization.nsga2_runner import extract_convergence_history, extract_pareto_plans, run_nsga2
from app.optimization.problem import FarmPlanProblem
from app.services import results_store

logger = logging.getLogger(__name__)

_MONTHS_IN_YEAR_ORDER = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def resolve_location(location: str) -> str:
    """Case-insensitive district lookup (frontend sends lowercase path segments, e.g. 'salem').
    Raises ValueError -- mapped to 404/400 in main.py -- for anything that is not one of the 38 official districts;
    taluks such as Pollachi get an explicit "taluk data not available" message."""
    return pp.resolve_location(location)


def _current_season(today: Optional[_dt.date] = None) -> str:
    """Maps today's calendar month onto Kharif/Rabi/Summer via
    app.config.SEASON_MONTH_MAP. Kharif/Rabi/Summer's month lists overlap
    at the edges (Feb/Mar fall in both Rabi and Summer) -- ties resolve to
    whichever season is listed first in SEASON_MONTH_MAP (currently Rabi)."""
    today = today or _dt.date.today()
    month_name = _MONTHS_IN_YEAR_ORDER[today.month - 1]
    for season, months in config.SEASON_MONTH_MAP.items():
        if month_name in months:
            return season
    return config.AG_SEASONS[0]  # unreachable in practice -- every month is mapped


def _latest_year_for(df, location: str) -> int:
    years = df.loc[df["Location"] == location, "Year"]
    return int(years.max())


# ---------------------------------------------------------------------------
# GET /api/weather/{location}
# ---------------------------------------------------------------------------

_CONDITION_TEXT = {
    "sunny": "Sunny",
    "partly_cloudy_day": "Partly Cloudy",
    "cloud": "Cloudy",
    "foggy": "Foggy",
    "rainy": "Rainy",
    "thunderstorm": "Thunderstorm",
    "ac_unit": "Snow",
}

def get_weather(location: str) -> dict:
    """DISABLED: the live-weather widget used a third-party API (Open-Meteo) and, offline, the synthetic rainfall/temperature
    CSVs. Neither is an official source. It is re-enabled once an IMD weather feed (district forecast / observed
    temperature, humidity) is integrated - TODO listed in docs/data_architecture/MIGRATION_REPORT.md."""
    resolve_location(location)
    raise FeatureUnavailable("Live weather widget", "IMD district weather (temperature, humidity, forecast) - not yet scraped",
                             "Official monthly rainfall is shown elsewhere.")


# ---------------------------------------------------------------------------
# GET /api/dashboard/{location}
# ---------------------------------------------------------------------------

_ACTION_LIBRARY = {
    "nitrogen": ("Apply nitrogen fertilizer", "Soil N status from the land survey is Low.", "high", "Next 48 hours"),
    "phosphorus": ("Apply phosphorus (DAP) fertilizer", "Soil P status from the land survey is Low.", "high", "Next 5 days"),
    "potassium": ("Apply potash (MOP) fertilizer", "Soil K status from the land survey is Low.", "medium", "Next 5 days"),
    "irrigation": ("Schedule additional irrigation", "Reservoir storage for this district is below 40%.", "high", "Next 24 hours"),
}


def _soil_status_label(fertility_index_0_100: float) -> str:
    if fertility_index_0_100 >= 70:
        return "Optimal"
    if fertility_index_0_100 >= 45:
        return "Moderate"
    return "Needs Attention"


def _current_land_row(land_df, location: str, year: int):
    """The official land/soil row for (location, year, current-season) -- falls
    back to the last row for that year if the current season is somehow
    missing, so this never raises for a location that's in the dataset."""
    year_rows = land_df[(land_df["Location"] == location) & (land_df["Year"] == year)]
    season_rows = year_rows[year_rows["Season"] == _current_season()]
    return season_rows.iloc[0] if not season_rows.empty else year_rows.iloc[-1]



# Reference farm size used only to express the dashboard's revenue-share
# percentages as an illustrative hectare column.
_REFERENCE_FARM_HA = 10.0


class PlanGenerationError(RuntimeError):
    """Raised by get_plans() when a live NSGA-II run fails and there is
    no other honest way to answer the request. Previously this path
    silently substituted the last saved run, then single-crop CSV
    estimates, flagged only via an is_fallback/fallback_reason field in
    the response body -- easy for a caller to miss. Replaced with a
    real error (see main.py, which turns this into HTTP 503) so a
    failed optimisation is never silently presented as a real plan.
    """

def ov_sources() -> list:
    return [{"dataset": r["name"], "file": r["filename"], "report_year": r["report_year"]} for r in svc_provenance()]


def svc_provenance():
    from app.datasets import service as svc
    return svc.provenance()


def get_dashboard(location: str, client_id: str | None = None) -> dict:
    """`client_id` (optional) is the requesting browser's persistent id -- see FarmPlanRequest.client_id.
    `active_plans` only counts this visitor's own saved runs for the district (same rule as get_history).
    Every KPI is derived from the official 2024-25 datasets; a KPI the data cannot support is None."""
    location = resolve_location(location)
    data = loader.load_all()
    crop_df, land_df, water_df = data["crop"], data["land"], data["water"]
    season = _current_season()

    # --- estimated_yield: area-weighted district yield of the season's crops (t/ha, mass-unit crops only) ---
    rows = crop_df[(crop_df["Location"] == location) & (crop_df["Season"] == season) & crop_df["Yield_Kg_Ha"].notna() & (crop_df["Area_Ha"] > 0)]
    estimated_yield = (round(float((rows["Yield_Kg_Ha"] * rows["Area_Ha"]).sum() / rows["Area_Ha"].sum()) / 1000.0, 1)
                       if not rows.empty else None)
    # Only one official report year per district is loaded, so there is no district year-over-year trend.
    yield_trend = None

    active_plans = sum(
        1 for r in results_store.list_saved_runs()
        if r["location"] == location and client_id and r.get("client_id") == client_id
    )

    # --- soil: Soil Health Card fertility index (None if the portal has no row for the district) ---
    land_row = land_df[(land_df["Location"] == location) & (land_df["Season"] == season)].iloc[0]
    fertility_index = None if land_row["Soil_Fertility_Index"] != land_row["Soil_Fertility_Index"] else float(land_row["Soil_Fertility_Index"])

    # --- water_utilization_pct: irrigated share of the district's cropped area (official area statistics) ---
    irr = land_row["Irrigation_Percent"]
    water_utilization_pct = None if irr != irr else round(float(irr), 1)
    water_rows = water_df[(water_df["Location"] == location) & water_df["Storage_Percent"].notna()]
    avg_storage_pct = float(water_rows["Storage_Percent"].mean()) if not water_rows.empty else None

    # --- recommended_actions: rule-based off Soil Health Card N/P/K class + reservoir storage ---
    actions = []
    for key, status_col in (("nitrogen", "N_Status"), ("phosphorus", "P_Status"), ("potassium", "K_Status")):
        if str(land_row[status_col]) == "Low":
            title, desc, prio, window = _ACTION_LIBRARY[key]
            actions.append({"id": key, "title": title, "description": desc, "priority": prio, "window": window})
    if avg_storage_pct is not None and avg_storage_pct < 40:
        title, desc, prio, window = _ACTION_LIBRARY["irrigation"]
        actions.append({"id": "irrigation", "title": title, "description": desc, "priority": prio, "window": window})
    if not actions:
        known = fertility_index is not None
        actions.append({
            "id": "monitor", "title": "No urgent action needed" if known else "Soil data not available",
            "description": ("Dominant Soil Health Card N/P/K classes and reservoir storage are not Low." if known
                            else "The Soil Health Card portal has no data for this district."),
            "priority": "low", "window": "Routine monitoring",
        })

    # --- crop_allocations: top 3 candidate crops by revenue at MSP (NOT an optimised plan) ---
    try:
        profile = pp.get_region_season_profile(location, season, max_candidate_crops=3)
        top3 = profile.candidate_crops
        total_revenue = sum(c.revenue_rs_lakh_hist for c in top3) or 1.0
        crop_allocations = [
            {"crop": c.name, "pct": round(c.revenue_rs_lakh_hist / total_revenue * 100, 1),
             "ha": round(c.revenue_rs_lakh_hist / total_revenue * _REFERENCE_FARM_HA, 1)}
            for c in top3
        ]
    except ValueError:
        crop_allocations = []

    return {
        "location": location,
        "data_year": int(crop_df["Year"].max()),
        "data_year_estimated": False,
        "estimated_yield": estimated_yield,
        "yield_trend": yield_trend,
        "active_plans": active_plans,
        "soil_health_pct": None if fertility_index is None else round(fertility_index),
        "water_utilization_pct": water_utilization_pct,
        "soil_status": None if fertility_index is None else _soil_status_label(fertility_index),
        "recommended_actions": actions,
        "crop_allocations": crop_allocations,
        "data_sources": ov_sources(),
    }


# ---------------------------------------------------------------------------
# GET /api/soil-profile/{location}
# ---------------------------------------------------------------------------

def get_soil_profile(location: str) -> dict:
    location = resolve_location(location)
    from app.data import official_view as ov
    from app.datasets import service as svc
    ss = ov.soil_summary(location)
    lu = svc.land_use(location)
    crop_df = loader.load_all()["crop"]
    loc = crop_df[(crop_df["Location"] == location)]
    per_crop = loc.drop_duplicates("Crop_Name")
    irrigated_ha = float(per_crop["Irrigated_Area_Ha"].sum())
    cropped_ha = float(per_crop["Area_Ha"].sum())      # same crops, same report: a consistent denominator for the irrigated area
    return {
        "location": location,
        "soil_pH": None, "organic_carbon_pct": None,        # the portal publishes classes, not mean values
        "N_status": ss and ss["n_status"], "P_status": ss and ss["p_status"], "K_status": ss and ss["k_status"],
        "fertility_index": None if ss is None else round(ss["fertility_index"] / 100.0, 3),
        "irrigated_ha": irrigated_ha,
        "total_agricultural_ha": cropped_ha,
        "net_area_sown_ha": lu.get("Net area sown"),
        "area_basis": "Irrigated and total area are both summed over the district's crops in the Season & Crop Report (gross cropped area).",
        "class_shares": None if ss is None else {k: ss[k] for k in ("n_shares", "p_shares", "k_shares", "oc_shares", "ph_shares")},
        "samples_tested": None if ss is None else ss["samples_tested"],
        "source": "Soil Health Card portal (soilhealth.dac.gov.in); TN Season & Crop Report 2024-25 (land use, irrigation)",
        "available": ss is not None,
    }


# ---------------------------------------------------------------------------
# GET /api/history/{location}
# ---------------------------------------------------------------------------

def get_history(location: str, client_id: str | None = None) -> dict:
    """`client_id` (optional) is the requesting browser's persistent id --
    see FarmPlanRequest.client_id. There are no real user accounts in this
    project, so a saved run only counts as *this* visitor's completed
    history if its stored client_id matches exactly. No client_id, or a
    mismatch (including older/demo runs saved before client_id existed,
    which have none), means it's excluded here -- a brand-new browser must
    never see someone else's, or seed/demo, saved runs presented as its
    own history. By product decision this returns ONLY a visitor's own
    real saved runs -- no CSV-derived filler rows for years nobody has
    actually run yet; the frontend shows a plain "no runs yet" empty
    state instead (see RunOptimizationView / HistoryView)."""
    location = resolve_location(location)

    real_runs = []
    for summary in results_store.list_saved_runs():
        if summary["location"] != location:
            continue
        if not client_id or summary.get("client_id") != client_id:
            continue
        record = results_store.load_run(summary["run_id"])
        if record is None:
            continue
        top_plan = record["plans"][0] if record["plans"] else None
        # top_plan's yield_tonnes/cost_rs are plan TOTALS over whatever
        # total_land_ha that run used, not per-hectare rates -- divide by
        # the plan's own area so "t/ha" and "/ha" are actually true.
        area_ha = sum(top_plan["area_ha"]) if top_plan else 0.0
        real_runs.append({
            "saved_at": summary.get("saved_at") or "",
            "id": summary["run_id"],
            "season": f"{summary['season']} {summary['year']}",
            "date": (summary.get("saved_at") or "")[:10],
            "location": location,
            "target_yield": f"{round(top_plan['yield_tonnes'] / area_ha, 2)} t/ha" if top_plan and area_ha else "--",
            "est_cost": f"₹{round(top_plan['cost_rs'] / area_ha):,}/ha" if top_plan and area_ha else "--",
            "status": "Completed",
            "num_plans": summary["n_plans"],
            "preference": summary.get("preference") or "balanced",
            "ranking": summary.get("ranking"),
            "fuzzy_weights": record["fuzzy_assessment"],
            "is_estimated": False,
        })
    # Most recently saved run first. (Sorting on the "Kharif 2023" display
    # string ordered runs alphabetically by season name instead.)
    history = sorted(real_runs, key=lambda h: h["saved_at"], reverse=True)
    for h in history:
        del h["saved_at"]
    return {"history": history}


# ---------------------------------------------------------------------------
# Shared: run the real pipeline once, reused by /api/plans and /api/comparison
# ---------------------------------------------------------------------------

_DEMO_POP_SIZE = 100  # > config.NSGA2_POP_SIZE (80) so the Analytics scatter has ~100 points


def _run_dashboard_pareto_front(
    location: str,
    season: Optional[str] = None,
    year: Optional[int] = None,
    total_land_ha: float = 5.0,
    budget_rs: Optional[float] = None,
    track_history: bool = False,
):
    """Runs preprocessing -> fuzzy -> NSGA-II once. Returns (profile,
    assessment, raw_feasible_plans, crop_confidence_map, result) so callers
    can re-rank the same front under different TOPSIS preferences without
    re-running the optimiser. Deliberately calls the lower-level pieces
    (FarmPlanProblem / run_nsga2 / ranking.rank_plans) directly instead of
    app.services.plan_service.generate_farm_plans, specifically so it can
    ask for more than plan_service's hardcoded config.MAX_RETURNED_PLANS
    (50) without touching that already-tested orchestration path.

    `track_history=True` costs ~2-3x the run time (pymoo snapshots every
    generation) -- only GET /api/plans/{location} opts into it, to power
    the Analytics convergence/hypervolume chart; GET /api/comparison/
    {location} doesn't need it and stays at the cheaper default.

    Returns (profile, assessment, raw_feasible_plans, crop_confidence_map,
    convergence_history) -- the last is [] unless track_history=True."""
    location = resolve_location(location)
    season = pp.canonical_choice(season, config.AG_SEASONS, "season") if season else _current_season()
    profile, assessment, raw_plans, conf_items, history = _cached_pareto_front(
        location, season, year, float(total_land_ha), budget_rs, track_history
    )
    return profile, assessment, list(raw_plans), dict(conf_items), list(history)


@lru_cache(maxsize=32)
def _cached_pareto_front(location, season, year, total_land_ha, budget_rs, track_history):
    """The expensive part of _run_dashboard_pareto_front, memoised.

    Safe to cache because the run is a pure function of its arguments:
    the CSVs are loaded once and never change at runtime, and run_nsga2
    reseeds with the fixed config.NSGA2_SEED on every call -- so a repeat
    request would recompute a bit-identical front. Only plain data is
    cached (not the pymoo result object), keeping each entry small."""
    profile = pp.get_region_season_profile(location, season, year=year)
    assessment = fz.assess_profile(profile)
    problem = FarmPlanProblem(profile, assessment, total_land_ha=total_land_ha, budget_rs=budget_rs)
    result = run_nsga2(problem, pop_size=_DEMO_POP_SIZE, track_history=track_history)
    raw_plans = tuple(p for p in extract_pareto_plans(result, problem) if p.feasible)
    conf_items = tuple(zip(problem.crop_vec.names, problem.crop_vec.crop_yield_confidence.tolist()))
    history = tuple(extract_convergence_history(result)) if track_history else ()
    return profile, assessment, raw_plans, conf_items, history


def clear_pareto_cache() -> None:
    """Drop memoised dashboard fronts (e.g. after reloading the CSVs)."""
    _cached_pareto_front.cache_clear()


# ---------------------------------------------------------------------------
# GET /api/compare-fuzzy/{location} -- Task 4, fuzzy vs non-fuzzy study
# ---------------------------------------------------------------------------

def _summarize_pareto_front(raw_plans, total_land_ha: float) -> dict:
    """Per-hectare aggregate stats over a feasible Pareto front, used to
    compare the fuzzy and non-fuzzy runs on a like-for-like basis without
    dumping every individual plan twice."""
    if not raw_plans:
        return {
            "n_plans": 0,
            "best_yield_tonnes_per_ha": None,
            "min_cost_rs_per_ha": None,
            "min_irrigated_ha_per_ha": None,
            "min_env_impact_per_ha": None,
        }
    per_ha = [
        {
            "yield_tonnes_per_ha": p.yield_tonnes / (sum(p.area_ha) or total_land_ha),
            "cost_rs_per_ha": p.cost_rs / (sum(p.area_ha) or total_land_ha),
            "irrigated_ha_per_ha": p.irrigated_ha / (sum(p.area_ha) or total_land_ha),
            "env_impact_per_ha": p.env_impact_score / (sum(p.area_ha) or total_land_ha),
        }
        for p in raw_plans
    ]
    return {
        "n_plans": len(raw_plans),
        "best_yield_tonnes_per_ha": round(max(x["yield_tonnes_per_ha"] for x in per_ha), 3),
        "min_cost_rs_per_ha": round(min(x["cost_rs_per_ha"] for x in per_ha), 2),
        "min_irrigated_ha_per_ha": round(min(x["irrigated_ha_per_ha"] for x in per_ha), 1),
        "min_env_impact_per_ha": round(min(x["env_impact_per_ha"] for x in per_ha), 3),
    }


def get_fuzzy_comparison(
    location: str,
    season: Optional[str] = None,
    year: Optional[int] = None,
    total_land_ha: float = 5.0,
    budget_rs: Optional[float] = None,
) -> dict:
    """Runs NSGA-II twice over the *same* region/season profile and fuzzy
    assessment -- once with the Mamdani fuzzy uncertainty adjustment
    applied to crop yield confidence (use_fuzzy=True, identical to what
    every other endpoint already does), once with it bypassed
    (use_fuzzy=False, every crop trusted at its raw "book" yield) -- and
    returns per-hectare summary stats for both, side by side. This is the
    Task 4 fuzzy-vs-non-fuzzy comparison study data source; see
    AnalyticsView.jsx for where it's rendered.
    """
    from app.optimization.nsga2_runner import run_nsga2_with_fuzzy_toggle

    location = resolve_location(location)
    season = pp.canonical_choice(season, config.AG_SEASONS, "season") if season else _current_season()

    profile = pp.get_region_season_profile(location, season, year=year)
    assessment = fz.assess_profile(profile)

    results = {}
    for use_fuzzy in (True, False):
        problem, result = run_nsga2_with_fuzzy_toggle(
            profile,
            assessment,
            total_land_ha=total_land_ha,
            budget_rs=budget_rs,
            use_fuzzy=use_fuzzy,
            pop_size=_DEMO_POP_SIZE,
            track_history=False,
        )
        raw_plans = [p for p in extract_pareto_plans(result, problem) if p.feasible]
        key = "fuzzy" if use_fuzzy else "non_fuzzy"
        results[key] = _summarize_pareto_front(raw_plans, total_land_ha)

    return {
        "location": location,
        "season": season,
        "year": profile.year,
        "total_land_ha": total_land_ha,
        "fuzzy_assessment": fz.assessment_payload(assessment, profile),
        "fuzzy": results["fuzzy"],
        "non_fuzzy": results["non_fuzzy"],
    }


# ---------------------------------------------------------------------------
# GET /api/plans/{location}
# ---------------------------------------------------------------------------

def get_plans(location: str, total_land_ha: float = 5.0, budget_rs: Optional[float] = None) -> dict:
    location = resolve_location(location)
    try:
        profile, assessment, raw_plans, crop_confidence_map, convergence_history = _run_dashboard_pareto_front(
            location, total_land_ha=total_land_ha, budget_rs=budget_rs, track_history=True
        )
        ranked = ranking.rank_plans(raw_plans, crop_confidence_map, preference="balanced", max_plans=_DEMO_POP_SIZE)
        if not ranked:
            raise RuntimeError("NSGA-II run produced no feasible plans")
        hypervolume_history = [
            {"generation": g["generation"], "hypervolume": g["hypervolume"]} for g in convergence_history
        ]

        plans_out = []
        for rp in ranked:
            crops = {
                name: round(pct / 100, 4)
                for name, pct in zip(rp.crop_names, rp.allocation_percent)
                if pct > 0.5
            }
            # rp.cost_rs / yield_tonnes / irrigated_ha / env_impact_score are
            # plan TOTALS over total_land_ha -- normalise to per-hectare so
            # plans (and, later, districts run at a different land size)
            # are comparable on a like-for-like basis.
            area = sum(rp.area_ha) or total_land_ha
            plans_out.append({
                "id": rp.rank - 1,
                "cost": round(rp.cost_rs / area),
                "yield_val": round(rp.yield_tonnes / area, 2),
                "water_val": round(rp.irrigated_ha / area, 3),  # kept key (UI compatibility); now irrigated ha per ha of farm
                "irrigated_ha_per_ha": round(rp.irrigated_ha / area, 3),
                "env_impact": round(rp.env_impact_score / area, 2),
                "is_recommended": rp.rank == 1,
                "crops": crops,
                "rank": rp.rank,
            })
        best = plans_out[0] if plans_out else None
        return {
            "location": location,
            "total_land_ha": total_land_ha,
            "num_plans": len(plans_out),
            "fuzzy_weights": {
                "yield_confidence": fz.assessment_payload(assessment, profile)["yield_confidence"],
                "irrigation_risk": fz.assessment_payload(assessment, profile)["irrigation_risk"],
                "applied": assessment is not None,
            },
            "plans": plans_out,
            "best_plan": {"id": best["id"], "cost": best["cost"], "yield_val": best["yield_val"]} if best else None,
            "is_fallback": False,
            "hypervolume_history": hypervolume_history,
        }
    except Exception as live_exc:  # noqa: BLE001 -- deliberate: catch broadly so we can raise one clean, honest error below
        logger.warning("live NSGA-II run failed for %s: %r", location, live_exc)
        raise PlanGenerationError(
            f"Could not generate plans for {location}: live NSGA-II optimisation "
            f"failed ({live_exc}). No saved-run or CSV-estimate fallback is used -- "
            f"see PlanGenerationError docstring."
        ) from live_exc


# ---------------------------------------------------------------------------
# GET /api/comparison/{location}
# ---------------------------------------------------------------------------

def _radar_scores(rp, trio, irrigation_risk: float, dep_by_crop: dict) -> dict:
    """0-100 scores across 6 axes for the comparison radar chart.
    yield/cost_eff/water/land are TOPSIS-style min-max normalisations
    computed over just these 3 compared plans (higher = better,
    direction-flipped for cost/water/land, where a lower raw value is
    better). land uses each plan's real env_impact_score -- NSGA-II's 4th
    optimisation objective, sqrt(leaching_risk * carbon_proxy) from
    fertiliser and irrigation load (see optimization/problem.py) -- as the
    land-impact proxy, so it's an independent signal rather than a copy of
    yield. risk is the region's fuzzy irrigation_risk, inverted (same
    value for all 3 plans -- it's a regional reading, not plan-specific).
    market has no real market data behind it, so it's built from something
    the dataset does have: the plan's crops' average Rainfall_Dependency
    -- lower climate-dependency is read as more market-stable regardless
    of weather swings."""
    yields = [p.yield_tonnes for p in trio]
    costs = [p.cost_rs for p in trio]
    waters = [p.irrigated_ha for p in trio]
    envs = [p.env_impact_score for p in trio]

    def norm(v, values, higher_better):
        lo, hi = min(values), max(values)
        if hi - lo < 1e-9:
            return 50.0
        n = (v - lo) / (hi - lo)
        return (n if higher_better else 1 - n) * 100

    deps = [
        dep_by_crop.get(name, 0.5)
        for name, pct in zip(rp.crop_names, rp.allocation_percent)
        if pct > 1.0
    ]
    avg_dep_factor = (
        sum(deps) / len(deps) if deps else 0.5
    )

    return {
        "yield": round(norm(rp.yield_tonnes, yields, True)),
        "cost_eff": round(norm(rp.cost_rs, costs, False)),
        "water": round(norm(rp.irrigated_ha, waters, False)),
        "land": round(norm(rp.env_impact_score, envs, False)),
        "risk": round((1 - irrigation_risk) * 100),
        "market": round((1 - avg_dep_factor) * 100),
    }


# DEPRECATED display placeholder. The dataset has no plot/field geometry,
# so these labels carry no information; they are kept in the response only
# so older frontend builds that read `allocations[].plots` don't break.
# The current frontend no longer renders them.
_PLOT_LABELS = ["Plots 1, 2, 4", "Plots 3, 5", "Plot 6", "Plot 7", "Plots 8, 9", "Plot 10"]


def get_comparison(location: str, total_land_ha: float = 5.0, budget_rs: Optional[float] = None) -> dict:
    location = resolve_location(location)
    profile, assessment, raw_plans, crop_confidence_map, _history = _run_dashboard_pareto_front(
        location, total_land_ha=total_land_ha, budget_rs=budget_rs
    )
    if not raw_plans:
        raise ValueError(f"No feasible plans found for {location} to build a comparison from.")

    dep_by_crop = {c.name: c.rainfed_share for c in profile.candidate_crops}

    # Plan A = most balanced (TOPSIS 'balanced' rank 1, i.e. closest to the
    # ideal point across all 4 objectives at once); Plan B = highest yield
    # (TOPSIS 'max_yield' rank 1); Plan C = lowest cost (TOPSIS 'min_cost'
    # rank 1) -- each is the #1 pick of a real TOPSIS ranking over the same
    # Pareto front, not a hand-picked plan.
    balanced = ranking.rank_plans(raw_plans, crop_confidence_map, preference="balanced")[0]
    max_yield = ranking.rank_plans(raw_plans, crop_confidence_map, preference="max_yield")[0]
    min_cost = ranking.rank_plans(raw_plans, crop_confidence_map, preference="min_cost")[0]
    trio = [balanced, max_yield, min_cost]

    chosen = {
        "A": (balanced, "Plan A -- Balanced", True),
        "B": (max_yield, "Plan B -- Max Yield", False),
        "C": (min_cost, "Plan C -- Lowest Cost", False),
    }
    water_values = [p.irrigated_ha for p in trio]

    plans_out = {}
    for key, (rp, label, recommended) in chosen.items():
        crop_items = [
            (name, pct / 100)
            for name, pct in zip(rp.crop_names, rp.allocation_percent)
            if pct > 1.0
        ]
        allocations = [
            {
                "crop": name,
                "pct": f"{round(frac * 100)}%",
                "ha": f"{round(frac * total_land_ha, 1)} Ha",
                "plots": _PLOT_LABELS[i % len(_PLOT_LABELS)],
            }
            for i, (name, frac) in enumerate(crop_items)
        ]
        if rp.irrigated_ha == min(water_values):
            water_label = "Efficient"
        elif rp.irrigated_ha == max(water_values):
            water_label = "High usage"
        else:
            water_label = "Moderate"

        # Same total_land_ha for all 3 (one NSGA-II run) -- normalise to
        # per-hectare for the headline yield/cost/env figures, matching
        # get_plans(); allocations[].ha below is deliberately the absolute
        # hectares instead, since that's what a farmer picking a plan wants.
        area = sum(rp.area_ha) or total_land_ha
        plans_out[key] = {
            "name": label,
            "crops": ", ".join(name for name, _ in crop_items),
            "yield_val": round(rp.yield_tonnes / area, 2),
            "cost": round(rp.cost_rs / area),
            "env_impact": round(rp.env_impact_score / area, 2),
            "water": water_label,
            "recommended": recommended,
            "allocations": allocations,
            "radar_scores": _radar_scores(rp, trio, fz.assessment_payload(assessment, profile)["irrigation_risk"], dep_by_crop),
        }

    return {"location": location, "total_land_ha": total_land_ha, "plans": plans_out}
