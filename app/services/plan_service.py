"""
Orchestrates the full pipeline described in Section III-A of the reference
paper:

    data collection/preprocessing -> fuzzy uncertainty modelling
    -> multi-objective (NSGA-II) optimisation -> decision output
    -> persist results to disk

This is the single entry point the FastAPI routes (and the CLI demo script)
call into.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from app import config
from app.data import preprocessing as pp
from app.decision import ranking
from app.fuzzy import engine as fz
from app.optimization.metrics import run_quality_metrics
from app.optimization.nsga2_runner import FarmPlan, extract_convergence_history, extract_pareto_plans, run_nsga2
from app.optimization.problem import FarmPlanProblem
from app.schemas import FarmPlanRequest
from app.services import results_store


def region_profile_payload(profile: pp.RegionSeasonProfile) -> dict:
    """The `region_profile` block of FarmPlanResponse. Shared with the
    explanation service so a live (unsaved) front is described with exactly
    the same fields as a saved run."""
    return {
        "location": profile.location,
        "year": profile.year,
        "season": profile.season,
        "soil": vars(profile.soil),
        "rainfall": vars(profile.rainfall),
        "water": vars(profile.water),
        "candidate_crops": [
            {
                "name": c.name,
                "crop_type": c.crop_type,
                "yield_kg_ha": c.yield_kg_ha,
                "water_req_mm": c.water_req_mm,
                "rainfall_dependency": c.rainfall_dependency,
                "irrigation_type": c.irrigation_type,
                "sowing_month": c.sowing_month,
                "harvest_month": c.harvest_month,
                "crop_duration_days": c.crop_duration_days,
            }
            for c in profile.candidate_crops
        ],
        "normalized_snapshot": pp.normalized_snapshot(profile),
        "data_year_estimated": profile.data_year_estimated,
    }


@dataclass(frozen=True)
class PipelineAdjustments:
    """Scenario modifications applied inside the normal pipeline (Scenario
    Simulation). Every default reproduces an ordinary run exactly.

    rainfall_factor          multiplies monthly rainfall before aggregation
    storage_override_pct     replaces seasonal reservoir storage % (fuzzy water input)
    fertilizer_price_factor  multiplies fertiliser prices in the cost objective
    topsis_weights           explicit [yield, cost, water, env] TOPSIS weights
    """
    rainfall_factor: float = 1.0
    storage_override_pct: Optional[float] = None
    fertilizer_price_factor: float = 1.0
    topsis_weights: Optional[Tuple[float, float, float, float]] = None


@dataclass
class PipelineRun:
    """A pipeline result plus the internals a caller may need beyond the
    response: the full feasible Pareto set (before filtering/truncation)
    and the FarmPlanProblem (for evaluating single-crop plans)."""
    response: dict
    feasible_plans: List[FarmPlan]
    problem: FarmPlanProblem


def run_pipeline(
    request: FarmPlanRequest,
    adjustments: Optional[PipelineAdjustments] = None,
    track_history: Optional[bool] = None,
    seed: Optional[int] = None,
) -> PipelineRun:
    """Stages 1-4 (preprocessing -> fuzzy -> NSGA-II -> TOPSIS) for one
    request. Used by generate_farm_plans and by the scenario simulator, so a
    simulated plan is produced by exactly the same code as a normal run."""
    adj = adjustments or PipelineAdjustments()

    # ---- Stage 1: data collection & preprocessing ----
    profile = pp.get_region_season_profile(
        location=request.location,
        season=request.season,
        year=request.year,
        max_candidate_crops=request.max_candidate_crops,
        rainfall_factor=adj.rainfall_factor,
        storage_override_pct=adj.storage_override_pct,
    )

    # ---- Stage 2: fuzzy uncertainty modelling ----
    assessment = fz.evaluate_uncertainty(
        rainfall_deviation_percent=profile.rainfall.avg_deviation_percent,
        water_storage_percent=profile.water.avg_storage_percent,
        soil_fertility_index=profile.soil.fertility_index,
    )

    # ---- Stage 3: multi-objective NSGA-II optimisation ----
    problem = FarmPlanProblem(
        profile=profile,
        assessment=assessment,
        total_land_ha=request.total_land_ha,
        budget_rs=request.budget_rs,
        fertilizer_price_factor=adj.fertilizer_price_factor,
    )

    pop_size = request.pop_size or config.NSGA2_POP_SIZE
    n_gen = request.n_gen or config.NSGA2_N_GEN

    # Only pay the extra history-tracking cost (~2-3x slower) when we're
    # actually going to persist the convergence curve.
    if track_history is None:
        track_history = bool(request.save_results)

    t0 = time.time()
    seed_kwargs = {} if seed is None else {"seed": seed}
    result = run_nsga2(problem, pop_size=pop_size, n_gen=n_gen, track_history=track_history, **seed_kwargs)
    optimize_seconds = round(time.time() - t0, 3)

    convergence_history = extract_convergence_history(result) if track_history else []

    raw_plans = extract_pareto_plans(result, problem)
    raw_plans = [p for p in raw_plans if p.feasible]

    # ---- Stage 4: decision output (filter -> rank -> summarise) ----
    filtered_plans = ranking.filter_plans(
        raw_plans,
        max_cost=request.max_cost_rs,
        max_water_liters=request.max_water_liters,
        min_yield_tonnes=request.min_yield_tonnes,
        max_env_impact=request.max_env_impact,
    )

    crop_confidence_map = dict(zip(problem.crop_vec.names, problem.crop_vec.crop_yield_confidence.tolist()))
    ranked = ranking.rank_plans(
        filtered_plans,
        crop_confidence_map=crop_confidence_map,
        preference=request.preference,
        weights=list(adj.topsis_weights) if adj.topsis_weights is not None else None,
    )

    meta = {
        "algorithm": "NSGA-II",
        "pop_size": pop_size,
        "n_gen": n_gen,
        "crossover_prob": config.NSGA2_CROSSOVER_PROB,
        "mutation_prob": config.NSGA2_MUTATION_PROB,
        "preference": request.preference,
        "n_pareto_solutions_found": len(raw_plans),
        "n_plans_returned": len(ranked),
        "optimize_seconds": optimize_seconds,
        "total_land_ha": request.total_land_ha,
        "budget_rs": request.budget_rs,
        # Engine mode, runtime profile and diversity statistics of this run.
        # Kept in the saved run record for reports; the API's RunMeta model
        # does not declare it, so the /api/optimize response is unchanged.
        "optimizer": getattr(result, "engine_report", None),
        # Pareto-front quality of this run (hypervolume, GD, IGD, IGD+,
        # spread, spacing, constraint satisfaction, effort, mean objectives;
        # see app/optimization/metrics.py). Observes the result only.
        "quality_metrics": run_quality_metrics(result, problem),
    }
    if adjustments is not None:
        meta["topsis_weights"] = (
            ranking.normalise_weights(adj.topsis_weights) if adj.topsis_weights is not None
            else ranking.preference_weights(request.preference)
        ).tolist()   # full precision: explanations re-rank with these exact weights
        meta["adjustments"] = {
            "rainfall_factor": adj.rainfall_factor,
            "storage_override_pct": adj.storage_override_pct,
            "fertilizer_price_factor": adj.fertilizer_price_factor,
            "custom_weights": adj.topsis_weights is not None,
        }

    response = {
        "region_profile": region_profile_payload(profile),
        "fuzzy_assessment": vars(assessment),
        "plans": ranking.to_dict_list(ranked),
        "convergence_history": convergence_history,
        "meta": meta,
    }
    return PipelineRun(response=response, feasible_plans=raw_plans, problem=problem)


def generate_farm_plans(
    request: FarmPlanRequest,
    results_dir: Optional[Path] = None,
) -> dict:
    response = run_pipeline(request).response
    convergence_history = response["convergence_history"]

    # ---- Stage 5: persist results to disk ----
    if request.save_results:
        saved = results_store.save_run_results(
            response,
            convergence_history,
            out_dir=results_dir if results_dir is not None else config.RESULTS_DIR,
            client_id=request.client_id,
        )
        response["run_id"] = saved.run_id
        response["saved_files"] = saved.to_dict()
    else:
        response["run_id"] = None
        response["saved_files"] = None

    return response
