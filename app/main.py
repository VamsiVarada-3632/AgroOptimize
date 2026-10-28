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
from fastapi.middleware.gzip import GZipMiddleware

from app.data import preprocessing as pp
from typing import Literal, Optional

from app.schemas import (
    CatalogOut,
    DistrictIntelligenceOut,
    ExplanationOut,
    FarmPlanRequest,
    FarmPlanResponse,
    SavedRunSummaryOut,
    SavedSimulationOut,
    SavedSimulationSummaryOut,
    SimulationOut,
    SimulationRequest,
    SimulationSaveIn,
    TopsisRankingOut,
    TopsisRerankIn,
)

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

# Plans, explanations and district profiles are large JSON documents
# (often 100-500 kB); compressing them cuts transfer size by ~85-90 %.
# Only the encoding changes, never the content.
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# Uptime monitors often probe with HEAD; answer it without a second schema entry.
@app.head("/health", include_in_schema=False)
def health_head() -> dict:
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


@app.get("/api/topsis/profiles")
def get_topsis_profiles():
    """Ranking profiles (weights per decision criterion, how they were
    derived), every criterion's definition, and the custom-weight rules."""
    from app.decision import profiles

    return profiles.catalogue()


def _rerank(run_id: str, body: TopsisRerankIn):
    from app.services import results_store, topsis_service

    record = results_store.load_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No saved run with id '{run_id}'.")
    try:
        return topsis_service.rerank_saved_run(
            record, body.profile, body.custom_weights.as_dict() if body.custom_weights else None, compare=body.compare)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/results/{run_id}/topsis", response_model=TopsisRankingOut)
def get_result_topsis(
    run_id: str,
    profile: Literal["balanced", "profit", "water", "sustainability", "low_cost"] = Query(
        "balanced", description="Ranking profile; use POST for custom weights."),
    compare: bool = Query(True, description="Also rank the front under every standard profile."),
):
    """Re-rank a saved run's Pareto front under a ranking profile. Only the
    TOPSIS stage runs: the plans, objectives and fuzzy assessment are the
    saved ones."""
    return _rerank(run_id, TopsisRerankIn(profile=profile, compare=compare))


@app.post("/api/results/{run_id}/topsis", response_model=TopsisRankingOut)
def post_result_topsis(run_id: str, body: TopsisRerankIn):
    """As GET, with custom weights: {"profile": "custom", "custom_weights": {...}}."""
    return _rerank(run_id, body)


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


@app.get("/api/district-intelligence/{location}", response_model=DistrictIntelligenceOut)
def get_district_intelligence(location: str):
    """Everything the project knows about one district in one response:
    overview, data coverage, climate, soil, water, crop history, crop
    suitability ranking, historical prices, generated insights and a
    summary. Built only from observed dataset rows and existing pipeline
    calculations; cached per district."""
    from app.services import district_service

    try:
        return district_service.get_district_intelligence(location)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Scenario Simulation
# ---------------------------------------------------------------------------

_REQUIRED_CLIENT_ID = Query(..., min_length=1, max_length=128, description="Opaque per-browser id.")


@app.post("/api/simulations/run", response_model=SimulationOut)
def run_simulation(request: SimulationRequest):
    """Run the baseline and the modified scenario through the full pipeline
    (preprocessing -> fuzzy -> NSGA-II -> TOPSIS -> explanation) over the
    same seeds and return the decision impact analysis. Never cached. The
    returned `token` lets this browser save exactly this result."""
    from app.services import simulation_service as sim

    try:
        result = sim.simulate(request.as_payload())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {**result, "token": sim.remember(result, request.client_id)}


@app.post("/api/simulations", response_model=SavedSimulationSummaryOut, status_code=201)
def save_simulation(body: SimulationSaveIn):
    """Save a result returned by POST /api/simulations/run in this session."""
    from app.services import results_store
    from app.services import simulation_service as sim

    result = sim.pending(body.token, body.client_id)
    if result is None:
        raise HTTPException(status_code=404, detail="That simulation result has expired; run it again to save it.")
    stored = results_store.save_simulation(result, client_id=body.client_id, name=body.name)
    summary = next(s for s in results_store.list_simulations(body.client_id) if s["simulation_id"] == stored["simulation_id"])
    return summary


