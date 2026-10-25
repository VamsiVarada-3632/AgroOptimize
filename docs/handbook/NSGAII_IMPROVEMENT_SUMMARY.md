# NSGA-II Improvement Summary

> This is the record of the first round (PR #12). The second round (quality metrics, constraint-aware initialisation, duplicate avoidance, and the rejected LHS, diversity crossover, objective-space stopping and parallel evaluation) is in [NSGAII_IMPROVEMENTS.md](NSGAII_IMPROVEMENTS.md) and [NSGAII_BENCHMARK_RESULTS.md](NSGAII_BENCHMARK_RESULTS.md); enhanced mode now also enables those two accepted switches.

What changed in the NSGA-II engine, why, how it was measured, and what it does to results and reproducibility. Analysis: [NSGAII_ANALYSIS.md](NSGAII_ANALYSIS.md). Measurements: [NSGAII_PROFILE.md](NSGAII_PROFILE.md). Literature: [NSGAII_RESEARCH_REVIEW.md](NSGAII_RESEARCH_REVIEW.md).

## 1. Two engine modes

| Mode | Selected by | Results | Purpose |
|---|---|---|---|
| **Original (published)** — default | `NSGA2_ENGINE_MODE = "original"` in `app/config.py`, or no environment variable | **Bit-identical** to the engine before this work | Reproducing the published results; baseline for comparisons |
| **Enhanced (experimental)** | `AGROOPTIMIZE_NSGA2_MODE=enhanced` (environment) or `NSGA2_ENGINE_MODE` in config; in code `run_nsga2(problem, mode="enhanced")` | Different, measurably better fronts | Ablation studies, future versions of the paper |

Every improvement is a separate switch in `config.NSGA2_ENGINE_FEATURES` and `EngineSettings` (`app/optimization/engine_settings.py`). Any single feature can be added to either mode for a benchmark:
```python
from dataclasses import replace
from app.optimization.engine_settings import engine_settings
run_nsga2(problem, engine=replace(engine_settings("original"), smart_initialization=True))
```
`scripts/benchmark_nsga2.py` does this for every feature (`--variants original,smart_initialization,enhanced,original@mutation_prob=0.05,…`).

The mode is deliberately **not** an API parameter: the brief rules out API and frontend changes. Every API path (Run Optimization, Scenario Simulation, District Intelligence, dashboards, comparison) uses the configured mode, and each saved run records which mode produced it (`meta.optimizer.engine`).

## 2. Improvements, decisions and evidence

All quality numbers: 16 problems × 10 evaluation seeds = 160 runs paired with the original on the same problem and seed (Wilcoxon signed-rank). Parameters were tuned on separate seeds (100–104).

| # | Improvement | Why it was needed | Research basis | Before → after | Effect on outputs | Reproducibility | Decision |
|---|---|---|---|---|---|---|---|
| 1 | **Smart initialisation** (20 % of the first population seeded from the district's candidate crops, multipliers at the lower bound) | Optimum lies on the lower-bound face of the multipliers (ANALYSIS §4.2); random starts take ~55 generations to get close | Friedrich & Wagner 2015 (seeding MOEAs) | Generations to reach the original's final quality: **55 → 10**; HV better in 98/160 (p 0.001); IGD+ better in 103/160 (p 3e-6) | Changes the front | Deterministic per seed | **Enhanced: on** |
| 2 | **Adaptive mutation** (diversity-guided, reduced after stagnation) with base p = 0.05 | p = 0.12 keeps knocking multipliers off their optimum (parameter study: 0.05 better in 76/80, 0.25 worse in 74/80) | Srinivas & Patnaik 1994; Eiben et al. 1999; Ursem 2002 | Alone (base 0.12): HV better in 130/160 (p 8e-17), IGD+ in 128/160 | Changes the front | Deterministic per seed | **Enhanced: on** (with base 0.05) |
| 3 | Adaptive crossover (0.95 → 0.70) | Exploration early, exploitation late | Eiben et al. 1999 | HV 87/73 (p 0.90), IGD+ 77/83 (p 0.31): **no measurable effect**; a steeper schedule (0.90 → 0.60) was worse | — | — | **Rejected** (available, off) |
| 4 | Tolerance-based duplicate removal (1e-4 normalised) | Clipped genes create duplicates (up to 31 % of offspring) | pymoo duplicate elimination | HV 77/83 (p 0.90), IGD+ 75/85: **no measurable effect**; 1e-3 was worse | — | — | **Rejected** (available, off). pymoo's exact-copy removal stays on in both modes |
| 5 | Early stopping (HV stagnation, 30 generations, after 60) | Save time when the front stops improving | Martí et al. 2016 | Evaluations **16,000 → 5,520** (−65 %), time −62 %, but HV worse in 117/160, IGD+ worse in 122/160 | Changes the front (worse) | Deterministic per seed | **Rejected** for enhanced (quality first); available, off, for time-limited use |
| 6 | Diversity monitoring (entropy, allocation diversity, mean crowding, first-front size, duplicate ratio) | No visibility into diversity | Zitzler et al. 2003 | New statistics in every run | **None** (observes only; tested) | Unchanged | **On in both modes** |
| 7 | Runtime profiling (total time, generations, evaluations, Pareto size, ms/generation) | No visibility into run cost | — | Logged (`app.optimization.nsga2_runner`, INFO) and saved in `meta.optimizer.profile` | **None** (tested) | Unchanged | **On in both modes** |
| 8 | Code optimisation: vectorised single-point crossover and binary tournament (same random draws, tested against the old loop and pymoo's tournament), cached problem constants, a monitor instead of pymoo's `save_history` | Python loops; per-generation deep copies of the algorithm | — | Saved run **748 → 287 ms** (2.6×), peak memory **57.8 → 1.6 MB**; selection 39 → 12 ms; crossover 22 → 3.5 ms | **None**: bit-identical on 96 fingerprinted runs and 3 recorded digests | Unchanged | **On in both modes** |

**Enhanced mode = 1 + 2 (+ 6, 7, 8).**

## 3. Before vs after (evaluation seeds, medians of 160 runs)

| Metric | Original | Enhanced | Change |
|---|---|---|---|
| Hypervolume ↑ | 0.4427 | 0.4608 | **+4.1 %**; better in 147/160 runs, every problem (p 5e-26) |
| IGD+ ↓ | 0.0399 | 0.0244 | **−39 %**; better in 154/160 (p 2e-26) |
| Generalised spread | 0.547 | 0.549 | unchanged (p 0.92) |
| Spacing ↓ | 0.093 | 0.071 | more even |
| Front size | 80 | 80 | unchanged |
| Land-allocation entropy ↑ | 0.556 | 0.569 | higher (p 3e-4) |
| Plans dominated by their own lower-bound copy ↓ | 91 % | 46 % | better converged |
| Generations to the original's final quality ↓ | 55 | 10 | **5.5× faster convergence** |
| Duplicates in final population | 0 | 0 | — |
| Evaluations | 16,000 | 15,999 | same budget |
| Front averages (yield / cost / water / impact) | — | +2.2 % / −1.2 % / −6.8 % / −5.8 % | better on all four |
| Run time, saved run (Salem Kharif) | 0.75 s (main) / 0.29 s | 0.37 s | slower than original, faster than before this work |
| Peak memory, saved run | 57.8 MB (main) | 1.6 MB | |

## 4. Impact on outputs and reproducibility

* **Original mode:** no output changes. Fronts, plans, rankings, explanations, convergence histories and every saved result are bit-identical to the engine before this work. The same seed gives the same front, as before. The only additions are `meta.optimizer` in saved run files (not in the API response, whose `RunMeta` model does not declare it) and an INFO log line per run.
* **Enhanced mode:** different fronts, deterministic per seed. Because TOPSIS normalises within the front, the **recommended plan changes**: on average the balanced rank-1 plan has 12 % less yield, 4 % lower cost, 7 % less water and 5 % lower impact than the original's. That is a different compromise on a better front, but it changes what a farmer is shown, which is why Enhanced is opt-in and labelled experimental. Published tables must be reproduced with the original mode.
* **Scientific justification for enhanced outputs:** the original engine returns plans that its own objectives prove suboptimal (ANALYSIS §4.2). Enhanced mode removes about half of that gap with techniques from the literature, using the same objectives, constraints and evaluation budget.
* **Note on the multipliers:** enhanced plans recommend the minimum irrigation and fertiliser multipliers more often, because the objectives contain no yield response to inputs. Before presenting such recommendations agronomically, the model should gain an input–yield response (RESEARCH_REVIEW.md; FAO-33).

## 5. Validation

| Check | Result |
|---|---|
| Original mode vs `main`: 96 runs (12 district-seasons × budget/none × 2 seeds × history on/off), population X and F, convergence history, decoded plans | identical (SHA-256) |
| Recorded digests, including an infeasible budget (tests) | identical |
| Vectorised crossover vs the old loop (5 sizes), including random draws consumed | identical |
| Vectorised tournament vs pymoo's (no budget, feasible budget, infeasible budget) | identical populations |
| Monitor history vs pymoo `save_history` | identical convergence history |
| Monitoring / profiling on vs off | identical populations |
| Each feature: deterministic per seed, within bounds, allocations sum to 1, changes the search | 5 parametrised tests |
| Backend tests | 595 passed (557 existing + 38 new) |
| Frontend tests, lint, build | unchanged code; pass |

Explanations, reports, history, Scenario Simulation, District Intelligence, comparison, analytics and Run Optimization all call the same engine; their test suites pass unchanged (one simulation test now also ignores the new wall-clock fields when comparing two runs).

## 6. Trade-offs

* **Time vs quality in Enhanced mode:** +25–80 % run time against the original mode, depending on the problem (hypervolume each generation for the stagnation test, and more duplicate rejections at the lower mutation rate). Still faster than the engine before this work for saved runs.
* **Observers cost ≈20 ms per run** (≈7 %), which uses up most of the speed-up for unsaved runs. They can be switched off (`diversity_monitoring`, `runtime_profiling`).
* **Early stopping** trades quality for time and is off by default.
* **Mode via configuration, not the API**, to respect the no-API-change rule; the frontend cannot switch modes per request.

## 7. Future improvements

1. An external non-dominated archive (ε-dominance) to keep the best front found rather than the last population (ANALYSIS §4.3).
2. A density estimator suited to four objectives, or NSGA-III/MOEA-D as comparison baselines (RESEARCH_REVIEW.md R-8).
3. SBX + polynomial mutation or block-aware crossover (changes the paper's operators).
4. Operators on pymoo's `random_state` to remove the run lock (changes all results).
5. An input–yield response in f1 so the multiplier genes carry a real trade-off (changes the objectives).
6. Optionally expose the engine mode per request once an API change is acceptable.
7. Population 100–160 when run time allows (HV better in 78/80 tuning runs at 160).
