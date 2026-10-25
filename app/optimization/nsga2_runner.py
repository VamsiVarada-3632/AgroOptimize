"""
Runs NSGA-II (Deb et al., 2002) over a FarmPlanProblem and decodes the
resulting Pareto front into plain farm-plan dictionaries.

NSGA-II retains only non-dominated solutions at each generation and uses
crowding distance to preserve diversity along the Pareto front (reference
paper, Section III-D) -- both behaviours are pymoo's NSGA2 defaults, so we
lean on the library for the selection/survival mechanics and supply our own
crossover/mutation/repair operators to match the paper's stated parameters.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.indicators.hv import HV
from pymoo.operators.sampling.lhs import LHS
from pymoo.operators.sampling.rnd import FloatRandomSampling
from pymoo.operators.selection.tournament import TournamentSelection
from pymoo.optimize import minimize
from pymoo.termination.default import DefaultMultiObjectiveTermination

from app import config
from app.data.preprocessing import RegionSeasonProfile
from app.fuzzy.engine import UncertaintyAssessment
from app.optimization.engine_settings import EngineSettings, engine_settings
from app.optimization.monitoring import EngineMonitor, FrontStagnationTermination
from app.optimization.operators import (
    AdaptiveGaussianMutation,
    AdaptiveSinglePointCrossover,
    AllocationRepair,
    BudgetAwareSampling,
    CountingDuplicateElimination,
    GaussianMutation,
    SinglePointCrossover,
    SmartSampling,
    TolerantDuplicateElimination,
    binary_tournament,
)
from app.optimization.problem import FarmPlanProblem

logger = logging.getLogger(__name__)

# The custom operators draw from NumPy's *process-global* RNG, which
# run_nsga2 reseeds before every run. FastAPI executes sync endpoints in a
# thread pool, so two overlapping requests could otherwise reseed / consume
# the same global RNG mid-run -- silently breaking the "same inputs + seed
# -> same Pareto front" guarantee. Serialising runs keeps every result
# bit-identical to a single-threaded run (each run takes well under a
# second, so the lock costs little in practice).
_NSGA2_RUN_LOCK = threading.Lock()


@dataclass
class FarmPlan:
    crop_names: List[str]
    allocation_fraction: List[float]
    area_ha: List[float]
    irrigation_multiplier: List[float]
    fertilizer_multiplier: List[float]
    yield_tonnes: float
    cost_rs: float
    water_liters: float
    env_impact_score: float
    feasible: bool


def run_nsga2(
    problem: FarmPlanProblem,
    pop_size: Optional[int] = None,
    n_gen: Optional[int] = None,
    crossover_prob: float = config.NSGA2_CROSSOVER_PROB,
    mutation_prob: Optional[float] = None,
    mutation_sigma: float = config.NSGA2_MUTATION_SIGMA,
    seed: int = config.NSGA2_SEED,
    verbose: bool = False,
    track_history: bool = False,
    mode: Optional[str] = None,
    engine: Optional[EngineSettings] = None,
):
    """Run NSGA-II. Set `track_history=True` to record the population's
    objectives at every generation (needed for convergence plots / the
    hypervolume trend in `extract_convergence_history`).

    `mutation_prob` defaults to the engine mode's base probability.
    `mode` selects the engine ("original" = published behaviour, the default
    from config.NSGA2_ENGINE_MODE; "enhanced" = experimental); `engine`
    passes explicit EngineSettings instead, e.g. one feature switched on for
    an ablation run. The returned result carries `result.engine_report`
    (mode, features, runtime profile, diversity statistics).
    """
    pop_size = pop_size or config.NSGA2_POP_SIZE
    n_gen = n_gen or config.NSGA2_N_GEN
    settings = engine if engine is not None else engine_settings(mode)
    # An explicit argument wins; otherwise the mode's base probability
    # (0.12, the paper's value, in the original engine).
    if mutation_prob is None:
        mutation_prob = settings.mutation_prob

    # Duplicate elimination: pymoo's exact-copy check in the original engine,
    # optionally a tolerance-based one; both wrapped in a counter that only
    # records how many offspring were rejected.
    if settings.duplicate_removal:
        inner = TolerantDuplicateElimination(settings.duplicate_tolerance, problem.xl, problem.xu)
        eliminate_duplicates = CountingDuplicateElimination(inner)
    else:
        eliminate_duplicates = CountingDuplicateElimination()

    if settings.smart_initialization:
        sampling = SmartSampling(settings.smart_init_fraction, lhs=settings.lhs_initialization)
    elif settings.lhs_initialization:
        # Latin Hypercube sampling (McKay, Beckman & Conover 1979): each gene's
        # range is split into pop_size strata and every stratum gets one
        # individual, so the first population covers the space evenly.
        sampling = LHS()
    else:
        sampling = FloatRandomSampling()
    if settings.constraint_aware_initialization:
        sampling = BudgetAwareSampling(sampling)

    if settings.adaptive_crossover:
        p = settings.adaptive_crossover_params
        crossover = AdaptiveSinglePointCrossover(
            p["start_prob"], p["end_prob"], schedule=p.get("schedule", "linear"),
            high_diversity_prob=p.get("high_diversity_prob", 0.85), low_diversity_prob=p.get("low_diversity_prob", 0.95),
            diversity_floor=p.get("diversity_floor", 0.5))
    else:
        crossover = SinglePointCrossover(prob=crossover_prob)

    mutation_cls = AdaptiveGaussianMutation if settings.adaptive_mutation else GaussianMutation
    mutation = mutation_cls(prob=mutation_prob, sigma=mutation_sigma, avoid_duplicates=settings.duplicate_avoidance)

    algorithm = NSGA2(
        pop_size=pop_size,
        sampling=sampling,
        # Same binary tournament as pymoo's NSGA-II default, vectorised.
        selection=TournamentSelection(func_comp=binary_tournament),
        crossover=crossover,
        mutation=mutation,
        repair=AllocationRepair(),
        eliminate_duplicates=eliminate_duplicates,
    )

    if settings.early_stopping:
        p = settings.early_stopping_params
        criterion = p.get("criterion", "hypervolume")
        if criterion == "hypervolume":
            termination = FrontStagnationTermination(n_gen, p["patience"], p["tolerance"], p["min_generations"])
        elif criterion == "objective_space":
            termination = DefaultMultiObjectiveTermination(
                xtol=p.get("xtol", 0.0005), cvtol=1e-8, ftol=p.get("ftol", 0.005),
                period=int(p.get("period", 50)), n_skip=int(p.get("n_skip", 5)), n_max_gen=n_gen)
        else:
            raise ValueError(f"Unknown early-stopping criterion {criterion!r}")
    else:
        termination = ("n_gen", n_gen)

    monitor = EngineMonitor(
        record_history=track_history,
        diversity=settings.diversity_monitoring,
        profiling=settings.runtime_profiling,
        adaptive_mutation=settings.adaptive_mutation_params if settings.adaptive_mutation else None,
        base_mutation_prob=mutation_prob,
        stagnation=settings.early_stopping_params if settings.adaptive_mutation else None,
        share_diversity=settings.adaptive_crossover and settings.adaptive_crossover_params.get("schedule") == "diversity",
    )

    with _NSGA2_RUN_LOCK:
        # Our custom operators (operators.py) draw from the plain numpy global
        # RNG (np.random.*), not from whatever internal RNG object pymoo wires
        # up for `seed=`. Seed it explicitly here so a given (problem, seed)
        # pair is fully reproducible end to end, independent of call history
        # elsewhere in the process.
        np.random.seed(seed)
        t0 = time.perf_counter()
        result = minimize(
            problem,
            algorithm,
            termination,
            seed=seed,
            verbose=verbose,
            # The monitor records each generation's objectives itself, so
            # pymoo's save_history (a deep copy of the whole algorithm every
            # generation: ~2.5x the run time, ~58 MB) is no longer needed.
            callback=monitor,
        )
        seconds = time.perf_counter() - t0

    result.engine_report = _engine_report(settings, result, monitor, seconds, pop_size, n_gen, seed)
    if settings.runtime_profiling:
        prof = result.engine_report["profile"]
        logger.info(
            "NSGA-II %s: %d generations, %d evaluations, Pareto size %d, %.3f s (%.2f ms/generation)",
            settings.mode, prof["generations"], prof["evaluations"], prof["pareto_size"],
            prof["total_seconds"], prof["avg_generation_ms"],
        )
    return result


def _engine_report(settings: EngineSettings, result, monitor: EngineMonitor, seconds: float,
                   pop_size: int, n_gen: int, seed: int) -> dict:
    """What a run records about its engine: mode and switches, runtime
    profile and diversity statistics (kept in the run's meta for reports)."""
    algorithm = result.algorithm
    generations = len(monitor.generations)
    report = {"engine": settings.describe(), "seed": seed, "pop_size": pop_size, "n_gen_budget": n_gen}
    if settings.runtime_profiling:
        report["profile"] = {
            "total_seconds": round(seconds, 4),
            "generations": generations,
            "evaluations": int(algorithm.evaluator.n_eval),
            "pareto_size": int(len(result.X)) if result.X is not None else 0,
            "avg_generation_ms": round(1000 * seconds / generations, 3) if generations else None,
        }
    if settings.early_stopping:
        stopped = getattr(algorithm.termination, "stopped_early_at", None)
        if stopped is None and generations < n_gen:
            stopped = generations   # pymoo's objective-space criterion: generations completed
        report["stopped_early_at"] = stopped
    if settings.duplicate_avoidance:
        report["copies_perturbed"] = int(getattr(algorithm.mating.mutation, "forced", 0))
    if settings.diversity_monitoring:
        report["diversity"] = monitor.summary()
    return report


def run_nsga2_with_fuzzy_toggle(
    profile: RegionSeasonProfile,
    assessment: UncertaintyAssessment,
    total_land_ha: float,
    budget_rs: Optional[float] = None,
    use_fuzzy: bool = True,
    **run_kwargs,
):
    """Convenience entry point for the Task 4 fuzzy-vs-non-fuzzy comparison
    study: builds a FarmPlanProblem with `use_fuzzy` applied (see
    CropVector.from_candidates / FarmPlanProblem in app/optimization/
    problem.py -- that's where the actual fuzzy-bypass logic lives) and
    runs it through the normal `run_nsga2`. `use_fuzzy=True` reproduces the
    exact behaviour every other caller (plan_service, dashboard_service)
    already gets; `use_fuzzy=False` is the non-fuzzy baseline, where every
    crop's yield confidence is trusted at 1.0 instead of being adjusted by
    the Mamdani rule base. Any extra `run_kwargs` (pop_size, n_gen, seed,
    etc.) pass straight through to `run_nsga2`.
    """
    problem = FarmPlanProblem(
        profile=profile,
        assessment=assessment,
        total_land_ha=total_land_ha,
        budget_rs=budget_rs,
        use_fuzzy=use_fuzzy,
    )
    result = run_nsga2(problem, **run_kwargs)
    return problem, result


def extract_convergence_history(result) -> List[dict]:
    """Per-generation convergence statistics, requires `run_nsga2(...,
    track_history=True)`. Returns [] if history wasn't tracked.

    For each generation: the best (min) and mean of every raw objective
    across that generation's surviving population, plus a normalised
    hypervolume indicator (Zitzler & Thiele, 1999) -- the standard
    MOEA convergence metric, tracking how much of the (normalised)
    objective space the current front dominates relative to a fixed
    reference point. A rising, plateauing hypervolume curve is the
    textbook signature of NSGA-II converging.
    """
    F_history = _objective_history(result)
    if not F_history:
        return []

    all_F = np.vstack(F_history)
    lo = all_F.min(axis=0)
    hi = all_F.max(axis=0)
    span = np.where(hi - lo < 1e-9, 1.0, hi - lo)
    # Fixed reference point in normalised space, slightly worse than the
    # worst value seen in any generation on every objective (required by
    # the hypervolume definition -- larger normalised F is worse here
    # since every objective is a "minimise" in FarmPlanProblem).
    hv_indicator = HV(ref_point=np.array([1.1, 1.1, 1.1, 1.1]))

    history: List[dict] = []
    for gen_idx, F in enumerate(F_history, start=1):
        F_norm = np.clip((F - lo) / span, 0.0, 1.5)
        history.append(
            {
                "generation": gen_idx,
                "population_size": int(F.shape[0]),
                "best_yield_tonnes": round(float(-F[:, 0].min()), 3),
                "mean_yield_tonnes": round(float(-F[:, 0].mean()), 3),
                "best_cost_rs": round(float(F[:, 1].min()), 2),
                "mean_cost_rs": round(float(F[:, 1].mean()), 2),
                "best_water_liters": round(float(F[:, 2].min()), 1),
                "mean_water_liters": round(float(F[:, 2].mean()), 1),
                "best_env_impact": round(float(F[:, 3].min()), 3),
                "mean_env_impact": round(float(F[:, 3].mean()), 3),
                "hypervolume": round(float(hv_indicator(F_norm)), 4),
            }
        )
    return history


def _objective_history(result) -> List[np.ndarray]:
    """Each generation's population objectives: from the EngineMonitor when
    the run recorded them, else from pymoo's own history (a result produced
    with save_history=True); empty if neither was kept."""
    monitor = getattr(getattr(result, "algorithm", None), "callback", None)
    if isinstance(monitor, EngineMonitor) and monitor.F_history:
        return monitor.F_history
    if getattr(result, "history", None):
        return [snapshot.pop.get("F") for snapshot in result.history]
    return []


def extract_pareto_plans(result, problem: FarmPlanProblem) -> List[FarmPlan]:
    """Decode every non-dominated solution pymoo found into a FarmPlan."""
    if result.X is None or len(result.X) == 0:
        return []

    X = np.atleast_2d(result.X)
    F = np.atleast_2d(result.F)
    G = np.atleast_2d(result.G) if result.G is not None else None

    plans: List[FarmPlan] = []
    for i in range(X.shape[0]):
        decoded = problem.decode(X[i])
        f1, f2, f3, f4 = F[i]
        feasible = True
        if G is not None:
            feasible = bool(np.all(G[i] <= 1e-6))
        plans.append(
            FarmPlan(
                crop_names=decoded["crop_names"],
                allocation_fraction=decoded["allocation_fraction"],
                area_ha=decoded["area_ha"],
                irrigation_multiplier=decoded["irrigation_multiplier"],
                fertilizer_multiplier=decoded["fertilizer_multiplier"],
                yield_tonnes=round(float(-f1), 3),
                cost_rs=round(float(f2), 2),
                water_liters=round(float(f3), 1),
                env_impact_score=round(float(f4), 3),
                feasible=feasible,
            )
        )
    return plans
