"""
AgroOptimize backend API.

A fuzzy-evolutionary (NSGA-II) decision support system for agricultural
farming under uncertainty. See notes/methodology_notes.md for the full
write-up and notes/viva_prep.md for a Q&A-style reference.

Run locally:
    uvicorn app.main:app --reload --port 8000

Then open http://127.0.0.1:8000/docs for interactive Swagger docs.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.data import preprocessing as pp
from typing import Literal

from app.schemas import CatalogOut, ExplanationOut, FarmPlanRequest, FarmPlanResponse, SavedRunSummaryOut

# Shared query-parameter validation for the dashboard endpoints. Land must
# be positive (it is a divisor in every per-hectare figure); the upper
# bounds only reject absurd inputs, not realistic farms.
_LAND_HA_QUERY = Query(5.0, gt=0, le=100_000, description="Farm size in hectares.")
_BUDGET_QUERY = Query(None, gt=0, description="Optional hard budget cap (Rs).")
_CLIENT_ID_QUERY = Query(None, max_length=128, description="Opaque per-browser id.")

app = FastAPI(
    title="AgroOptimize API",
    description=(
        "Fuzzy-evolutionary decision support system for agricultural farming "
        "under uncertainty. Combines a Mamdani fuzzy inference engine "
        "(rainfall / water / soil uncertainty) with NSGA-II multi-objective "
        "optimisation (yield, cost, water use, environmental impact) to "
        "produce a ranked set of Pareto-optimal farming plans."
    ),
    version="0.1.0",
)

# CORS for the Vite/React frontend (src: stitch_agrooptimize_app). Must be
# added before any route definitions -- it isn't order-sensitive for
# @app.get/@app.post itself, but keeping it first makes it apply to every
# route below without having to think about it again.
#
# The deployed frontend (Vercel, see stitch_agrooptimize_app/vercel.json)
# is served from whatever domain Vercel assigns it, which isn't known at
# code-time -- set CORS_ALLOW_ORIGINS (comma-separated) in the backend's
# deployment environment to add it, e.g.
# CORS_ALLOW_ORIGINS=https://agrooptimize.vercel.app. Local dev keeps
# working unchanged via the hardcoded localhost defaults below.
_default_origins = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:3000",
]
_extra_origins = [o.strip() for o in os.environ.get("CORS_ALLOW_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_default_origins + _extra_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/catalog", response_model=CatalogOut)
def get_catalog():
    """What locations / years / seasons / crops the dataset covers."""
    return pp.list_catalog()


@app.get("/api/region-profile")
def get_region_profile(location: str, season: str, year: int | None = None):
    """Preprocessing + fuzzy stages only -- useful for inspecting/demoing
    the data pipeline without running the (slower) optimisation stage."""
    try:
        profile = pp.get_region_season_profile(location=location, season=season, year=year)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    from app.fuzzy import engine as fz

    assessment = fz.evaluate_uncertainty(
        profile.rainfall.avg_deviation_percent,
        profile.water.avg_storage_percent,
        profile.soil.fertility_index,
    )
    return {
        "location": profile.location,
        "year": profile.year,
        "season": profile.season,
        "soil": vars(profile.soil),
        "rainfall": vars(profile.rainfall),
        "water": vars(profile.water),
        "candidate_crops": [c.name for c in profile.candidate_crops],
        "normalized_snapshot": pp.normalized_snapshot(profile),
        "data_year_estimated": profile.data_year_estimated,
        "fuzzy_assessment": vars(assessment),
    }


@app.post("/api/farm-plans", response_model=FarmPlanResponse)
def post_farm_plans(request: FarmPlanRequest):
    """Full pipeline: preprocessing -> fuzzy -> NSGA-II -> ranked plans.

    When `save_results` (default true) is set on the request, the run is
    also written to disk under results/ -- see GET /api/results and
    GET /api/results/{run_id} to browse/retrieve saved runs afterwards.
    """
    from app.services.plan_service import generate_farm_plans

    try:
        return generate_farm_plans(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/results", response_model=list[SavedRunSummaryOut])
def list_results():
    """Every run that has been saved to disk so far (most recent first).

    `client_id` is always null here: it is the only thing scoping
    GET /api/history/{location} to one browser, so publishing every run's
    id would let any caller read any other visitor's history."""
    from app.services import results_store

    return [{**run, "client_id": None} for run in results_store.list_saved_runs()]


@app.get("/api/results/{run_id}", response_model=FarmPlanResponse)
def get_result(run_id: str):
    """Full saved record for one past run, including its convergence
    history -- exactly what was written to results/<run_id>.json."""
    from app.services import results_store

    record = results_store.load_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No saved run with id '{run_id}'.")
    return record


@app.get("/api/results/{run_id}/explanation", response_model=ExplanationOut)
def get_result_explanation(run_id: str, rank: int = Query(1, ge=1, le=500, description="Plan rank to explain (1 = top).")):
    """Structured, data-derived explanation of one plan in a saved run:
    reasons, objective balance, trade-offs, constraints, benefits, risks,
    historical context, confidence breakdown and pipeline trace. See
    app/services/explanation_service.py."""
    from app.services import explanation_service, results_store

    record = results_store.load_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No saved run with id '{run_id}'.")
    try:
        return explanation_service.explain_saved_run(record, rank=rank)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Frontend-facing dashboard endpoints (stitch_agrooptimize_app).
