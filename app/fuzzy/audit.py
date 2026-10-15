"""
Audit of the Mamdani fuzzy system: measurements behind
docs/handbook/FUZZY_SYSTEM_ANALYSIS.md. Read-only -- nothing here changes
the engine or any optimisation result.

  rule_dominance()     rules whose every consequent is also concluded by a
                       rule with a subset of its conditions (provably inert
                       under min-AND / max aggregation), and partly
                       dominated rules
  membership_coverage() per input: epsilon-completeness, weakly covered
                       intervals, overlap at each crossing, partition sums
  output_bounds()      the crisp range centroid defuzzification can reach
  leave_one_out(grid)  largest output change on a grid when each rule is
                       removed (numerical check of the dominance proof)
  firing_statistics()  how often each rule fires / decides / is masked on
                       the dataset's real region profiles
  monotonicity(grid)   direction checks of the outputs against each input
  evaluate_grid()      batch evaluation with the exact aggregation of
                       engine._aggregate (identical to the engine, faster)
"""

from __future__ import annotations

import itertools
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import skfuzzy as fuzz

from app import config
from app.fuzzy import engine as fz

WEAK_COVERAGE = 0.5      # epsilon-completeness threshold commonly required of a fuzzy partition


def rule_dominance() -> dict:
    specs = fz.rule_specs()
    inert, partial = [], []
    for spec in specs:
        ants = set(spec.antecedents)
        dominated = {}
        for cons in spec.consequents:
            dominated[cons] = [o.number for o in specs
                               if o.number != spec.number and set(o.antecedents) <= ants and cons in o.consequents]
        entry = {"rule": spec.number, "if": spec.text_if, "then": spec.text_then,
                 "dominated_by": {f"{v} is {t}": d for (v, t), d in dominated.items()}}
        if all(dominated.values()):
            inert.append(entry)
        elif any(dominated.values()):
            partial.append(entry)
    return {"rules": len(specs), "inert": inert, "partly_dominated": partial,
            "effective_rules": len(specs) - len(inert),
            "proof": "With AND = min, a rule with a superset of another rule's conditions never fires more strongly; "
                     "with max aggregation its cut of a shared consequent term is therefore never the maximum, so it "
                     "cannot change the aggregated set."}


def _antecedents():
    _, rainfall_dev, water_storage, soil_fert = fz._build_system()
    return (rainfall_dev, water_storage, soil_fert)


def membership_coverage(step: float = 0.01) -> dict:
    """Coverage of each input partition, evaluated on a fine grid (step
    0.01) from the exact triangle parameters."""
    out = {}
    for var, sets in fz.MEMBERSHIP_FUNCTIONS.items():
        if var not in fz.INPUT_BOUNDS:
            continue
        lo, hi = fz.INPUT_BOUNDS[var]
        u = np.round(np.arange(lo, hi + step / 2, step), 6)
        mfs = {label: fuzz.trimf(u, list(abc)) for label, abc in sets.items()}
        stack = np.vstack(list(mfs.values()))
        best = stack.max(axis=0)
        weak_mask = best < WEAK_COVERAGE
        weak, i = [], 0
        while i < len(u):
            if weak_mask[i]:
                j = i
                while j + 1 < len(u) and weak_mask[j + 1]:
                    j += 1
                weak.append([round(float(u[i]), 2), round(float(u[j]), 2)])
                i = j + 1
            else:
                i += 1
        labels = list(mfs)
        crossings = []
        for a, b in zip(labels, labels[1:]):
            both = np.minimum(mfs[a], mfs[b])
            k = int(np.argmax(both))
            overlap = u[both > 0]
            crossings.append({"sets": [a, b], "at": round(float(u[k]), 2), "membership": round(float(both[k]), 3),
                              "overlap_width": round(float(overlap[-1] - overlap[0]), 2) if len(overlap) else 0.0})
        sums = stack.sum(axis=0)
        out[var] = {
            "universe": [lo, hi],
            "sets": {label: list(abc) for label, abc in sets.items()},
            "epsilon_completeness": round(float(best.min()), 3),
            "weak_intervals": weak,
            "weak_share_pct": round(float(weak_mask.mean() * 100), 1),
            "uncovered_points": int(np.sum(best == 0)),
            "membership_sum_range": [round(float(sums.min()), 3), round(float(sums.max()), 3)],
            "crossings": crossings,
        }
    return out


