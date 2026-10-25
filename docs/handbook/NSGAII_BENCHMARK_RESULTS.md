# NSGA-II Benchmark Results

Evidence for every engine change in [NSGAII_IMPROVEMENTS.md](NSGAII_IMPROVEMENTS.md). Produced with:
* `scripts/benchmark_nsga2.py`: quality and ablation study
* `scripts/benchmark_tight_budget.py`: constraint study
* `scripts/report_nsga2_benchmark.py`: charts and tables
* `scripts/profile_nsga2.py`: phase profile

Raw summaries are in [`benchmarks/`](benchmarks/).

## 1. Methodology

| Item | Setting |
|---|---|
| Problems | 16: the 12 district × season profiles (5 ha, no budget) and the Kharif profile of each district with a budget of 5 ha × the median single-crop cost |
| Seeds | evaluation seeds 0–9 (PR #12 tuned its parameters on seeds 100–104; the new switches have no tuned parameters) |
| Budget | population 80, 200 generations, 16,000 evaluations per run, for every variant |
| Pairing | each variant is compared with its baseline engine on the same problem and seed; Wilcoxon signed-rank test (Derrac et al. 2011) |
| Reference front | per problem: non-dominated union of every front of every variant and seed, plus each solution's copy with irrigation and fertiliser multipliers at 0.7 (never worse in this model) |
| Normalisation | objectives scaled by the reference front's ideal and nadir; hypervolume reference point 1.1 |
| Indicators | hypervolume (HV ↑), generational distance (GD ↓), inverted generational distance (IGD ↓), IGD+ (↓), generalised spread (↓), spacing (↓), front size, final-population constraint satisfaction, duplicates rejected, generations to 99 % of the original engine's median final HV, evaluations, wall time, peak traced memory (tracemalloc, 4 problems, seed 0) |
| Machine | Apple M-series laptop, Python 3.13, NumPy 2.3.5, pymoo 0.6.2; convergence history tracked in the study (as for saved runs) |
| Runs | ablation study: 14 variants × 160 = 2,240 runs; final comparison: 3 × 160; tight-budget study: 4 engines × 80 |

"Better/worse" counts paired runs; for time, "better" means faster. Run times differ between study sessions (laptop load), so compare times within one table, where all variants ran in the same session.

## 2. Final result: original vs enhanced

| Engine | HV | GD | IGD | IGD+ | Spread | Spacing | Dup. rejected | Gen. to 99 % | Evals | Time (s) | Peak MB |
|---|---|---|---|---|---|---|---|---|---|---|---|
| original (published, default) | 0.4431 | 0.3277 | 0.0660 | 0.0392 | 0.547 | 0.093 | 738 | 55 | 16,000 | 0.336 | 1.17 |
| enhanced (PR #12) | 0.4608 | 0.1565 | 0.0434 | 0.0238 | 0.549 | 0.071 | 8,022 | 10 | 15,999 | 0.513 | 1.17 |
| **enhanced (this work)** | **0.4643** | 0.1655 | 0.0450 | 0.0247 | **0.509** | 0.071 | **140** | **10** | 15,999 | **0.300** | 1.21 |

Medians of 160 runs. Front size 80 and constraint satisfaction 1.00 for all.

| Comparison | HV | GD | IGD+ | Spread | Time |
|---|---|---|---|---|---|
| enhanced (this work) vs original | 150/10 (p 3e-26) | 154/6 (p 3e-27) | 152/8 (p 3e-26) | 92/68 (p 0.006) | 86/74 faster (p 8e-5) |
| enhanced (PR #12) vs original | 147/13 (p 5e-26) | 151/9 (p 3e-26) | 155/5 (p 2e-26) | 79/81 (p 0.92) | 0/160 faster (p 5e-28) |
| enhanced (this work) vs enhanced (PR #12) | 87/73 (p 0.91) | 77/82 (p 0.82) | 76/84 (p 0.26) | 93/67 (p 0.007) | **159/1 faster (p 5e-28)** |

Hypervolume, median [IQR]:
* original: 0.4431 [0.4005, 0.4749]
* enhanced (PR #12): 0.4608 [0.4323, 0.4845]
* enhanced (this work): 0.4643 [0.4326, 0.4827]

![Paired hypervolume difference](benchmarks/final_hypervolume_difference.png)
![Convergence](benchmarks/final_convergence.png)
![Runtime](benchmarks/final_runtime.png)

More charts: [IGD+](benchmarks/final_igd_plus_difference.png), [GD](benchmarks/final_gd_difference.png), [spread](benchmarks/final_spread_difference.png), [memory](benchmarks/final_memory.png).

### Runtime without convergence history (the API's unsaved path)
Median of 7 seeds, ms per run:

| Problem | original | enhanced (PR #12) | enhanced (this work) |
|---|---|---|---|
| Salem Kharif | 285 | 342 | 297 |
| Erode Rabi | 305 | 506 | 295 |
| Coimbatore Summer | 373 | 618 | 295 |
| Erode Kharif, budget ₹230,000 | 394 | 491 | 407 |

The current enhanced engine costs 13–52 % less time than PR #12's. It is within ±4 % of the original engine, except where duplicates were frequent (Coimbatore Summer, 21 % faster). With history tracked, as in the study, the median over all 160 runs is faster than the original (0.300 vs 0.336 s).

## 3. Ablation: each switch on its own

### 3.1 Against the original engine

| Variant | HV | GD | IGD | IGD+ | Spread | Spacing | Dup. rejected | Gen. to 99 % | Time (s) | Peak MB |
|---|---|---|---|---|---|---|---|---|---|---|
| original (published) | 0.4432 | 0.3282 | 0.0668 | 0.0406 | 0.547 | 0.093 | 738 | 55 | 0.401 | 1.17 |
| + LHS initialisation | 0.4434 | 0.3336 | 0.0650 | 0.0386 | 0.523 | 0.095 | 696 | 55 | 0.400 | 1.17 |
| + constraint-aware init. | 0.4433 | 0.3297 | 0.0671 | 0.0408 | 0.546 | 0.093 | 809 | 55 | 0.402 | 1.17 |
| + diversity crossover | 0.4403 | 0.3172 | 0.0667 | 0.0398 | 0.532 | 0.093 | 696 | 55 | 0.398 | 1.19 |
| + duplicate avoidance | 0.4453 | 0.3287 | 0.0663 | 0.0402 | 0.538 | 0.093 | **20** | 55 | **0.343** | 1.19 |
| + early stop (pymoo default) | 0.4432 | 0.3282 | 0.0668 | 0.0406 | 0.547 | 0.093 | 738 | 55 | 0.454 | 1.19 |
| + early stop (pymoo, ftol 0.05, xtol 0.005) | 0.4433 | 0.3280 | 0.0663 | 0.0410 | 0.545 | 0.093 | 719 | 55 | 0.460 | 1.16 |
| + parallel evaluation (4 threads) | 0.4432 | 0.3282 | 0.0668 | 0.0406 | 0.547 | 0.093 | 738 | 55 | 0.436 | 1.18 |

| Variant vs original | HV | GD | IGD+ | Spread | Time |
|---|---|---|---|---|---|
| + LHS initialisation | 84/76 (0.54) | 78/82 (0.93) | 82/78 (0.48) | 84/76 (0.61) | 93/67 (0.001) |
| + constraint-aware init. (acts on 40 budget runs only) | 19/21 (0.67) | 16/24 (0.15) | 23/17 (0.99) | 16/24 (0.33) | 86/74 (0.11) |
| + diversity crossover | 90/70 (0.22) | 92/68 (0.14) | 89/71 (0.18) | 79/81 (0.86) | 78/82 (0.69) |
| + duplicate avoidance | 91/69 (0.43) | 85/75 (0.72) | 77/83 (0.57) | 79/81 (0.55) | **153/7 (3e-23)** |
| + early stop (pymoo default): never triggered | 0/0 | 0/0 | 0/0 | 0/0 | 32/128 (3e-5) |
| + early stop (pymoo, loose): stopped early, changing the result, in 11 runs | 6/5 (0.53) | 7/4 (0.37) | 5/6 (0.86) | 7/4 (0.42) | 31/129 (4e-6) |
| + parallel evaluation: identical results | 0/0 | 0/0 | 0/0 | 0/0 | 37/123 (0.002) |

### 3.2 Against the enhanced engine of PR #12

| Variant vs enhanced (PR #12) | HV | GD | IGD+ | Spread | Time |
|---|---|---|---|---|---|
| + LHS initialisation | 82/78 (0.48) | 92/64 (0.10) | 74/86 (0.98) | 77/83 (0.58) | 79/81 (0.76) |
| + constraint-aware init. | 24/16 (0.19) | 22/18 (0.55) | 20/20 (0.71) | 21/19 (0.46) | 96/64 (0.002) |
| + diversity crossover | 86/74 (0.33) | 85/75 (0.18) | 78/82 (0.65) | 88/72 (0.44) | 89/71 (0.014) |
| + duplicate avoidance | 80/80 (0.47) | 75/84 (0.63) | 69/91 (0.054) | **97/63 (0.001)** | **156/4 (1e-24)** |
| + early stop (pymoo, loose): changed the result in 22 runs | 10/12 (0.61) | 11/11 (0.94) | 14/8 (0.18) | 12/10 (0.78) | 35/125 (7e-6) |

![Ablation: paired hypervolume difference](benchmarks/ablation_hypervolume_difference.png)

More charts: [IGD+](benchmarks/ablation_igd_plus_difference.png), [GD](benchmarks/ablation_gd_difference.png), [spread](benchmarks/ablation_spread_difference.png), [runtime](benchmarks/ablation_runtime.png), [memory](benchmarks/ablation_memory.png), [convergence](benchmarks/ablation_convergence.png).

## 4. Tight budgets: constraint-aware initialisation

The ablation budgets leave feasible plans in generation 1 of every run, so the constraint-aware switch has nothing to repair there. Here the budget is 5 % or 20 % above the cheapest possible plan, for the Kharif season of every district, 10 seeds (80 paired runs per engine).

| Engine | HV better/worse (p) | median ΔHV | IGD+ better/worse (p) | First feasible generation, off → on (median, max) |
|---|---|---|---|---|
| original | 48/32 (0.12) | +0.0026 | 49/31 (0.061) | 8, 19 → **1, 1** |
| enhanced (PR #12) | **57/23 (4e-5)** | +0.0060 | **49/31 (8e-4)** | 1, 1 → 1, 1 |

## 5. Profile (Salem Kharif and two contrasting problems, median of 5, no history)

| Phase (ms per run) | Salem Kharif original | Salem Kharif enhanced | Coimbatore Summer original | Coimbatore Summer enhanced | Erode Kharif budget original | Erode Kharif budget enhanced |
|---|---|---|---|---|---|---|
| Duplicate elimination | 46.5 | 45.2 | **94.3** | 39.1 | 49.0 | 43.6 |
| Evaluation | 38.2 | 37.8 | 37.9 | 37.4 | 37.8 | 38.4 |
| Monitoring (observation) | 34.1 | 40.2 | 33.3 | 38.7 | 34.4 | 40.7 |
| Mutation | 7.9 | 26.4 | 9.9 | 31.3 | 8.0 | 28.2 |
| Selection | 11.4 | 10.7 | 24.8 | 9.6 | 12.2 | 9.8 |
| **Optimisation total** | 307 | 327 | **420** | **320** | 406 | 420 |
| Mating rounds (calls) | 354 | 325 | 846 | 298 | 386 | 296 |
| Duplicates rejected | 317 of 16,408 | 188 of 16,276 | 7,191 of 23,260 | 134 of 16,204 | 503 of 16,590 | 150 of 16,222 |
| Over-budget evaluations | 0 | 0 | 0 | 0 | 993 | 605 |
| Front beaten by its lower-bound copy | 97.5 % | 58.8 % | 50.0 % | 41.3 % | 96.3 % | 42.5 % |

Other figures:
* CPU utilisation is 1.00 (single thread) in every case.
* No dominated solutions remain in the final population, because the whole population is the first front.
* Peak traced memory is 1.4–1.8 MB.
* Quality metrics take 0.7 ms per run, TOPSIS 0.6 ms and fuzzy inference under 0.1 ms (cached).

## 6. Exactness of the output-preserving changes

| Check | Result |
|---|---|
| 96-run fingerprint of the original engine (12 district-seasons × budget/none × 2 seeds × history on/off: population X and F, convergence history, plans) | `aa942cba79791d4f`, identical to `main` |
| Same fingerprint for PR #12's enhanced engine | `d0679ccd00e9aa59`, identical to `main` |
| 48 early-stopping runs, including an infeasible budget | identical to `main` |
| Golden digests of the original engine (tests) and of PR #12's enhanced engine recorded on `main` | identical |
| Parallel evaluation vs serial (1–7 workers, with and without a budget, both modes, population 300) | identical |
| Re-scored benchmark (shared metrics module vs the old inline functions) | identical HV, IGD+, spread, spacing on all runs |