#
# These all take a lowercase district path segment (coimbatore / erode /
# salem / pollachi) rather than the Title-case `location` the rest of the
# API uses, to match how the frontend derives a district from the user's
# saved farm location. See app/services/dashboard_service.py for the
# derivation of every field -- everything here is computed from
# data/raw/*.csv and the real fuzzy/NSGA-II/TOPSIS pipeline, not hardcoded.
# ---------------------------------------------------------------------------


@app.get("/api/weather/{location}")
def get_weather(location: str):
    """Current conditions + 5-day forecast from the live Open-Meteo API.
    If that call fails (no network, API down) it falls back to this
    district's historical rainfall.csv averages for the current and next
    five calendar months; the `source` field says which path produced the
    response."""
    from app.services import dashboard_service as ds

    try:
        return ds.get_weather(location)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/dashboard/{location}")
def get_dashboard(location: str, client_id: str | None = _CLIENT_ID_QUERY):
    """Dashboard KPI summary: yield/trend, active plans, soil health, water
    utilisation, recommended actions (from N/P/K status), and top-3
    crop allocation -- all derived from crop.csv/land.csv/water_availability.csv.
    `active_plans` is scoped to this browser's own client_id, the same rule
    GET /api/history/{location} uses -- a brand new client_id correctly
    gets 0."""
    from app.services import dashboard_service as ds

    try:
        return ds.get_dashboard(location, client_id=client_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/history/{location}")
def get_history(location: str, client_id: str | None = _CLIENT_ID_QUERY):
    """Past optimisation runs for a district: ONLY this browser's own real
    saved runs from results/ (matched by `client_id` -- there are no user
    accounts here, so a run only shows for the client that generated it).
    No CSV-derived filler rows -- a brand new client_id (or none) returns
    an empty list, and the frontend shows a "no runs yet" empty state."""
    from app.services import dashboard_service as ds

    try:
        return ds.get_history(location, client_id=client_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/soil-profile/{location}")
def get_soil_profile_by_district(location: str):
    """Soil snapshot for the farm-map section, read directly from the
    district's land.csv (current season's row)."""
    from app.services import dashboard_service as ds

    try:
        return ds.get_soil_profile(location)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/plans/{location}")
def get_plans_by_district(
    location: str, total_land_ha: float = _LAND_HA_QUERY, budget_rs: float | None = _BUDGET_QUERY
):
    """Up to ~100 Pareto-optimal plans for AnalyticsView's scatter plot, from
    a live NSGA-II run. If that run fails there is no saved-run or
    CSV-estimate fallback (removed -- see dashboard_service.PlanGenerationError):
    this endpoint returns a clear 503 rather than silently substituting an
    old run or a synthetic single-crop estimate for a real optimisation."""
    from app.services import dashboard_service as ds

    try:
        return ds.get_plans(location, total_land_ha=total_land_ha, budget_rs=budget_rs)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ds.PlanGenerationError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Optimization failed",
                "message": str(exc),
                "location": location,
            },
        ) from exc


@app.get("/api/comparison/{location}")
def get_comparison_by_district(
    location: str, total_land_ha: float = _LAND_HA_QUERY, budget_rs: float | None = _BUDGET_QUERY
):
    """Plan A (balanced) / B (max yield) / C (lowest cost) for
    ComparisonView -- each the #1 pick of a real TOPSIS ranking over the
    same live Pareto front, not hand-picked."""
    from app.services import dashboard_service as ds

    try:
        return ds.get_comparison(location, total_land_ha=total_land_ha, budget_rs=budget_rs)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/compare-fuzzy/{location}")
def get_fuzzy_comparison_by_district(
    location: str,
    season: str | None = None,
    year: int | None = None,
    total_land_ha: float = _LAND_HA_QUERY,
    budget_rs: float | None = _BUDGET_QUERY,
):
    """Fuzzy-vs-non-fuzzy comparison study (Task 4): runs NSGA-II twice
    over the same region/season/fuzzy-assessment -- once with the Mamdani
    fuzzy uncertainty adjustment applied to crop yield confidence, once
    with it bypassed -- and returns per-hectare summary stats for both, so
    AnalyticsView can render them side by side. See
    dashboard_service.get_fuzzy_comparison / app/optimization/problem.py
    (CropVector.from_candidates use_fuzzy flag) for how the bypass works."""
    from app.services import dashboard_service as ds

    try:
        return ds.get_fuzzy_comparison(
            location, season=season, year=year, total_land_ha=total_land_ha, budget_rs=budget_rs
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/comparison/{location}/explanation", response_model=ExplanationOut)
def get_comparison_explanation(
    location: str,
    plan: Literal["A", "B", "C"] = Query("A", description="A = balanced, B = max yield, C = lowest cost."),
    total_land_ha: float = _LAND_HA_QUERY,
    budget_rs: float | None = _BUDGET_QUERY,
):
    """Explanation of Plan A, B or C from GET /api/comparison/{location},
    built from the same memoised Pareto front."""
    from app.services import explanation_service

    try:
        return explanation_service.explain_comparison_plan(location, plan, total_land_ha=total_land_ha, budget_rs=budget_rs)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
