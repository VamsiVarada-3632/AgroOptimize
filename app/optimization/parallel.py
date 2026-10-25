"""
Parallel fitness evaluation for NSGA-II (engine switch parallel_evaluation).

FarmPlanProblem evaluates a whole population in one vectorised NumPy pass,
and each row's objectives depend only on that row. ChunkedThreadEvaluator
splits the population into `workers` chunks, evaluates them on a shared
thread pool (NumPy releases the GIL inside its array kernels) and joins the
results in the original order, so every objective value -- and therefore
every result -- is identical to the serial evaluation. No random numbers are
involved.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from pymoo.core.evaluator import Evaluator

_POOLS: dict = {}
_POOLS_LOCK = threading.Lock()


def _pool(workers: int) -> ThreadPoolExecutor:
    # One process-wide pool per size. Kept out of the evaluator itself, which
    # pymoo deep-copies together with the algorithm at the start of a run.
    with _POOLS_LOCK:
        if workers not in _POOLS:
            _POOLS[workers] = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="nsga2-eval")
        return _POOLS[workers]


class ChunkedThreadEvaluator(Evaluator):
    def __init__(self, workers: int = 4, **kwargs):
        super().__init__(**kwargs)
        self.workers = max(1, int(workers))

    def _eval(self, problem, pop, evaluate_values_of, **kwargs):
        X = pop.get("X")
        chunks = [idx for idx in np.array_split(np.arange(len(X)), min(self.workers, len(X))) if len(idx)]
        if len(chunks) <= 1:
            return super()._eval(problem, pop, evaluate_values_of, **kwargs)

        def evaluate(idx):
            return problem.evaluate(X[idx], return_values_of=evaluate_values_of, return_as_dictionary=True, **kwargs)

        parts = list(_pool(self.workers).map(evaluate, chunks))
        for key in parts[0]:
            values = [part[key] for part in parts]
            if values[0] is not None:
                pop.set(key, np.concatenate(values, axis=0))
        pop.apply(lambda ind: ind.evaluated.update(parts[0].keys()))
