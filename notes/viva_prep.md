# AgroOptimize -- Viva / Review Prep (Q&A)

Companion to `methodology_notes.md`. That file explains *what the system
does and why*; this one is drilling material -- likely questions, with
answers short enough to say out loud in 15-30 seconds. Read
`methodology_notes.md` first if a concept here feels unfamiliar.

---

## Cram sheet (memorise these numbers)

- **4 objectives**: yield (maximise), cost, water use, environmental impact
  (all minimise).
- **NSGA-II params**: population 80, 200 generations, single-point
  crossover p=0.85, Gaussian mutation p=0.12.
- **Chromosome length**: `3n` for `n` candidate crops (allocation +
  irrigation multiplier + fertilizer multiplier per crop).
- **Fuzzy engine**: 3 inputs (rainfall deviation, water storage, soil
  fertility), 2 outputs (yield confidence, irrigation risk), 14 Mamdani
  rules, triangular membership functions, centroid defuzzification.
- **Dataset**: 4 locations (Coimbatore, Erode, Salem, Pollachi) x 4 years
  (2020-2023) x 3 seasons (Kharif, Rabi, Summer), 4 CSV kinds per location
  (crop, land/soil, rainfall, water availability).
- **Ranking method**: TOPSIS over the Pareto front, 5 preference modes.
- **Convergence evidence**: hypervolume indicator tracked every generation
  (normalised, ref point 1.1/1.1/1.1/1.1); typically rises fast for ~30
  generations then plateaus -- see any `results/*_convergence.png`.
- **Results persistence**: every run writes to `results/` -- full JSON,
  ranked-plans CSV, convergence CSV, convergence PNG. Also browsable via
  `GET /api/results` and `GET /api/results/{run_id}`.
- **Stack**: Python, FastAPI, pymoo (NSGA-II), scikit-fuzzy (Mamdani FIS),
  pandas/numpy, matplotlib.
- **Tests**: 34 automated tests, all passing (`pytest -v`).

---

## Foundational theory

**Q: What is a multi-objective optimisation problem, and why not just
combine the 4 objectives into 1 with weights and use a normal GA?**
Because the "right" weights aren't known in advance and change per farmer
(some care more about cost, some about yield). Collapsing objectives into
one score before searching throws away the trade-off information -- you'd
only ever see the single solution matching *your* guessed weights, with no
visibility into what you gave up. NSGA-II searches for the whole Pareto
front once, and weighting/choosing happens afterwards, as a separate,
transparent step (our TOPSIS ranking stage) -- so different farmers, or the
same farmer with different priorities, can reuse the *same* optimisation
run.

**Q: What is Pareto dominance / a Pareto-optimal solution?**
Solution A dominates solution B if A is at least as good as B on every
objective and strictly better on at least one. A solution is Pareto-optimal
(non-dominated) if no other feasible solution dominates it -- improving any
one objective from there necessarily makes another objective worse.

**Q: Walk me through NSGA-II in your own words.**
Start with a random population. Each generation: create offspring via
crossover + mutation, merge parents and offspring (2N individuals), sort
them into fronts by Pareto dominance (front 1 = non-dominated, front 2 =
non-dominated after removing front 1, etc.), then fill the next
generation's N slots front-by-front; if a front doesn't fully fit, use
crowding distance to keep the most spread-out individuals from that front.
Repeat for the set number of generations. The "NSGA" in the name means
Non-dominated Sorting Genetic Algorithm; "II" is Deb et al.'s 2002
improvement over the original NSGA (mainly: elitism, and crowding distance
replacing the older, slower fitness-sharing niching method).

**Q: What is crowding distance and why does it matter?**
For each solution in a front, it's the sum (across all objectives) of the
normalised distance to its two nearest neighbours in that front. High
crowding distance = solution sits in a sparse region = kept preferentially
when a front has to be trimmed. Without it, NSGA-II could converge to a
tight cluster on one part of the Pareto front and lose diversity -- you'd
get 80 nearly-identical "high yield" plans instead of a spread from
low-input to high-input.

**Q: What is hypervolume, and why did you add it?**
The volume of objective space that a Pareto front dominates, measured
against a fixed reference point that's deliberately worse than every
solution seen. It's the standard single-number quality metric for a
multi-objective front because, unlike tracking one objective's best value,
it rewards both convergence *towards* the true front *and* spread/diversity
*across* it simultaneously -- a front that's excellent on yield but
collapsed to one point is not rewarded, correctly. We added it
(`extract_convergence_history`, tracked per generation via
`save_history=True`) specifically to have real evidence the algorithm
converges rather than just trusting the final generation looks reasonable
-- a real run's hypervolume climbs sharply for ~30 generations then
plateaus, the textbook NSGA-II signature (see any
`results/*_convergence.png`).

