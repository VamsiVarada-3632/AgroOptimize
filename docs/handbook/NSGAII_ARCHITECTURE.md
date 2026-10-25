# NSGA-II Architecture

Every part of the AgroOptimize NSGA-II engine, traced function by function. Companion documents:
* [NSGAII_ANALYSIS.md](NSGAII_ANALYSIS.md): behaviour and weaknesses
* [NSGAII_PROFILE.md](NSGAII_PROFILE.md): where the time goes
* [NSGAII_RESEARCH_REVIEW.md](NSGAII_RESEARCH_REVIEW.md): literature
* [NSGAII_IMPROVEMENTS.md](NSGAII_IMPROVEMENTS.md): what changed and why
* [NSGAII_BENCHMARK_RESULTS.md](NSGAII_BENCHMARK_RESULTS.md): the evidence

Code lives in `app/optimization/`: `problem.py`, `nsga2_runner.py`, `operators.py`, `monitoring.py`, `metrics.py`, `engine_settings.py`, `parallel.py`. Selection mechanics come from pymoo 0.6.2 (`pymoo.algorithms.moo.nsga2`, `pymoo.core.*`, `pymoo.operators.survival.rank_and_crowding`).

## 1. Call graph

```
plan_service.run_pipeline(request)                                     app/services/plan_service.py
 ├─ preprocessing.get_region_season_profile → RegionSeasonProfile      app/data/preprocessing.py
 ├─ fuzzy.evaluate_uncertainty → UncertaintyAssessment                 app/fuzzy/engine.py
 ├─ FarmPlanProblem(profile, assessment, land, budget)                 problem.py
 ├─ run_nsga2(problem, pop_size, n_gen, seed, track_history, mode|engine)   nsga2_runner.py
 │    ├─ engine_settings(mode) → EngineSettings (switches from config)  engine_settings.py
 │    ├─ build operators: sampling, TournamentSelection(binary_tournament),
 │    │    crossover, mutation, AllocationRepair, CountingDuplicateElimination,
 │    │    [ChunkedThreadEvaluator]                                     operators.py, parallel.py
 │    ├─ termination: ("n_gen", n) | FrontStagnationTermination | DefaultMultiObjectiveTermination
 │    ├─ EngineMonitor (pymoo Callback)                                 monitoring.py
 │    └─ with _NSGA2_RUN_LOCK: np.random.seed(seed); pymoo.minimize(problem, NSGA2(...), termination, seed=seed)
 │         ├─ _initialize_infill: sampling.do → repair → duplicates → evaluator.eval
 │         ├─ _initialize_advance: RankAndCrowding.do (rank + crowding on generation 1)
 │         └─ per generation:
 │              _infill: Mating loop (infill.py) until pop_size unique offspring
 │                  TournamentSelection → crossover → mutation → repair → duplicate elimination
 │              evaluator.eval(offspring)                             (FarmPlanProblem._evaluate)
 │              _advance: Population.merge(parents, offspring) → RankAndCrowding.do (keep pop_size)
 │              _set_optimum: opt = rank-0 individuals (or least-violating if none feasible)
 │              termination.update → callback.notify (EngineMonitor)
 ├─ result.engine_report  (mode, switches, profile, diversity)          nsga2_runner._engine_report
 ├─ extract_convergence_history(result)  (saved runs)                   nsga2_runner.py
 ├─ extract_pareto_plans(result, problem) → FarmPlan list               nsga2_runner.py
 ├─ metrics.run_quality_metrics(result, problem) → meta.quality_metrics metrics.py
 └─ ranking.filter_plans → ranking.rank_plans (TOPSIS)                   app/decision/ranking.py
```

`run_pipeline` is the single entry point used by Run Optimization, saved runs, explanations, Scenario Simulation, District Intelligence (through `single_crop_metrics`), the dashboards and the comparison endpoints.

## 2. Problem definition — `FarmPlanProblem` (problem.py)