def output_bounds() -> dict:
    """Centroid of a single fully-fired extreme term: the lowest/highest
    crisp value the engine can produce."""
    out = {}
    for var in fz.OUTPUT_VARIABLES:
        lo = fz._centroid01(var, {"low": 1.0})
        hi = fz._centroid01(var, {"high": 1.0})
        out[var] = {"min": round(lo, 4), "max": round(hi, 4)}
    return out


def _firing(r, w, s, memberships_fn=fz._raw_memberships):
    m = memberships_fn(fz._clipped_inputs(r, w, s))
    return {spec.number: min(m[v][t] for v, t in spec.antecedents) for spec in fz.rule_specs()}


def evaluate_point(r: float, w: float, s: float, exclude: Optional[int] = None) -> Dict[str, float]:
    """Crisp outputs (0-1, unrounded) via the exact aggregation; `exclude`
    removes one rule. Falls back to 0.5 like the engine."""
    cuts = fz._term_cuts(_firing(r, w, s), exclude=exclude)
    out = {}
    for var in fz.OUTPUT_VARIABLES:
        c = fz._centroid01(var, {t: v for t, (v, _) in cuts[var].items()})
        out[var] = 0.5 if c is None else c
    return out


def grid(n: int = 21) -> List[Tuple[float, float, float]]:
    lo = [b[0] for b in fz.INPUT_BOUNDS.values()]
    hi = [b[1] for b in fz.INPUT_BOUNDS.values()]
    axes = [np.linspace(a, b, n) for a, b in zip(lo, hi)]
    return [tuple(float(v) for v in p) for p in itertools.product(*axes)]


def evaluate_grid(points: Iterable[Tuple[float, float, float]]) -> np.ndarray:
    """(N, 2) array of [yield_conf, irrigation_risk] for many inputs."""
    return np.array([[o["yield_conf"], o["irrigation_risk"]] for o in (evaluate_point(*p) for p in points)])


def leave_one_out(points: Optional[List[Tuple[float, float, float]]] = None) -> List[dict]:
    points = points or grid(11)
    base = evaluate_grid(points)
    rows = []
    for spec in fz.rule_specs():
        alt = np.array([[o["yield_conf"], o["irrigation_risk"]] for o in (evaluate_point(*p, exclude=spec.number) for p in points)])
        diff = np.abs(alt - base)
        rows.append({"rule": spec.number, "max_change_yield_conf": round(float(diff[:, 0].max()), 4),
                     "max_change_irrigation_risk": round(float(diff[:, 1].max()), 4),
                     "points_changed_pct": round(float(np.mean(diff.max(axis=1) > 1e-12) * 100), 1)})
    return rows


def dataset_points() -> List[dict]:
    """Fuzzy inputs of every location/season/year region profile in the data."""
    from app.data import preprocessing as pp
    years = sorted(int(y) for y in pp.load_all()["crop"]["Year"].unique())
    out = []
    for loc in config.LOCATIONS:
        for season in config.AG_SEASONS:
            for year in years:
                try:
                    p = pp.get_region_season_profile(loc, season, year)
                except ValueError:
                    continue
                out.append({"location": loc, "season": season, "year": year, "estimated": p.data_year_estimated,
                            "inputs": (p.rainfall.avg_deviation_percent, p.water.avg_storage_percent, p.soil.fertility_index)})
    return out


