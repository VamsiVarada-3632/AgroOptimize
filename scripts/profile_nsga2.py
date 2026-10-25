"""
Phase-by-phase profile of one NSGA-II optimisation run.

Wraps the pymoo and AgroOptimize components with timers (the wrappers only
measure; they do not touch any random number generator, so the profiled run
produces exactly the same Pareto front as an unprofiled one) and reports:

    preprocessing, fuzzy inference, sampling, objective evaluation,
    tournament selection, crossover, mutation, repair, duplicate elimination,
    non-dominated sorting, crowding distance, run monitoring,
    convergence-history extraction, plan decoding, quality metrics and TOPSIS
    ranking -- plus wall/CPU time and CPU utilisation, peak traced memory,
    evaluations, evaluations of over-budget plans (constraint violations),
    dominated solutions in the final population, Pareto-front size, offspring
    rejected as duplicates, and per-generation diversity / hypervolume.

Usage:
    python scripts/profile_nsga2.py [--location Salem --season Kharif]
        [--repeats 5] [--mode original|enhanced] [--switch duplicate_avoidance ...]
        [--budget 200000] [--json out.json]

`--mode` is only used when the engine supports it; on older checkouts it is
ignored so the same script profiles the code before and after a change.
"""

from __future__ import annotations

import argparse
import inspect
import json
import statistics
import sys
import time
import tracemalloc
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pymoo.core import duplicate as pm_duplicate  # noqa: E402
from pymoo.core import evaluator as pm_evaluator  # noqa: E402
from pymoo.operators.selection import tournament as pm_tournament  # noqa: E402
from pymoo.operators.survival.rank_and_crowding import metrics as pm_metrics  # noqa: E402
from pymoo.util.nds import non_dominated_sorting as pm_nds  # noqa: E402

from app import config  # noqa: E402
from app.data import preprocessing as pp  # noqa: E402
from app.decision import ranking  # noqa: E402
from app.fuzzy import engine as fz  # noqa: E402
from app.optimization import metrics, monitoring, nsga2_runner, operators  # noqa: E402
from app.optimization.problem import FarmPlanProblem  # noqa: E402

TIMES: dict = defaultdict(float)
CALLS: dict = defaultdict(int)
COUNTS: dict = defaultdict(int)


def _timed(name, fn):
    def wrapper(*args, **kwargs):
        t0 = time.perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            TIMES[name] += time.perf_counter() - t0
            CALLS[name] += 1
    wrapper.__wrapped__ = fn
    return wrapper


def _count_duplicates(fn):
    """Counts how many offspring the duplicate eliminator rejects."""
    def wrapper(self, pop, *args, **kwargs):
        out = fn(self, pop, *args, **kwargs)
        kept = out[0] if isinstance(out, tuple) else out
        COUNTS["offspring_checked"] += len(pop)
        COUNTS["offspring_rejected_as_duplicate"] += len(pop) - len(kept)
        return out
    return wrapper


def _count_infeasible(fn):
    """Counts evaluated plans that violate the budget constraint."""
    def wrapper(self, problem, pop, *args, **kwargs):
        out = fn(self, problem, pop, *args, **kwargs)
        cv = np.ravel(pop.get("CV")) if len(pop) else np.empty(0)
        COUNTS["evaluated"] += len(cv)
        COUNTS["evaluated_over_budget"] += int((cv > 0).sum())
        return out
    return wrapper


