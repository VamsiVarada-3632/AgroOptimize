# Research Review (examiner's perspective)

Reviewed against the team's paper (`reference_docs/Reference_Paper_AgroOptimize.pdf`), the Phase-2 rubric, and the actual code and data. Every quantitative claim here was measured on 2026-09-29.

## 1. Overall assessment

The **engineering** is well above typical final-year level: a clean layered pipeline, a working full-stack deployment, 205 automated tests, reproducible seeded runs, convergence evidence, and unusually honest in-code documentation of assumptions. The **research** claims are weaker than the engineering: the optimisation model has a structural defect that makes two of its three decision-variable blocks inert, the fuzzy layer can only rescale yield, and the dataset shows clear signs of being synthetic while the paper describes it as government data. None of this is hidden by the code – an examiner who reads it will find it. The team should present these openly as limitations with a concrete fix plan rather than be surprised by them.

## 2. Rubric mapping (Phase 2, research-based)

| Rubric item | Evidence in repo | Risk |
|---|---|---|
| Problem statement & gap | `docs/problem_statement.md`, `docs/literature_survey.md` (5 verified papers) | Gap statement says "validated on real Tamil Nadu data" – not supportable today (§5) |
| Methodology (workflow, algorithms, maths, datasets, evaluation) | Methodology notes, this docs set | Evaluation strategy is thin: no baseline other than fuzzy on/off; no quantitative comparison against the paper's results |
| Implementation ≈60 % / 85–90 % | End-to-end backend + frontend + deployment + tests | Strong |
| Preliminary verification & results | Hypervolume convergence, saved runs, results write-ups | Write-ups are from an older dataset (not reproducible now); no statistical robustness (multiple seeds) |
| Technical knowledge / viva | viva_prep.md | Several prepared answers are now inaccurate (14 vs 26 rules, 34 tests, old prices, "real data") |

## 3. Paper vs implementation

| Paper claims | Implementation | Gap |
|---|---|---|
| Fuzzy MFs "triangular and trapezoidal"; soil moisture with 5 sets (Very Dry…Wet) | 5 variables × 3 triangular sets; no soil-moisture variable | Different model |
| Fuzzy + "probability theory"; outputs are "scenario probability weights" | Two crisp scalars; no probabilities or scenarios | Not implemented |
| Chromosome includes "type and amount of fertilizer" and "harvest timing schedule" | Amount multiplier only; no fertiliser type; no timing | Partially |
| "Allocation of crops per plot" | Land shares of one farm; no plots | Different granularity |
| "Numeric data scaled to [0,1] … between the optimization calculations" | Scaling only for display; optimiser uses natural units | Differs |
| NSGA-II, 200 generations, single-point crossover p=0.85, Gaussian mutation p=0.12 | Exactly as stated | ✔ |
| "Final set of 20 to 50 Pareto-optimal plans" | 80–100 non-dominated, 50/100 returned | Close |
| "Confidence interval of robustness" per plan; "Min/Max yield" columns in Table II | Categorical confidence label only; no yield range | Not implemented |
| Parallel-coordinates visual; printable one-page report with irrigation schedules | Scatter + radar; plain-text report; generic 2-step template | Partially |
| Results: 5-acre farm, ~2.2 crore L, Sugarcane + Wheat + Groundnut ≈40 t/ha, 100 plans | Current code/data produce different mixes (e.g. Salem Kharif: Tapioca-dominant, 12.95 t/ha) | Paper results not reproducible from this code/data |
| Reference [2]: Huang et al., *Sustainability* 17(7) 2829 | Repo's literature survey lists Huang et al. in *Scientific Reports* 15:34070 and gives *Sustainability* 17(7) 2829 to Erdoğdu et al. | Citation inconsistency – verify and correct |

## 4. Technical correctness of the model

| # | Issue | Evidence | Consequence | Fix |
|---|---|---|---|---|
| R-1 | Irrigation and fertiliser multipliers have no benefit | f1 has no multiplier term; f2–f4 increase with them | 74–99 % of fertiliser genes and 52–100 % of irrigation genes end at the 0.7 floor; two-thirds of the chromosome is effectively inert | Yield response: FAO-33 water-production function `1 − Ya/Ym = Ky (1 − ETa/ETm)` for irrigation; Mitscherlich or quadratic-plateau response for N |
| R-2 | Yield objective sums tonnes of different crops | sugarcane ≈95 t/ha vs cotton 1.5 t/ha | Optimiser favours heavy crops; "t/ha" of a mix is not meaningful to farmers | Maximise net return (yield × price − cost) – `MSP_Rs_Qtl` already exists – or calorie/protein output |
| R-3 | Fuzzy output only rescales yield per crop | compare-fuzzy: identical min-cost/min-water/min-impact in both arms | The "fuzzy vs non-fuzzy study" mostly shows yield multiplied by the crop confidence (≈0.44–0.88; Salem Kharif best yield 13.96 vs 26.96 t/ha) | Let uncertainty act on water need (irrigation_risk → effective rainfall) and on feasibility; or optimise expected value over rainfall scenarios |
| R-4 | 5 of 26 fuzzy rules have zero effect; rules cannot "cap" outputs under max aggregation | rule-deletion experiment (ALGORITHMS §2.2) | Rule-count claims overstate the model; rule comments misdescribe behaviour | Remove or rewrite; state "21 effective rules" |
| R-5 | Seasonal deviation = mean of monthly percentages; Rabi spans two different seasons | DATA_VALIDATION D5–D6 | irrigation_risk shifts up to 0.21 | totals-based deviation; Oct(Y)–Mar(Y+1) |
| R-6 | Hypervolume normalised per run | ALGORITHMS §4.4 | HV values can't be compared across runs/variants | fixed global normalisation bounds; report HV of fuzzy vs non-fuzzy on the same scale |
| R-7 | Only one seed per result | – | No evidence of robustness | 20–30 seeds, report mean ± sd HV and front statistics |
| R-8 | 4 objectives with NSGA-II; no baseline algorithm | – | Examiners commonly ask "why not NSGA-III/MOEA-D?" | Add NSGA-III (pymoo) and an exact ε-constraint LP baseline for f1–f3 |
| R-9 | Env. impact formula: √(N-leaching × carbon proxy) with arbitrary factors; carbon uses gross, not net, water | CONFIGURATION §2 | Units undefined | Report as index; or use IPCC EF1 for N₂O-CO₂e and pump energy for CO₂ |
| R-10 | Cost excludes water, energy, seed, machinery | f2 | Underestimates cost; the unwired water cost exists | include CACP cost-of-cultivation components |
| R-11 | Perennial crops (coconut, mango, banana, sugarcane) allocated as single-season options | DATASETS §2 | Agronomically invalid mixes | constrain perennials or model multi-season |