def firing_statistics(points: Optional[List[dict]] = None) -> dict:
    points = points if points is not None else dataset_points()
    stats = {spec.number: {"rule": spec.number, "if": spec.text_if, "then": spec.text_then, "fired": 0, "decisive": 0,
                           "masked": 0, "decisive_only_by_tie": 0, "strength_sum": 0.0, "importance_max": 0.0, "contribution_sum": 0.0}
             for spec in fz.rule_specs()}
    fired_counts, sets_seen = [], {var: set() for var in fz.INPUT_BOUNDS}
    for p in points:
        e = fz.explain_inference(*p["inputs"])
        fired_counts.append(e["summary"]["fired"])
        for var, info in e["inputs"].items():
            sets_seen[var].update(t for t, v in info["memberships"].items() if v > 0)
        for r in e["rules"]:
            st = stats[r["rule"]]
            if r["status"] == "not fired":
                continue
            st["fired"] += 1
            st["strength_sum"] += r["strength"]
            st[r["status"]] += 1
            if r["status"] == "decisive" and r["tied_with"] and r["importance"] == 0:
                st["decisive_only_by_tie"] += 1
            st["importance_max"] = max(st["importance_max"], r["importance"])
            st["contribution_sum"] += sum(r["contribution_pct"].values()) / 2
    n = len(points)
    rows = []
    for st in stats.values():
        rows.append({**{k: st[k] for k in ("rule", "if", "then", "fired", "decisive", "decisive_only_by_tie", "masked")},
                     "fired_pct": round(st["fired"] / n * 100, 1) if n else 0.0,
                     "mean_strength_when_fired": round(st["strength_sum"] / st["fired"], 3) if st["fired"] else None,
                     "mean_contribution_pct": round(st["contribution_sum"] / n, 1) if n else 0.0,
                     "max_importance": round(st["importance_max"], 4)})
    all_sets = {ant.label: set(ant.terms) for ant in _antecedents()}
    return {"profiles": n, "rules": rows,
            "fired_per_profile": {"min": min(fired_counts), "max": max(fired_counts),
                                  "mean": round(float(np.mean(fired_counts)), 2)} if fired_counts else None,
            "never_fired": [r["rule"] for r in rows if r["fired"] == 0],
            "never_decisive": [r["rule"] for r in rows if r["decisive"] == 0],
            "input_sets_never_activated": {v: sorted(all_sets[v] - sets_seen[v]) for v in all_sets}}


def monotonicity(n: int = 21) -> List[dict]:
    """Share of grid steps in which an output moves against the expected
    direction, and the largest such move. Expected directions follow the
    rule base's own reading: more soil fertility or storage should not
    lower yield confidence; more storage should not raise irrigation risk."""
    axes = [np.linspace(*fz.INPUT_BOUNDS[v], n) for v in fz.INPUT_BOUNDS]
    pts = list(itertools.product(*axes))
    values = evaluate_grid(pts).reshape(n, n, n, 2)
    checks = [("yield_conf", "soil_fert", 2, 0, +1), ("yield_conf", "water_storage", 1, 0, +1),
              ("irrigation_risk", "water_storage", 1, 1, -1)]
    rows = []
    for out_name, in_name, axis, k, sign in checks:
        d = np.diff(values[..., k], axis=axis) * sign
        viol = d < -1e-9
        rows.append({"output": out_name, "input": in_name, "expected": "non-decreasing" if sign > 0 else "non-increasing",
                     "violating_steps_pct": round(float(viol.mean() * 100), 1),
                     "largest_violation": round(float(-d.min()) if viol.any() else 0.0, 4)})
    return rows


@lru_cache(maxsize=1)
def summary() -> dict:
    """Static audit used by GET /api/fuzzy/audit (rule base + data are fixed at runtime)."""
    return {"dominance": rule_dominance(), "coverage": membership_coverage(), "output_bounds": output_bounds(),
            "dataset_firing": firing_statistics()}
