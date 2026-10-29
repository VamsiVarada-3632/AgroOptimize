# Fuzzy Model Improvements

Research record of the second round of work on the Mamdani fuzzy system: what was audited, which improvements were ranked, which three were implemented, and why each was accepted or rejected. The baseline is the earlier audit ([FUZZY_SYSTEM_ANALYSIS.md](FUZZY_SYSTEM_ANALYSIS.md), [FUZZY_RESEARCH_REVIEW.md](FUZZY_RESEARCH_REVIEW.md)); its findings are not repeated here, only used. All measurements are in [FUZZY_BENCHMARK_RESULTS.md](FUZZY_BENCHMARK_RESULTS.md) and reproduce with `scripts/benchmark_fuzzy_models.py`.

**Summary.** Three improvements were implemented as independent switches on `FuzzyModel` (`app/fuzzy/engine.py`) and accepted:

| # | Improvement | Switch | Outputs change? |
|---|---|---|---|
| I1 | Strong (Ruspini) partition for storage and fertility, same modal values | `strong_partition` | Yes |
| I2 | Rainfall sets centred on the IMD categories, crossing at the IMD boundary | `imd_rainfall` | Yes |
| I3 | Leave out the six provably inert rules | `prune_inert` | No (identical) |

Together they form the `improved` model. The **default remains `original`**, so every published result, the paper's tables and all saved runs reproduce exactly (2,595 fuzzy inputs, the audit and 12 API runs are bit-identical to `main`). The improved model is selected per request (`fuzzy_model`), per simulation, or for a deployment with `AGROOPTIMIZE_FUZZY_MODEL=improved`.

## 1. Phase 1 — what the new audit found

The earlier audit established low ε-completeness, the six inert rules, capping rules that cannot cap, the clipped rainfall range and soil dominance. Re-auditing only to find improvements added these measured findings (60 dataset profiles, 21³ input grid):

| ID | Finding | Evidence | Consequence |
|---|---|---|---|
| A-1 | **Evidence-blind outputs.** When only one output term has a positive cut, the centroid equals that term's centroid whatever the firing strength. | Original: yield confidence formed by a single term in 10/60 profiles, irrigation risk in 30/60. Pollachi Kharif: rainfall *surplus* 0.28, storage *high* 0.30, soil *good* 0.41 — weak evidence on every input — yet yield confidence 0.858 (*high*) and risk 0.152, because only the *high* / *low* terms fire. | Output differences between regions are partly an artefact of the weak overlaps, not of the evidence. |
| A-2 | **Noise sensitivity.** Small input changes cause large output jumps where an input sits in a weak band. | Rainfall ±5 pp, storage ±2 pp, fertility ±2 (8 corners per profile): risk changes by up to 0.208; mean 0.035. | Recommendations depend on measurement noise more than necessary. |
| A-3 | **Hidden importance.** A subsumed rule tied with the general rule that subsumes it makes the general rule look unimportant in leave-one-out attribution (removing either leaves the other setting the cut). | General rules show importance 0 although they decide the output in 18 rule readings; attribution is wrong in 29/60 profiles. | Explanations understate the rules that actually decide the output. |
| A-4 | **The capping intent is itself non-monotone.** Read as real upper bounds, rules 16, 19, 23 make yield confidence *fall* as fertility rises (rule 19 has *soil good* in its condition). | Implemented as implicative constraints: largest yield-vs-fertility violation 0.137 (original 0.011). | "Fixing" the capping rules as written would make the model worse; they need re-formulation by a domain expert. |
| A-5 | **Product AND does not resolve inert rules.** Subsumption holds for any t-norm (T(a, b, c) ≤ T(a, b)). | Product AND: still 20 effective rules; yield-vs-storage steps > 0.01 rise from 7.3 % to 16.6 %. | Weights or t-norm changes are not a cheap way to activate the scenario rules. |
| A-6 | **Output sets are as weakly overlapped as the inputs** (cross at 0.231). | Mean membership of the output's own label: 0.511 (yield), 0.618 (risk) in the original. | Linguistic output labels have low support; noted for a future version (§4). |
| A-7 | **Soil dominates yield confidence.** | First-order variance share of fertility in yield confidence: 0.59 (rainfall 0.19, storage 0.16). | Quantifies R-3 of the earlier audit; needs new rules (expert input), not a parameter change. |

## 2. Phase 2 — candidate improvements ranked by impact

