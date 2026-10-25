# NSGA-II Improvements

What changed in the NSGA-II engine in this round, why, and what it does. Evidence: [NSGAII_BENCHMARK_RESULTS.md](NSGAII_BENCHMARK_RESULTS.md). Structure: [NSGAII_ARCHITECTURE.md](NSGAII_ARCHITECTURE.md). Previous round (PR #12): [NSGAII_IMPROVEMENT_SUMMARY.md](NSGAII_IMPROVEMENT_SUMMARY.md).

## 1. Summary

* **The published engine is unchanged.** `original` mode is still the default and reproduces every published result bit for bit. It is the same 96-run fingerprint as `main`, and the golden digests pass.
* **The enhanced engine is better and now fast.** Against the original:
  * hypervolume better in 150 of 160 paired runs, GD in 154, IGD+ in 152;
  * spread better (p 0.006), and the original's final quality is reached in 10 generations instead of 55;
  * median run time 0.30 s instead of 0.34 s (saved runs).

  Against PR #12's enhanced engine it has the same front quality, better spread, and takes 42 % less time.
* **Every run reports its quality.** `meta.quality_metrics` reports hypervolume and its ratio to a reference front, GD, IGD, IGD+, spread, spacing, Pareto size, constraint satisfaction, runtime and mean objectives. It is returned by the API, stored with saved runs and shown in Reports.
* **Six switches were evaluated.** Two were accepted into enhanced mode. Four were rejected, because they measured no benefit; they remain available for ablation runs.
* **Two speed-ups are output-preserving.** They are exact and apply to both modes.
* **The API is backward compatible.** `quality_metrics` is a new optional field; nothing was removed or renamed.

## 2. Changes

### 2.1 Output-preserving speed-ups (both modes)

| Change | Why | Before → after | Results |
|---|---|---|---|
| Front hypervolume read from the cached population arrays (`monitoring.front_hypervolume`) | the per-generation hypervolume used by adaptive mutation and early stopping read the front through pymoo's per-individual getters, at ~30× the cost of the hypervolume itself | part of the enhanced-mode gain below | bit-identical |
| Parent-population X cached in the duplicate check (`CountingDuplicateElimination`) | each mating batch was checked against the same parent population, whose X was re-read for every batch | enhanced 4–13 % faster (Coimbatore Summer 690 → 600 ms), original 1–2 % | bit-identical |

### 2.2 New switches

Each switch is independent (`EngineSettings`, `config.NSGA2_ENGINE_FEATURES`) and off in the original engine.

| # | Switch | Why | How | Scientific basis | Benchmark | Decision |
|---|---|---|---|---|---|---|
| A | Adaptive mutation (PR #12) | fixed p = 0.12 keeps knocking multipliers off their optimum | diversity-guided, reduced after stagnation, base 0.05 | Srinivas & Patnaik 1994; Eiben et al. 1999; Ursem 2002 | accepted in PR #12; re-measured in the final comparison | **enhanced: on** (unchanged) |
| B | Adaptive crossover, `schedule="diversity"` (new) | the linear schedule of PR #12 had no effect; recombine more when the population stagnates | p_c 0.85 at the running diversity peak, up to 0.95 as allocation diversity falls to half the peak (it never falls below its start in this problem) | Srinivas & Patnaik 1994; Ursem 2002 | HV n.s. vs original (p 0.22) and vs enhanced (p 0.33) | **rejected** |
| C1 | Latin Hypercube initialisation `lhs_initialization` | uniform sampling can leave parts of each gene's range empty | pymoo LHS (maxmin) for the random part of the first population; seeds kept | McKay, Beckman & Conover 1979 | HV n.s. (p 0.54 / 0.48): with 200 generations and the smart seeds the initial layout is forgotten | **rejected** |
| C2 | Constraint-aware initialisation `constraint_aware_initialization` | random first plans often exceed a tight budget; the original engine needed up to 19 generations to find a feasible plan | over-budget plans: fertiliser to 0.7, then allocation blended towards the cheapest crop with the exact weight that meets the budget; deterministic | repair-based constraint handling (Coello Coello 2002; Deb 2000 for the constrained domination it complements) | ordinary budgets: neutral (feasible plans exist in generation 1). Tight budgets: first feasible generation 8 → 1 (original); enhanced HV better in 57/80 (p 4e-5), IGD+ 49/31 (p 8e-4) | **enhanced: on** |
| D | Duplicate avoidance `duplicate_avoidance` | copies are never evaluated but each costs another mating round: 2–40 % of offspring in the original engine (median 4 %), 14–73 % in the enhanced one (median 33 %) | an offspring still equal to a parent after mutation gets one Gaussian step on a random gene | duplicate genotypes waste GA effort (Ronald 1998); the exact-copy check itself is pymoo's | quality equal to enhanced (HV p 0.47; IGD+ 69/91, p 0.054, median +0.0003); spread better (p 0.001); faster in 156/160 runs; duplicates rejected 8,022 → 140 (median) | **enhanced: on** |
| E | Early stopping, `criterion="objective_space"` (new) | the hypervolume-stagnation rule of PR #12 lowered quality | pymoo's robust multi-objective termination (decision-space, CV and objective-space tolerances over a window) | Blank & Deb 2020; Martí et al. 2016 | default tolerances never trigger within 200 generations; looser ones change 11–22 of 160 runs, no quality change, and the extra checks make runs slower | **rejected** |
| F | Parallel evaluation `parallel_evaluation` | requested; only useful if evaluation dominates the run | chunks on a thread pool, joined in order; identical results | master–slave parallel GAs pay off only when evaluation is expensive (Cantú-Paz 2000) | identical fronts; 4–24 % slower at population 80, 1–8 % at 300 (evaluation is ~0.05 ms of vectorised arithmetic per generation) | **rejected** (kept as a switch) |

The previous round's tolerance-based duplicate removal, linear crossover schedule and hypervolume early stopping stay available and off (NSGAII_IMPROVEMENT_SUMMARY.md).

### 2.3 Quality metrics (`app/optimization/metrics.py`)

* **Indicators:**
  * hypervolume (Zitzler & Thiele 1999);
  * GD (Van Veldhuizen & Lamont 1998);
  * IGD (Coello & Reyes Sierra 2004);
  * IGD+ (Ishibuchi et al. 2015);
  * generalised spread (Zhou et al. 2006);
  * spacing (Schott 1995).

  All are computed on objectives normalised by a reference front.
* **Per-run reference:** a single run has no external reference front. The run uses the non-dominated union of its front and the copies of its plans with input multipliers at 0.7. That copy is never worse in this model, which makes GD, IGD and the hypervolume ratio a direct measure of how far the run is from converging.
* **Other figures:** Pareto and feasible front size, constraint satisfaction rate, share beaten by the lower-bound copy, runtime, generations, evaluations, mean objectives.
* **Where it shows:** in the API (`meta.quality_metrics` in `POST /api/farm-plans` and `GET /api/results/{id}`), in saved runs, and in Reports (four headline metrics on the card; every metric in the downloaded report). Runs saved earlier show "Not recorded".
* **Performance and safety:** it costs under 1 ms per run and does not touch the search (tested). NaN values become null.
* **Shared with the benchmark:** the benchmark uses the same module. Its re-scored values are identical to the earlier inline code.

### 2.4 Tooling
* `scripts/benchmark_nsga2.py`:
  * GD and IGD;
  * text parameters and performance switches;
  * constraint satisfaction, duplicates rejected and first feasible generation;
  * comparisons against both engines;
  * `--memory`.
* `scripts/benchmark_tight_budget.py`: the constraint study.
* `scripts/report_nsga2_benchmark.py`: charts and Markdown tables.
* `scripts/profile_nsga2.py`:
  * CPU utilisation;
  * over-budget evaluations;
  * dominated solutions;
  * share beaten by the lower-bound copy;
  * monitoring and quality-metric timers;
  * `--switch`.

## 3. Before vs after (enhanced engine)

| Measure (median of 160 paired runs) | original | enhanced, PR #12 | enhanced, this work |
|---|---|---|---|
| Hypervolume ↑ | 0.4431 | 0.4608 | **0.4643** |
| GD ↓ | 0.3277 | **0.1565** | 0.1655 |
| IGD ↓ | 0.0660 | **0.0434** | 0.0450 |
| IGD+ ↓ | 0.0392 | **0.0238** | 0.0247 |
| Spread ↓ | 0.547 | 0.549 | **0.509** |
| Spacing ↓ | 0.093 | 0.071 | 0.071 |
| Duplicates rejected per run | 738 | 8,022 | **140** |
| Generations to 99 % of the original's final HV | 55 | 10 | 10 |
| Time per saved run (s) | 0.336 | 0.513 | **0.300** |
| Peak memory (MB) | 1.17 | 1.17 | 1.21 |

The GD/IGD/IGD+ differences between the two enhanced engines are not significant (p 0.82 / 0.26), and neither is hypervolume (p 0.91). The two enhanced engines are equally good fronts, and this one is cheaper and more evenly spread.

## 4. Impact on outputs and reproducibility

* **Original mode:** no output changes. The only addition is `meta.quality_metrics` in the response and saved runs.
* **Enhanced mode:** fronts differ from PR #12's enhanced engine, deterministically per seed (new golden digests recorded in the tests). As before, TOPSIS's rank-1 plan differs from the original engine's, so enhanced mode stays opt-in (`AGROOPTIMIZE_NSGA2_MODE=enhanced`) and the published tables must be reproduced with `original`.
* **Platform:** results are bit-identical on the same platform. A different CPU architecture or C library (e.g. x86-64 Linux vs arm64 macOS) gives a different but equally good trajectory. This was measured during the Render deployment: hypervolume +0.7 % on average over 12 district-seasons.

## 5. Validation

| Check | Result |
|---|---|
| Original-engine fingerprint (96 runs) and golden digests | identical to `main` |
| PR #12 enhanced engine (96-run fingerprint, 3 digests) with the new switches off | identical to `main` |
| Objectives, constraints, fuzzy outputs, TOPSIS | untouched by this work; their test suites pass unchanged |
| Every switch: deterministic per seed, within bounds, valid plans, changes the search (or, for parallel evaluation, does not) | tested |
| APIs and UI | all backend and frontend tests pass; Reports checked in the browser with no console errors |
| Tests | 649 backend (595 on `main`; +51 in `tests/test_nsga2_optimization.py`, +3 from the new switches in the per-feature test), 61 frontend (57 on `main`; +4) |

## 6. Limitations

* **Many objectives:** with four objectives the whole population is non-dominated from generation 4–8. Every improvement here works around that loss of selection pressure, and none removes it. The remedy is a many-objective algorithm (NSGA-III, MOEA/D) or an archive, which is outside the "keep NSGA-II" scope.
* **Remaining convergence gap:** even the enhanced engine leaves 41–59 % of the front beaten by its own lower-bound copy. The multipliers have no yield response, so the search space has a known optimal face that a GA approaches slowly.
* **Per-run reference front:** the reference used for the per-run metrics is built from the run's own front, so GD and IGD in the API measure convergence towards the multiplier bound, not towards the true Pareto front. The benchmark uses a common reference built from all runs.
* **Timing:** run times come from one laptop and vary by a few percent between sessions. Comparisons are paired within one session.
* **Statistics:** significance is per indicator, with no multiple-comparison correction. The accepted changes have p < 1e-20 on time and p < 0.01 on spread or tight-budget hypervolume, well clear of any correction. The rejected ones fail even uncorrected.
* **Parameters:** the new switches use literature defaults (pymoo LHS, pymoo termination tolerances, crossover 0.85/0.95). Only the early-stopping tolerances were varied.

## 7. Future work

1. An external ε-dominance archive (Laumanns et al. 2002) to return the best front found rather than the last population.
2. NSGA-III or MOEA/D as a comparison baseline for four objectives (RESEARCH_REVIEW.md R-8).
3. A yield response to irrigation and fertiliser in f1, so the multiplier genes carry a real trade-off (an objective change).
4. Run-level parallelism for Scenario Simulation's 5-seed ensemble (independent runs, so it would scale, unlike per-population evaluation), with care for the global RNG lock.
5. A platform-independent random stream for the operators (pymoo's Generator instead of the NumPy global RNG and C `log`), accepting one change of all results.
6. A per-request engine mode once an API change is acceptable.
