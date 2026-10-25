"""
Custom NSGA-II genetic operators, implemented to match the reference paper
(Section III-D) literally rather than relying on pymoo's default SBX /
polynomial-mutation operators:

    "...evolved over 200 generations with single-point crossover with
    probability 0.85 and Gaussian mutation with probability 0.12."

Chromosome layout (length = 3 * n_crops), for n_crops candidate crops:

    [ alloc_0 .. alloc_{n-1} | irrigation_mult_0 .. irrigation_mult_{n-1} | fertilizer_mult_0 .. fertilizer_mult_{n-1} ]

  * alloc_i             - fraction of the farm's land given to crop i (repaired to sum to 1)
  * irrigation_mult_i   - multiplier on crop i's baseline water requirement
  * fertilizer_mult_i   - multiplier on crop i's baseline fertilizer dose
"""

from __future__ import annotations

import numpy as np
from pymoo.core.crossover import Crossover
from pymoo.core.duplicate import DefaultDuplicateElimination
from pymoo.core.mutation import Mutation
from pymoo.core.repair import Repair
from pymoo.core.sampling import Sampling
from pymoo.operators.sampling.lhs import LHS


class AllocationRepair(Repair):
    """Keeps the chromosome feasible after crossover/mutation:
    - the land-allocation genes are renormalised to sum to 1 (a farmer can't
      plant 140% of their land), preserving their relative ratios.
    - all genes are clipped back into the problem's [xl, xu] bounds.
    """

    def _do(self, problem, X, **kwargs):
        Xp = np.array(X, dtype=float, copy=True)
        n = problem.n_crops

        alloc = Xp[:, 0:n]
        alloc = np.clip(alloc, 0.0, None)
        row_sums = alloc.sum(axis=1, keepdims=True)
        degenerate = (row_sums <= 1e-9).flatten()
        if degenerate.any():
            alloc[degenerate] = 1.0 / n  # a row that collapsed to all-zero goes uniform
            row_sums = alloc.sum(axis=1, keepdims=True)
        alloc = alloc / row_sums
        Xp[:, 0:n] = alloc

        Xp = np.clip(Xp, problem.xl, problem.xu)
        return Xp


class SinglePointCrossover(Crossover):
    """Classic single-point crossover: pick one cut point along the
    chromosome and swap the tails between the two parents."""

    def __init__(self, prob: float = 0.85):
        super().__init__(2, 2, prob=prob)

    def _do(self, problem, X, **kwargs):
        _, n_matings, n_var = X.shape
        # Vectorised over matings. One randint call with size=n_matings draws
        # exactly the same cut points, in the same order, as the former loop
        # of scalar np.random.randint(1, n_var) calls (tested), so offspring
        # are bit-identical; the loop cost ~0.1 ms per generation.
        if n_var > 1:
            points = np.random.randint(1, n_var, size=n_matings)
        else:
            points = np.ones(n_matings, dtype=int)
        tail = np.arange(n_var)[None, :] >= points[:, None]  # (n_matings, n_var): True where genes swap
        parent1, parent2 = X[0], X[1]
        Y = np.empty_like(X)
        Y[0] = np.where(tail, parent2, parent1)
        Y[1] = np.where(tail, parent1, parent2)
        return Y


class GaussianMutation(Mutation):
    """Per-gene Gaussian perturbation applied independently with
    probability `prob` per gene, then clipped back to bounds."""

    def __init__(self, prob: float = 0.12, sigma: float = 0.12):
        super().__init__()
        self.gene_prob = prob
        self.sigma = sigma

    def _do(self, problem, X, **kwargs):
        Xp = np.array(X, dtype=float, copy=True)
        mask = np.random.random(Xp.shape) < self.gene_prob
        span = np.asarray(problem.xu) - np.asarray(problem.xl)
        noise = np.random.normal(0.0, self.sigma, Xp.shape) * span
        Xp[mask] += noise[mask]
        Xp = np.clip(Xp, problem.xl, problem.xu)
        return Xp


# ---------------------------------------------------------------------------
# Selection. pymoo's NSGA-II binary tournament (nsga2.binary_tournament)
# compares the pairs one at a time in Python. This version makes the same
# decisions with array operations and draws a random number only for ties,
# in the same order and through the same `random_state.choice([a, b])` call,
# so the selected parents -- and therefore every result -- are identical.
# ---------------------------------------------------------------------------

POPULATION_KEYS = ("X", "F", "CV", "rank", "crowding")


