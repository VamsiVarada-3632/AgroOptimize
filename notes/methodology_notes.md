# AgroOptimize -- Methodology Notes

Reference notes for 23CSE498 Project Phase II. Covers the theory behind
fuzzy logic + NSGA-II, how it maps onto the actual code in this repo, every
formula used, and every assumption made. Read this before a guide/panel
review or the viva -- `viva_prep.md` in this folder is the companion Q&A
document.

---

## 1. The problem, in one paragraph

A farmer choosing what to plant faces four things pulling against each
other: they want high yield, low cost, low water use, and low environmental
damage -- and they can't fully trust the numbers because rainfall, soil
condition and water availability are never perfectly known in advance. Most
existing decision-support tools optimise one objective at a time (usually
yield or cost) and treat the inputs as exact numbers. This project does two
things differently: it treats rainfall/soil/water uncertainty explicitly
with **fuzzy logic**, and it optimises all four objectives *simultaneously*
with **NSGA-II**, producing not one answer but a set of equally-valid
trade-off plans that a farmer can choose between.

## 2. System pipeline

```
   data/raw/*.csv                    (Section III-B)
        |
        v
  app/data/preprocessing.py   -->  RegionSeasonProfile
        |                          (soil, rainfall, water, candidate crops)
        v
  app/fuzzy/engine.py         -->  UncertaintyAssessment    (Section III-C)
        |                          (yield_confidence, irrigation_risk)
        v
  app/optimization/problem.py -->  FarmPlanProblem           (Section III-D)
  app/optimization/nsga2_runner.py -> Pareto front (20-80 candidate plans)
        |
        v
  app/decision/ranking.py     -->  Ranked, filtered, explained plans (Section III-E)
        |
        v
  app/services/results_store.py -> results/<run_id>.json + .csv + .png (Section 8)
        |
        v
  app/main.py (FastAPI)       -->  JSON response / Swagger UI
```

`app/services/plan_service.py` is the single function (`generate_farm_plans`)
that wires all five stages together (including persistence); both
`app/main.py` (the API) and `run_demo.py` (the CLI) call into it. Keeping
every stage as a pure, independently-testable module (rather than one big
script) is *why* `tests/test_pipeline.py` can test preprocessing, fuzzy
logic, NSGA-II, ranking and results persistence in isolation as well as
end-to-end.

## 3. The dataset

`data/raw/` holds 16 CSVs: 4 Tamil Nadu districts (Coimbatore, Erode, Salem,
Pollachi) x 4 kinds of data, each spanning 2020-2023.

