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

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.data import preprocessing as pp
from app.schemas import CatalogOut, FarmPlanRequest, FarmPlanResponse, SavedRunSummaryOut

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

# Permissive CORS for now -- a dedicated frontend will be wired up later.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    """Every run that has been saved to disk so far (most recent first)."""
    from app.services import results_store

    return results_store.list_saved_runs()


@app.get("/api/results/{run_id}", response_model=FarmPlanResponse)
def get_result(run_id: str):
    """Full saved record for one past run, including its convergence
    history -- exactly what was written to results/<run_id>.json."""
    from app.services import results_store

    record = results_store.load_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No saved run with id '{run_id}'.")
    return record
