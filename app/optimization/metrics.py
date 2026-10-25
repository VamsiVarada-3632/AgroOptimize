"""
Quality indicators for NSGA-II fronts, shared by the API (every run carries
`meta.quality_metrics`) and the benchmark (scripts/benchmark_nsga2.py).

All distance and volume indicators are computed on objectives normalised to
[0, 1] by the ideal and nadir point of a reference front, with every
objective minimised (yield enters as -yield, as in FarmPlanProblem):

* hypervolume       Zitzler & Thiele 1999; reference point 1.1 on every axis
* GD                generational distance, Van Veldhuizen & Lamont 1998:
                    mean distance from each solution to the reference front
* IGD               inverted generational distance, Coello & Reyes Sierra 2004:
                    mean distance from each reference point to the front
* IGD+              Ishibuchi et al. 2015 (weakly Pareto compliant)
* spread            generalised spread, Zhou et al. 2006 (0 = perfectly even)
* spacing           Schott 1995 (0 = equally spaced neighbours)

A single run has no external reference front. Every run therefore uses a
reference it can compute exactly: the non-dominated union of its front and
each solution's copy with the irrigation and fertiliser multipliers at their
lower bound. In FarmPlanProblem yield does not depend on the multipliers
while cost, water and impact rise with them, so that copy is never worse on
any objective (NSGAII_ANALYSIS.md section 4.2). GD and IGD then measure how far
the run is from converging on that face of the search space, and
`hypervolume_ratio` is the share of the reference front's hypervolume the
run reaches (1.0 = fully converged in this sense). Benchmarks pass a common
reference front instead, built from every run on the same problem.
"""

from __future__ import annotations

import math
from typing import Optional, Sequence

import numpy as np
from pymoo.indicators.gd import GD
from pymoo.indicators.hv import HV
from pymoo.indicators.igd import IGD
from pymoo.indicators.igd_plus import IGDPlus
from pymoo.util.nds.non_dominated_sorting import NonDominatedSorting

HV_REFERENCE = 1.1
OBJECTIVE_NAMES = ("yield_tonnes", "cost_rs", "water_liters", "env_impact_score")


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

def nondominated(F: np.ndarray) -> np.ndarray:
    """The non-dominated rows of F (all objectives minimised)."""
    F = np.atleast_2d(np.asarray(F, dtype=float))
    if len(F) == 0:
        return F
    return F[NonDominatedSorting().do(F, only_non_dominated_front=True)]


def normalisation(reference: np.ndarray):
    """(lower bound, span) mapping the reference front's ideal to 0 and its
    nadir to 1; a degenerate objective keeps span 1."""
    lo, hi = reference.min(axis=0), reference.max(axis=0)
    return lo, np.where(hi - lo > 1e-12, hi - lo, 1.0)


def hypervolume(Fn: np.ndarray, ref: float = HV_REFERENCE) -> float:
    if len(Fn) == 0:
        return 0.0
    return float(HV(ref_point=np.full(Fn.shape[1], ref))(Fn))


def generational_distance(Fn: np.ndarray, reference_n: np.ndarray) -> float:
    return float(GD(reference_n)(Fn)) if len(Fn) else math.nan


def inverted_generational_distance(Fn: np.ndarray, reference_n: np.ndarray) -> float:
    return float(IGD(reference_n)(Fn)) if len(Fn) else math.nan


def igd_plus(Fn: np.ndarray, reference_n: np.ndarray) -> float:
    return float(IGDPlus(reference_n)(Fn)) if len(Fn) else math.nan


def generalized_spread(Fn: np.ndarray, extremes: Sequence[np.ndarray]) -> float:
    """Zhou et al. (2006) generalised spread on normalised objectives:
    distance of the front to the reference extremes plus the deviation of the
    nearest-neighbour distances from their mean, relative to their total."""
    if len(Fn) < 2:
        return math.nan
    D = np.linalg.norm(Fn[:, None, :] - Fn[None, :, :], axis=2)
    np.fill_diagonal(D, np.inf)
    d = D.min(axis=1)
    d_mean = d.mean()
    d_ext = sum(np.linalg.norm(Fn - e, axis=1).min() for e in extremes)
    denom = d_ext + len(Fn) * d_mean
    return float((d_ext + np.abs(d - d_mean).sum()) / denom) if denom > 0 else math.nan


def spacing(Fn: np.ndarray) -> float:
    """Schott (1995) spacing: standard deviation of the L1 nearest-neighbour
    distances on normalised objectives."""
    if len(Fn) < 2:
        return math.nan
    D = np.abs(Fn[:, None, :] - Fn[None, :, :]).sum(axis=2)
    np.fill_diagonal(D, np.inf)
    d = D.min(axis=1)
    return float(np.sqrt(((d - d.mean()) ** 2).sum() / (len(Fn) - 1)))


def extremes(reference_n: np.ndarray):
    """The reference point that is best on each objective."""
    return [reference_n[np.argmin(reference_n[:, m])] for m in range(reference_n.shape[1])]