Every candidate was screened on the same metrics before anything was implemented (the screening evaluators are in the benchmark script). Impact = measured effect on the audit findings; only literature-backed candidates were considered.

| Rank | Candidate | Literature | Screened effect | Decision |
|---|---|---|---|---|
| 1 | **I1** Strong partition for storage and fertility (keep modal values 0/50/100) | Ruspini (1969); Lee (1990) ε ≥ 0.5; Pedrycz (1994): triangles with ½ overlap reconstruct exactly | Largest monotonicity violation 0.065 → 0.023; yield single-term outputs 10 → 0 | **Implemented, accepted** (with I2) |
| 2 | **I2** Rainfall sets on IMD categories, strong partition, crossing at ±19.75 % | IMD categories [12]; Lee (1990); fuzzy classes anchored on survey classes (McBratney & Odeh 1997) | ε 0.143 → 0.5; IMD label agreement 51 → 60/60; risk noise −34 % | **Implemented, accepted** (with I1) |
| 3 | **I3** Remove the six provably inert rules | Guillaume (2001): compact, non-redundant rule bases | Outputs identical; inference −27 %, memory −30 %, correct attribution | **Implemented, accepted** |
| 4 | Capping rules 16, 19, 23 as implicative upper bounds | Dubois & Prade (1996) | Rule 19 becomes effective, but monotonicity violations double (A-4) | **Rejected** |
| 5 | Product AND | Mamdani variants | No inert rule activated; monotonicity worse (A-5) | **Rejected** |
| 6 | Rule weights / certainty factors | Ishibuchi & Nakashima (2001) | Needs weight values; none can be justified without expert elicitation or outcome data, and tuning them to this benchmark would be fitting the result | **Deferred** |
| 7 | Wider rainfall universe / IMD "large" categories | IMD [12] | No effect: deficit and surplus are already 1 at ±60 %, so values beyond it give the same output unless new rules are written | **Rejected** (no measurable benefit) |
| 8 | Rescale or change defuzzification to reach 0 and 1 | Van Leekwijck & Kerre (1999) | Rescaling changes numbers without new information ("better confidence" by construction); mean-of-maxima is discontinuous | **Rejected** |
| 9 | Gaussian membership functions | Pedrycz (1994) | Shape is not the cause (A-1, A-2 come from overlap); would change every output with no coverage gain over I1/I2 | **Rejected** |
| 10 | Strong partition of the output sets | Lee (1990) | Would raise label support (A-6) but moves every centroid; a separate versioned change | **Deferred** |
| 11 | Data-driven calibration (ANFIS/TSK), interval type-2 sets | Jang (1993); Mendel (2001) | Needs realised-yield outcome data, which the dataset lacks | **Future work** |

## 3. Phase 3–6 — the implemented improvements

Each improvement is a separate switch; each was benchmarked on its own and in the cumulative chain Original → I1 → I1+I2 → I1+I2+I3 (final). Full tables, charts and paired tests: [FUZZY_BENCHMARK_RESULTS.md](FUZZY_BENCHMARK_RESULTS.md).

### I1 — Strong partition for storage and fertility

* **Why.** Storage and fertility sets cross at 0.231 and a reading's memberships can sum to 0.375, so fertility 70 is only 0.2 *medium* and 0.25 *good*. This is the cause of the non-monotone yield and risk responses to storage (earlier audit §5) and of evidence-blind outputs (A-1).
* **How.** `STRONG_PARTITION_SETS`: low (0, 0, 50), medium (0, 50, 100), high (50, 100, 100) for storage; poor / medium / good the same for fertility. The modal values are the original ones; only the feet move to the neighbours' peaks, so no new threshold is introduced.
* **What changed.** ε 0.231 → 0.5 and memberships sum to 1 on both inputs; rainfall and rules unchanged.
* **How much (alone).** Largest yield-vs-storage violation 0.0653 → 0.0215 (−67 %); steps with a drop > 0.01: 7.3 % → 1.8 %; yield-vs-fertility violations 0.7 % → 0; yield noise −21 %, risk noise −20 %; single-term yield outputs 10 → 0. **But** the spread of yield confidence across profiles falls from 0.098 to 0.041 and its signal-to-noise ratio from 4.08 to 2.15: alone, I1 removes the artefactual spread without giving rainfall more weight.
* **Decision.** Accepted as part of the improved model, not on its own (yield signal-to-noise halves alone; restored by I2).

### I2 — IMD-aligned rainfall partition

