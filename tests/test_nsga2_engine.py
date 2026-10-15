"""
Tests for the NSGA-II engine modes, operators and monitoring.

The original engine must reproduce the published results exactly, so the
first group checks it against digests recorded from the engine before
this work, and checks each speed-up against the code it replaced. The
other groups check that each enhanced feature does what it says, stays
within bounds and is deterministic.
"""

from __future__ import annotations

import dataclasses
import hashlib

import numpy as np
import pytest
from pymoo.algorithms.moo.nsga2 import binary_tournament as pymoo_binary_tournament
from pymoo.operators.selection.tournament import TournamentSelection

from app import config
from app.data import preprocessing as pp
from app.fuzzy import engine as fz
from app.optimization import nsga2_runner, operators
from app.optimization.engine_settings import FEATURES_CHANGING_OUTPUTS, EngineSettings, engine_settings
from app.optimization.monitoring import (
    adaptive_mutation_prob,
    allocation_diversity,
    mean_crowding,
    population_entropy,
)
from app.optimization.nsga2_runner import extract_convergence_history, extract_pareto_plans, run_nsga2
from app.optimization.operators import SinglePointCrossover, SmartSampling, seed_chromosomes
from app.optimization.problem import FarmPlanProblem

FAST = dict(pop_size=config.NSGA2_FAST_POP_SIZE, n_gen=config.NSGA2_FAST_N_GEN)


def _problem(location="Salem", season="Kharif", year=None, budget=None, land=5.0):
    profile = pp.get_region_season_profile(location, season, year=year)
    assessment = fz.evaluate_uncertainty(
        profile.rainfall.avg_deviation_percent,
        profile.water.avg_storage_percent,
        profile.soil.fertility_index,
    )
    return FarmPlanProblem(profile, assessment, total_land_ha=land, budget_rs=budget)


def _digest(result) -> str:
    X = np.ascontiguousarray(result.pop.get("X"))
    F = np.ascontiguousarray(result.pop.get("F"))
    return hashlib.sha256(X.tobytes() + F.tobytes()).hexdigest()[:16]


def _same_population(r1, r2):
    np.testing.assert_array_equal(r1.pop.get("X"), r2.pop.get("X"))
    np.testing.assert_array_equal(r1.pop.get("F"), r2.pop.get("F"))


@pytest.fixture(scope="module")
def salem():
    return _problem()


# ---------------------------------------------------------------------------
# Original engine: published results unchanged
# ---------------------------------------------------------------------------

# Digests of the final population recorded with the engine as it was before
# the mode switch, vectorised operators and monitor were added.
@pytest.mark.parametrize(
    "args, kwargs, digest",
    [
        (("Coimbatore", "Kharif", 2023, 200_000), dict(pop_size=24, n_gen=15, seed=7), "76f9be6f11d8a0c0"),
        (("Salem", "Kharif", None, None), dict(seed=42), "5e51af2fa33eb620"),
        # budget below every plan's cost: exercises the infeasible branch of the tournament
        (("Erode", "Rabi", None, 120_000), dict(pop_size=40, n_gen=60, seed=3), "715330adb9d41f43"),
    ],
)
def test_original_mode_reproduces_published_results(args, kwargs, digest):
    location, season, year, budget = args
    result = run_nsga2(_problem(location, season, year, budget), mode="original", **kwargs)
    assert _digest(result) == digest


def test_default_mode_is_original():
    assert config.NSGA2_ENGINE_MODE == "original"
    settings = engine_settings()
    assert settings.mode == "original"
    assert not settings.changes_outputs
    assert settings.mutation_prob == config.NSGA2_MUTATION_PROB == 0.12   # the paper's value


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        engine_settings("turbo")


def _loop_crossover(X):
    """The single-point crossover as it was written before vectorisation."""
    _, n_matings, n_var = X.shape
    Y = np.empty_like(X)
    for k in range(n_matings):
        p1, p2 = X[0, k], X[1, k]
        point = np.random.randint(1, n_var) if n_var > 1 else 1
        Y[0, k] = np.concatenate([p1[:point], p2[point:]])
        Y[1, k] = np.concatenate([p2[:point], p1[point:]])
    return Y


@pytest.mark.parametrize("n_var", [1, 2, 6, 15, 36])
def test_vectorised_crossover_matches_the_loop(n_var):
    X = np.random.default_rng(n_var).random((2, 40, n_var))
    np.random.seed(11)
    expected = _loop_crossover(X)
    after_loop = np.random.random()
    np.random.seed(11)
    got = SinglePointCrossover()._do(None, X)
    np.testing.assert_array_equal(got, expected)
    assert np.random.random() == after_loop  # same number of draws consumed