def population_arrays(algorithm, pop) -> dict:
    """X, F, CV, rank and crowding of `pop` as arrays, read once per
    population. pymoo stores them per individual, so each read loops over the
    population in Python; the monitor (after a generation) and the tournament
    (several times during the next one, when duplicates are rejected) share
    this one read. Keyed on the population object itself, which survival
    replaces every generation."""
    cached = algorithm.data.get("_population_arrays")
    if cached is None or cached[0] is not pop:
        cached = (pop, dict(zip(POPULATION_KEYS, pop.get(*POPULATION_KEYS))))
        algorithm.data["_population_arrays"] = cached
    return cached[1]


def binary_tournament(pop, P, algorithm, random_state=None, **kwargs):
    n_tournaments, n_parents = P.shape
    if n_parents != 2:
        raise ValueError("Only implemented for binary tournament!")
    if algorithm.tournament_type != "comp_by_dom_and_crowding":
        # Only the NSGA-II default is reimplemented; anything else is pymoo's.
        from pymoo.algorithms.moo.nsga2 import binary_tournament as pymoo_binary_tournament
        return pymoo_binary_tournament(pop, P, algorithm, random_state=random_state, **kwargs)

    a, b = P[:, 0], P[:, 1]
    arrays = population_arrays(algorithm, pop)
    CV, F, CD = arrays["CV"][:, 0], arrays["F"], arrays["crowding"].astype(float)
    a_cv, b_cv = CV[a], CV[b]

    S = np.full(n_tournaments, -1, dtype=int)
    tie = np.zeros(n_tournaments, dtype=bool)

    # At least one infeasible: smaller constraint violation wins.
    infeasible = (a_cv > 0.0) | (b_cv > 0.0)
    S[infeasible & (a_cv < b_cv)] = a[infeasible & (a_cv < b_cv)]
    S[infeasible & (a_cv > b_cv)] = b[infeasible & (a_cv > b_cv)]
    tie |= infeasible & (a_cv == b_cv)

    # Both feasible: Pareto dominance (Dominator.get_relation), then crowding.
    feasible = ~infeasible
    Fa, Fb = F[a], F[b]
    a_better = (Fa < Fb).any(axis=1)
    b_better = (Fb < Fa).any(axis=1)
    a_dom = feasible & a_better & ~b_better
    b_dom = feasible & b_better & ~a_better
    S[a_dom] = a[a_dom]
    S[b_dom] = b[b_dom]
    undecided = feasible & ~a_dom & ~b_dom
    cd_a, cd_b = CD[a], CD[b]
    S[undecided & (cd_a > cd_b)] = a[undecided & (cd_a > cd_b)]
    S[undecided & (cd_a < cd_b)] = b[undecided & (cd_a < cd_b)]
    tie |= undecided & ~(cd_a > cd_b) & ~(cd_a < cd_b)

    for i in np.flatnonzero(tie):  # same draws, same order as pymoo's loop
        S[i] = random_state.choice([a[i], b[i]])

    return S[:, None]


# ---------------------------------------------------------------------------
# Enhanced-mode operators (off in the original engine). Each is used only
# when its switch in EngineSettings is on. Adaptive state is read from
# `algorithm.data["adaptive"]`, which EngineMonitor (monitoring.py) updates
# after every generation, so the operators stay stateless and deterministic.
# ---------------------------------------------------------------------------

class AdaptiveSinglePointCrossover(SinglePointCrossover):
    """Single-point crossover whose probability is set every generation.

    schedule "linear" -- deterministic parameter control (Eiben, Hinterding &
        Michalewicz 1999): `start_prob` in the first generation, moving
        linearly to `end_prob` in the last.
    schedule "diversity" -- adaptive control from population diversity
        (Srinivas & Patnaik 1994; Ursem 2002): `high_diversity_prob` while the
        allocation diversity is at its peak so far, moving linearly to
        `low_diversity_prob` as it falls to `diversity_floor` x that peak.
        The ratio is published by EngineMonitor in algorithm.data["adaptive"].
    """

    def __init__(self, start_prob: float, end_prob: float, schedule: str = "linear",
                 high_diversity_prob: float = 0.85, low_diversity_prob: float = 0.95,
                 diversity_floor: float = 0.5):
        super().__init__(prob=start_prob if schedule == "linear" else high_diversity_prob)
        if schedule not in ("linear", "diversity"):
            raise ValueError(f"Unknown crossover schedule {schedule!r}")
        self.schedule = schedule
        self.start_prob = float(start_prob)
        self.end_prob = float(end_prob)
        self.high_diversity_prob = float(high_diversity_prob)
        self.low_diversity_prob = float(low_diversity_prob)
        self.diversity_floor = float(diversity_floor)

    def do(self, problem, pop, parents=None, *args, **kwargs):
        algorithm = kwargs.get("algorithm")
        if algorithm is not None:
            adaptive = algorithm.data.setdefault("adaptive", {})
            if self.schedule == "linear":
                self.prob = self.start_prob + (self.end_prob - self.start_prob) * _progress(algorithm)
            else:
                ratio = adaptive.get("diversity_ratio", 1.0)
                level = float(np.clip((ratio - self.diversity_floor) / (1.0 - self.diversity_floor), 0.0, 1.0))
                self.prob = self.low_diversity_prob + (self.high_diversity_prob - self.low_diversity_prob) * level
            adaptive["crossover_prob"] = self.prob
        return super().do(problem, pop, parents, *args, **kwargs)