**Q: What is elitism in this context?**
Parents and offspring compete together for survival (2N -> N), so a good
solution found in generation 5 can never be lost just because generation 6
happened to produce weaker offspring. The original NSGA (1994) didn't do
this and converged slower / less reliably.

**Q: Why single-point crossover and Gaussian mutation specifically,
instead of pymoo's defaults (SBX, polynomial mutation)?**
Because the reference paper states those exact operators and probabilities
(single-point crossover p=0.85, Gaussian mutation p=0.12). We implemented
them from scratch as custom pymoo `Crossover`/`Mutation` subclasses
(`app/optimization/operators.py`) specifically so the algorithm matches the
paper's stated design rather than silently using different default
operators.

**Q: What is fuzzy logic, in one sentence?**
A way of reasoning with degrees of truth (e.g. "60% moderate, 40% dry")
instead of forcing every input into one exact category, which suits
real-world agricultural readings like "rainfall was a bit below normal."

**Q: Walk me through fuzzification -> inference -> defuzzification.**
Fuzzification converts a crisp input (e.g. rainfall deviation = -15%) into
membership degrees across overlapping fuzzy sets (e.g. 0.4 "deficit", 0.6
"normal") using membership functions. Inference applies the rule base:
each rule's firing strength is the min of its antecedents' membership
degrees (Mamdani AND = min), and when multiple rules affect the same
output fuzzy set, they're combined with max. Defuzzification converts the
resulting output fuzzy set back into one crisp number -- we use the
centroid method (the "center of mass" of the aggregated output membership
function), scikit-fuzzy's default.

**Q: Why triangular membership functions and not trapezoidal or
Gaussian?**
Triangular functions are the simplest to define, interpret, and justify to
a non-technical stakeholder (three points: where membership starts, peaks,
ends), and are standard for expert-authored rule bases where you don't have
enough data to statistically fit a more complex shape. The reference paper
explicitly allows both triangular and trapezoidal; we used triangular
uniformly for consistency across all five linguistic variables.

**Q: Why Mamdani inference instead of Sugeno?**
Mamdani produces fuzzy (linguistic) outputs that get defuzzified, which is
more interpretable and better suited to a hand-authored, expert-knowledge
rule base -- you can literally read a rule as "if rainfall is deficient and
storage is low, irrigation risk is high." Sugeno represents outputs as
mathematical functions of the inputs, which is more common when rules are
learned/tuned from data (e.g. ANFIS). The paper specifies "a Mamdani-type
fuzzy inference engine," and our use case (encoding domain-expert
heuristics) fits Mamdani's strengths.

---

## Project-specific

**Q: What are your four objectives, precisely, and which direction does
each optimise?**
1) Expected yield in tonnes (maximise) -- crop yield scaled by land
allocated and the fuzzy-adjusted confidence factor. 2) Total production
cost in Rs (minimise) -- fertilizer + pesticide + labour. 3) Total
irrigation water in litres (minimise) -- only the gap between crop water
need and effective rainfall. 4) Environmental impact score (minimise) --
geometric mean of a nitrogen-leaching proxy and a carbon-emission proxy.

**Q: What exactly is a "chromosome" here? What does one individual in the
population represent?**
One complete candidate farm plan: for each of the `n` candidate crops, what
fraction of the land to give it, how much to scale irrigation relative to
the textbook requirement, and how much to scale fertilizer dose. Length
`3n`. Decoding a chromosome (`FarmPlanProblem.decode`) turns it back into
crop names, hectares per crop, and multipliers.

**Q: Why is land allocation "repaired" instead of just being a normal
mutated gene?**
Because crossover and mutation operate gene-by-gene with no awareness that
the allocation genes must sum to 1 (a farmer's land can't sum to more or
less than 100% across crops). `AllocationRepair` runs after every
crossover/mutation step and renormalises just that block, preserving
relative ratios between crops rather than clipping arbitrarily. Without it,
most of the population would represent physically impossible plans.

