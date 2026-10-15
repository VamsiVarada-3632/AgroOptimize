# Fuzzy Improvement Summary

What changed in the fuzzy system, what did not, and the measured effect. Principle: the published Mamdani system, its 26 rules, its membership functions and every optimisation result stay exactly as they were; improvements are in explainability, auditability, performance and maintainability. Changes that would alter results are documented with measurements as proposals ([FUZZY_SYSTEM_ANALYSIS.md](FUZZY_SYSTEM_ANALYSIS.md) §8).

## 1. Before vs after

| Area | Before | After |
|---|---|---|
| Inference | scikit-fuzzy Mamdani, recomputed on every call | Same inference, memoised on the clipped inputs (4096 entries); a new result object per call |
| Rule base | 26 rules, inline | Same 26 rules; read once into `rule_specs()` (with the scenario names already in the comments) |
| Membership functions | Inline `trimf` calls | Same triangles in `MEMBERSHIP_FUNCTIONS`; input bounds in `INPUT_BOUNDS` |
| Explanation | Fired rules with strengths | Plus per-rule status (decisive / masked / tied), limiting condition, area contribution, leave-one-out importance, ranking, output term memberships (`explain_inference`) |
| Audit | Hand-measured statements in docs (one wrong: 5 inert rules) | `app/fuzzy/audit.py`: dominance (6 inert, 20 effective), coverage, output bounds, leave-one-out grid, firing on real data, monotonicity — tested and served at `/api/fuzzy/audit` |
| API | — | `GET /api/fuzzy/explain`, `GET /api/fuzzy/audit` (new, read-only); existing responses gain `fuzzy_reasoning.inference` |
| Frontend | Plain fired-rule table | Ranked table with status, share, limiting condition, importance (falls back to the plain table) |

**Rule changes:** none. **Membership function changes:** none (moved into a table, values identical).

## 2. Validation

| Check | Result |
|---|---|
| Fuzzy outputs (assessment, memberships, fired rules, output terms) on 9,321 inputs (60 real profiles + 21³ grid incl. out-of-range values) | **bit-identical** before/after |
| Optimisation fingerprint (48 stored outputs across districts, seasons, preferences, budgets) | **identical** to `main` |
| Explanation reconstruction vs engine | difference 0 on grid and random points |
| Backend tests | 557 passed (387 existing + 170 new) |
| Frontend tests, lint, build | pass |
| Determinism with the same seed | unchanged (outputs identical) |

Explanations, reports, comparison, Scenario Simulation and District Intelligence all run through the same engine and are covered by their existing test suites, which pass unchanged.

## 3. Performance (median of 5, same machine, `scripts/benchmark_fuzzy.py`, two runs each)

| Measure | main | this branch | Change |
|---|---|---|---|
| Inference, new inputs (ms/call) | 3.79–3.80 | 3.00–3.10 | about −20 % (consistent across runs; cause not isolated) |
| Inference, repeated inputs (ms/call) | 3.89–3.99 | 0.005 | ≈ 780× faster (memoised) |
| Memberships + fired rules, new inputs (ms) | 3.47–3.49 | 0.024–0.025 | ≈ 140× faster: rule list built once instead of walking scikit-fuzzy's rule-order generator each call |
| Full explanation of a saved run (ms) | 6.5–6.7 | 3.8 | 1.7× faster **despite** adding the rule attribution (≈ 4.5 ms when computed on its own) |
| Scenario simulation (s) | 4.05–4.08 | 3.97–4.22 | unchanged — dominated by NSGA-II |
| Peak traced memory, 60 inferences (KB) | 2,425–2,673 | 2,230–2,233 | ≈ −10 % |
| Audit grid (1,331 points) | 5.31 s via the engine | 0.21 s via the exact batch path | 25× faster for analysis |

The fuzzy layer is under 1 % of an optimisation run (one inference per run, 13 per simulation), so end-to-end optimisation time is unchanged; the gains matter for explanations, dashboards and analysis.

## 4. Measured properties (unchanged, now reported)

| Property | Value |
|---|---|
| Effective rules | 20 of 26 (13, 15, 19, 21, 25, 26 subsumed) |
| Rules fired per real profile | 2–11, mean 5.4; decisive 1–5, mean 3.0 |
| Rules never firing on the data | 11 (need water *low* or soil *poor*, never observed) |
| ε-completeness | rainfall 0.143, storage 0.231, fertility 0.231 |
| Monotonicity violations | yield vs storage 14.4 % of steps (≤ 0.065); risk vs storage 12.0 % (≤ 0.059); yield vs fertility 0.7 % |
| Output ceiling (centroid) | yield 0.150–0.883; risk 0.117–0.867 |

## 5. Benefits
* Every fuzzy number in an explanation can now be traced to the rule that produced it, with its exact share and importance.
* The documentation's claims about the rule base are now generated and tested; an error in the earlier docs (5 vs 6 inert rules) is corrected.
* Explanation and dashboard paths are faster; nothing about the published results changed.

## 6. Risks
* Memoisation: results are cached per clipped input triple; the engine is a pure function of its inputs and returns fresh objects, which is tested. If membership functions or rules are edited at runtime (they are not), caches must be cleared.
* The explanation reconstruction depends on scikit-fuzzy's aggregation scheme; it checks itself against the engine on every call (`matches_engine`) and in tests, so a library change would be detected.
* Payload size: plan explanations grow by the inference block (10.5 KB on a 33 KB explanation for Salem Kharif).

## 7. Future work
The output-changing proposals (IMD-aligned rainfall partition with ε ≥ 0.5, effective capping rules, rule weights or product AND, wider rainfall universe, calibration when outcome data exist) are in [FUZZY_SYSTEM_ANALYSIS.md](FUZZY_SYSTEM_ANALYSIS.md) §8 with their impact on reproducibility, and their literature basis in [FUZZY_RESEARCH_REVIEW.md](FUZZY_RESEARCH_REVIEW.md). They should be done as a versioned model change with the paper's tables re-run.