@pytest.mark.parametrize("budget", [None, 200_000, 20_000])
def test_vectorised_tournament_matches_pymoo(monkeypatch, budget):
    problem = _problem("Coimbatore", "Rabi", budget=budget)
    ours = run_nsga2(problem, seed=5, pop_size=30, n_gen=25)
    monkeypatch.setattr(nsga2_runner, "TournamentSelection",
                        lambda func_comp: TournamentSelection(func_comp=pymoo_binary_tournament))
    theirs = run_nsga2(problem, seed=5, pop_size=30, n_gen=25)
    _same_population(ours, theirs)


def test_monitor_history_matches_pymoo_save_history(salem):
    ours = run_nsga2(salem, seed=4, track_history=True, **FAST)
    np.random.seed(4)
    from pymoo.optimize import minimize
    algorithm = nsga2_runner.NSGA2(
        pop_size=FAST["pop_size"],
        sampling=nsga2_runner.FloatRandomSampling(),
        crossover=SinglePointCrossover(prob=config.NSGA2_CROSSOVER_PROB),
        mutation=operators.GaussianMutation(prob=config.NSGA2_MUTATION_PROB, sigma=config.NSGA2_MUTATION_SIGMA),
        repair=operators.AllocationRepair(),
        eliminate_duplicates=True,
    )
    theirs = minimize(salem, algorithm, ("n_gen", FAST["n_gen"]), seed=4, save_history=True)
    assert extract_convergence_history(ours) == extract_convergence_history(theirs)
    _same_population(ours, theirs)


def test_monitoring_and_profiling_do_not_change_results(salem):
    base = engine_settings("original")
    quiet = dataclasses.replace(base, diversity_monitoring=False, runtime_profiling=False)
    _same_population(run_nsga2(salem, seed=9, engine=base, **FAST), run_nsga2(salem, seed=9, engine=quiet, **FAST))


def test_history_tracking_does_not_change_results(salem):
    _same_population(run_nsga2(salem, seed=2, **FAST), run_nsga2(salem, seed=2, track_history=True, **FAST))


def test_cached_problem_constants_give_the_same_objectives(salem):
    """FarmPlanProblem now precomputes per-crop constants; the objectives
    must equal the formula written out in full."""
    from app.optimization.problem import config as pc
    X = np.random.default_rng(0).uniform(salem.xl, salem.xu, (50, salem.n_var))
    F = salem.evaluate(X, return_as_dictionary=True)["F"]
    n, cv = salem.n_crops, salem.crop_vec
    alloc = X[:, :n] / np.clip(X[:, :n].sum(axis=1, keepdims=True), 1e-9, None)
    irr, fert = X[:, n:2 * n], X[:, 2 * n:]
    area = alloc * salem.total_land_ha
    prices = {k: v * salem.fertilizer_price_factor for k, v in pc.FERTILIZER_PRICE_RS_PER_KG_NUTRIENT.items()}
    fert_cost = cv.fert_n_kg_ha * prices["N"] + cv.fert_p_kg_ha * prices["P"] + cv.fert_k_kg_ha * prices["K"]
    cost = (area * (fert * fert_cost + cv.pesticide_cost_rs_ha + cv.labor_days_ha * pc.LABOR_WAGE_RS_PER_DAY)).sum(1)
    net = np.clip(cv.water_req_mm - salem.effective_rainfall_mm, 0.0, None)
    water = (area * irr * net * pc.LITERS_PER_MM_PER_HA).sum(1)
    yld = (area * (cv.yield_kg_ha / 1000.0) * cv.crop_yield_confidence).sum(1)
    leach = (area * fert * cv.fert_n_kg_ha).sum(1)
    carbon = (area * fert * (cv.fert_n_kg_ha + cv.fert_p_kg_ha + cv.fert_k_kg_ha) * pc.CARBON_FERTILIZER_FACTOR
              + area * irr * cv.water_req_mm * pc.CARBON_PUMPING_FACTOR).sum(1)
    np.testing.assert_array_equal(F, np.column_stack([-yld, cost, water, np.sqrt(leach * carbon)]))


# ---------------------------------------------------------------------------
# Engine report (profiling and diversity monitoring)
# ---------------------------------------------------------------------------

def test_engine_report_records_profile_and_diversity(salem):
    result = run_nsga2(salem, seed=1, **FAST)
    report = result.engine_report
    assert report["engine"] == {"mode": "original", "features": ["diversity_monitoring", "runtime_profiling"],
                                "mutation_prob": config.NSGA2_MUTATION_PROB}
    prof = report["profile"]
    assert prof["generations"] == FAST["n_gen"]
    assert prof["evaluations"] == FAST["pop_size"] * FAST["n_gen"]
    assert prof["pareto_size"] == len(result.X)
    assert prof["total_seconds"] > 0 and prof["avg_generation_ms"] > 0
    div = report["diversity"]
    for key in ("entropy", "allocation_diversity", "mean_crowding", "front_size"):
        assert set(div[key]) == {"initial", "final", "min"}
    assert 0 <= div["entropy"]["final"] <= 1
    assert 0 <= div["duplicate_ratio"] < 1