| Element | Definition |
|---|---|
| Decision variables | 3n real genes for n candidate crops (2–5 in the dataset): land shares `a_i ∈ [1e-4, 1]`, irrigation multipliers `m_i ∈ [0.7, 1.3]`, fertiliser multipliers `r_i ∈ [0.7, 1.3]` |
| Decoding | shares normalised to sum 1; `area_i = a_i / Σa × land` (`_evaluate`, `decode`) |
| f1 (min) | −Σ area_i × yield_i(t/ha) × fuzzy crop confidence_i |
| f2 (min) | Σ area_i × (r_i × fert cost/ha + pesticide/ha + labour days/ha × wage) |
| f3 (min) | Σ area_i × m_i × max(water req − effective rain, 0) × 10,000 L |
| f4 (min) | √(leaching × carbon); leaching = Σ area × r × N; carbon = Σ area × (r × NPK × 0.15 + m × water req × 0.01) |
| Constraint | g = f2 − budget ≤ 0, only when a budget is given (pymoo constrained domination) |
| Evaluation | fully vectorised over the population, one NumPy pass; per-crop constants precomputed in `__init__` |
| Other entry points | `single_crop_metrics()` (one crop, one hectare, multipliers 1.0; District Intelligence, smart seeds), `decode(x)` |

Property used by several components: yield does not depend on `m` or `r`, while f2–f4 increase with them. So a plan's copy with every multiplier at 0.7 is never worse (NSGAII_ANALYSIS.md §4.2).

## 3. Components

### 3.1 Initialisation
| Setting | Class | Behaviour |
|---|---|---|
| default | `pymoo FloatRandomSampling` | uniform in the bounds (pymoo `random_state`) |
| `lhs_initialization` | `pymoo LHS` | Latin Hypercube: one individual per stratum of each gene (maxmin criterion) |
| `smart_initialization` | `operators.SmartSampling(fraction, lhs)` | 20 % knowledge-based seeds (`seed_chromosomes`: dominant-crop plans; yield, yield/cost, yield/water-proportional and even allocations; multipliers at 0.7), the rest uniform or LHS |
| `constraint_aware_initialization` | `operators.BudgetAwareSampling(inner)` → `make_budget_feasible` | over-budget plans: fertiliser multipliers to 0.7, then the allocation is blended towards the cheapest crop with the exact weight that meets the budget |

pymoo then applies `AllocationRepair` and duplicate elimination, and evaluates the population.

### 3.2 Evaluation
`pymoo.core.evaluator.Evaluator` calls `problem.evaluate(X)` → `FarmPlanProblem._evaluate`, which sets F (4 objectives), G (budget) and, through pymoo, CV and FEAS. With `parallel_evaluation`, `parallel.ChunkedThreadEvaluator` splits X into chunks on a shared thread pool and joins them in order, so the values are identical.

### 3.3 Fast non-dominated sorting
`RankAndCrowding` (pymoo `operators/survival/rank_and_crowding/classes.py`) calls `NonDominatedSorting` (`fast_non_dominated_sort`, Deb et al. 2002, compiled) on the merged 2N population. Constrained domination: feasible solutions dominate infeasible ones, and infeasible ones are ordered by CV. Each individual gets `rank` (0 = first front).

### 3.4 Crowding distance
In the same survival step, `calc_crowding_distance` (`rank_and_crowding/metrics.py`) gives each front's boundary points ∞ and interior points the sum of normalised neighbour gaps per objective. It is computed on every front that is kept and on the front that is split.

### 3.5 Elitism and replacement
(μ + λ) survival: parents and offspring are merged (`GeneticAlgorithm._advance` → `Population.merge`), whole fronts fill the next population in rank order, and the last front is truncated by descending crowding distance. The best solutions are never lost.

### 3.6 Selection and tournament
`TournamentSelection(func_comp=operators.binary_tournament)` draws random pairs (pymoo `random_state`). `binary_tournament` is a vectorised copy of pymoo's `comp_by_dom_and_crowding` that makes identical decisions:
1. if either is infeasible, the lower CV wins;
2. otherwise Pareto dominance between the pair decides;
3. otherwise the larger crowding distance wins;
4. otherwise `random_state.choice([a, b])` decides.

It reads X, F, CV, rank and crowding through `operators.population_arrays` (one read per population object, cached in `algorithm.data`).