def install_timers() -> None:
    # The project's operators (the adaptive variants subclass these, so
    # wrapping the base classes' _do covers them too).
    for cls_name, label in (("AllocationRepair", "repair"), ("SinglePointCrossover", "crossover"),
                            ("GaussianMutation", "mutation")):
        cls = getattr(operators, cls_name)
        cls._do = _timed(label, cls.__dict__["_do"])
    # Counted outside the timer, so the count itself is not timed as evaluation.
    pm_evaluator.Evaluator.eval = _count_infeasible(_timed("evaluation", pm_evaluator.Evaluator.eval))
    monitoring.EngineMonitor.notify = _timed("monitoring", monitoring.EngineMonitor.notify)
    pm_tournament.TournamentSelection._do = _timed("selection", pm_tournament.TournamentSelection._do)
    dup_do = pm_duplicate.DuplicateElimination.do
    pm_duplicate.DuplicateElimination.do = _timed("duplicate_elimination", _count_duplicates(dup_do))
    pm_nds.NonDominatedSorting.do = _timed("non_dominated_sorting", pm_nds.NonDominatedSorting.do)
    pm_metrics.FunctionalDiversity._do = _timed("crowding_distance", pm_metrics.FunctionalDiversity._do)


def _supports(fn, name: str) -> bool:
    return name in inspect.signature(fn).parameters


def decision_entropy(X: np.ndarray, xl: np.ndarray, xu: np.ndarray, bins: int = 10) -> float:
    """Mean per-gene Shannon entropy of the population, normalised to [0, 1]."""
    span = np.where(xu - xl > 0, xu - xl, 1.0)
    Z = np.clip((X - xl) / span, 0.0, 1.0 - 1e-12)
    idx = (Z * bins).astype(int)
    ent = []
    for j in range(X.shape[1]):
        p = np.bincount(idx[:, j], minlength=bins) / X.shape[0]
        p = p[p > 0]
        ent.append(float(-(p * np.log(p)).sum() / np.log(bins)))
    return float(np.mean(ent))


