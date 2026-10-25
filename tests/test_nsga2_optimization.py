"""
Tests for the second round of NSGA-II engine work: run-time improvements
that must not change any result, the new switchable features, the quality
metrics and their exposure through the API.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pymoo.indicators.hv import HV

from app.main import app
from app.optimization import metrics, monitoring, operators
from app.optimization.nsga2_runner import extract_pareto_plans, run_nsga2
from app.services import results_store

from tests.test_nsga2_engine import _digest, _problem

# Digests of the enhanced engine as merged in PR #12 (recorded on main):
# any later speed-up must reproduce them exactly.
ENHANCED_GOLDEN = [
    (dict(location="Salem", season="Kharif"), "1e64a443331f689f"),
    (dict(location="Erode", season="Rabi", budget=120000.0), "c5747c91779d74a5"),
    (dict(location="Coimbatore", season="Summer"), "51ead5e790b5a25b"),
]


@pytest.mark.parametrize("args,digest", ENHANCED_GOLDEN)
def test_enhanced_engine_reproduces_its_recorded_results(args, digest):
    result = run_nsga2(_problem(**args), pop_size=40, n_gen=60, seed=3, mode="enhanced")
    assert _digest(result) == digest


# ---------------------------------------------------------------------------
# Speed-ups that must be exact
# ---------------------------------------------------------------------------

def _hypervolume_from_getters(algorithm):
    """front_hypervolume as it was computed before: algorithm.opt filtered by
    FEAS, read through pymoo's per-individual getters."""
    lo, span = algorithm.data["_hv_bounds"]
    opt = algorithm.opt
    feasible = opt[np.ravel(opt.get("FEAS")).astype(bool)]
    if not len(feasible):
        return 0.0
    F = (feasible.get("F") - lo) / span
    return float(HV(ref_point=np.full(F.shape[1], 1.1))(F))


@pytest.mark.parametrize("budget", [None, 150000.0, 20000.0])  # 20000: no feasible plan at all
def test_front_hypervolume_matches_the_getter_computation(budget):
    result = run_nsga2(_problem("Erode", "Kharif", budget=budget), pop_size=30, n_gen=12, seed=5, mode="enhanced")
    algorithm = result.algorithm
    algorithm.data.pop("_hv_cache", None)
    assert monitoring.front_hypervolume(algorithm) == _hypervolume_from_getters(algorithm)


def test_duplicate_eliminator_caches_population_reads():
    result = run_nsga2(_problem("Coimbatore", "Summer"), pop_size=24, n_gen=6, seed=1)
    pop = result.pop
    eliminator = operators.CountingDuplicateElimination()
    first = eliminator._decision_vectors(pop)
    assert eliminator._decision_vectors(pop) is first  # served from the cache
    np.testing.assert_array_equal(first, pop.get("X"))
    other = pop[:5]
    np.testing.assert_array_equal(eliminator._decision_vectors(other), pop.get("X")[:5])


def test_duplicate_eliminator_still_rejects_copies():
    result = run_nsga2(_problem("Salem", "Kharif"), pop_size=24, n_gen=4, seed=2)
    pop = result.pop
    eliminator = operators.CountingDuplicateElimination()
    doubled = pop.__class__.merge(pop[:6], pop[:6])
    kept = eliminator.do(doubled)
    assert len(kept) == 6
    assert (eliminator.checked, eliminator.rejected) == (12, 6)


# ---------------------------------------------------------------------------
# Quality metrics (app/optimization/metrics.py)
# ---------------------------------------------------------------------------


def test_nondominated_keeps_only_the_front():
    F = np.array([[0.0, 1.0], [1.0, 0.0], [1.0, 1.0], [0.5, 0.5]])
    assert sorted(map(tuple, metrics.nondominated(F))) == [(0.0, 1.0), (0.5, 0.5), (1.0, 0.0)]