* **Why.** IMD classifies a season within ±19 % of normal as *normal*; the original sets cross at ±12.9 % with membership 0.143, so 9 of 60 profiles IMD calls normal are labelled deficit or surplus, and 42 % of the rainfall universe has no membership above 0.5.
* **How.** `IMD_RAINFALL_SETS`: deficit (−60, −60, −39.5, 0), normal (−39.5, 0, 39.5), surplus (0, 39.5, 60, 60). Each set peaks at the midpoint of its IMD band (−59…−20, −19…+19, +20…+59), so neighbours cross at 0.5 at ±19.75 %, between the IMD bands. `imd_category()` gives the IMD label for checks.
* **What changed.** Rainfall ε 0.143 → 0.5; storage, fertility and rules unchanged.
* **How much (alone).** IMD label agreement 51 → 60/60; risk noise −34 % (max 0.208 → 0.110); signal-to-noise up for both outputs (4.08 → 4.51, 4.02 → 5.25). **But** monotonicity steps with a drop > 0.01 rise from 7.3 % to 11.7 % (the storage crossings of A-1 are now reached at more rainfall values; the largest violation is unchanged at 0.065).
* **Decision.** Accepted with I1, which removes the cause of the extra violations.

### I1 + I2 together

| Measure | Original | I1+I2 | Change |
|---|---|---|---|
| ε-completeness (rain / storage / fertility) | 0.143 / 0.231 / 0.231 | 0.5 / 0.5 / 0.5 | meets Lee's ε ≥ 0.5 |
| Largest monotonicity violation | 0.0653 | 0.0231 | −65 % |
| Steps with a drop > 0.01 (yield vs storage / risk vs storage) | 7.3 % / 5.9 % | 2.8 % / 3.8 % | −62 % / −36 % |
| IMD label agreement | 51/60 | 60/60 | +9 |
| Mean output change under input noise (yield / risk) | 0.024 / 0.035 | 0.0079 / 0.0161 | −67 % / −54 % |
| Largest output change under noise (yield / risk) | 0.102 / 0.208 | 0.037 / 0.085 | −63 % / −59 % |
| Signal-to-noise (yield / risk) | 4.08 / 4.02 | 4.07 / 5.93 | unchanged / +48 % |
| Single-term outputs (yield / risk) | 10 / 30 of 60 | 0 / 4 | evidence now shapes the value |
| Rule support (strongest firing per profile) | 0.435 | 0.677 | +56 % |

Costs, reported as found: more rules fire per profile (5.4 → 9.3) and more of them are masked (zero-influence fired rules 3.2 → 6.8), the mean membership of the output's own label falls (yield 0.511 → 0.389) because the outputs now sit between the unchanged output sets (A-6), and the spread of yield confidence across profiles narrows (0.098 → 0.032) because the extremes in the original came from single weakly fired rules (A-1). Yield signal-to-noise is unchanged, so the ability to tell regions apart relative to noise is kept.

### I3 — Remove the provably inert rules

* **Why.** Rules 13, 15, 19, 21, 25, 26 repeat a conclusion of a rule with a subset of their conditions; with AND = min and max aggregation they can never set a cut (earlier audit §4.1). They still count as "26 rules", appear among fired rules, and — new here (A-3) — hide the importance of the rule they duplicate.
* **How.** `subsumed_rules()` finds them from the rule structure; `prune_inert` leaves them out and keeps the original numbering. Because the argument uses only the rule structure, it holds for every membership function, including I1 and I2 (tested).
* **What changed.** 26 → 20 rules, all effective. Outputs identical (tested on random, grid and dataset inputs, and the pipeline metrics are identical).
* **How much.** Fired rules per profile 5.38 → 4.13; zero-influence fired rules 3.2 → 1.65; importance of the general rule restored in 29/60 profiles (18 readings from 0); inference time 3.08 → 2.24 ms (−27 %), explanation 3.83 → 3.01 ms (−21 %), peak memory 2,877 → 2,013 KB (−30 %). In the final model: 9.33 → 7.17 fired rules per profile, 6.82 → 4.48 zero-influence.
* **Decision.** Accepted (better runtime, memory and explanation; nothing degraded).

### Pipeline impact of the final model

