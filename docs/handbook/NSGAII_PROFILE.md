# NSGA-II Profile

Measured runtime, memory, diversity and quality of the NSGA-II engine before and after this work. Context: [NSGAII_ANALYSIS.md](NSGAII_ANALYSIS.md). Decisions: [NSGAII_IMPROVEMENT_SUMMARY.md](NSGAII_IMPROVEMENT_SUMMARY.md).

**Machine and method.** One Apple-silicon laptop, Python 3.13, pymoo 0.6.2, NumPy, single process, no other load (the quality study ran alone). Timings are medians of repeated runs; run-to-run noise is about ±10 %. "main" is the code before this work, checked out separately.

**Reproduce.**
```
python scripts/profile_nsga2.py [--mode original|enhanced] [--no-history]   # phase profile
python scripts/benchmark_nsga2.py --seeds 10                                # quality study (≈12 min)
python scripts/benchmark_nsga2.py --seeds 5 --seed-offset 100 --variants …  # tuning / parameter study
```

## 1. Phase profile (Salem Kharif, 5 crops, pop 80 × 200 generations, median of 5)

| Phase | main | original (this branch) | enhanced |
|---|---|---|---|
| Preprocessing | 1.7 ms | 1.6 ms | 1.5 ms |
| Fuzzy inference | < 0.1 ms (cached) | < 0.1 ms | < 0.1 ms |
| Sampling + first evaluation | in "evaluation" | same | same |
| Objective evaluation (200 calls) | 38.8 ms | 37.2 ms | 38.9 ms |
| Tournament selection | 39.1 ms | **11.9 ms** | 17.4 ms |
| Crossover | 21.7 ms | **3.5 ms** | 5.3 ms |
| Mutation | 8.2 ms | 8.1 ms | 9.6 ms |
| Repair | 4.0 ms | 3.8 ms | 5.7 ms |
| Duplicate elimination | 49.1 ms | 49.1 ms | 68.5 ms |
| Non-dominated sorting | 6.5 ms | 6.4 ms | 6.6 ms |
| Crowding distance | 11.2 ms | 11.1 ms | 10.9 ms |
| History extraction | 19.2 ms | **7.0 ms** | 6.1 ms |
| Decoding | 0.4 ms | 0.5 ms | 0.4 ms |
| TOPSIS ranking | 0.7 ms | 0.6 ms | 0.6 ms |
| **Optimisation, saved run (history on)** | **748 ms** | **287 ms** | 367 ms |
| **Optimisation, unsaved run** | 298 ms | 295 ms | 354 ms |
| Peak traced memory, saved run | **57.8 MB** | **1.6 MB** | 1.6 MB |
| Peak traced memory, unsaved run | 0.6 MB | 0.6 MB | 0.7 MB |
| CPU utilisation | 100 % of one core | same | same |
| Generations / evaluations | 200 / 16,000 | 200 / 16,000 | 200 / 16,000 |
| Pareto-front size | 80 | 80 | 80 |
| Offspring rejected as duplicates | 317 of 16,408 (1.9 %) | identical | 2,163 of 18,248 (11.9 %) |

The selection, crossover and history savings in the original mode are partly spent on the new per-generation diversity monitoring (≈20 ms), which is why an unsaved run is only slightly faster; a saved run, the default for Run Optimization, is 2.6× faster and uses 36× less memory. Enhanced mode costs more time because (a) the adaptive controller computes the first-front hypervolume every generation and (b) the lower mutation probability creates more exact duplicates, each needing another mating round.

## 2. Across all 12 district-seasons (5 ha, no budget, pop 80 × 200, median of 3 passes)

| | main | original (this branch) |
|---|---|---|
| Unsaved run | 341 ms | 321 ms |
| Saved run (history + extraction) | 871 ms | 329 ms |
| Peak memory, saved run | 57.8 MB | 1.6 MB |
| Results (96 fingerprinted runs: 12 problems × budget/no budget × 2 seeds × history on/off) | — | **bit-identical** |

## 3. Scalability (Salem Kharif; seconds, median of 3)

| Crops | Population | main, unsaved | main, saved | original, unsaved | original, saved | enhanced, unsaved | enhanced, saved |
|---|---|---|---|---|---|---|---|
| 2 | 80 | 0.67 | 1.23 | 0.70 | 0.68 | 0.44 | 0.43 |
| 2 | 300 | 2.13 | 4.27 | 2.14 | 1.86 | 1.44 | 1.38 |
| 5 | 40 | 0.17 | 0.42 | 0.17 | 0.17 | 0.25 | 0.30 |
| 5 | 80 | 0.29 | 0.79 | 0.29 | 0.31 | 0.53 | 0.40 |
| 5 | 160 | 0.57 | 1.54 | 0.56 | 0.58 | 0.84 | 0.72 |
| 5 | 300 | 1.13 | 3.06 | 1.09 | 1.17 | 1.45 | 1.76 |