**Q: How does the fuzzy engine's output actually affect the optimisation,
concretely?**
Two ways. First, `yield_confidence` (per crop, adjusted by that crop's
rainfall dependency) directly scales down the yield objective -- a season
assessed as risky produces lower *expected* yield for the same allocation,
so the optimiser naturally favours safer crops/allocations under bad
conditions. Second, `irrigation_risk` doesn't currently rescale the water
objective directly (that's driven by the effective-rainfall calculation
instead) -- it's exposed in the API response as a farmer-facing risk
signal and feeds the per-crop confidence penalty. Be upfront about this
split if asked exactly where each fuzzy output is consumed.

**Q: What happens if the farmer's budget makes the problem infeasible (no
plan fits)?**
The budget is encoded as a pymoo inequality constraint
(`G = total_cost - budget <= 0`). If NSGA-II can't find any feasible
individual, `extract_pareto_plans` still returns solutions but flags
`feasible=False`; `plan_service.generate_farm_plans` filters those out
before ranking, so an over-tight budget currently yields an *empty* plan
list rather than a crash. (Documented current behaviour -- a nice concrete
"future work" answer is: surface a clear "no feasible plan under this
budget, nearest feasible cost is X" message instead of an empty list.)

**Q: How do you know the algorithm is actually working, not just running
without crashing?**
Four lines of evidence: (1) 34 automated tests check specific invariants
-- allocation fractions sum to 1, all areas fit within the farmer's land,
cost stays within budget when one is given, output ranges are sane; (2)
qualitative sanity check -- `max_yield` preference reliably returns
higher-yield/higher-cost plans than `min_cost`, which returns the cheapest
corner of the same Pareto front (same optimisation run, different ranking);
(3) reproducibility -- the same problem + seed produces an identical Pareto
front across separate runs (verified explicitly during development after
finding and fixing a random-seed propagation bug, see `methodology_notes.md`
Section 6.6); (4) convergence evidence -- hypervolume tracked every
generation rises sharply then plateaus around generation 30-40 (the
textbook NSGA-II signature), saved to `results/*_convergence.png` /
`*_convergence.csv` for every run, not just asserted.

**Q: Why does "balanced" not just average the objectives 25/25/25/25?**
Empirically, yield correlates 0.7-0.85 with the other three objectives in
this system (more land + inputs raises yield *and* cost *and* water *and*
impact together), so treating all four as independent, equally-weighted
criteria lets cost/water/impact gang up 3-to-1 against yield -- the
"balanced" pick collapsed to a near-zero-yield corner, which no farmer
would actually call balanced. We weight yield as its own group (30%)
against the footprint group as a whole (70% split three ways), tuned
against the actual Pareto front until the top pick sits genuinely in the
middle of the range on every objective. Full derivation in
`methodology_notes.md` Section 7.

**Q: Why TOPSIS instead of just sorting by a weighted sum?**
A weighted sum has the same "correlated objectives" problem described
above, plus a subtler one: it can only ever favour points on the *convex
hull* of the objective space, so it can systematically miss well-balanced
solutions that aren't on that hull. TOPSIS instead ranks by geometric
closeness to an ideal point and distance from a worst point, which handles
non-convex regions of the front better and is a standard, literature-cited
technique for post-processing NSGA-II Pareto fronts specifically because
of this.

**Q: Your yield/cost/water numbers -- are they real or synthetic?**
Yield, water requirement, fertilizer dose, pesticide cost and labour are
read directly from the district-level historical dataset (`data/raw/`,
sourced per-crop per-season per-year). What's *assumed* on top of that is
the economic conversion layer -- fertilizer Rs/kg nutrient prices, labour
daily wage, and the environmental-impact proxy constants -- because the
dataset gives physical quantities (kg of N applied) but not a canonical
market price for them. Full list in `methodology_notes.md` Section 8; all
centralised in `app/config.py` so they're one-line changes if given better
figures.

**Q: Why these four districts / why this dataset at all?**
Coimbatore, Erode, Salem and Pollachi are neighbouring Tamil Nadu
agricultural districts with meaningfully different soil types (Red Sandy
Loam, Red Laterite, Red Loam) and rainfall/water profiles, giving the
system genuine cross-region variation to demonstrate the fuzzy engine and
optimiser responding differently -- rather than one location where results
would look the same regardless of the algorithm.

**Q: How did you handle the mismatch between crop.csv's agricultural
seasons and rainfall.csv's monthly/meteorological seasons?**
Built an explicit season-to-months mapping (`config.SEASON_MONTH_MAP`,
e.g. Kharif = June-September) and aggregate the monthly rainfall/water
rows by `Month.isin(...)` rather than trusting their own `Season` label,
which uses a different vocabulary (Winter/Monsoon/etc.). This is a
documented assumption following the standard regional cropping calendar,
not an exact scientific mapping -- there's inherent overlap at season
boundaries (e.g. February appears in both Rabi and Summer's month lists).

**Q: What's the time complexity, and how fast does it actually run?**
NSGA-II's non-dominated sorting is O(M x N^2) per generation (M=4
objectives, N=population=80), so about O(M x N^2 x G) = O(4 x 6400 x 200)
≈ 5.1M comparisons for a full run -- but because our objective evaluation
is fully vectorised with numpy (no per-individual Python loop), a complete
80-population/200-generation run measures well under a second in practice
(~0.5s), and the full API round-trip test (`tests/test_pipeline.py`) is
part of a 29-test suite that runs in under 2 seconds total.

**Q: What's not implemented yet / what would you do next?**
Frontend (deliberately deferred until the UI design is finalised -- this
API is designed to be consumed by it), per-plot (rather than region-level)
granularity, live weather API integration instead of historical CSVs,
calibrating the economic assumption constants against real supplier
quotes, and a clearer "infeasible budget" response instead of an empty
plan list. See `methodology_notes.md` Section 9 for the full, honest list
-- naming these proactively lands much better than being asked and
backpedaling.

**Q: How is this different from just using a normal Genetic Algorithm
tuned by hand for one objective?**
Two independent upgrades, both in the reference paper's title: (1)
multi-objective search (NSGA-II) instead of collapsing to one objective
up front, so the *farmer* chooses the trade-off after seeing real options
instead of the *developer* guessing weights beforehand; (2) explicit
uncertainty modelling (fuzzy logic) instead of treating rainfall/soil
readings as exact, so a "slightly below normal" rainfall season doesn't
get rounded to either "normal" or "drought" and lose the nuance in
between.

---

## Rubric-aligned questions (Guide Review 1 / Panel Review 1 framing)

**Q: What's your research gap / what's novel here versus the literature
you reviewed?**
Most existing agricultural decision-support systems address optimisation
*or* uncertainty, not both together (see Related Works in the paper --
refs [1]-[20] mostly do one or the other). This system combines a Mamdani
fuzzy inference layer for uncertainty with NSGA-II multi-objective search
for optimisation in a single pipeline, and grounds it in real multi-year,
multi-district agricultural data rather than a synthetic example.

**Q: What's your evaluation strategy?**
Automated correctness tests (invariants: feasibility, allocation sums,
budget respect, sane output ranges) across all 4 locations x 3 seasons (12
combinations); qualitative validation that different preference modes
(`max_yield`/`min_cost`/`balanced`/etc.) produce meaningfully different,
internally consistent recommendations on the *same* Pareto front;
reproducibility checks (same seed -> same result). Longer-term: compare
recommended plans against the historical actual-outcome data already in
the dataset (e.g. did seasons flagged "high irrigation risk" by the fuzzy
engine correlate with years where `Deviation_Percent` was actually very
negative?).

**Q: What have you actually implemented so far (for the "Initial
Implementation Progress" rubric line)?**
Full backend: data loading/preprocessing for all 16 CSVs, the complete
fuzzy inference engine, a from-scratch NSGA-II with custom operators
matching the paper's parameters plus per-generation convergence/hypervolume
tracking, TOPSIS-based decision ranking, a file-based results persistence
layer (JSON + CSV + convergence chart per run), a REST API with 6 endpoints
plus interactive Swagger docs, a CLI demo, and a 34-test automated suite
covering every module and the full end-to-end flow, including persistence.
Not yet implemented: the frontend (intentionally sequenced after
backend/UI finalisation).

**Q: Can you demo it right now?**
Yes, two ways: `python3 run_demo.py --location <X> --season <Y> --land
<Z> --budget <B>` prints a full run to the terminal with no server needed
and saves it to `results/`; or `uvicorn app.main:app --reload` + open
`/docs` for a live, clickable Swagger UI to run requests, see raw JSON
responses, and browse past runs via `GET /api/results`.

---

## Things to have open / ready during the review

- `run_demo.py` output for at least two different `--preference` values on
  the same location/season, to show the trade-off visibly.
- One `results/*_convergence.png` open, to show hypervolume actually
  climbing and plateauing -- the single most convincing image if a panel
  asks "how do you know it converged."
- `pytest -v` output (34 passed).
- `app/config.py` open, to point at the assumption constants directly if
  asked "where does this number come from."
- This file and `methodology_notes.md`.
