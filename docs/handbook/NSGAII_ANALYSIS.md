# NSGA-II Analysis

A study of the AgroOptimize NSGA-II engine as published: how it works, what it does well, where it falls short, and where it spends its time. Measurements come from `scripts/profile_nsga2.py` (phase profile) and `scripts/benchmark_nsga2.py` (quality study); see [NSGAII_PROFILE.md](NSGAII_PROFILE.md) for the numbers in full and [NSGAII_IMPROVEMENT_SUMMARY.md](NSGAII_IMPROVEMENT_SUMMARY.md) for what was changed.

## 1. Execution flow

```
plan_service.run_pipeline
  ├─ preprocessing.get_region_season_profile      (candidate crops, rainfall, storage, soil)
  ├─ fuzzy.evaluate_uncertainty                   (yield confidence, irrigation risk)
  ├─ FarmPlanProblem(profile, assessment, land, budget)
  ├─ nsga2_runner.run_nsga2(problem, pop 80, gen 200, seed 42)
  │     ├─ np.random.seed(seed) under _NSGA2_RUN_LOCK
  │     └─ pymoo minimize(NSGA2, ("n_gen", 200), seed=42)
  │           gen 1:  sampling → repair → duplicate elimination → evaluate → rank & crowding
  │           gen 2…200:
  │               binary tournament (×2 per mating) → single-point crossover (p 0.85)
  │               → Gaussian mutation (p 0.12 per gene) → repair → duplicate elimination
  │               (repeat until 80 unique offspring) → evaluate
  │               → merge parents + offspring (160) → non-dominated sort → crowding → keep 80
  ├─ extract_convergence_history (if the run is saved)
  ├─ extract_pareto_plans → feasible plans
  ├─ ranking.filter_plans → ranking.rank_plans (TOPSIS, top 50)
  └─ response / saved run → explanations, reports, history, comparison, simulation
```

Explanations, Scenario Simulation, District Intelligence, the dashboards and the comparison endpoints all call `run_nsga2` (directly or through `run_pipeline`), so any engine change reaches all of them.

## 2. Current implementation

| Component | Implementation | Notes |
|---|---|---|
| Chromosome | 3n real genes: n land shares, n irrigation multipliers, n fertiliser multipliers (n = 2–5 candidate crops by default, up to 12) | Shares ∈ [1e-4, 1], multipliers ∈ [0.7, 1.3] |
| Initialisation | pymoo `FloatRandomSampling`: uniform in the bounds, then repaired | Seeded through pymoo's `Generator` |
| Objectives | f1 = −yield, f2 = cost, f3 = irrigation water, f4 = √(leaching × carbon) | Vectorised over the population in `FarmPlanProblem._evaluate` |
| Constraint | budget: g = cost − budget ≤ 0 (only when a budget is given) | pymoo constraint domination |
| Repair | `AllocationRepair`: shares clipped ≥ 0, renormalised to 1; every gene clipped to its bounds | |
| Selection | pymoo binary tournament, `comp_by_dom_and_crowding`: lower constraint violation, then Pareto dominance between the two, then larger crowding distance; random on ties | Deb et al. use *rank* then crowding (crowded-comparison operator); comparing by dominance of the pair is pymoo's default and equivalent in effect when the whole population is one front (§4.1) |
| Crossover | `SinglePointCrossover`, applied per mating with p = 0.85; one cut in 1…3n−1, tails swapped | Matches the paper's operator |
| Mutation | `GaussianMutation`: each gene with p = 0.12, δ ~ N(0, 0.12 × range), clipped | Matches the paper's operator |
| Duplicates | pymoo `DefaultDuplicateElimination` (Euclidean distance ≤ 1e-16, i.e. exact copies), against the population and the other offspring; mating is repeated until 80 unique offspring exist | |
| Non-dominated sorting | pymoo `fast_non_dominated_sort` (Deb et al. 2002) | |
| Crowding distance | pymoo `calc_crowding_distance`, computed once on the splitting front | Standard NSGA-II |
| Elitism | (μ + λ): parents and offspring merged, best 80 by rank then crowding | Standard NSGA-II |
| Termination | fixed 200 generations | |
| Pareto set returned | pymoo `result.opt`: the first front of the final population | |
| Randomness | Two streams: pymoo's seeded `Generator` (sampling, crossover yes/no, tournament pairs and ties, survival tie order) and NumPy's global RNG (cut points, mutation), seeded per run under a lock | Same seed → same front (tested) |
| Convergence history | pymoo `save_history=True` deep-copied the whole algorithm every generation | Replaced by a monitor (§6) |