def test_observers_can_be_switched_off(salem):
    quiet = dataclasses.replace(engine_settings("original"), diversity_monitoring=False, runtime_profiling=False)
    report = run_nsga2(salem, seed=1, engine=quiet, **FAST).engine_report
    assert "profile" not in report and "diversity" not in report


def test_population_entropy_bounds():
    xl, xu = np.zeros(4), np.ones(4)
    assert population_entropy(np.full((50, 4), 0.3), xl, xu) == pytest.approx(0.0)
    even = np.tile((np.arange(100) + 0.5)[:, None] / 100, (1, 4))
    assert population_entropy(even, xl, xu) == pytest.approx(1.0)


def test_allocation_diversity_and_mean_crowding():
    X = np.array([[1.0, 0.0, 0.7], [0.0, 1.0, 0.7]])
    assert allocation_diversity(X, 2) == pytest.approx(0.5)
    rank = np.array([0, 0, 0, 1])
    crowding = np.array([np.inf, 0.2, 0.4, 9.0])
    assert mean_crowding(rank, crowding) == pytest.approx(0.3)


# ---------------------------------------------------------------------------
# Enhanced features
# ---------------------------------------------------------------------------

def _with(feature: str, **params) -> EngineSettings:
    return dataclasses.replace(engine_settings("original"), **{feature: True}, **params)


@pytest.mark.parametrize("feature", FEATURES_CHANGING_OUTPUTS)
def test_each_feature_is_valid_deterministic_and_changes_the_search(salem, feature):
    settings = _with(feature, early_stopping_params={"patience": 5, "tolerance": 1e-3, "min_generations": 10})
    r1 = run_nsga2(salem, seed=3, engine=settings, pop_size=30, n_gen=40)
    r2 = run_nsga2(salem, seed=3, engine=settings, pop_size=30, n_gen=40)
    _same_population(r1, r2)                       # deterministic for a seed
    base = run_nsga2(salem, seed=3, pop_size=30, n_gen=40)
    assert _digest(r1) != _digest(base)            # the feature does change the search
    X = r1.pop.get("X")
    assert np.all(X >= salem.xl - 1e-12) and np.all(X <= salem.xu + 1e-12)
    for plan in extract_pareto_plans(r1, salem):
        assert abs(sum(plan.allocation_fraction) - 1.0) < 1e-6
    assert feature in r1.engine_report["engine"]["features"]


def test_enhanced_mode_runs_end_to_end(salem):
    settings = engine_settings("enhanced")
    assert settings.changes_outputs
    assert settings.mutation_prob == config.NSGA2_ENGINE_MUTATION_PROB["enhanced"]
    result = run_nsga2(salem, mode="enhanced", seed=42)
    assert result.engine_report["engine"]["mode"] == "enhanced"
    assert len([p for p in extract_pareto_plans(result, salem) if p.feasible]) > 0


def test_mode_is_selected_by_the_environment(monkeypatch, salem):
    monkeypatch.setattr(config, "NSGA2_ENGINE_MODE", "enhanced")
    assert engine_settings().mode == "enhanced"
    assert run_nsga2(salem, seed=1, **FAST).engine_report["engine"]["mode"] == "enhanced"


def test_seed_chromosomes_use_the_candidate_crops(salem):
    seeds = seed_chromosomes(salem)
    n = salem.n_crops
    assert seeds.shape == (n + 4, salem.n_var)
    np.testing.assert_allclose(seeds[:, n:], np.tile(salem.xl[n:], (len(seeds), 1)))  # multipliers at lower bound
    assert np.all(seeds[:, :n] >= salem.xl[:n])
    for i in range(n):                              # one dominant-crop plan per candidate crop
        assert np.argmax(seeds[i, :n]) == i
    shares = seeds[:, :n] / seeds[:, :n].sum(axis=1, keepdims=True)
    np.testing.assert_allclose(shares.sum(axis=1), 1.0)


def test_lower_bound_multipliers_are_never_worse(salem):
    """The fact smart initialisation relies on: for any allocation, the
    lower-bound multipliers are at least as good on every objective."""
    X = np.random.default_rng(1).uniform(salem.xl, salem.xu, (200, salem.n_var))
    X_lb = X.copy()
    X_lb[:, salem.n_crops:] = salem.xl[salem.n_crops:]
    F = salem.evaluate(X, return_as_dictionary=True)["F"]
    F_lb = salem.evaluate(X_lb, return_as_dictionary=True)["F"]
    assert np.all(F_lb <= F + 1e-9 * np.abs(F))
    np.testing.assert_array_equal(F_lb[:, 0], F[:, 0])  # yield does not depend on the multipliers