NSGA-II (original engine, 80 × 200, 12 problems × 5 seeds) solves the improved model's problems as well as the original's: hypervolume ratio to each model's reference front 0.9611 vs 0.9598 (Wilcoxon p = 0.54); GD, IGD, IGD+, spread and spacing differ by ≤ 3 % (except GD −19 %), none significant; all populations 100 % feasible, front size 80. The raw hypervolume is 2.1 % lower (p < 0.001) because the front *shape* changes where the fuzzy outputs changed most (Pollachi Summer −0.058, Erode Summer −0.030); it is not a convergence loss. TOPSIS ranking of a fixed front under input noise is more stable (mean Kendall τ 0.9991 → 0.9996, p < 0.001; minimum 0.993 → 0.996); the top crop is kept under noise in 74.0 % of cases instead of 67.7 % (not significant, p = 0.36), and the land moved in the top plan is 11.0 % vs 9.5 % (not significant, p = 0.23). Optimisation time is not affected measurably: the fuzzy stage is one inference (≈3 ms) per ≈0.33 s run, and the run-to-run drift in the benchmark (+4 % for `pruned_rules`, whose computation is identical to the original apart from the fuzzy stage) is larger than any model effect.

## 4. Effect on published results

Selecting `improved` changes every fuzzy output and therefore every optimisation result. The default model is unchanged, so nothing published changes unless the model is switched.

| Profile (2024) | Original yield / risk | Improved yield / risk | Why |
|---|---|---|---|
| Pollachi Kharif (+20.4 %, 72 %, 76.5) | 0.858 / 0.152 | 0.683 / 0.345 | Original: only *high*/*low* fire, weakly (A-1). Improved: +20.4 % is on the IMD normal/excess boundary (0.48 / 0.52); storage and fertility are between medium and high. |
| Erode Summer (+18.4 %, 53.8 %, 70.9) | 0.703 / 0.155 | 0.677 / 0.351 | +18.4 % is IMD *normal*; the original called it *surplus* (0.24, normal 0) and one rule at 0.24 set the risk. |
| Coimbatore Kharif (−41.1 %, 85 %, 70.3) | 0.620 / 0.430 | 0.646 / 0.357 | Deficit is now full (IMD *deficient*), and the canal-advantage rule 24 fires at 0.59 instead of 0.19. |
| Salem Kharif (−21.1 %, 62 %, 67.8) | 0.636 / 0.465 | 0.667 / 0.361 | −21.1 % is just inside IMD *deficient*: deficit 0.53, normal 0.47 instead of deficit 0.29 only. |

**Advantages:** inputs are fully covered (ε = 0.5), labels match IMD, outputs respond to evidence strength, less sensitivity to input noise, faster inference and correct explanations. **Disadvantages:** published numbers change if the model is switched; outputs are less extreme (Pollachi no longer at the 0.883 ceiling); more rules fire and more are masked; output-label support is lower until the output sets are also re-partitioned. The yield-confidence spread between regions is smaller; whether the original spread was real cannot be decided without realised-yield data.

## 5. Reproducibility

* `original` is the default and bit-identical to `main` (fingerprint of 2,595 inputs × assessment, memberships, fired rules, explanation, output term; the audit; 12 API runs).
* Every model is checked against an uncached scikit-fuzzy run and against its own explanation (`tests/test_fuzzy_models.py`).
* Saved runs record `meta.fuzzy_model`; runs saved before this change are explained with `original`.
* `python3 scripts/benchmark_fuzzy_models.py --json out.json` then `python3 scripts/report_fuzzy_benchmark.py out.json` regenerates every number and chart.

## References
Numbered references [1]–[17] are those of [FUZZY_RESEARCH_REVIEW.md](FUZZY_RESEARCH_REVIEW.md) (Lee 1990 [6], Pedrycz 1994 [5], Guillaume 2001 [7], McBratney & Odeh 1997 [9], Van Leekwijck & Kerre 1999 [10], IMD [12], Jang 1993 [4], Mendel 2001 [8]). Added here:

18. Ruspini, E. H. (1969). A new approach to clustering. *Information and Control*, 15(1), 22–32.
19. Dubois, D., & Prade, H. (1996). What are fuzzy rules and how to use them. *Fuzzy Sets and Systems*, 84(2), 169–185.
20. Ishibuchi, H., & Nakashima, T. (2001). Effect of rule weights in fuzzy rule-based classification systems. *IEEE Transactions on Fuzzy Systems*, 9(4), 506–515.
21. Wilcoxon, F. (1945). Individual comparisons by ranking methods. *Biometrics Bulletin*, 1(6), 80–83.