def test_hypervolume_of_a_single_point():
    assert metrics.hypervolume(np.zeros((1, 4))) == pytest.approx(1.1 ** 4)
    assert metrics.hypervolume(np.empty((0, 4))) == 0.0


def test_gd_and_igd_on_a_hand_calculated_case():
    front = np.array([[0.0, 1.0], [1.0, 0.0]])
    reference = np.array([[0.0, 0.0]])
    assert metrics.generational_distance(front, reference) == pytest.approx(1.0)
    assert metrics.inverted_generational_distance(front, reference) == pytest.approx(1.0)
    # A front equal to the reference is at distance 0 both ways.
    assert metrics.generational_distance(front, front) == 0.0
    assert metrics.inverted_generational_distance(front, front) == 0.0


def test_spacing_and_spread_of_an_evenly_spaced_front():
    front = np.array([[0.0, 1.0], [0.5, 0.5], [1.0, 0.0]])
    assert metrics.spacing(front) == pytest.approx(0.0)
    assert metrics.generalized_spread(front, metrics.extremes(front)) == pytest.approx(0.0)
    uneven = np.array([[0.0, 1.0], [0.1, 0.9], [1.0, 0.0]])
    assert metrics.spacing(uneven) > 0.1
    assert metrics.generalized_spread(uneven, metrics.extremes(front)) > 0.1


def test_metrics_need_enough_points():
    one = np.array([[0.2, 0.3]])
    assert math.isnan(metrics.spacing(one))
    assert math.isnan(metrics.generalized_spread(one, metrics.extremes(one)))
    assert math.isnan(metrics.generational_distance(np.empty((0, 2)), one))


def test_front_quality_of_the_reference_itself():
    ref = np.array([[0.0, 4.0, 1.0, 2.0], [1.0, 3.0, 2.0, 1.0], [2.0, 1.0, 0.0, 3.0]])
    q = metrics.front_quality(ref, ref)
    assert q["hypervolume_ratio"] == pytest.approx(1.0)
    assert q["gd"] == 0.0 and q["igd"] == 0.0 and q["igd_plus"] == 0.0


def test_lower_bound_reference_dominates_or_equals_the_front():
    problem = _problem("Salem", "Kharif")
    result = run_nsga2(problem, pop_size=30, n_gen=15, seed=4)
    X, F = metrics.feasible_front(result)
    ref = metrics.lower_bound_reference(problem, X, F)
    q = metrics.front_quality(F, ref)
    assert 0.0 < q["hypervolume_ratio"] <= 1.0 + 1e-9
    assert q["gd"] >= 0.0 and q["igd"] >= 0.0


REQUIRED_KEYS = {"reference_front", "pareto_size", "feasible_pareto_size", "constraint_satisfaction_rate",
                 "dominated_by_lower_bound_copy", "runtime_seconds", "generations", "evaluations",
                 "mean_objectives", "hypervolume", "hypervolume_ratio", "gd", "igd", "igd_plus", "spread", "spacing"}


def test_run_quality_metrics_report():
    problem = _problem("Erode", "Rabi", budget=200000.0)
    result = run_nsga2(problem, pop_size=30, n_gen=15, seed=4)
    q = metrics.run_quality_metrics(result, problem)
    assert set(q) == REQUIRED_KEYS
    assert q["feasible_pareto_size"] <= q["pareto_size"] <= 30
    assert 0.0 <= q["constraint_satisfaction_rate"] <= 1.0
    assert q["evaluations"] == result.engine_report["profile"]["evaluations"]
    plans = [p for p in extract_pareto_plans(result, problem) if p.feasible]
    assert q["mean_objectives"]["yield_tonnes"] == pytest.approx(np.mean([p.yield_tonnes for p in plans]), rel=1e-3)


def test_metrics_of_an_infeasible_run_are_null_not_nan():
    problem = _problem("Erode", "Kharif", budget=20000.0)
    result = run_nsga2(problem, pop_size=24, n_gen=8, seed=1)
    q = metrics.run_quality_metrics(result, problem)
    assert q["feasible_pareto_size"] == 0 and q["constraint_satisfaction_rate"] == 0.0
    assert q["hypervolume"] is None and q["mean_objectives"] is None