def test_smart_sampling_mixes_seeds_and_random_individuals(salem):
    rng = np.random.default_rng(0)
    X = SmartSampling(0.25)._do(salem, 40, random_state=rng)
    n_seed = 10
    assert X.shape == (40, salem.n_var)
    np.testing.assert_allclose(X[:n_seed, salem.n_crops:], salem.xl[salem.n_crops])
    assert np.all(X >= salem.xl - 1e-12) and np.all(X <= salem.xu + 1e-12)
    assert X[n_seed:, salem.n_crops:].std() > 0.1  # the rest is uniform random


def test_tolerant_duplicate_removal_keeps_individuals_apart(salem):
    tol = 1e-2
    result = run_nsga2(salem, seed=2, engine=_with("duplicate_removal", duplicate_tolerance=tol), pop_size=30, n_gen=30)
    Z = (result.pop.get("X") - salem.xl) / (salem.xu - salem.xl)
    D = np.linalg.norm(Z[:, None] - Z[None], axis=2)
    np.fill_diagonal(D, np.inf)
    assert D.min() > tol


def test_adaptive_mutation_probability_rule():
    params = {"min_prob": 0.06, "max_prob": 0.30, "diversity_floor": 0.5, "converged_scale": 0.5}  # explicit, not the config values
    assert adaptive_mutation_prob(0.12, params, 1.0, False) == pytest.approx(0.12)   # healthy diversity
    assert adaptive_mutation_prob(0.12, params, 0.25, False) == pytest.approx(0.24)  # diversity halved below floor
    assert adaptive_mutation_prob(0.12, params, 0.01, False) == pytest.approx(0.30)  # capped
    assert adaptive_mutation_prob(0.12, params, 1.0, True) == pytest.approx(0.06)    # converged -> fine tuning


def test_adaptive_crossover_follows_its_schedule(salem):
    settings = _with("adaptive_crossover")
    result = run_nsga2(salem, seed=1, engine=settings, pop_size=20, n_gen=11)
    probs = [g["crossover_prob"] for g in result.algorithm.callback.generations if "crossover_prob" in g]
    p = settings.adaptive_crossover_params
    assert probs[0] == pytest.approx(p["start_prob"])
    assert probs[-1] == pytest.approx(p["end_prob"])
    assert all(a >= b for a, b in zip(probs, probs[1:]))


def test_early_stopping_stops_on_stagnation_but_not_before_the_minimum(salem):
    params = {"patience": 5, "tolerance": 1e9, "min_generations": 20}  # huge tolerance: always "stagnant"
    result = run_nsga2(salem, seed=1, engine=_with("early_stopping", early_stopping_params=params), n_gen=200, pop_size=20)
    assert result.engine_report["stopped_early_at"] == 20
    assert result.engine_report["profile"]["generations"] == 20


def test_early_stopping_runs_the_full_budget_while_improving(salem):
    params = {"patience": 5, "tolerance": -1.0, "min_generations": 5}  # never stagnant
    result = run_nsga2(salem, seed=1, engine=_with("early_stopping", early_stopping_params=params), **FAST)
    assert result.engine_report["stopped_early_at"] is None
    assert result.engine_report["profile"]["generations"] == FAST["n_gen"]


# ---------------------------------------------------------------------------
# Pipeline integration
# ---------------------------------------------------------------------------

def test_pipeline_records_the_engine_report_in_meta(tmp_path):
    from app.schemas import FarmPlanRequest
    from app.services.plan_service import generate_farm_plans
    request = FarmPlanRequest(location="Salem", season="Kharif", total_land_ha=5.0, save_results=True, **FAST)
    response = generate_farm_plans(request, results_dir=tmp_path)
    optimizer = response["meta"]["optimizer"]
    assert optimizer["engine"]["mode"] == "original"
    assert optimizer["profile"]["generations"] == FAST["n_gen"]
    import json
    saved = json.loads((tmp_path / f"{response['run_id']}.json").read_text())
    assert saved["meta"]["optimizer"]["profile"]["evaluations"] == FAST["pop_size"] * FAST["n_gen"]


def test_api_response_meta_is_unchanged():
    """The engine report is kept in saved runs only; the API's RunMeta does not expose it."""
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    body = {"location": "Salem", "season": "Kharif", "total_land_ha": 5.0, "save_results": False, **FAST}
    res = client.post("/api/farm-plans", json=body)
    assert res.status_code == 200
    assert "optimizer" not in res.json()["meta"]