def front_quality(F: np.ndarray, reference: np.ndarray) -> dict:
    """Every indicator of front F (raw objectives) against `reference`
    (raw objectives of the reference front)."""
    F = np.atleast_2d(np.asarray(F, dtype=float))
    reference = nondominated(reference)
    lo, span = normalisation(reference)
    Fn = (F - lo) / span if len(F) else F
    ref_n = (reference - lo) / span
    hv, hv_ref = hypervolume(Fn), hypervolume(ref_n)
    return {
        "hypervolume": hv,
        "hypervolume_ratio": hv / hv_ref if hv_ref > 0 else math.nan,
        "gd": generational_distance(Fn, ref_n),
        "igd": inverted_generational_distance(Fn, ref_n),
        "igd_plus": igd_plus(Fn, ref_n),
        "spread": generalized_spread(Fn, extremes(ref_n)),
        "spacing": spacing(Fn),
    }


# ---------------------------------------------------------------------------
# Per-run metrics (stored in meta.quality_metrics)
# ---------------------------------------------------------------------------

def lower_bound_copy(problem, X: np.ndarray) -> np.ndarray:
    """X with every irrigation and fertiliser multiplier at its lower bound."""
    X = np.array(X, dtype=float, copy=True)
    X[:, problem.n_crops:] = np.asarray(problem.xl)[problem.n_crops:]
    return X


def feasible_front(result):
    """Decision vectors and objectives of the run's final feasible first front."""
    if result.X is None or np.size(result.X) == 0:
        return np.empty((0, 0)), np.empty((0, 4))
    X, F = np.atleast_2d(result.X), np.atleast_2d(result.F)
    G = np.atleast_2d(result.G) if result.G is not None and np.size(result.G) else None
    ok = np.all(G <= 1e-6, axis=1) if G is not None else np.ones(len(F), dtype=bool)
    return X[ok], F[ok]


def lower_bound_copies(problem, X: np.ndarray) -> np.ndarray:
    """Objectives of the lower-bound copies of X (feasible ones only when a
    budget applies)."""
    if len(X) == 0:
        return np.empty((0, 4))
    copies = problem.evaluate(lower_bound_copy(problem, X), return_as_dictionary=True)
    F_lb = copies["F"]
    if problem.budget_rs:
        F_lb = F_lb[np.all(copies["G"] <= 1e-6, axis=1)]
    return F_lb


def lower_bound_reference(problem, X: np.ndarray, F: np.ndarray) -> np.ndarray:
    """Non-dominated union of the front and its lower-bound copies."""
    if len(F) == 0:
        return F
    return nondominated(np.vstack([F, lower_bound_copies(problem, X)]))


def share_dominated_by_lower_bound_copy(problem, X: np.ndarray, F: np.ndarray) -> float:
    """Share of the front strictly dominated by its own lower-bound copy (a
    direct measure of unfinished convergence in this problem)."""
    if len(F) == 0:
        return math.nan
    F_lb = problem.evaluate(lower_bound_copy(problem, X), return_as_dictionary=True)["F"]
    not_worse = np.all(F_lb <= F + 1e-9 * np.abs(F), axis=1)
    better = np.any(F_lb < F - 1e-6 * np.abs(F), axis=1)
    return float((not_worse & better).mean())


def _clean(value):
    """JSON-safe: NaN/inf become None, numpy scalars become floats."""
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, (float, np.floating)):
        value = float(value)
        return round(value, 6) if math.isfinite(value) else None
    if isinstance(value, np.integer):
        return int(value)
    return value


def run_quality_metrics(result, problem) -> dict:
    """Quality metrics of one run, JSON-ready: Pareto quality against the
    run's lower-bound reference (see module docstring), diversity,
    constraint satisfaction, effort and the mean objectives of the front."""
    X, F = feasible_front(result)
    pop_cv = np.ravel(result.pop.get("CV")) if result.pop is not None else np.empty(0)
    report = getattr(result, "engine_report", {}) or {}
    profile = report.get("profile", {})
    out = {
        "reference_front": "front + lower-bound-multiplier copies (non-dominated union)",
        "pareto_size": int(np.atleast_2d(result.F).shape[0]) if result.F is not None else 0,
        "feasible_pareto_size": int(len(F)),
        "constraint_satisfaction_rate": float((pop_cv <= 0.0).mean()) if pop_cv.size else None,
        "dominated_by_lower_bound_copy": share_dominated_by_lower_bound_copy(problem, X, F),
        "runtime_seconds": profile.get("total_seconds"),
        "generations": profile.get("generations"),
        "evaluations": profile.get("evaluations"),
        "mean_objectives": None,
    }
    if len(F):
        means = F.mean(axis=0)
        out["mean_objectives"] = dict(zip(OBJECTIVE_NAMES, [-means[0], means[1], means[2], means[3]]))
        out.update(front_quality(F, lower_bound_reference(problem, X, F)))
    else:
        out.update({k: None for k in ("hypervolume", "hypervolume_ratio", "gd", "igd", "igd_plus", "spread", "spacing")})
    return _clean(out)


def summarise_runs(values: Optional[Sequence[float]]) -> Optional[dict]:
    """Median and inter-quartile range of a metric over runs (benchmarks)."""
    vals = np.array([v for v in (values or []) if v is not None and math.isfinite(v)], dtype=float)
    if not len(vals):
        return None
    q1, med, q3 = np.percentile(vals, [25, 50, 75])
    return {"median": float(med), "q1": float(q1), "q3": float(q3), "n": int(len(vals))}