class AdaptiveGaussianMutation(GaussianMutation):
    """Gaussian mutation whose per-gene probability is set each generation by
    EngineMonitor from population diversity (higher when diversity collapses,
    lower once the front has stagnated); see monitoring.adaptive_mutation_prob."""

    def _do(self, problem, X, **kwargs):
        algorithm = kwargs.get("algorithm")
        if algorithm is not None:
            self.gene_prob = algorithm.data.get("adaptive", {}).get("mutation_prob", self.gene_prob)
        return super()._do(problem, X, **kwargs)


def _progress(algorithm) -> float:
    """Position in the offspring generations, 0 at the first and 1 at the
    last. Generation 1 is the initial population, so offspring are created
    while n_gen runs from 2 to n_max_gen."""
    n_max = getattr(algorithm.termination, "n_max_gen", None)
    if n_max is None:
        for term in getattr(algorithm.termination, "terminations", ()):
            n_max = getattr(term, "n_max_gen", n_max)
    if not n_max or n_max <= 2:
        return 0.0
    return float(np.clip((algorithm.n_gen - 2) / (n_max - 2), 0.0, 1.0))


class SmartSampling(Sampling):
    """Initial population partly seeded from the district's data.

    A share `fraction` of the individuals are built from the candidate crops,
    which the preprocessing stage already selected from the district's
    historical records:
      * one plan per crop with most of the land on that crop (the historical
        single-crop practice the farmer is likely to know),
      * land in proportion to the fuzzy-adjusted historical yield, to yield
        per rupee and yield per litre of irrigation, and an even split.
    Their irrigation and fertiliser multipliers are set to the lower bound:
    in FarmPlanProblem yield does not depend on the multipliers while cost,
    water and environmental impact rise with them, so for any allocation the
    lower bound is never worse on any objective (existing optimisation
    knowledge about these objectives, not a new agronomic assumption).
    If more seeds are requested than these, the rest are random blends of
    them. All remaining individuals are uniform random, as in the original
    engine, or a Latin Hypercube sample when `lhs` is set. Seeding is the
    "seeding the initial population" technique of Friedrich & Wagner (2015).
    """

    def __init__(self, fraction: float, lhs: bool = False):
        super().__init__()
        self.fraction = float(fraction)
        self.lhs = bool(lhs)

    def _do(self, problem, n_samples, *args, random_state=None, **kwargs):
        n_seed = int(round(self.fraction * n_samples))
        seeds = seed_chromosomes(problem)
        if n_seed > len(seeds):
            k = n_seed - len(seeds)
            i = random_state.integers(0, len(seeds), size=k)
            j = random_state.integers(0, len(seeds), size=k)
            w = random_state.random((k, 1))
            seeds = np.vstack([seeds, w * seeds[i] + (1 - w) * seeds[j]])
        seeds = seeds[:n_seed]
        n_rand = n_samples - len(seeds)
        if self.lhs and n_rand > 1:
            rand = LHS()._do(problem, n_rand, random_state=random_state)
        else:
            xl, xu = problem.bounds()
            rand = xl + (xu - xl) * random_state.random((n_rand, problem.n_var))
        return np.vstack([seeds, rand])


class BudgetAwareSampling(Sampling):
    """Constraint-aware initialisation for budget problems: the plans drawn
    by `inner` that exceed the budget are moved just inside it (see
    make_budget_feasible); all others are kept as drawn."""

    def __init__(self, inner: Sampling):
        super().__init__()
        self.inner = inner

    def _do(self, problem, n_samples, *args, **kwargs):
        X = self.inner._do(problem, n_samples, *args, **kwargs)
        return make_budget_feasible(problem, X)