def profile_once(location: str, season: str, land: float, budget, mode: str, track_history: bool, switches=()):
    TIMES.clear(); CALLS.clear(); COUNTS.clear()
    wall0, cpu0 = time.perf_counter(), time.process_time()

    t = time.perf_counter()
    profile = pp.get_region_season_profile(location=location, season=season)
    TIMES["preprocessing"] += time.perf_counter() - t

    t = time.perf_counter()
    assessment = fz.evaluate_uncertainty(
        profile.rainfall.avg_deviation_percent, profile.water.avg_storage_percent, profile.soil.fertility_index)
    TIMES["fuzzy_inference"] += time.perf_counter() - t

    problem = FarmPlanProblem(profile, assessment, total_land_ha=land, budget_rs=budget)
    kwargs = {"track_history": track_history}
    if switches:
        import dataclasses
        from app.optimization.engine_settings import engine_settings
        kwargs["engine"] = dataclasses.replace(engine_settings(mode), **{s: True for s in switches})
    elif _supports(nsga2_runner.run_nsga2, "mode"):
        kwargs["mode"] = mode

    t = time.perf_counter()
    result = nsga2_runner.run_nsga2(problem, **kwargs)
    TIMES["optimisation_total"] += time.perf_counter() - t

    t = time.perf_counter()
    history = nsga2_runner.extract_convergence_history(result) if track_history else []
    TIMES["history_extraction"] += time.perf_counter() - t

    t = time.perf_counter()
    plans = [p for p in nsga2_runner.extract_pareto_plans(result, problem) if p.feasible]
    TIMES["decoding"] += time.perf_counter() - t

    t = time.perf_counter()
    quality = metrics.run_quality_metrics(result, problem)
    TIMES["quality_metrics"] += time.perf_counter() - t

    t = time.perf_counter()
    conf = dict(zip(problem.crop_vec.names, problem.crop_vec.crop_yield_confidence.tolist()))
    ranked = ranking.rank_plans(plans, crop_confidence_map=conf, preference="balanced")
    TIMES["topsis_ranking"] += time.perf_counter() - t

    wall, cpu = time.perf_counter() - wall0, time.process_time() - cpu0
    algo = result.algorithm
    X = result.pop.get("X")
    F = result.pop.get("F")
    rounded = np.round(F, 6)
    return {
        "times_s": dict(TIMES),
        "calls": dict(CALLS),
        "counts": dict(COUNTS),
        "wall_s": wall,
        "cpu_s": cpu,
        "cpu_utilisation": cpu / wall if wall else None,
        # pymoo advances n_gen once more after the last generation.
        "generations": (result.engine_report["profile"]["generations"]
                        if "profile" in getattr(result, "engine_report", {}) else int(algo.n_gen) - 1),
        "evaluations": int(algo.evaluator.n_eval),
        "pareto_size": int(len(result.X)) if result.X is not None else 0,
        "feasible_plans": len(plans),
        "ranked_plans": len(ranked),
        "final_population_entropy": decision_entropy(X, problem.xl, problem.xu),
        "final_duplicate_objective_vectors": int(len(F) - len(np.unique(rounded, axis=0))),
        "final_hypervolume": history[-1]["hypervolume"] if history else None,
        "final_dominated_solutions": int((np.ravel(result.pop.get("rank")) > 0).sum()),
        "front_beaten_by_lower_bound_copy": quality["dominated_by_lower_bound_copy"],
        "quality_metrics": quality,
        "history": history,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--location", default="Salem")
    ap.add_argument("--season", default="Kharif")
    ap.add_argument("--land", type=float, default=5.0)
    ap.add_argument("--budget", type=float, default=None)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--mode", default="original")
    ap.add_argument("--no-history", action="store_true")
    ap.add_argument("--switch", action="append", default=[], help="engine switch to turn on (repeatable)")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    install_timers()
    # Warm-up (imports, CSV caches, scikit-fuzzy caches) is excluded.
    profile_once(args.location, args.season, args.land, args.budget, args.mode, False, args.switch)

    runs = [profile_once(args.location, args.season, args.land, args.budget, args.mode, not args.no_history, args.switch)
            for _ in range(args.repeats)]

    tracemalloc.start()
    profile_once(args.location, args.season, args.land, args.budget, args.mode, not args.no_history, args.switch)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    keys = sorted({k for r in runs for k in r["times_s"]})
    summary = {k: statistics.median(r["times_s"].get(k, 0.0) for r in runs) for k in keys}
    out = {
        "config": {**vars(args), "pop_size": config.NSGA2_POP_SIZE, "n_gen": config.NSGA2_N_GEN},
        "median_times_s": summary,
        "median_wall_s": statistics.median(r["wall_s"] for r in runs),
        "median_cpu_s": statistics.median(r["cpu_s"] for r in runs),
        "peak_traced_memory_mb": peak / 1e6,
        "last_run": {k: v for k, v in runs[-1].items() if k != "history"},
        "history_first_last": (runs[-1]["history"][:1] + runs[-1]["history"][-1:]) if runs[-1]["history"] else [],
    }

    width = max(len(k) for k in keys)
    print(f"{args.location} {args.season}, pop {config.NSGA2_POP_SIZE}, gen {config.NSGA2_N_GEN}, "
          f"history={'off' if args.no_history else 'on'}, median of {args.repeats}")
    for k in keys:
        print(f"  {k:<{width}}  {summary[k] * 1000:9.2f} ms   ({runs[-1]['calls'].get(k, 1)} calls)")
    print(f"  wall {out['median_wall_s']:.3f} s, cpu {out['median_cpu_s']:.3f} s, "
          f"peak traced memory {out['peak_traced_memory_mb']:.1f} MB")
    lr = out["last_run"]
    print(f"  generations {lr['generations']}, evaluations {lr['evaluations']}, Pareto size {lr['pareto_size']}, "
          f"duplicates rejected {lr['counts'].get('offspring_rejected_as_duplicate', 0)} of "
          f"{lr['counts'].get('offspring_checked', 0)} checked, final entropy {lr['final_population_entropy']:.3f}")
    print(f"  cpu utilisation {lr['cpu_utilisation']:.2f}, over-budget evaluations "
          f"{lr['counts'].get('evaluated_over_budget', 0)} of {lr['counts'].get('evaluated', 0)}, "
          f"dominated solutions in final population {lr['final_dominated_solutions']}, "
          f"front beaten by its lower-bound copy {lr['front_beaten_by_lower_bound_copy']}")
    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=2, default=float))


if __name__ == "__main__":
    main()