Run time grows linearly with population size in every mode. With history it no longer grows faster than without (main: ≈2.7× at every size). Two-crop problems are slower than five-crop ones because 31 % of their offspring are exact duplicates and need another mating round; Enhanced mode is faster on them (cause not isolated).

## 4. Parameter study (tuning seeds 100–104, 16 problems = 80 paired runs per row)

Hypervolume (HV, higher is better) and IGD+ (lower is better) are computed per problem on objectives normalised by a common reference front (see §5). "better/worse" counts paired runs against the published settings; p is the Wilcoxon signed-rank test.

| Setting | HV | IGD+ | HV better/worse | p (HV) | Evaluations | Time |
|---|---|---|---|---|---|---|
| **Published (pop 80, 200 gen, p_c 0.85, p_m 0.12, σ 0.12)** | 0.4404 | 0.0371 | – | – | 16,000 | 0.37 s |
| pop 40 | 0.4177 | 0.0480 | 4/76 | 3e-14 | 8,000 | 0.23 s |
| pop 160 | 0.4649 | 0.0265 | 78/2 | 3e-14 | 32,000 | 0.68 s |
| 100 generations | 0.4386 | 0.0424 | 28/52 | 0.001 | 8,000 | 0.18 s |
| 400 generations | 0.4464 | 0.0410 | 37/43 | 0.49 | 32,000 | 0.75 s |
| p_c 0.6 | 0.4416 | 0.0410 | 26/54 | 5e-4 | 16,000 | 0.40 s |
| p_c 0.95 | 0.4464 | 0.0402 | 45/35 | 0.40 | 16,000 | 0.36 s |
| **p_m 0.05** | **0.4593** | **0.0270** | **76/4** | 6e-14 | 16,000 | 0.48 s |
| p_m 0.25 | 0.4241 | 0.0582 | 6/74 | 4e-14 | 16,000 | 0.31 s |
| σ 0.05 | 0.4522 | 0.0337 | 51/29 | 0.013 | 16,000 | 0.36 s |
| σ 0.25 | 0.4375 | 0.0415 | 21/59 | 3e-6 | 16,000 | 0.39 s |

Findings: the mutation probability is the parameter that matters most — the paper's 0.12 is too disruptive for this problem (it keeps knocking multipliers off their optimal bound, NSGAII_ANALYSIS.md §4.2). A larger population helps but doubles the cost; more generations do not help (the front drifts rather than improves after the early generations).

### Feature tuning (same seeds)

| Variant | HV better/worse | IGD+ better/worse | Decision |
|---|---|---|---|
| Adaptive mutation (min 0.06, ×0.5) | 48/32 (p 0.02) | 52/28 | tune further |
| Adaptive mutation (min 0.02, ×0.2) | 64/16 (p 2e-7) | 59/21 | **chosen parameters** |
| Adaptive crossover 0.95 → 0.70 | 40/40 (p 0.44) | 35/45 | no effect |
| Adaptive crossover 0.90 → 0.60 | 22/58 (p 0.001) | 34/46 | worse |
| Smart initialisation 10 % / 20 % / 30 % | 31/49, 36/44, 38/42 (n.s.) | 41/39, 50/30 (p 0.04), 41/39 | **20 %**; converges in 10 instead of 60 generations |
| Duplicate tolerance 1e-4 / 1e-3 | 37/43 (n.s.) / 26/54 (p 0.003) | 39/41 / 34/46 | no benefit |
| Early stopping (30 gens / 50 gens & min 100 / tol 1e-3) | 13/67, 18/62, 11/69 | 19/61, 24/56, 19/61 | always worse; saves 46–65 % of evaluations |
| Smart init + adaptive mutation, base p_m 0.12 | 64/16 (p 6e-10) | 70/10 | |
| **Smart init + adaptive mutation, base p_m 0.05** | **79/1 (p 4e-14)** | **77/3** | **= enhanced mode** |

## 5. Quality study — before vs after (evaluation seeds 0–9, 16 problems = 160 paired runs)

Problems: the 12 district × season profiles (5 ha, no budget) and Kharif in each district with a budget of 5 ha × the median single-crop cost per hectare. Indicators are computed on each run's final feasible first front, normalised per problem by the ideal and nadir of a reference front: the non-dominated union of every front from every variant and seed, plus each solution's copy with its multipliers at the lower bound (never worse, so it tightens the reference). Medians over the 160 runs.

