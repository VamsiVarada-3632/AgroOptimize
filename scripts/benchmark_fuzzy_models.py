"""
Benchmark of the fuzzy models (docs/handbook/FUZZY_BENCHMARK_RESULTS.md).

    python3 scripts/benchmark_fuzzy_models.py [--json out.json] [--seeds 5] [--quick]

Every model in the comparison is measured with the same code:

  fuzzy layer   rules (count, effective, fired / decisive per profile),
                coverage (epsilon-completeness), monotonicity on a 21^3
                grid, confidence (output level, term membership, rule
                support), robustness to input noise, signal-to-noise ratio
                across the 60 dataset profiles, first-order sensitivity,
                agreement of the rainfall label with IMD, runtime, memory
  pipeline      NSGA-II (original engine) on 4 districts x 3 seasons x
                seeds: runtime, hypervolume, GD, IGD, IGD+, spread,
                spacing (each model against the union of its own runs),
                constraint satisfaction; TOPSIS ranking stability and
                recommendation stability under input noise

The comparison runs the original model, each improvement on its own, the
cumulative chain (1, 1+2, 1+2+3 = final) and two screened candidates that
are not in the engine (product AND, capping rules read as implicative
constraints), whose fuzzy-layer metrics come from an exact re-implementation
of the aggregation (checked against the engine on the original model).
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import statistics
import sys
import time
import tracemalloc
import warnings
from types import SimpleNamespace

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("AGROOPTIMIZE_RESULTS_DIR", "/tmp/agrooptimize_fuzzy_benchmark")

import numpy as np  # noqa: E402
import skfuzzy as fuzz  # noqa: E402
from scipy.stats import kendalltau  # noqa: E402

from app import config  # noqa: E402
from app.data import preprocessing as pp  # noqa: E402
from app.decision import ranking  # noqa: E402
from app.fuzzy import audit  # noqa: E402
from app.fuzzy import engine as fz  # noqa: E402
from app.fuzzy.engine import FuzzyModel  # noqa: E402
from app.optimization import metrics  # noqa: E402
from app.optimization.nsga2_runner import extract_pareto_plans, run_nsga2  # noqa: E402
from app.optimization.problem import FarmPlanProblem  # noqa: E402

GRID_N = 21
NOISE = (5.0, 2.0, 2.0)   # +/- rainfall deviation (pp), storage (pp), fertility index (points)
SEASONS = ("Kharif", "Rabi", "Summer")

I1 = FuzzyModel("I1 strong partition", strong_partition=True)
I2 = FuzzyModel("I2 IMD rainfall", imd_rainfall=True)
I3 = FuzzyModel("I3 pruned rules", prune_inert=True)
I12 = FuzzyModel("I1+I2", strong_partition=True, imd_rainfall=True)
FINAL = FuzzyModel("I1+I2+I3 (final)", strong_partition=True, imd_rainfall=True, prune_inert=True)
ENGINE_MODELS = [fz.ORIGINAL, I1, I2, I3, I12, FINAL]
CHAIN = ["original", I1.name, I12.name, FINAL.name]


# ---------------------------------------------------------------------------
# Evaluators
# ---------------------------------------------------------------------------

class EngineEvaluator:
    """Exact, unrounded outputs of an engine model (audit.evaluate_point)."""

    def __init__(self, model: FuzzyModel):
        self.model, self.name = model, model.name

    def specs(self):
        return fz.rule_specs(self.model)

    def memberships(self, p):
        return fz._raw_memberships(fz._clipped_inputs(*p), self.model)

    def firing(self, p):
        m = self.memberships(p)
        return {s.number: min(m[v][t] for v, t in s.antecedents) for s in self.specs()}

    def __call__(self, p, exclude=None):
        o = audit.evaluate_point(*p, exclude=exclude, model=self.model)
        return o["yield_conf"], o["irrigation_risk"]

    def membership_table(self):
        return fz.membership_functions(self.model)


class ScreenEvaluator(EngineEvaluator):
    """Original membership functions and rules with a different AND
    operator and/or some rules read as implicative upper bounds
    ("output is at most <term>", Kleene-Dienes implication, combined by
    intersection as Dubois & Prade 1996 prescribe for constraint rules)."""

    def __init__(self, name, tnorm="min", caps=()):
        super().__init__(fz.ORIGINAL)
        self.name, self.tnorm, self.caps = name, tnorm, tuple(caps)

    def firing(self, p):
        m = self.memberships(p)
        agg = min if self.tnorm == "min" else (lambda xs: float(np.prod(list(xs))))
        return {s.number: agg(m[v][t] for v, t in s.antecedents) for s in self.specs()}

    def __call__(self, p, exclude=None):
        f = self.firing(p)
        out = []
        for var in fz.OUTPUT_VARIABLES:
            cuts = {}
            for s in self.specs():
                if s.number == exclude or s.number in self.caps:
                    continue
                for v, t in s.consequents:
                    if v == var:
                        cuts[t] = max(cuts.get(t, 0.0), f[s.number])
            universe, agg, _ = fz._aggregate(var, cuts, self.model)
            consequent = fz._consequent(var, self.model)
            for s in self.specs():
                if s.number not in self.caps or s.number == exclude:
                    continue
                for v, t in s.consequents:
                    if v != var:
                        continue
                    mf = fuzz.interp_membership(consequent.universe, consequent[t].mf, universe)
                    at_most = np.where(universe <= universe[np.argmax(mf)], 1.0, mf)
                    agg = np.minimum(agg, np.maximum(1 - f[s.number], at_most))
            out.append(0.5 if not np.any(agg > 0) else float(fuzz.defuzz(universe, agg, "centroid")) / 100)
        return tuple(out)


SCREENED = [ScreenEvaluator("S1 product AND", tnorm="prod"),
            ScreenEvaluator("S2 implicative caps (16, 19, 23)", caps=(16, 19, 23))]


# ---------------------------------------------------------------------------
# Fuzzy-layer metrics
# ---------------------------------------------------------------------------

def dataset_inputs():
    return [tuple(p["inputs"]) for p in audit.dataset_points()]


def grid_points(n=GRID_N):
    axes = [np.linspace(*fz.INPUT_BOUNDS[v], n) for v in fz.INPUT_BOUNDS]
    return [tuple(float(x) for x in p) for p in itertools.product(*axes)], axes


def epsilon(table):
    out = {}
    for var, (lo, hi) in fz.INPUT_BOUNDS.items():
        u = np.linspace(lo, hi, 12001)
        out[var] = round(float(np.vstack([fz._mf(u, p) for p in table[var].values()]).max(0).min()), 3)
    return out


def fuzzy_metrics(ev, data, grid, axes):
    r = {"model": ev.name}
    r["epsilon_completeness"] = epsilon(ev.membership_table())
    g = np.array([ev(p) for p in grid]).reshape(GRID_N, GRID_N, GRID_N, 2)
    mono = {}
    for name, axis, k, sign in (("yield_vs_storage", 1, 0, 1), ("yield_vs_fertility", 2, 0, 1),
                                ("risk_vs_storage", 1, 1, -1)):
        d = np.diff(g[..., k], axis=axis) * sign
        mono[name] = {"steps_pct": round(float((d < -1e-9).mean() * 100), 1),
                      "steps_over_0.01_pct": round(float((d < -0.01).mean() * 100), 1),
                      "largest": round(float(max(0.0, -d.min())), 4)}
    r["monotonicity"] = mono
    r["max_change_per_input_unit"] = [round(float(np.abs(np.diff(g, axis=a)).max() / (axes[a][1] - axes[a][0])), 4)
                                      for a in range(3)]
    r["first_order_sensitivity"] = {}
    for k, out in enumerate(("yield_conf", "irrigation_risk")):
        y = g[..., k]
        r["first_order_sensitivity"][out] = {
            var: round(float(y.mean(axis=tuple(j for j in range(3) if j != i)).var() / y.var()), 3)
            for i, var in enumerate(fz.INPUT_BOUNDS)}

    d = np.array([ev(p) for p in data])
    r["output_mean"] = [round(float(x), 4) for x in d.mean(0)]
    r["output_std"] = [round(float(x), 4) for x in d.std(0)]
    r["output_range"] = [[round(float(d[:, k].min()), 3), round(float(d[:, k].max()), 3)] for k in range(2)]

    fired, support, active = [], [], set()
    for p in data:
        f = ev.firing(p)
        on = [n for n, v in f.items() if v > 0]
        fired.append(len(on))
        active |= set(on)
        support.append(max(f.values()))
    numbers = [s.number for s in ev.specs()]
    r["rules"] = len(numbers)
    r["fired_per_profile"] = round(float(np.mean(fired)), 2)
    r["rule_support_mean"] = round(float(np.mean(support)), 3)
    r["rules_never_fired_on_data"] = sorted(set(numbers) - active)

    # Effective rules: removing the rule changes an output somewhere (11^3 grid + data).
    pts = audit.grid(11) + list(data)
    base = np.array([ev(p) for p in pts])
    effective = [n for n in numbers if np.abs(np.array([ev(p, exclude=n) for p in pts]) - base).max() > 1e-12]
    r["effective_rules"] = len(effective)
    r["inert_rules"] = sorted(set(numbers) - set(effective))

    # Robustness: output change under every +/- NOISE corner around each profile.
    deltas = []
    for p in data:
        b = np.array(ev(p))
        for sgn in itertools.product((-1, 1), repeat=3):
            q = tuple(x + s * e for x, s, e in zip(p, sgn, NOISE))
            deltas.append(np.abs(np.array(ev(q)) - b))
    deltas = np.array(deltas)
    r["noise_change_mean"] = [round(float(x), 4) for x in deltas.mean(0)]
    r["noise_change_max"] = [round(float(x), 4) for x in deltas.max(0)]
    r["signal_to_noise"] = [round(float(d[:, k].std() / deltas[:, k].mean()), 2) for k in range(2)]

    labels = [max(ev.memberships(p)["rainfall_dev"].items(), key=lambda kv: kv[1])[0] for p in data]
    r["imd_label_agreement"] = sum(lab == fz.imd_category(p[0]) for lab, p in zip(labels, data))
    return r


def engine_only_metrics(model, data):
    """Explanation, confidence and cost measures that need the real engine."""
    r = {}
    expl = [fz.explain_inference(*p, model=model) for p in data]
    r["decisive_per_profile"] = round(float(np.mean([e["summary"]["decisive"] for e in expl])), 2)
    r["masked_per_profile"] = round(float(np.mean([e["summary"]["masked"] for e in expl])), 2)
    r["zero_importance_fired_per_profile"] = round(float(np.mean(
        [sum(1 for x in e["rules"] if x["status"] != "not fired" and x["importance"] == 0) for e in expl])), 2)
    r["output_term_membership_mean"] = {
        v: round(float(np.mean([e["outputs"][v]["term_membership"] for e in expl])), 3) for v in fz.OUTPUT_VARIABLES}
    r["fallback_used"] = sum(e["outputs"][v]["fallback_used"] for e in expl for v in fz.OUTPUT_VARIABLES)
    # Outputs formed by a single output term: the centroid is then that term's
    # centroid whatever the firing strength, so the value ignores how strongly
    # the evidence supports it (e.g. yield 0.883 from one rule firing at 0.4).
    r["single_term_outputs"] = {v: sum(sum(1 for c in e["outputs"][v]["term_cuts"].values() if c["cut"] > 0) == 1
                                       for e in expl) for v in fz.OUTPUT_VARIABLES}

    def clear():
        for f in (fz._evaluate_cached, fz._memberships_cached, fz._fired_cached):
            f.cache_clear()

    def distinct():
        clear()
        for p in data:
            fz.evaluate_uncertainty(*p, model=model)

    def explain_all():
        clear()
        for p in data:
            fz.explain_inference(*p, model=model)

    distinct()
    runs = []
    for _ in range(5):
        t = time.perf_counter()
        distinct()
        runs.append(time.perf_counter() - t)
    r["inference_ms_per_call"] = round(statistics.median(runs) / len(data) * 1000, 3)
    runs = []
    for _ in range(3):
        t = time.perf_counter()
        explain_all()
        runs.append(time.perf_counter() - t)
    r["explanation_ms_per_call"] = round(statistics.median(runs) / len(data) * 1000, 2)
    fz._build_system.cache_clear()
    fz._rule_specs.cache_clear()
    clear()
    tracemalloc.start()
    fz.build_system(model)
    for p in data:
        fz.evaluate_uncertainty(*p, model=model)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    r["peak_memory_kb_build_and_60_inferences"] = round(peak / 1024, 1)
    return r


# ---------------------------------------------------------------------------
# Pipeline metrics
# ---------------------------------------------------------------------------

def problems():
    out = []
    for loc in config.LOCATIONS:
        for season in SEASONS:
            out.append((f"{loc} {season}", pp.get_region_season_profile(loc, season)))
    return out


def balanced_closeness(plans):
    return ranking.topsis_scores([p.yield_tonnes for p in plans], [p.cost_rs for p in plans],
                                 [p.water_liters for p in plans], [p.env_impact_score for p in plans],
                                 ranking.preference_weights("balanced"))[0]


def land_shares(plan, crops):
    share = dict(zip(plan.crop_names, plan.allocation_fraction))
    v = np.array([share.get(c, 0.0) for c in crops])
    return v / v.sum() if v.sum() > 0 else v


def pipeline_metrics(model, profs, seeds):
    runs, fronts = [], {}
    stability = {"topsis_kendall_tau": [], "top_plan_land_moved_pct": [], "top_crop_unchanged": []}
    for key, prof in profs:
        x = (prof.rainfall.avg_deviation_percent, prof.water.avg_storage_percent, prof.soil.fertility_index)
        assessment = fz.evaluate_uncertainty(*x, model=model)
        problem = FarmPlanProblem(prof, assessment, 5.0)
        crops = [c.name for c in prof.candidate_crops]
        base_result = None
        for s in seeds:
            t = time.perf_counter()
            res = run_nsga2(problem, seed=s)
            plans = [p for p in extract_pareto_plans(res, problem) if p.feasible]
            sec = time.perf_counter() - t
            G = np.atleast_2d(res.pop.get("G"))
            runs.append({"problem": key, "seed": s, "seconds": sec,
                         "population_feasible_pct": float(np.mean(np.all(G <= 1e-6, axis=1)) * 100),
                         "feasible_front": len(plans),
                         "F": [[-p.yield_tonnes, p.cost_rs, p.water_liters, p.env_impact_score] for p in plans]})
            fronts.setdefault(key, []).extend(runs[-1]["F"])
            if s == seeds[0]:
                base_result, base_plans = res, plans
        # Stability under input noise (seed fixed): every +/- NOISE corner.
        base_close = balanced_closeness(base_plans)
        base_top = base_plans[int(np.argmax(base_close))]
        X = np.atleast_2d(base_result.X)
        keep = [i for i, p in enumerate(extract_pareto_plans(base_result, problem)) if p.feasible]
        for sgn in itertools.product((-1, 1), repeat=3):
            q = tuple(v + s * e for v, s, e in zip(x, sgn, NOISE))
            pert = FarmPlanProblem(prof, fz.evaluate_uncertainty(*q, model=model), 5.0)
            # TOPSIS stability: the same Pareto set re-scored under the perturbed fuzzy outputs.
            out = pert.evaluate(X, return_as_dictionary=True)
            rescored = extract_pareto_plans(SimpleNamespace(X=X, F=out["F"], G=out.get("G")), pert)
            close = balanced_closeness([rescored[i] for i in keep])
            stability["topsis_kendall_tau"].append(float(kendalltau(base_close, close)[0]))
            res = run_nsga2(pert, seed=seeds[0])
            pplans = [p for p in extract_pareto_plans(res, pert) if p.feasible]
            top = pplans[int(np.argmax(balanced_closeness(pplans)))]
            a, b = land_shares(base_top, crops), land_shares(top, crops)
            stability["top_plan_land_moved_pct"].append(float(np.abs(a - b).sum() / 2 * 100))
            stability["top_crop_unchanged"].append(bool(crops[int(np.argmax(a))] == crops[int(np.argmax(b))]))
        print(f"    {model.name}: {key}", flush=True)

    quality = []
    for r in runs:
        q = metrics.front_quality(np.array(r["F"]), np.array(fronts[r["problem"]]))
        quality.append({**q, "problem": r["problem"], "seed": r["seed"]})
    agg = lambda k: round(float(np.mean([q[k] for q in quality])), 4)  # noqa: E731
    return {
        "runs": len(runs),
        "runtime_s_mean": round(float(np.mean([r["seconds"] for r in runs])), 3),
        "hypervolume": agg("hypervolume"), "gd": agg("gd"), "igd": agg("igd"), "igd_plus": agg("igd_plus"),
        "spread": agg("spread"), "spacing": agg("spacing"),
        "population_feasible_pct": round(float(np.mean([r["population_feasible_pct"] for r in runs])), 1),
        "feasible_front_mean": round(float(np.mean([r["feasible_front"] for r in runs])), 1),
        "topsis_kendall_tau_mean": round(float(np.mean(stability["topsis_kendall_tau"])), 3),
        "topsis_kendall_tau_min": round(float(np.min(stability["topsis_kendall_tau"])), 3),
        "top_plan_land_moved_pct_mean": round(float(np.mean(stability["top_plan_land_moved_pct"])), 1),
        "top_crop_unchanged_pct": round(float(np.mean(stability["top_crop_unchanged"]) * 100), 1),
        "stability_cases": {k: [round(float(v), 6) for v in vals] for k, vals in stability.items()},
        "fuzzy_outputs": {k: [round(v, 3) for v in (fz.evaluate_uncertainty(
            p.rainfall.avg_deviation_percent, p.water.avg_storage_percent, p.soil.fertility_index,
            model=model).yield_confidence, fz.evaluate_uncertainty(
            p.rainfall.avg_deviation_percent, p.water.avg_storage_percent, p.soil.fertility_index,
            model=model).irrigation_risk)] for k, p in profs},
        "per_run": [{k: v for k, v in r.items() if k != "F"} | {kk: round(float(vv), 6) for kk, vv in q.items()
                    if kk not in ("problem", "seed")} for r, q in zip(runs, quality)],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--quick", action="store_true", help="fuzzy layer only (no NSGA-II)")
    args = ap.parse_args()

    data = dataset_inputs()
    grid, axes = grid_points()
    check = max(abs(a - b) for p in data + grid[::50]
                for a, b in zip(ScreenEvaluator("check")(p), EngineEvaluator(fz.ORIGINAL)(p)))
    assert check < 1e-12, f"screening evaluator differs from the engine by {check}"

    out = {"setup": {"profiles": len(data), "grid": f"{GRID_N}^3", "noise": NOISE, "seeds": args.seeds,
                     "pop_size": config.NSGA2_POP_SIZE, "n_gen": config.NSGA2_N_GEN,
                     "screening_check_max_diff": check},
           "models": {}}
    for ev in [EngineEvaluator(m) for m in ENGINE_MODELS] + SCREENED:
        t = time.perf_counter()
        r = fuzzy_metrics(ev, data, grid, axes)
        if isinstance(ev, ScreenEvaluator):
            r["screened_only"] = True
        else:
            r.update(engine_only_metrics(ev.model, data))
        out["models"][ev.name] = r
        print(f"  fuzzy layer: {ev.name} ({time.perf_counter() - t:.1f} s)", flush=True)

    if not args.quick:
        profs = problems()
        for m in ENGINE_MODELS:
            out["models"][m.name]["pipeline"] = pipeline_metrics(m, profs, list(range(args.seeds)))

    out["chain"] = CHAIN
    text = json.dumps(out, indent=1, default=float)
    if args.json:
        with open(args.json, "w") as f:
            f.write(text)
    summary = {k: {kk: v for kk, v in m.items() if kk != "pipeline"} | (
        {"pipeline": {kk: vv for kk, vv in m["pipeline"].items() if kk not in ("per_run", "fuzzy_outputs")}}
        if "pipeline" in m else {}) for k, m in out["models"].items()}
    print(json.dumps(summary, indent=1, default=float))


if __name__ == "__main__":
    main()
