"""
Tight-budget study of constraint-aware initialisation.

The main benchmark's budgets (5 ha x the median single-crop cost) leave
feasible plans in the first generation of every run, so a feasibility-
oriented initialisation has nothing to do there. This study uses budgets
5 % and 20 % above the cheapest possible plan (one crop, multipliers at
their lower bound) for the Kharif season of every district, 10 seeds each,
and compares each engine with and without constraint_aware_initialization:

  original            published engine
  enhanced (PR #12)   adaptive mutation + smart initialisation

Indicators use one reference front per problem (all runs plus their
lower-bound-multiplier copies; app.optimization.metrics). Reported: paired
hypervolume and IGD+ (Wilcoxon signed-rank), and the first generation with
a feasible plan.

    python scripts/benchmark_tight_budget.py [--seeds 10] [--json out.json]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import statistics
import sys
from pathlib import Path

import numpy as np
from scipy.stats import wilcoxon

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402
from app.data import preprocessing as pp  # noqa: E402
from app.fuzzy import engine as fz  # noqa: E402
from app.optimization import metrics  # noqa: E402
from app.optimization.engine_settings import engine_settings  # noqa: E402
from app.optimization.nsga2_runner import run_nsga2  # noqa: E402
from app.optimization.problem import FarmPlanProblem  # noqa: E402

FACTORS = (1.05, 1.2)


def engines():
    original = engine_settings("original")
    pr12 = dataclasses.replace(engine_settings("enhanced"), duplicate_avoidance=False,
                               constraint_aware_initialization=False)
    return {
        ("original", False): original,
        ("original", True): dataclasses.replace(original, constraint_aware_initialization=True),
        ("enhanced (PR #12)", False): pr12,
        ("enhanced (PR #12)", True): dataclasses.replace(pr12, constraint_aware_initialization=True),
    }


def cheapest_plan_cost(problem: FarmPlanProblem) -> float:
    n = problem.n_crops
    lower = np.full((n, n), config.FERTILIZER_MULT_MIN)
    X = np.hstack([np.eye(n), np.full((n, n), config.IRRIGATION_MULT_MIN), lower])
    return float(problem.evaluate(X, return_as_dictionary=True)["F"][:, 1].min())


def first_feasible_generation(result):
    for row in result.algorithm.callback.generations:
        if row.get("feasible_share", 0) > 0:
            return row["generation"]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    rows = []
    for loc in config.LOCATIONS:
        prof = pp.get_region_season_profile(loc, "Kharif")
        a = fz.evaluate_uncertainty(prof.rainfall.avg_deviation_percent, prof.water.avg_storage_percent,
                                    prof.soil.fertility_index)
        cheapest = cheapest_plan_cost(FarmPlanProblem(prof, a, 5.0))
        for factor in FACTORS:
            problem = FarmPlanProblem(prof, a, 5.0, budget_rs=cheapest * factor)
            results = {key: [run_nsga2(problem, seed=s, engine=eng) for s in range(args.seeds)]
                       for key, eng in engines().items()}
            fronts = [metrics.feasible_front(r) for rs in results.values() for r in rs]
            reference = metrics.nondominated(np.vstack(
                [F for X, F in fronts if len(F)] + [metrics.lower_bound_copies(problem, X) for X, F in fronts if len(X)]))
            for (engine, aware), rs in results.items():
                for seed, r in enumerate(rs):
                    X, F = metrics.feasible_front(r)
                    q = metrics.front_quality(F, reference) if len(F) else {"hypervolume": 0.0, "igd_plus": float("nan")}
                    rows.append({"problem": f"{loc} Kharif, budget {factor:.2f} x cheapest", "engine": engine,
                                 "constraint_aware": aware, "seed": seed, "hypervolume": q["hypervolume"],
                                 "igd_plus": q["igd_plus"], "first_feasible_generation": first_feasible_generation(r),
                                 "constraint_satisfaction": float((np.ravel(r.pop.get("CV")) <= 0).mean())})
        print(f"  {loc}: done", flush=True)

    print("\nengine               n   HV better/worse   p        median dHV   IGD+ better/worse  p        first feasible gen (median, max)")
    for engine in ("original", "enhanced (PR #12)"):
        key = lambda r: (r["problem"], r["seed"])  # noqa: E731
        on = sorted([r for r in rows if r["engine"] == engine and r["constraint_aware"]], key=key)
        off = sorted([r for r in rows if r["engine"] == engine and not r["constraint_aware"]], key=key)
        hv_on, hv_off = np.array([r["hypervolume"] for r in on]), np.array([r["hypervolume"] for r in off])
        ig_on, ig_off = np.array([r["igd_plus"] for r in on]), np.array([r["igd_plus"] for r in off])
        d_hv, d_ig = hv_on - hv_off, ig_on - ig_off
        p_hv = wilcoxon(hv_on, hv_off).pvalue if np.any(d_hv) else float("nan")
        p_ig = wilcoxon(ig_on, ig_off).pvalue if np.any(d_ig) else float("nan")
        ff_off = [r["first_feasible_generation"] for r in off if r["first_feasible_generation"]]
        ff_on = [r["first_feasible_generation"] for r in on if r["first_feasible_generation"]]
        print(f"{engine:<20}{len(d_hv):>3}   {int((d_hv > 1e-12).sum()):>3}/{int((d_hv < -1e-12).sum()):<3}         {p_hv:<8.3g} {np.median(d_hv):+.5f}     "
              f"{int((d_ig < -1e-12).sum()):>3}/{int((d_ig > 1e-12).sum()):<3}            {p_ig:<8.3g} "
              f"off {statistics.median(ff_off)}, {max(ff_off)} -> on {statistics.median(ff_on)}, {max(ff_on)}")
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=1, default=float))


if __name__ == "__main__":
    main()