| Kind | File pattern | Granularity | Key columns |
|---|---|---|---|
| Crop history | `<loc>_crop.csv` | per Location/Year/Season/Crop | Yield_Kg_Ha, Water_Req_mm, Fertilizer_N/P/K_Kg_Ha, Pesticide_Cost_Rs_Ha, Labor_Days_Ha, MSP_Rs_Qtl, Rainfall_Dependency |
| Land & soil | `<loc>_land.csv` | per Location/Year/Season | Soil_Type, Avg_Soil_pH, Organic_Carbon_Percent, N/P/K_Status, Irrigation_Percent |
| Rainfall | `<loc>_rainfall.csv` | per Location/Year/**Month** | Monthly_Rainfall_mm, Deviation_Percent, Humidity_Percent, Min/Max_Temp_C |
| Water availability | `<loc>_water_availability.csv` | per Location/Year/**Month** | Storage_Percent, Groundwater_Status, Deficit_Surplus_MCM |

Two things worth knowing cold for the viva:

* **Season vocabulary differs across files.** `crop.csv`/`land.csv` use
  *agricultural* seasons (Kharif/Rabi/Summer). `rainfall.csv`/
  `water_availability.csv` are monthly and use *meteorological* seasons
  (Winter/Summer/Southwest Monsoon/Northeast Monsoon) which don't line up
  1:1 with the agricultural ones. `app/config.SEASON_MONTH_MAP` is the
  bridge: it defines which calendar months fall inside each agricultural
  season (e.g. Kharif = June-September), and `preprocessing.py` filters the
  monthly rainfall/water rows by `Month.isin(...)` rather than by their own
  `Season` column. This is a documented modelling assumption following the
  standard Tamil Nadu agricultural calendar, not a fact read off the CSVs.
* **Candidate crops are selected, not exhaustive.** For a given
  location/year/season there may be 5-11 crops on record. To keep the
  chromosome a manageable size and mirror the 3-crop-style combinations the
  reference paper reports, `preprocessing.get_region_season_profile` sorts
  by historical `Revenue_Rs_Lakh` and takes the top
  `config.DEFAULT_MAX_CANDIDATE_CROPS` (default 6, configurable per
  request via `max_candidate_crops`).

## 4. Stage 1 -- Preprocessing (`app/data/preprocessing.py`)

`get_region_season_profile(location, season, year)` returns a
`RegionSeasonProfile`: a `SoilProfile`, a `RainfallProfile`, a
`WaterProfile`, and a list of `CropCandidate` (one per candidate crop).

**Soil fertility index** (0-100), used later by the fuzzy engine:

```
ph_score   = clamp(100 - |pH - 6.5| * 40, 0, 100)      # 6.5 = agronomic optimum
oc_score   = clamp(organic_carbon% / 1.0 * 100, 0, 100) # 1.0% treated as "good"
npk_score  = mean(status_score(N), status_score(P), status_score(K))
             where status_score: Low->30, Medium->60, High->90
fertility_index = 0.3*ph_score + 0.3*oc_score + 0.4*npk_score
```

The 0.3/0.3/0.4 weighting gives NPK status slightly more say than either
pH or organic carbon alone, since it's a composite of three nutrients
already. This is a modelling choice, not a cited formula -- be ready to say
so plainly if asked.

**Effective rainfall.** Water need is offset by rainfall the crop can
actually use, not the raw rainfall total:

```
effective_rainfall_mm = avg_monthly_rainfall_mm * n_months_in_season * 0.7
```

The 0.7 (`config.RAINFALL_UTILIZATION_FACTOR`) accounts for runoff /
percolation / evaporation losses -- a standard simplifying assumption in
agronomic water-balance modelling (real usable-rainfall fractions vary by
soil and slope; we use one constant across the board).

**Normalisation.** `normalized_snapshot()` min-max scales the raw soil/
rainfall/water readings into [0,1] against fixed, domain-informed reference
ranges (e.g. pH 4-9, rainfall 0-150mm/month) -- this is what Section III-B
of the paper means by "numeric data are all scaled to [0,1] to make
dimensions comparable." It's for *display/transparency*, not fed into the
optimiser directly (the optimiser works in natural units -- tonnes, Rs,
litres -- because those are what a farmer actually reads off the result).

## 5. Stage 2 -- Fuzzy uncertainty modelling (`app/fuzzy/engine.py`)

This is a classic **Mamdani fuzzy inference system**, built with
`scikit-fuzzy`. Three crisp inputs come in, two crisp outputs come out; the
fuzzy machinery lives entirely between:

**Inputs (antecedents), each with 3 triangular membership functions:**

| Variable | Universe | Sets |
|---|---|---|
| `rainfall_dev` | Deviation_Percent, [-60,60] | deficit / normal / surplus |
| `water_storage` | Storage_Percent, [0,100] | low / medium / high |
| `soil_fert` | fertility_index, [0,100] | poor / medium / good |

**Outputs (consequents), each with 3 triangular membership functions:**

| Variable | Meaning | Sets |
|---|---|---|
| `yield_conf` | how much of the "book" yield to expect | low / medium / high |
| `irrigation_risk` | extra irrigation pressure this season | low / medium / high |

**Rule base** (14 rules, `app/fuzzy/engine.py::_build_system`), e.g.:

```
IF rainfall_dev IS deficit AND water_storage IS low
   THEN irrigation_risk IS high, yield_conf IS low

IF rainfall_dev IS normal AND water_storage IS medium
   THEN irrigation_risk IS low, yield_conf IS high

IF soil_fert IS good THEN yield_conf IS high
IF soil_fert IS poor THEN yield_conf IS low
```

**Inference & defuzzification.** scikit-fuzzy's `ControlSystemSimulation`
does Mamdani-style min-max inference (each rule's firing strength = min of
its antecedents' membership degrees; multiple rules affecting the same
output are combined with max) and defuzzifies with the **centroid method**
(the default) to produce one crisp number per output.

**Why Mamdani and not Sugeno?** Mamdani is more interpretable (both inputs
*and* outputs are linguistic, e.g. "high irrigation risk" is a real fuzzy
set you can plot) and is standard for expert-knowledge-driven rule bases
like this one, which is exactly what the paper specifies ("A Mamdani-type
fuzzy inference engine"). Sugeno (outputs as functions, not fuzzy sets) is
more common when you're tuning rules from data (e.g. ANFIS/neuro-fuzzy) --
not the case here.

**Per-crop adjustment.** The region-level `yield_confidence` is the same
for every crop in a season, but a drip-irrigated sugarcane and a rainfed
sorghum don't feel a rainfall deficit equally. `crop_yield_confidence()`
scales the penalty by the crop's own `Rainfall_Dependency` column
(Very Low/Low/Medium/High -> factor 0.1/0.3/0.6/1.0), capped at a 40%
maximum penalty:

```
penalty = irrigation_risk * dependency_factor * 0.4
crop_confidence = base_yield_confidence * (1 - penalty)
```

## 6. Stage 3 -- NSGA-II optimisation (`app/optimization/`)

### 6.1 Why NSGA-II

We have **4 objectives that genuinely conflict** (maximise yield vs.
minimise cost/water/impact) -- exactly the situation multi-objective
evolutionary algorithms exist for. A single-objective GA would need the 4
objectives collapsed into 1 (via arbitrary weights) *before* searching,
throwing away information about the trade-off curve. NSGA-II instead
searches for the whole **Pareto front** -- every solution where you
literally cannot improve one objective without making another worse -- and
hands the *set* to the decision-maker afterwards. That two-phase structure
(search first, decide later) is why Stage 4 (ranking) exists as a separate
step.

### 6.2 Core NSGA-II concepts (know these cold)

* **Pareto dominance**: solution A dominates B if A is at least as good as
  B on every objective and strictly better on at least one. Non-dominated
  = no other solution dominates it.
* **Fast non-dominated sorting**: splits the population into fronts
  (front 1 = non-dominated set, front 2 = non-dominated after removing
  front 1, etc.) in O(MN^2) time (M = objectives, N = population size).
* **Crowding distance**: within a front, estimates how "crowded" a
  solution's neighbourhood is (sum of normalised distances to its nearest
  neighbour on each objective). Larger crowding distance = more unique =
  preferred, when two solutions are on the same front. This is what keeps
  the final Pareto front *spread out* across the whole trade-off curve
  instead of clumped in one region.
* **Elitism**: parents and offspring are merged (2N individuals) and the
  best N survive by front rank then crowding distance -- good solutions
  are never lost between generations, unlike a plain GA.

Steps 2-4 (dominance sorting, crowding distance, elitist survival) are all
handled by pymoo's `NSGA2` algorithm class -- we didn't reimplement them,
because they're mechanical/well-established and reimplementing them
correctly (particularly crowding distance) is easy to get subtly wrong. We
*did* implement our own genetic operators (see below) to match the paper's
stated parameters exactly.

### 6.3 Chromosome (decision variable) encoding

For `n` candidate crops, a chromosome is a real-valued vector of length
`3n`:

```
[ alloc_0 .. alloc_{n-1} | irrigation_mult_0 .. irrigation_mult_{n-1} | fertilizer_mult_0 .. fertilizer_mult_{n-1} ]
```

* `alloc_i` in [0,1]: fraction of the farmer's total land given to crop i.
  Repaired after every generation (`AllocationRepair`) to sum to 1 -- a
  farmer can't plant 140% of their land.
* `irrigation_mult_i` in [0.7, 1.3]: multiplier on crop i's baseline
  `Water_Req_mm`. Lets the optimiser under/over-irrigate relative to the
  textbook value.
* `fertilizer_mult_i` in [0.7, 1.3]: multiplier on crop i's baseline NPK
  dose.

This is the paper's "vector of decision variables: the allocation of crops
per plot, amount of irrigation per crop, type and amount of fertilizer
applied" (harvest timing is taken directly from the dataset's
Sowing/Harvest month rather than optimised -- a scoped-down simplification
worth naming proactively if asked, see `viva_prep.md`).

### 6.4 Genetic operators (`app/optimization/operators.py`)

Implemented from scratch (not pymoo's default SBX/polynomial-mutation) to
match the paper's Section III-D literally:

* **`SinglePointCrossover(prob=0.85)`** -- picks one random cut point along
  the 3n-length chromosome, swaps the tails of two parents.
* **`GaussianMutation(prob=0.12, sigma=0.12)`** -- each gene independently
  has a 12% chance of receiving `N(0, sigma * gene_range)` noise, then
  clipped back to its bounds.
* **`AllocationRepair`** -- runs after crossover/mutation every generation;
  renormalises the allocation block to sum to 1 (preserving relative
  ratios) and clips all genes back into bounds. This is what keeps every
  individual in the population *feasible* (in the land-allocation sense)
  at all times.

### 6.5 The four objectives (`app/optimization/problem.py::_evaluate`)

All four are computed vectorised across the whole population at once (no
per-individual Python loop) for speed -- a full 80-population, 200-
generation run completes in well under a second.

1. **Yield** (maximise, stored as `f1 = -yield_tonnes`):
   `sum_i( area_i * yield_kg_ha_i / 1000 * crop_confidence_i )` -- the fuzzy
   `crop_yield_confidence` from Stage 2 scales down the "book" yield to an
   *expected* yield under this season's uncertainty.

2. **Cost** (minimise, Rs):
   `sum_i( area_i * (fert_mult_i * fertilizer_cost_i + pesticide_cost_i + labor_days_i * wage) )`
   where `fertilizer_cost_i = N_i*6.5 + P_i*27 + K_i*17` (Rs per kg
   nutrient -- see Section 8, Assumptions).

3. **Water** (minimise, litres):
   `sum_i( area_i * irrigation_mult_i * max(water_req_mm_i - effective_rainfall_mm, 0) * 10,000 )`
   -- only the *irrigation gap* (crop need minus what the season's rainfall
   already supplies) counts, converted to litres via the standard
   1mm-over-1ha = 10,000L identity.

4. **Environmental impact** (minimise, unitless score):
   `sqrt(leaching_total * carbon_total)` where `leaching_total` is the
   area-weighted nitrogen applied (N is the most leach-prone nutrient) and
   `carbon_total` is a synthetic proxy combining fertilizer load and
   irrigation volume. The paper defines this objective as "the product of
   the chemical leaching risk and carbon emission proxies"; we take the
   **square root of that product** (a geometric mean) so the composite
   stays in the same order of magnitude as either component instead of
   blowing up as a squared unit -- a deliberate, documented deviation, not
   an oversight.

A 5th quantity, **budget**, is an optional inequality constraint
(`out["G"] = cost - budget_rs`), not an objective -- the farmer's budget is
a hard limit, not something to be traded off against yield.

### 6.6 Hyperparameters

`app/config.py`: population 80, generations 200, crossover probability
0.85, mutation probability 0.12 -- the last three lifted directly from the
paper. Population size (80) is our own choice, large enough to keep the
Pareto front well populated (paper reports 20-50 final solutions; we
typically retain the full population since `eliminate_duplicates=True`
already prunes exact duplicates).

**Reproducibility.** `run_nsga2()` explicitly calls `np.random.seed(seed)`
before constructing the algorithm, because our custom operators draw from
the plain NumPy global RNG rather than whatever internal RNG pymoo wires up
internally for its own default operators. Without this, the *same* problem
and seed could silently produce different Pareto fronts across separate
process runs -- verified during development (see git history / dev notes)
and fixed before this was relied on for any weight-tuning decisions.

### 6.7 Convergence tracking -- proving the algorithm actually converges

Early versions of this system only ever looked at the *final* generation's
Pareto front -- which runs, but gives no evidence NSGA-II actually improved
anything over its 200 generations rather than, say, the first generation's
random population already happening to be fine. `run_nsga2(...,
track_history=True)` now asks pymoo to snapshot the surviving population at
every generation (`save_history=True`), and
`extract_convergence_history(result)` (`app/optimization/nsga2_runner.py`)
turns that into one record per generation: the best and mean of every raw
objective across that generation's population, plus a **hypervolume**
indicator.

**Hypervolume**, in one line: the volume of objective space dominated by
the current Pareto front, relative to a fixed reference point that's
deliberately worse than every solution ever seen. It is *the* standard
scalar quality metric for a multi-objective front (unlike a single
objective's best value, it rewards both convergence *and* spread/diversity
across all 4 objectives at once). We normalise every objective to [0,1]
first (using the min/max observed across the *entire* run, held fixed) --
without this, the wildly different natural scales of yield (tens),
cost (hundreds of thousands), water (millions) and env-impact (hundreds)
would make a raw hypervolume number meaningless, dominated entirely by
whichever objective happens to have the largest absolute range. Reference
point: `(1.1, 1.1, 1.1, 1.1)` in normalised space -- slightly outside the
worst value seen on every objective, as the hypervolume definition
requires.

A real run (`results/*_convergence.png`) shows hypervolume climbing sharply
for the first ~30 generations then plateauing around 0.49-0.51 -- textbook
NSGA-II behaviour: fast early improvement while the population is still
finding the general shape of the trade-off surface, followed by
fine-grained refinement with diminishing returns. That plateau is itself
evidence 200 generations is enough for this problem size; if hypervolume
were still climbing steeply at generation 200, that would be the signal to
increase `NSGA2_N_GEN`.

Cost: history tracking makes a run ~2-3x slower (deep-copying the
population every generation) -- still under ~1.2s at the paper's
pop=80/gen=200 settings, but it's off by default (`track_history=False`)
for quick/test runs and only switched on when a run is actually going to be
persisted (see Section 8).

## 7. Stage 4 -- Decision output (`app/decision/ranking.py`)

NSGA-II returns a *set*; something still has to pick an order. We use
**TOPSIS** (Technique for Order Preference by Similarity to Ideal
Solution):

1. Normalise each objective across the returned plan set to a 0-1
   "goodness" score (`_minmax_norm`, higher is always better after this
   step).
2. Multiply by a preference-specific weight vector (`balanced`,
   `max_yield`, `min_cost`, `min_water`, `min_env_impact`).
3. Find the ideal point (best score achieved on each objective, across the
   set) and the worst point (worst score on each).
4. For every plan, compute Euclidean distance to both.
5. `closeness = distance_to_worst / (distance_to_best + distance_to_worst)`
   -- ranges 0-1, higher = better. Sort descending.

**Why TOPSIS and not a plain weighted sum?** We measured yield correlating
0.7-0.85 with cost/water/env in this dataset (more land and inputs raises
all four at once) -- three of the four objectives are, in effect,
redundant proxies for "resource intensity." A naive equal weighted sum lets
those three outvote yield 3-to-1, so the "balanced" #1 pick collapsed to a
minimal-input corner solution (tiny yield, tiny everything else) -- not
what a farmer would call "balanced." Weighting yield as its own group,
comparable in total weight to the footprint group (`0.30` vs.
`0.70/3 ≈ 0.233` each -- see `ranking._PREFERENCE_WEIGHTS`), was tuned
empirically against the actual Pareto front until the "balanced"
recommendation genuinely sits in the *middle* of the yield/cost/water/env
range, mirroring how the reference paper itself highlights a deliberately
balanced "Plan #1 (Best)" rather than either extreme of its own results
table.

**Trade-off text.** Deliberately computed from a *separate*, non-flipped
min-max bucket (`_plain_minmax`) rather than the TOPSIS goodness scores --
otherwise "Low cost" could accidentally mean "scored low on the cost
objective" (i.e. *expensive*) instead of "is cheap." Worth checking this
distinction is understood if asked, it's an easy trap.

## 8. Results persistence -- "store the results in a file"

Every run through `plan_service.generate_farm_plans()` (API, CLI, or
direct call) writes its results to disk under `results/` by default
(`FarmPlanRequest.save_results`, default `true`) via
`app/services/results_store.py`. One run, one `run_id`
(`<location>_<season>_<year>_<UTC-timestamp>`), up to four files:

| File | Contents |
|---|---|
| `<run_id>.json` | The complete API response -- region profile, fuzzy assessment, every ranked plan, run metadata -- **plus** the full per-generation convergence history embedded under `convergence_history`. The one-stop record of a run. |
| `<run_id>_plans.csv` | The ranked plan table flattened to one row per plan (rank, crop mix, yield/cost/water/env, trade-off summary) -- opens directly in Excel/Sheets for the report. |
| `<run_id>_convergence.csv` | One row per generation (best/mean of each objective, hypervolume) -- the raw numbers behind the convergence chart. |
| `<run_id>_convergence.png` | The two-panel chart described in Section 6.7 (hypervolume, and best yield/cost) vs. generation. |

Why files and not a database: this was an explicit requirement, not a
default choice -- results are meant to be inspectable, versionable
(committable to git as evidence of runs) and directly attachable to a
report, none of which a database naturally gives you at this project
stage. `GET /api/results` (list) and `GET /api/results/{run_id}` (full
record) expose the same saved runs over the API without needing direct
filesystem access -- see `app/main.py`.

`generate_farm_plans(request, results_dir=...)` accepts an override
directory (used by the test suite to write into a temp directory instead
of the real `results/` folder, keeping `pytest` side-effect-free) --
callers going through the API/CLI always use `app/config.RESULTS_DIR`
(`results/` at the project root).

## 9. Assumptions -- the definitive list

Everything below is a modelling assumption, not a number read from the
dataset. All live in `app/config.py` with inline comments; collected here
for one-stop reference.

| Assumption | Value | Used for |
|---|---|---|
| Urea (N) price | Rs 6.5/kg nutrient | cost objective |
| DAP (P) price | Rs 27/kg nutrient | cost objective |
| MOP (K) price | Rs 17/kg nutrient | cost objective |
| Labour wage | Rs 400/day | cost objective |
| Rainfall utilisation factor | 0.7 | effective rainfall (water objective) |
| 1mm over 1ha = 10,000L | fixed unit conversion, not an assumption | water objective |
| Carbon-per-NPK factor | 0.15 | environmental impact objective |
| Carbon-per-irrigation-mm factor | 0.01 | environmental impact objective |
| Rainfall dependency -> risk factor | Very Low 0.1 / Low 0.3 / Medium 0.6 / High 1.0 | fuzzy per-crop yield adjustment |
| Soil fertility weights | pH 0.3, organic carbon 0.3, NPK 0.4 | fertility index |
| Season-to-months mapping | Kharif=Jun-Sep, Rabi=Oct-Mar, Summer=Feb-May | aligning monthly rainfall/water data to cropping seasons |
| "Balanced" preference weight split | yield 0.30, others 0.233 each | TOPSIS ranking |

## 10. Known limitations / good-faith answers if asked

* **Not per-plot.** Decisions are region/season-level allocation fractions,
  not literal per-plot GPS assignments (the dataset is aggregate district
  statistics, not per-farm plot records).
* **Harvest timing isn't optimised**, only sourced from the dataset's fixed
  Sowing/Harvest month columns -- a scoped-down version of the paper's full
  "harvest timing schedule" decision variable.
* **Economic constants are approximate market rates**, not live prices --
  flagged clearly in `config.py` and swappable in one place.
* **4 years of rainfall history**, not the "at least five years" the paper
  mentions as typical -- the dataset covers 2020-2023.
* **No live weather API integration yet** -- rainfall/water figures are the
  dataset's historical records for the selected year, not a real-time
  forecast.
* **Frontend is not built yet** -- deliberately deferred until the UI is
  finalised; the API (`/docs`) and CLI (`run_demo.py`) are the current
  interface.
