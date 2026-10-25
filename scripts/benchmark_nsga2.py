"""
Quality benchmark and ablation study of the NSGA-II engine modes.

Runs every variant on the same problems with the same seeds and compares
each one with the original (published) engine:

  variants   original, each enhanced feature switched on alone on top of the
             original engine, and the enhanced mode (or any list given)
  problems   the 12 district x season profiles (5 ha, no budget) and one
             budget-constrained profile per district (Kharif, budget = 5 ha x
             the median single-crop cost per ha)
  seeds      --seeds (default 10: 0..9)

Metrics per run, computed on the final feasible first front with the
objectives normalised per problem by the ideal and nadir of the reference
front (the non-dominated union of every front found by every variant and
seed, plus each solution's copy with the multipliers at their lower bound,
which is never worse -- see operators.SmartSampling):

  hypervolume (ref. point 1.1, higher is better), GD, IGD and IGD+ (lower is
  better; app.optimization.metrics),
  generalised spread (Zhou et al. 2006, lower = more even), spacing (Schott
  1995), front size, duplicate objective vectors in the final population,
  population entropy, mean crowding distance, evaluations, generations,
  runtime, hypervolume per generation (convergence speed), average
  objectives over the front, the objectives of the TOPSIS top plan
  (balanced preference), and the share of the front that is dominated by its
  own lower-bound-multiplier copy (a direct measure of unfinished
  convergence in this problem).

Each variant is compared with the original on the same (problem, seed)
pairs with the Wilcoxon signed-rank test.

Usage:
    python scripts/benchmark_nsga2.py [--seeds 10] [--seed-offset 0]
        [--variants original,smart_initialization,original@pop_size=160,...]
        [--json results.json] [--quick]

Variant syntax: see parse_variant.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np
from scipy.stats import wilcoxon

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402
from app.data import loader, preprocessing as pp  # noqa: E402
from app.decision import ranking  # noqa: E402
from app.fuzzy import engine as fz  # noqa: E402
from app.optimization import metrics  # noqa: E402
from app.optimization.engine_settings import FEATURES_CHANGING_OUTPUTS, engine_settings  # noqa: E402
from app.optimization.monitoring import population_entropy  # noqa: E402
from app.optimization.nsga2_runner import extract_pareto_plans, run_nsga2  # noqa: E402
from app.optimization.problem import FarmPlanProblem  # noqa: E402

HISTORY_STEP = 5  # hypervolume is computed every HISTORY_STEP generations


def problems():
    out = []
    for loc in loader.available_locations():
        for season in loader.available_seasons():
            prof = pp.get_region_season_profile(loc, season)
            a = fz.evaluate_uncertainty(prof.rainfall.avg_deviation_percent,
                                        prof.water.avg_storage_percent, prof.soil.fertility_index)
            out.append((f"{loc} {season}", FarmPlanProblem(prof, a, 5.0)))
    for loc in loader.available_locations():
        prof = pp.get_region_season_profile(loc, "Kharif")
        a = fz.evaluate_uncertainty(prof.rainfall.avg_deviation_percent,
                                    prof.water.avg_storage_percent, prof.soil.fertility_index)
        unconstrained = FarmPlanProblem(prof, a, 5.0)
        budget = 5.0 * statistics.median(m["cost_rs_ha"] for m in unconstrained.single_crop_metrics())
        out.append((f"{loc} Kharif budget {budget:,.0f}", FarmPlanProblem(prof, a, 5.0, budget_rs=budget)))
    return out


RUN_KWARGS = ("pop_size", "n_gen", "crossover_prob", "mutation_prob", "mutation_sigma")


def parse_variant(spec: str):
    """`base[+feature...][@key=value[+key=value...]]` -> (EngineSettings, run kwargs).

    base is "original" or "enhanced" (or a feature name, meaning original +
    that feature); keys are run_nsga2 arguments (pop_size, n_gen,
    crossover_prob, mutation_prob, mutation_sigma), EngineSettings scalars
    (smart_init_fraction, duplicate_tolerance) or dict parameters written
    as e.g. early_stopping_params.patience=50.
    """
    head, _, params = spec.partition("@")
    parts = head.split("+")
    base = parts[0] if parts[0] in ("original", "enhanced") else "original"
    features = parts[1:] if parts[0] in ("original", "enhanced") else parts
    settings = engine_settings(base)
    for f in features:
        if f not in FEATURES_CHANGING_OUTPUTS:
            raise SystemExit(f"unknown feature {f!r} in {spec!r}")
        settings = dataclasses.replace(settings, **{f: True})
    run_kwargs = {}
    for item in filter(None, params.split("+")):
        key, _, value = item.partition("=")
        value = float(value)
        if key in RUN_KWARGS:
            run_kwargs[key] = int(value) if key in ("pop_size", "n_gen") else value
        elif "." in key:
            field_name, sub = key.split(".", 1)
            d = dict(getattr(settings, field_name))
            d[sub] = int(value) if value.is_integer() and sub in ("patience", "min_generations") else value
            settings = dataclasses.replace(settings, **{field_name: d})
        else:
            settings = dataclasses.replace(settings, **{key: value})
    return dataclasses.replace(settings, mode=spec), run_kwargs


def run_one(problem, spec, seed):
    settings, run_kwargs = parse_variant(spec)
    t0 = time.perf_counter()
    result = run_nsga2(problem, seed=seed, engine=settings, track_history=True, **run_kwargs)
    seconds = time.perf_counter() - t0
    X, F = metrics.feasible_front(result)
    monitor = result.algorithm.callback
    plans = [p for p in extract_pareto_plans(result, problem) if p.feasible]
    conf = dict(zip(problem.crop_vec.names, problem.crop_vec.crop_yield_confidence.tolist()))
    ranked = ranking.rank_plans(plans, crop_confidence_map=conf, preference="balanced")
    top = ranked[0] if ranked else None
    pop_X, pop_F = result.pop.get("X"), result.pop.get("F")
    dominated_by_copy = metrics.share_dominated_by_lower_bound_copy(problem, X, F) if len(X) else 0.0
    report = result.engine_report
    return {
        "F": F, "X": X,
        "F_history": [f for i, f in enumerate(monitor.F_history) if i % HISTORY_STEP == HISTORY_STEP - 1],
        "seconds": seconds,
        "generations": report["profile"]["generations"],
        "evaluations": report["profile"]["evaluations"],
        "front_size": int(len(F)),
        "entropy": population_entropy(pop_X, problem.xl, problem.xu),
        # Entropy of the land-allocation genes only: the multiplier genes are
        # expected to converge to their bound, which lowers the full entropy.
        "allocation_entropy": population_entropy(pop_X[:, :problem.n_crops], problem.xl[:problem.n_crops],
                                                 problem.xu[:problem.n_crops]),
        "mean_crowding": report.get("diversity", {}).get("mean_crowding", {}).get("final"),
        "duplicate_ratio": report.get("diversity", {}).get("duplicate_ratio"),
        "population_duplicates": int(len(pop_F) - len(np.unique(np.round(pop_F, 6), axis=0))),
        "mean_objectives": F.mean(axis=0).tolist() if len(F) else None,
        "top_plan": _top_objectives(top),
        "dominated_by_lower_bound_copy": dominated_by_copy,
    }


def _top_objectives(top):
    if top is None:
        return None
    d = ranking.to_dict_list([top])[0]
    return {k: d[k] for k in ("yield_tonnes", "cost_rs", "water_liters", "env_impact_score") if k in d}


def score(runs_by_problem, problems_list):
    """Adds normalised quality indicators (app.optimization.metrics) to every
    run, against one reference front per problem: the non-dominated union of
    every front found by every variant and seed, plus each solution's
    lower-bound-multiplier copy."""
    for name, problem in problems_list:
        runs = runs_by_problem[name]
        fronts = [r["F"] for r in runs if len(r["F"])]
        copies = [metrics.lower_bound_copies(problem, r["X"]) for r in runs if len(r["X"])]
        ref = metrics.nondominated(np.vstack(fronts + copies))
        if problem.budget_rs:
            ref = ref[ref[:, 1] <= problem.budget_rs + 1e-6]
        lo, span = metrics.normalisation(ref)
        for r in runs:
            r.update(metrics.front_quality(r["F"], ref) if len(r["F"]) else
                     {"hypervolume": 0.0, "hypervolume_ratio": 0.0, "gd": float("nan"), "igd": float("nan"),
                      "igd_plus": float("nan"), "spread": float("nan"), "spacing": float("nan")})
            r["hv_history"] = [metrics.hypervolume(metrics.nondominated((f - lo) / span)) for f in r["F_history"]]
        best = max(r["hypervolume"] for r in runs)
        for r in runs:
            r["hv_ratio"] = r["hypervolume"] / best if best > 0 else float("nan")


def generations_to(target, hv_history):
    for i, v in enumerate(hv_history):
        if v >= target:
            return (i + 1) * HISTORY_STEP
    return None


def compare(rows_v, rows_o, key, higher_is_better):
    a = np.array([r[key] for r in rows_v], dtype=float)
    b = np.array([r[key] for r in rows_o], dtype=float)
    ok = np.isfinite(a) & np.isfinite(b)
    a, b = a[ok], b[ok]
    diff = a - b
    better = int(((diff > 1e-12) if higher_is_better else (diff < -1e-12)).sum())
    worse = int(((diff < -1e-12) if higher_is_better else (diff > 1e-12)).sum())
    p = float("nan")
    if np.any(np.abs(diff) > 1e-12):
        p = float(wilcoxon(a, b).pvalue)
    return {"median_variant": float(np.median(a)), "median_original": float(np.median(b)),
            "median_diff": float(np.median(diff)), "better": better, "worse": worse,
            "ties": int(len(diff) - better - worse), "p_value": p}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--seed-offset", type=int, default=0,
                    help="first seed; tuning used seeds 100+, the reported study seeds 0..9")
    ap.add_argument("--variants", default="original," + ",".join(FEATURES_CHANGING_OUTPUTS) + ",enhanced")
    ap.add_argument("--quick", action="store_true", help="3 problems x 3 seeds, for a smoke test")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    variants = [v.strip() for v in args.variants.split(",") if v.strip()]
    variants = [v if "+" in v or "@" in v or v in ("original", "enhanced") else f"original+{v}" for v in variants]
    if "original" not in variants:
        variants.insert(0, "original")
    probs = problems()
    seeds = list(range(args.seed_offset, args.seed_offset + args.seeds))
    if args.quick:
        probs, seeds = probs[:2] + probs[-1:], seeds[:3]

    runs_by_problem = {name: [] for name, _ in probs}
    t_start = time.perf_counter()
    for name, problem in probs:
        for v in variants:
            for seed in seeds:
                r = run_one(problem, v, seed)
                r.update(variant=v, problem=name, seed=seed)
                runs_by_problem[name].append(r)
        print(f"  {name}: done ({time.perf_counter() - t_start:.0f} s)", flush=True)
    score(runs_by_problem, probs)

    runs = [r for rs in runs_by_problem.values() for r in rs]
    key = lambda r: (r["problem"], r["seed"])  # noqa: E731
    by_variant = {v: sorted([r for r in runs if r["variant"] == v], key=key) for v in variants}

    # Convergence speed: generations to reach 99 % of the original engine's
    # median final hypervolume on the same problem.
    for name, _ in probs:
        target = 0.99 * statistics.median(
            r["hypervolume"] for r in runs if r["problem"] == name and r["variant"] == "original")
        for r in runs:
            if r["problem"] == name:
                r["generations_to_99pct_original_hv"] = generations_to(target, r["hv_history"])

    metrics_list = [("hypervolume", True), ("gd", False), ("igd", False), ("igd_plus", False),
                    ("spread", False), ("spacing", False),
               ("front_size", True), ("entropy", True), ("allocation_entropy", True), ("population_duplicates", False),
               ("dominated_by_lower_bound_copy", False), ("seconds", False), ("evaluations", False)]
    summary = {}
    for v in variants:
        if v == "original":
            continue
        summary[v] = {m: compare(by_variant[v], by_variant["original"], m, hib) for m, hib in metrics_list}

    def med(v, k):
        vals = [r[k] for r in by_variant[v] if r[k] is not None and np.isfinite(r[k])]
        return statistics.median(vals) if vals else float("nan")

    def reached(v):
        rs = by_variant[v]
        return sum(r["generations_to_99pct_original_hv"] is not None for r in rs) / len(rs)

    def objective_means(v):
        tops = [r["top_plan"] for r in by_variant[v] if r["top_plan"]]
        return {k: statistics.mean(t[k] for t in tops) for k in tops[0]} if tops else {}

    table = {}
    for v in variants:
        gens = [r["generations_to_99pct_original_hv"] for r in by_variant[v]
                if r["generations_to_99pct_original_hv"] is not None]
        table[v] = {
            "hypervolume": med(v, "hypervolume"), "gd": med(v, "gd"), "igd": med(v, "igd"),
            "igd_plus": med(v, "igd_plus"), "spread": med(v, "spread"),
            "spacing": med(v, "spacing"), "front_size": med(v, "front_size"), "entropy": med(v, "entropy"),
            "allocation_entropy": med(v, "allocation_entropy"),
            "population_duplicates": med(v, "population_duplicates"),
            "dominated_by_lower_bound_copy": med(v, "dominated_by_lower_bound_copy"),
            "seconds": med(v, "seconds"), "evaluations": med(v, "evaluations"), "generations": med(v, "generations"),
            "median_generations_to_99pct_original_hv": statistics.median(gens) if gens else None,
            "share_reaching_99pct_original_hv": reached(v),
            "top_plan_mean": objective_means(v),
        }

    print(f"\n{len(probs)} problems x {len(seeds)} seeds, pop {config.NSGA2_POP_SIZE}, gen budget {config.NSGA2_N_GEN}")
    head = f"{'variant':<44}{'HV':>8}{'IGD+':>9}{'spread':>8}{'size':>6}{'entropy':>8}{'dom.copy':>9}{'gen99':>7}{'evals':>7}{'s':>7}"
    print(head)
    for v in variants:
        t = table[v]
        g = t["median_generations_to_99pct_original_hv"]
        print(f"{v:<44}{t['hypervolume']:8.4f}{t['igd_plus']:9.4f}{t['spread']:8.3f}{t['front_size']:6.0f}"
              f"{t['entropy']:8.3f}{t['dominated_by_lower_bound_copy']:9.2f}{(g if g else float('nan')):7.0f}"
              f"{t['evaluations']:7.0f}{t['seconds']:7.3f}")
    print("\nPaired vs original (Wilcoxon signed-rank): better/worse/ties, median diff, p")
    for v, s in summary.items():
        parts = []
        for m in ("hypervolume", "gd", "igd_plus", "spread", "allocation_entropy", "seconds"):
            c = s[m]
            parts.append(f"{m} {c['better']}/{c['worse']}/{c['ties']} {c['median_diff']:+.4g} p={c['p_value']:.2g}")
        print(f"  {v}: " + "; ".join(parts))

    if args.json:
        slim = [{k: v for k, v in r.items() if k not in ("F", "X", "F_history")} for r in runs]
        Path(args.json).write_text(json.dumps({"variants": variants, "seeds": seeds,
                                               "problems": [n for n, _ in probs], "table": table,
                                               "paired": summary, "runs": slim}, indent=1, default=float))


if __name__ == "__main__":
    main()