def test_computing_metrics_does_not_change_the_run():
    problem = _problem("Salem", "Kharif")
    a = run_nsga2(problem, pop_size=24, n_gen=10, seed=9)
    metrics.run_quality_metrics(a, problem)
    b = run_nsga2(problem, pop_size=24, n_gen=10, seed=9)
    assert _digest(a) == _digest(b)


def test_api_returns_and_saves_quality_metrics(tmp_path, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "RESULTS_DIR", tmp_path)
    client = TestClient(app)
    body = {"location": "Salem", "season": "Kharif", "year": 2023, "total_land_ha": 5,
            "pop_size": 24, "n_gen": 10, "save_results": False}
    res = client.post("/api/farm-plans", json=body)
    assert res.status_code == 200
    q = res.json()["meta"]["quality_metrics"]
    assert set(q) == REQUIRED_KEYS and q["hypervolume"] > 0

    from app.services import plan_service
    saved = plan_service.generate_farm_plans(plan_service.FarmPlanRequest(**{**body, "save_results": True}),
                                             results_dir=tmp_path)
    record = results_store.load_run(saved["run_id"], out_dir=tmp_path)
    assert set(record["meta"]["quality_metrics"]) == REQUIRED_KEYS


def test_saved_runs_without_metrics_still_validate():
    from app.schemas import RunMeta
    meta = RunMeta(pop_size=80, n_gen=200, crossover_prob=0.85, mutation_prob=0.12, preference="balanced",
                   n_pareto_solutions_found=80, n_plans_returned=50, optimize_seconds=0.3)
    assert meta.quality_metrics is None


# ---------------------------------------------------------------------------
# Switchable features
# ---------------------------------------------------------------------------

import dataclasses  # noqa: E402

from app.optimization.engine_settings import engine_settings  # noqa: E402


def _with(base="original", **features):
    return dataclasses.replace(engine_settings(base), **features)


def _strata_filled(X, xl, xu):
    """True when every gene of the n rows of X has one value in each of n equal strata."""
    n = len(X)
    idx = np.floor((X - xl) / (xu - xl) * n).clip(0, n - 1).astype(int)
    return all(len(set(idx[:, j])) == n for j in range(X.shape[1]))


def test_lhs_sampling_fills_every_stratum():
    problem = _problem("Salem", "Kharif")
    rng = np.random.default_rng(0)
    X = operators.LHS()._do(problem, 40, random_state=rng)
    assert _strata_filled(X, problem.xl, problem.xu)


def test_smart_sampling_with_lhs_keeps_seeds_and_stratifies_the_rest():
    problem = _problem("Salem", "Kharif")
    X = operators.SmartSampling(0.2, lhs=True)._do(problem, 40, random_state=np.random.default_rng(0))
    n_seed = 8  # 20 % of 40
    np.testing.assert_array_equal(X[:n_seed], operators.seed_chromosomes(problem)[:n_seed])
    assert _strata_filled(X[n_seed:], problem.xl, problem.xu)


@pytest.mark.parametrize("base", ["original", "enhanced"])
def test_lhs_initialization_is_deterministic_and_in_bounds(base):
    problem = _problem("Erode", "Kharif", budget=180000.0)
    engine = _with(base, lhs_initialization=True)
    a = run_nsga2(problem, pop_size=30, n_gen=10, seed=6, engine=engine)
    b = run_nsga2(problem, pop_size=30, n_gen=10, seed=6, engine=engine)
    assert _digest(a) == _digest(b)
    X = a.pop.get("X")
    assert np.all(X >= problem.xl - 1e-12) and np.all(X <= problem.xu + 1e-12)
    assert _digest(a) != _digest(run_nsga2(problem, pop_size=30, n_gen=10, seed=6, mode=base))
