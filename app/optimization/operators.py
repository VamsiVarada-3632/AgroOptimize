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
from pymoo.core.mutation import Mutation
from pymoo.core.repair import Repair


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
        Y = np.empty_like(X)
        for k in range(n_matings):
            parent1, parent2 = X[0, k], X[1, k]
            point = np.random.randint(1, n_var) if n_var > 1 else 1
            child1 = np.concatenate([parent1[:point], parent2[point:]])
            child2 = np.concatenate([parent2[:point], parent1[point:]])
            Y[0, k], Y[1, k] = child1, child2
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