### 3.7 Crossover
`operators.SinglePointCrossover` (p 0.85 per mating, decided by pymoo's `random_state`): one cut in 1 … 3n−1 per mating (`np.random.randint`, global RNG), tails swapped (vectorised). `AdaptiveSinglePointCrossover` sets the probability each generation:
* `schedule="linear"`: 0.95 → 0.70 over the run;
* `schedule="diversity"`: 0.85 while allocation diversity is at its peak, rising to 0.95 as it falls to half the peak.

### 3.8 Mutation
`operators.GaussianMutation`: each gene with probability p (0.12; 0.05 base in enhanced mode) gets `N(0, 0.12 × range)`, then is clipped (`np.random`, global RNG).
* `AdaptiveGaussianMutation` reads p each generation from `algorithm.data["adaptive"]`, which `EngineMonitor` sets with `monitoring.adaptive_mutation_prob` (raised when diversity collapses, scaled down after hypervolume stagnation).
* With `duplicate_avoidance`, an offspring still identical to a parent gets one extra Gaussian step on a random gene.

### 3.9 Repair
`operators.AllocationRepair`: shares clipped at ≥ 0 and renormalised to sum 1, then every gene clipped to its bounds. It is applied after sampling and after every mating batch.

### 3.10 Duplicate elimination
`operators.CountingDuplicateElimination` is pymoo's exact-copy check (Euclidean distance ≤ 1e-16) against the batch itself, the parent population and the offspring found so far. It counts checked and rejected candidates, and caches X for the last few population objects (the parent population is checked once per batch). With `duplicate_removal`, `TolerantDuplicateElimination` uses a normalised tolerance (1e-4). The mating loop in `pymoo/core/infill.py` repeats until there are `pop_size` unique offspring (at most 100 rounds), so rejected copies are never evaluated but cost extra rounds.

### 3.11 Termination
| Setting | Class | Rule |
|---|---|---|
| default | `("n_gen", 200)` | fixed budget |
| `early_stopping`, criterion `hypervolume` | `monitoring.FrontStagnationTermination` | stop when the first-front hypervolume (`front_hypervolume`) rose by < 1e-4 (relative) in 30 generations, after generation 60 |
| `early_stopping`, criterion `objective_space` | `pymoo DefaultMultiObjectiveTermination` | stop when decision-space movement, CV and objective-space change (ideal, nadir, front) stay below xtol/cvtol/ftol for `period` generations |

### 3.12 Monitoring and reporting
`EngineMonitor.notify` runs after every generation. It is observation only, except for publishing the adaptive values. It records:
* the convergence history F;
* entropy, allocation diversity, mean crowding, front size, feasible share and duplicate ratio;
* the wall time per generation;
* the adaptive mutation probability and the diversity ratio.

`nsga2_runner._engine_report` builds `result.engine_report` (saved as `meta.optimizer`). `metrics.run_quality_metrics` builds `meta.quality_metrics` (API and saved runs).

## 4. Randomness and reproducibility

| Stream | Draws | Seeded by |
|---|---|---|
| pymoo `random_state` (NumPy Generator) | sampling, LHS, tournament pairs and ties, crossover yes/no, survival tie order, smart-seed blends | `minimize(..., seed=seed)` |
| NumPy global RNG | crossover cut points, mutation mask and noise, duplicate-avoidance steps | `np.random.seed(seed)` in `run_nsga2` |

Both are reseeded per run under `_NSGA2_RUN_LOCK`, so concurrent requests cannot interleave draws. Same inputs + seed → same front (tested). Bit-identical results hold on the same platform: an x86-64 Linux server and an arm64 Mac follow different trajectories because the C library's `log` and NumPy's fused multiply-add differ in the last bit (recorded during the Render deployment).

## 5. Configuration

All switches and parameters are in `app/config.py` (`NSGA2_ENGINE_MODE`, `NSGA2_ENGINE_FEATURES`, `NSGA2_ENGINE_MUTATION_PROB`, `NSGA2_ADAPTIVE_MUTATION`, `NSGA2_ADAPTIVE_CROSSOVER`, `NSGA2_SMART_INIT_FRACTION`, `NSGA2_DUPLICATE_TOLERANCE`, `NSGA2_EARLY_STOPPING`, `NSGA2_PARALLEL_WORKERS`), and are read into the frozen `EngineSettings` dataclass. `original` reproduces the published engine bit for bit. Any switch can be turned on for a single run: `run_nsga2(problem, engine=dataclasses.replace(engine_settings("original"), lhs_initialization=True))`.
