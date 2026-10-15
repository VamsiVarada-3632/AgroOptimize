"""
Run monitoring for the NSGA-II engine: convergence history, diversity
statistics, runtime profile, the adaptive-mutation controller and the
early-stopping criterion.

Everything here except the two enhanced features (adaptive mutation, early
stopping) only *observes* the run -- no random numbers are drawn and no
individual is changed -- so the original engine with monitoring on produces
exactly the same Pareto front as without it.
"""

from __future__ import annotations

import time
from typing import List, Optional

import numpy as np
from pymoo.core.callback import Callback
from pymoo.core.termination import Termination
from pymoo.indicators.hv import HV

from app.optimization.operators import population_arrays

ENTROPY_BINS = 10
_HV_REF = np.full(4, 1.1)


def population_entropy(X: np.ndarray, xl: np.ndarray, xu: np.ndarray, bins: int = ENTROPY_BINS) -> float:
    """Mean Shannon entropy of the genes, each binned into `bins` equal
    intervals of its bounds and normalised by log(bins): 1 = genes spread
    evenly over their range, 0 = every individual has the same value."""
    span = np.where(xu - xl > 0, xu - xl, 1.0)
    n, n_var = X.shape
    idx = np.clip(((X - xl) / span * bins).astype(int), 0, bins - 1)
    # One bincount over all genes at once (gene j uses bins j*bins .. j*bins+bins-1).
    counts = np.bincount((idx + np.arange(n_var) * bins).ravel(), minlength=n_var * bins)
    p = counts[counts > 0] / n
    return float(-(p * np.log(p)).sum() / (n_var * np.log(bins)))


def allocation_diversity(X: np.ndarray, n_crops: int) -> float:
    """Mean standard deviation of the land-allocation genes (already in
    [0, 1]). Only the allocation genes carry the trade-off between plans:
    the multiplier genes are expected to converge to their lower bound (see
    operators.SmartSampling), so their loss of spread is convergence, not a
    diversity problem."""
    return float(X[:, :n_crops].std(axis=0).mean())


def mean_crowding(rank: np.ndarray, crowding: np.ndarray) -> Optional[float]:
    """Average finite crowding distance of the first front (boundary points
    have infinite distance and are left out, as is usual when reporting it)."""
    if rank is None or crowding is None or rank.dtype == object:
        return None
    cd = np.asarray(crowding[rank == 0], dtype=float)
    cd = cd[np.isfinite(cd)]
    return float(cd.mean()) if cd.size else None


def front_hypervolume(algorithm) -> float:
    """Hypervolume of the current first front, with objectives normalised by
    the range of the initial population (fixed for the whole run) and the
    reference point at 1.1 on every axis. Cached per generation, so the
    early-stopping test and the adaptive controller share one computation."""
    data = algorithm.data
    cache = data.get("_hv_cache")
    if cache is not None and cache[0] == algorithm.n_gen:
        return cache[1]
    if "_hv_bounds" not in data:
        F0 = algorithm.pop.get("F")
        lo, hi = F0.min(axis=0), F0.max(axis=0)
        data["_hv_bounds"] = (lo, np.where(hi - lo > 1e-12, hi - lo, 1.0))
    lo, span = data["_hv_bounds"]
    opt = algorithm.opt
    feasible = opt[np.ravel(opt.get("FEAS")).astype(bool)] if opt is not None else []
    value = 0.0
    if len(feasible):
        F = (feasible.get("F") - lo) / span
        value = float(HV(ref_point=_HV_REF[: F.shape[1]])(F))
    data["_hv_cache"] = (algorithm.n_gen, value)
    data.setdefault("front_hv", []).append(value)
    return value


def stagnated(algorithm, patience: int, tolerance: float) -> bool:
    """True when the first-front hypervolume rose by less than `tolerance`
    (relative to its value `patience` generations ago) over the last
    `patience` generations. Relative, because the hypervolume is normalised
    by the initial population and grows well above 1 as the front improves."""
    series = algorithm.data.get("front_hv", [])
    if len(series) <= patience:
        return False
    before = series[-1 - patience]
    return series[-1] - before < tolerance * max(abs(before), 1e-12)


def adaptive_mutation_prob(base: float, params: dict, diversity_ratio: float, is_stagnant: bool) -> float:
    """Diversity-guided mutation probability (Srinivas & Patnaik 1994;
    Ursem 2002): when allocation diversity falls below `diversity_floor` x its
    initial value the probability is raised in inverse proportion; once the
    front has stagnated it is scaled by `converged_scale` for fine tuning."""
    p = base
    floor = params["diversity_floor"]
    if diversity_ratio < floor:
        p = base * floor / max(diversity_ratio, 1e-9)
    if is_stagnant:
        p *= params["converged_scale"]
    return float(np.clip(p, params["min_prob"], params["max_prob"]))