@app.get("/api/simulations", response_model=list[SavedSimulationSummaryOut])
def list_simulations(client_id: str = _REQUIRED_CLIENT_ID):
    """This browser's saved simulations, newest first."""
    from app.services import results_store

    return results_store.list_simulations(client_id)


@app.get("/api/simulations/{simulation_id}", response_model=SavedSimulationOut)
def get_simulation(simulation_id: str, client_id: str = _REQUIRED_CLIENT_ID):
    from app.services import results_store

    record = results_store.load_simulation(simulation_id, client_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No saved simulation with id '{simulation_id}'.")
    return record


@app.delete("/api/simulations/{simulation_id}")
def delete_simulation(simulation_id: str, client_id: str = _REQUIRED_CLIENT_ID):
    from app.services import results_store

    if not results_store.delete_simulation(simulation_id, client_id):
        raise HTTPException(status_code=404, detail=f"No saved simulation with id '{simulation_id}'.")
    return {"deleted": simulation_id}


# ---------------------------------------------------------------------------
# Fuzzy system transparency (read-only)
# ---------------------------------------------------------------------------

def _fuzzy_model_or_400(name: Optional[str]):
    from app.fuzzy import engine as fz

    try:
        return fz.resolve_model(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/fuzzy/models")
def fuzzy_models():
    """The fuzzy models the engine can run: the published one, each
    improvement on its own, and their switches, rule numbers and membership
    functions. `default` is the model used when a request names none."""
    from app.fuzzy import engine as fz

    return {
        "default": fz.resolve_model().name,
        "models": [{"name": m.name, "description": m.description,
                    "switches": {"strong_partition": m.strong_partition, "imd_rainfall": m.imd_rainfall,
                                 "prune_inert": m.prune_inert},
                    "rules": list(fz.rule_numbers(m)),
                    "membership_functions": {v: {t: list(p) for t, p in sets.items()}
                                             for v, sets in fz.membership_functions(m).items()}}
                   for m in fz.MODELS.values()],
    }


@app.get("/api/fuzzy/explain")
def explain_fuzzy(
    rainfall_dev: float = Query(..., description="Season rainfall deviation from normal, %."),
    water_storage: float = Query(..., description="Seasonal reservoir storage, %."),
    soil_fert: float = Query(..., description="Soil fertility index, 0-100."),
    model: Optional[str] = Query(None, description="Fuzzy model (GET /api/fuzzy/models); default if omitted."),
):
    """Rule-level explanation of the Mamdani engine for one input triple:
    memberships, every rule's firing strength, status (decisive / masked /
    not fired), contribution and leave-one-out importance, and per output
    the term cuts and crisp value. Inputs are clipped like the engine's."""
    import math

    from app.fuzzy import engine as fz

    if not all(math.isfinite(v) for v in (rainfall_dev, water_storage, soil_fert)):
        raise HTTPException(status_code=422, detail="Inputs must be finite numbers.")
    return fz.explain_inference(rainfall_dev, water_storage, soil_fert, model=_fuzzy_model_or_400(model))


@app.get("/api/fuzzy/audit")
def audit_fuzzy(model: Optional[str] = Query(None, description="Fuzzy model (GET /api/fuzzy/models); default if omitted.")):
    """Static audit of the rule base and membership functions plus rule
    firing statistics on the dataset's region profiles (cached per model)."""
    from app.fuzzy import audit

    return audit.summary(_fuzzy_model_or_400(model))


# ---------------------------------------------------------------------------
# Frontend (production build), registered last so every API route wins
# ---------------------------------------------------------------------------

from app.frontend import mount_frontend  # noqa: E402

mount_frontend(app)