| Metric | Original | +Adaptive mutation | +Adaptive crossover | +Smart init | +Duplicate removal | +Early stopping | **Enhanced** | p_m 0.05 only |
|---|---|---|---|---|---|---|---|---|
| Hypervolume ↑ | 0.4427 | 0.4519 | 0.4407 | 0.4456 | 0.4424 | 0.4277 | **0.4608** | 0.4589 |
| IGD+ ↓ | 0.0399 | 0.0328 | 0.0414 | 0.0358 | 0.0398 | 0.0507 | **0.0244** | 0.0284 |
| Generalised spread ↓ | 0.547 | 0.540 | 0.531 | 0.521 | 0.547 | 0.537 | 0.549 | 0.557 |
| Spacing ↓ | 0.093 | 0.089 | 0.096 | 0.092 | 0.097 | 0.097 | **0.071** | 0.080 |
| Front size | 80 | 80 | 80 | 80 | 80 | 80 | 80 | 80 |
| Allocation entropy ↑ | 0.556 | 0.565 | 0.574 | 0.566 | 0.556 | 0.551 | 0.569 | 0.574 |
| Full decision-space entropy | 0.367 | 0.332 | 0.376 | 0.346 | 0.371 | 0.463 | 0.265 | 0.288 |
| Duplicates in final population | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Plans dominated by their own lower-bound copy ↓ | 91 % | 76 % | 91 % | 84 % | 91 % | 100 % | **46 %** | 62 % |
| Generations to 99 % of the original's final HV ↓ | 55 | 55 | 50 | **10** | 50 | 50 | **10** | 45 |
| Runs reaching it | 99 % | 100 % | 98 % | 100 % | 99 % | 76 % | 100 % | 100 % |
| Evaluations | 16,000 | 16,000 | 16,000 | 15,999 | 16,000 | 5,520 | 15,999 | 16,000 |
| Generations run | 200 | 200 | 200 | 200 | 200 | 69 | 200 | 200 |
| Time per run (with history) | 0.34 s | 0.41 s | 0.35 s | 0.34 s | 0.36 s | 0.13 s | 0.53 s | 0.43 s |

Paired against the original (Wilcoxon signed-rank, 160 pairs):

| Variant | HV better/worse, p | IGD+ better/worse, p | Spread p | Allocation entropy p |
|---|---|---|---|---|
| Adaptive mutation | 130/30, 8e-17 | 128/32, 1e-14 | 0.97 | 0.90 |
| Adaptive crossover | 87/73, 0.90 | 77/83, 0.31 | 0.60 | 0.60 |
| Smart initialisation | 98/62, 0.001 | 103/57, 3e-6 | 0.12 | 0.30 |
| Duplicate removal | 77/83, 0.90 | 75/85, 0.85 | 0.59 | 0.51 |
| Early stopping | 43/117, 5e-13 (worse) | 38/122, 6e-15 (worse) | 0.96 | 0.87 |
| **Enhanced** | **147/13, 5e-26** | **154/6, 2e-26** | 0.92 | **3e-4 (higher)** |
| p_m 0.05 only | 147/13, 1e-24 | 149/11, 2e-23 | 0.40 | 0.01 |

Enhanced wins on hypervolume in every one of the 16 problems (7–10 of 10 seeds each, 10/10 in seven of them, including all four budget-constrained ones).

**Diversity.** Objective-space spread and front size are unchanged, spacing is more even (0.093 → 0.071) and the diversity of the land allocations is higher. The full decision-space entropy falls because the multiplier genes converge to their bound — which is the optimum, not a loss of diversity.

**Average objectives.** Over the whole front, Enhanced plans have on average +2.2 % yield, −1.2 % cost, −6.8 % water and −5.8 % environmental impact (median of per-run relative changes).

**The recommended (TOPSIS rank-1, balanced) plan changes.** TOPSIS normalises each objective within the plans it is given. On the better Enhanced front the balanced compromise moves towards lower-input plans: on average −12 % yield, −4 % cost, −7 % water and −5 % impact compared with the original's rank-1 plan (medians). This is a different compromise on a better front, not a worse plan; it is the main reason Enhanced is opt-in.

## 6. Diversity statistics recorded per run

Every run now records (meta → `optimizer.diversity`): population entropy, allocation diversity, mean finite crowding distance and first-front size (initial / final / minimum), and the share of offspring rejected as duplicates. Example (Salem Kharif, original, seed 42): entropy 0.865 → 0.407, first front 13 → 80 individuals (full from generation 8), 1.9 % of offspring rejected. Coimbatore Summer: 31 % rejected; Erode Rabi: 12 %.