class FrontStagnationTermination(Termination):
    """Early stopping: terminate when the first front's hypervolume has not
    improved by `tolerance` in `patience` generations (after `min_generations`),
    or at the generation budget, whichever comes first."""

    def __init__(self, n_max_gen: int, patience: int, tolerance: float, min_generations: int):
        super().__init__()
        self.n_max_gen = n_max_gen
        self.patience = int(patience)
        self.tolerance = float(tolerance)
        self.min_generations = int(min_generations)
        self.stopped_early_at: Optional[int] = None

    def _update(self, algorithm):
        front_hypervolume(algorithm)
        if (algorithm.n_gen >= self.min_generations and algorithm.n_gen < self.n_max_gen
                and stagnated(algorithm, self.patience, self.tolerance)):
            self.stopped_early_at = int(algorithm.n_gen)
            return 1.0
        return algorithm.n_gen / self.n_max_gen


class EngineMonitor(Callback):
    """Called by pymoo after every generation.

    * record_history     -- keeps each generation's objective matrix (what
                            extract_convergence_history needs) instead of
                            pymoo's save_history, which deep-copies the whole
                            algorithm every generation.
    * diversity          -- entropy, allocation diversity, mean crowding
                            distance, first-front size, duplicate ratio.
    * profiling          -- per-generation wall time.
    * adaptive_mutation  -- sets algorithm.data["adaptive"]["mutation_prob"]
                            for the next generation.
    """

    def __init__(self, record_history: bool = False, diversity: bool = True, profiling: bool = True,
                 adaptive_mutation: Optional[dict] = None, base_mutation_prob: float = 0.12,
                 stagnation: Optional[dict] = None):
        super().__init__()
        self.record_history = record_history
        self.diversity = diversity
        self.profiling = profiling
        self.adaptive_mutation = adaptive_mutation
        self.base_mutation_prob = base_mutation_prob
        self.stagnation = stagnation
        self.duplicate_counter = None  # the run's CountingDuplicateElimination, found in initialize()
        self.F_history: List[np.ndarray] = []
        self.generations: List[dict] = []
        self._t_last: Optional[float] = None
        self._dup_last = (0, 0)
        self._diversity0: Optional[float] = None

    def initialize(self, algorithm):
        self._t_last = time.perf_counter()
        # minimize() deep-copies the algorithm, so the counter is looked up on
        # the copy that actually runs rather than passed in.
        counter = getattr(algorithm, "eliminate_duplicates", None)
        if hasattr(counter, "rejected"):
            self.duplicate_counter = counter

    def notify(self, algorithm):
        pop = algorithm.pop
        arrays = population_arrays(algorithm, pop)
        if self.record_history:
            self.F_history.append(arrays["F"].copy())

        row: dict = {"generation": int(algorithm.n_gen)}
        now = time.perf_counter()
        if self.profiling:
            row["seconds"] = now - self._t_last
        self._t_last = now

        if self.diversity or self.adaptive_mutation is not None:
            X = arrays["X"]
            problem = algorithm.problem
            div = allocation_diversity(X, problem.n_crops)
            if self._diversity0 is None:
                self._diversity0 = div if div > 0 else 1.0
            row["allocation_diversity"] = div
            if self.diversity:
                row["entropy"] = population_entropy(X, problem.xl, problem.xu)
                row["mean_crowding"] = mean_crowding(arrays["rank"], arrays["crowding"])
                row["front_size"] = int(len(algorithm.opt)) if algorithm.opt is not None else 0
                if self.duplicate_counter is not None:
                    checked = self.duplicate_counter.checked - self._dup_last[0]
                    rejected = self.duplicate_counter.rejected - self._dup_last[1]
                    self._dup_last = (self.duplicate_counter.checked, self.duplicate_counter.rejected)
                    row["duplicate_ratio"] = rejected / checked if checked else 0.0

        if self.adaptive_mutation is not None:
            is_stagnant = False
            if self.stagnation is not None:
                front_hypervolume(algorithm)
                is_stagnant = stagnated(algorithm, self.stagnation["patience"], self.stagnation["tolerance"])
            prob = adaptive_mutation_prob(self.base_mutation_prob, self.adaptive_mutation,
                                          row["allocation_diversity"] / self._diversity0, is_stagnant)
            algorithm.data.setdefault("adaptive", {})["mutation_prob"] = prob
            row["mutation_prob"] = prob
        if "adaptive" in algorithm.data and "crossover_prob" in algorithm.data["adaptive"]:
            row["crossover_prob"] = algorithm.data["adaptive"]["crossover_prob"]
        if "front_hv" in algorithm.data:
            row["front_hypervolume"] = algorithm.data["front_hv"][-1]
        self.generations.append(row)

    def summary(self) -> dict:
        """Diversity statistics for the run report (first, last, minimum)."""
        rows = self.generations
        if not rows or not self.diversity:
            return {}
        out = {}
        for key in ("entropy", "allocation_diversity", "mean_crowding", "front_size"):
            values = [r[key] for r in rows if r.get(key) is not None]
            if values:
                out[key] = {"initial": _round(values[0]), "final": _round(values[-1]), "min": _round(min(values))}
        if self.duplicate_counter is not None and self.duplicate_counter.checked:
            out["duplicate_ratio"] = _round(self.duplicate_counter.rejected / self.duplicate_counter.checked)
            out["duplicates_rejected"] = int(self.duplicate_counter.rejected)
        return out


def _round(x):
    return round(float(x), 4) if isinstance(x, (float, np.floating)) else x