## 5. Dataset quality and scientific validity
See [DATA_VALIDATION.md](DATA_VALIDATION.md). The decisive points: 2024 is synthetic and the default; storage is identical every year; yields flat 2020–23; rainfall normals are season-flat; provenance is "course-provided". With inputs that barely vary year to year, the system cannot demonstrate *uncertainty handling* on real variability. **The paper and literature survey must not describe this as government or real observed data unless the source is confirmed.**

## 6. Reproducibility

| Aspect | Status |
|---|---|
| Deterministic runs (seed 42) | ✔, now also under concurrent requests |
| Environment | ✘ no lock file; Python 3.11 (Docker) vs 3.13 (dev) |
| Data versioning | ✘ two diverging dataset copies; reported results from an older version |
| Scripts to regenerate every figure/table | Partial (`run_demo.py`; no script regenerating the paper tables) |
| Tests | ✔ 205 |

## 7. Novelty
Combining a Mamdani FIS with NSGA-II and TOPSIS for crop planning is a known pattern (the survey itself cites Fuzzy-Expert-NSGA-II and fuzzy-GA work). Defensible novelty is **contextual and engineering**: a complete, open, tested decision-support web system for four Tamil Nadu locations with transparent assumptions. After fixing R-1–R-3, a genuinely interesting contribution would be showing *how* uncertainty changes the recommended crop mix (not just its yield number).

## 8. Limitations to state proactively
1. District-level aggregates, not farm-level data; one farm modelled as land shares.
2. Dataset provenance and synthetic 2024 year.
3. Input multipliers inert (R-1); tonnage objective (R-2).
4. Fuzzy rules hand-authored, not calibrated against outcomes.
5. Single-season, no rotation or perennial handling.
6. Economic constants from single-point price quotes; environmental impact is an index.
7. No validation against observed farm outcomes.

## 9. Future work (prioritised)
1. Confirm/replace data with IMD, CWC/India-WRIS, CGWB, DES APY, Soil Health Card sources.
2. Crop-water and nitrogen response functions (R-1), profit objective (R-2).
3. Scenario-based uncertainty (sample historic rainfall/storage) with expected-value or CVaR objectives; compare to fuzzy.
4. Baselines: NSGA-III, ε-constraint LP; multi-seed statistics with fixed-normalisation HV.
5. Multi-season rotation model with perennial constraints.
6. Field validation with farmers / KVK agronomists; elicit preference weights (AHP).

## 10. Viva readiness – questions an examiner is likely to ask

| Question | Honest answer grounded in the code |
|---|---|
| "Why do all your top plans use the minimum fertiliser and irrigation?" | Because the current yield model does not respond to inputs; any extra input only adds cost/water/impact, so it is dominated. Planned fix: FAO-33 / N-response functions. |
| "Is your data real?" | State exactly what is known: course-provided baseline 2020–23 of unconfirmed origin; 2024 estimated from 2023 and flagged in the UI/API. |
| "What does fuzzy logic change?" | It scales each crop's expected yield by a confidence derived from rainfall deviation, storage and soil; it does not change cost/water/impact, so the fuzzy/non-fuzzy fronts differ only in the yield axis and possibly crop ranking. |
| "How many rules?" | 26 written, 21 effective – 5 are subsumed under max aggregation (show the deletion experiment). |
| "How do you know it converged?" | Hypervolume rises from ≈0.26 to ≈0.81 and plateaus (Salem Kharif, pop 100); per-run normalised; multi-seed statistics are future work. |
| "Why NSGA-II for 4 objectives?" | Paper specification; NSGA-III/MOEA-D are better suited for ≥4 objectives – planned comparison. |
| "Why TOPSIS; how were weights chosen?" | Closeness to ideal favours balanced plans; 'balanced' yield weight 0.30 tuned by hand because the other three objectives correlate 0.85–1.0 with yield. |
| "Are results reproducible?" | Yes for a given seed and dataset version – including under concurrent requests (fixed and tested). |