TOPSIS then ranks the feasible first front (see SCORING_AND_RANKING.md), and the explanation layer describes the ranked plans; neither changes the Pareto set.

## 3. Strengths

* **Faithful to the paper** — operators, probabilities and generation count are exactly those stated (Section III-D), and the code says so.
* **Reproducible** — fixed seeds, a run lock against concurrent reseeding (tested), deterministic decoding.
* **Vectorised objectives** — the whole population is evaluated in one NumPy pass (≈0.05 ms per generation of the actual arithmetic).
* **Standard survival** — fast non-dominated sorting, crowding distance and (μ + λ) elitism from pymoo, a well-tested implementation.
* **Feasibility first** — constraint domination handles the budget without penalty tuning.
* **Small problem** — 6–15 genes by default; a full run is ≈0.3 s.

## 4. Weaknesses

### 4.1 The whole population is non-dominated almost immediately
With four objectives, almost every pair of plans trades off at least one objective. Measured on three district-seasons: the first front holds the entire population from generation 4–8 onwards, and for 96–98 % of all generations every individual has rank 0. From then on, Pareto ranking exerts no selection pressure: tournaments are decided by crowding distance alone (the well-known loss of dominance pressure with ≥ 4 objectives; Purshouse & Fleming 2007, Ishibuchi et al. 2008). NSGA-III would address this but is out of scope; the improvements here work within NSGA-II.

### 4.2 The returned plans are not fully converged
In `FarmPlanProblem`, yield does not depend on the irrigation or fertiliser multipliers while cost, water and environmental impact increase with them. So for any land allocation, setting every multiplier to its lower bound (0.7) is never worse on any objective — the true Pareto set lies on that face (ALGORITHMS.md §3.2 notes the same property). Measured on the published engine (seed 42, 12 district-seasons, 960 returned plans): **every one of the 960 plans is strictly dominated by the same plan with its multipliers at 0.7**, which would save on average 0–3 % of cost, 0–18 % of water and up to 14 % of environmental impact. The cause is §4.1: a plan with multipliers of 0.85 is only dominated by a plan with almost the same allocation and lower multipliers, which rarely exists in the population, so nothing removes it; mutation then keeps pushing multipliers off the bound (half of all Gaussian steps from 0.7 go up, the other half are clipped back).

This is a statement about convergence under the model's own objectives, not about agronomy: the objectives contain no yield response to inputs, so the model always prefers the minimum dose. Whether recommending 0.7× doses is agronomically sensible is a modelling question (RESEARCH_REVIEW.md, FAO-33 yield response); changing the objectives was out of scope.

### 4.3 More generations do not help
With no external archive and crowding-only selection, the first front drifts rather than improves after the early generations: 400 generations give no better hypervolume or IGD+ than 200 on the benchmark (NSGAII_PROFILE.md §4). The fixed budget of 200 is therefore not a limiting factor, and running longer is not a remedy.

### 4.4 Duplicates and clipping
Exact duplicates are removed, but genes clipped to a bound make exact copies common in small problems: 2 % of offspring are rejected as duplicates in Salem Kharif (5 crops), 12 % in Erode Rabi (3 crops) and **31 %** in Coimbatore Summer (2 crops). Every rejection costs another round of selection, crossover, mutation and repair.