def make_budget_feasible(problem, X: np.ndarray) -> np.ndarray:
    """Repair of over-budget plans before the first evaluation (a standard
    repair-based constraint-handling initialisation; Coello Coello 2002):

    1. their fertiliser multipliers go to the lower bound (in this model cost
       depends on the inputs only through fertiliser), then
    2. if still over budget, their land allocation is blended towards the
       cheapest single-crop plan, a' = (1 - w) a + w e_cheapest, with the
       smallest w that meets the budget. Cost is linear in w for fixed
       multipliers, so w is solved exactly rather than searched.

    Deterministic (no random numbers). Nothing changes when there is no
    budget, or when even the cheapest plan exceeds it (no feasible point to
    move towards)."""
    budget = getattr(problem, "budget_rs", None)
    if not budget:
        return X
    n = problem.n_crops
    xl = np.asarray(problem.xl, dtype=float)
    X = np.array(X, dtype=float, copy=True)

    def cost(Y):
        return problem.evaluate(Y, return_as_dictionary=True)["F"][:, 1]

    cheapest = np.tile(xl, (n, 1))
    cheapest[:, :n] = np.where(np.eye(n, dtype=bool), 1.0, xl[:n])
    single = cost(cheapest)
    c = int(np.argmin(single))
    if single[c] > budget:
        return X

    over = cost(X) > budget
    X[over, 2 * n:] = xl[2 * n:]
    still = np.flatnonzero(cost(X) > budget)
    if len(still):
        alloc = X[still, :n] / X[still, :n].sum(axis=1, keepdims=True)
        target = np.where(np.arange(n) == c, 1.0, 0.0)
        c0 = cost(X[still])
        Y = X[still].copy()
        Y[:, :n] = np.clip(target, xl[:n], None)
        c1 = cost(Y)
        w = np.clip((c0 - budget) / np.where(c0 - c1 > 0, c0 - c1, np.inf) * (1 + 1e-6) + 1e-9, 0.0, 1.0)
        X[still, :n] = np.clip((1 - w)[:, None] * alloc + w[:, None] * target, xl[:n], None)
    return X


def seed_chromosomes(problem) -> np.ndarray:
    """Knowledge-based chromosomes for SmartSampling (see its docstring)."""
    n = problem.n_crops
    cv = problem.crop_vec
    xl = np.asarray(problem.xl, dtype=float)

    yield_t_ha = cv.yield_kg_ha / 1000.0 * cv.crop_yield_confidence
    metrics = problem.single_crop_metrics()  # per-hectare objectives at baseline inputs
    cost = np.array([m["cost_rs_ha"] for m in metrics])
    water = np.array([m["water_l_ha"] for m in metrics])

    def share(weights):
        weights = np.clip(np.nan_to_num(weights, nan=0.0, posinf=0.0), 0.0, None)
        return weights / weights.sum() if weights.sum() > 0 else np.full(n, 1.0 / n)

    allocations = [np.where(np.arange(n) == i, 1.0, 0.0) for i in range(n)]
    allocations += [
        share(yield_t_ha),
        share(yield_t_ha / np.where(cost > 0, cost, np.inf)),
        share(yield_t_ha / np.where(water > 0, water, np.inf)),
        np.full(n, 1.0 / n),
    ]
    X = np.tile(xl, (len(allocations), 1))
    X[:, :n] = np.clip(np.array(allocations), xl[:n], None)
    return X


class TolerantDuplicateElimination(DefaultDuplicateElimination):
    """Treats two chromosomes as duplicates when their distance in the
    decision space, normalised to [0, 1] per gene, is at most `tolerance`
    (pymoo's default only removes exact copies)."""

    def __init__(self, tolerance: float, xl, xu):
        span = np.asarray(xu, dtype=float) - np.asarray(xl, dtype=float)
        self._xl = np.asarray(xl, dtype=float)
        self._span = np.where(span > 0, span, 1.0)
        super().__init__(epsilon=tolerance, func=self._normalised)

    def _normalised(self, pop):
        return (pop.get("X") - self._xl) / self._span


class CountingDuplicateElimination(DefaultDuplicateElimination):
    """pymoo's default duplicate elimination, unchanged, that also counts how
    many candidates it rejects (for diversity monitoring)."""

    def __init__(self, inner=None):
        super().__init__(func=self._decision_vectors)
        self.inner = inner
        self.checked = 0
        self.rejected = 0
        self._recent = []  # (population, X) of the last few populations read

    def _decision_vectors(self, pop):
        """pop.get("X"), remembered for the last few population objects. The
        mating loop checks every batch of offspring against the same parent
        population, so its X was read again on each of the ~2-3 batches per
        generation. Keyed on the object itself (held, so it cannot be reused)."""
        for obj, X in self._recent:
            if obj is pop:
                return X
        X = pop.get("X")
        self._recent = [(pop, X)] + self._recent[:3]
        return X

    def do(self, pop, *args, **kwargs):
        out = self.inner.do(pop, *args, **kwargs) if self.inner is not None else super().do(pop, *args, **kwargs)
        kept = out[0] if isinstance(out, tuple) else out
        self.checked += len(pop)
        self.rejected += len(pop) - len(kept)
        return out