### 4.5 Operator design
* Single-point crossover on a block chromosome: two thirds of the cut points fall inside the multiplier blocks, so most crossovers exchange multiplier blocks rather than recombine allocations (ALGORITHMS.md §4.2).
* Gaussian σ = 0.12 of the range is large for fine tuning near the bound and fixed for the whole run.
* Mutation and crossover probabilities are fixed for the whole run (no parameter control).

### 4.6 Engineering
* `save_history=True` deep-copied the algorithm every generation: saved runs took 2.5× as long and held ≈58 MB at their peak (fixed, §6).
* The tournament and the single-point crossover were Python loops over the matings (fixed, bit-identical).
* Constant per-crop quantities were recomputed in every evaluation (fixed, bit-identical).
* pymoo stores everything per `Individual`; most of the remaining run time is pymoo reading and writing those objects (§5), not the optimisation itself.
* Two random streams and a global lock serialise concurrent optimisations. Moving the operators onto pymoo's `random_state` would remove the lock but change every published result, so it is left as future work.

## 5. Bottlenecks (published engine, Salem Kharif, pop 80 × 200)

| Phase | Time per run | Share |
|---|---|---|
| Duplicate elimination | 49 ms | 16 % |
| Tournament selection | 39 ms | 13 % |
| Objective evaluation (pymoo evaluator incl. the vectorised objectives) | 38 ms | 13 % |
| Single-point crossover | 21 ms | 7 % |
| Crowding distance | 11 ms | 4 % |
| Mutation | 8 ms | 3 % |
| Non-dominated sorting | 6 ms | 2 % |
| Repair | 4 ms | 1 % |
| pymoo bookkeeping (population objects, merging, termination) | ≈120 ms | ≈40 % |
| **Total without history** | **≈298 ms** | |
| History snapshots (`save_history`) | +≈450 ms | |
| **Total with history (saved runs)** | **≈748 ms**, peak ≈58 MB | |

Preprocessing (1.6 ms), fuzzy inference (cached, < 0.1 ms), decoding (0.4 ms) and TOPSIS (0.6 ms) are negligible.

## 6. What was changed (summary)

Two modes now exist, chosen in `app/config.py` (`NSGA2_ENGINE_MODE`, or the environment variable `AGROOPTIMIZE_NSGA2_MODE`):

* **Original (published, default)** — identical results, faster: vectorised crossover and tournament, cached problem constants, a lightweight history monitor instead of `save_history`, plus diversity monitoring and a runtime profile. Bit-identical to the engine before this work on 96 fingerprinted runs and three recorded digests (tests).
* **Enhanced (experimental)** — adds the improvements that passed the quality study. Each improvement is a separate switch.

Details, measurements and the accept/reject decision for each improvement are in [NSGAII_IMPROVEMENT_SUMMARY.md](NSGAII_IMPROVEMENT_SUMMARY.md).

## 7. Research opportunities

| Opportunity | Why | Status |
|---|---|---|
| Knowledge-based seeding of the initial population | §4.2: the optimum lies on a known face of the decision space; seeding is a recognised technique (Friedrich & Wagner 2015) | Implemented (enhanced) |
| Adaptive parameter control | Fixed p_m and p_c for the whole run (§4.5); Eiben et al. 1999 | Implemented and evaluated |
| Tolerance-based duplicate removal | §4.4 | Implemented and evaluated |
| Stagnation-based termination | §4.3 | Implemented and evaluated |
| External non-dominated archive (ε-dominance, Laumanns et al. 2002) | §4.3: keeps the best front found instead of the drifting last one | Future work |
| Density estimators designed for ≥ 4 objectives | §4.1 (Kukkonen & Deb 2006) | Future work |
| SBX + polynomial mutation, or block-aware crossover | §4.5 | Future work (changes the paper's operators) |
| Operators on pymoo's `random_state` | removes the run lock (§4.6) | Future work (changes all results) |
| Yield response to irrigation and fertiliser in f1 | §4.2: makes the multiplier genes meaningful | Future work (changes the objectives) |
| NSGA-III / MOEA/D and an ε-constraint LP baseline | RESEARCH_REVIEW.md R-8 | Future work |
