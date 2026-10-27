# TOPSIS Architecture

How the ranking stage turns NSGA-II's Pareto front into ranked plans: every function, its inputs and outputs, and who calls it. Section 1–4 describe the published ranking as it was before the dynamic engine; section 5 shows what the engine added around it. Weights: [TOPSIS_WEIGHT_ANALYSIS.md](TOPSIS_WEIGHT_ANALYSIS.md). The engine: [TOPSIS_DYNAMIC_ENGINE.md](TOPSIS_DYNAMIC_ENGINE.md).

## 1. Position in the pipeline

```
preprocessing ─► fuzzy assessment ─► NSGA-II (4 objectives) ─► feasible Pareto front (≤ population size plans)
                                                                      │
                                         ranking.filter_plans ◄───────┘   optional hard limits from the request
                                                                      │
                                         ranking.rank_plans  ◄────────┘   TOPSIS, sort, truncate to 50
                                                                      │
                                         RankedPlan list ─► API response, saved run, explanations, reports
```

TOPSIS never feeds back into the search. It only orders plans that NSGA-II already found, so the ranking stage can change without touching the optimiser, the objectives or the fuzzy outputs.

## 2. Criteria

The published ranking uses exactly the four NSGA-II objectives of each plan (`app/optimization/problem.py`):

| Criterion | Plan field | Type | Meaning |
|---|---|---|---|
| yield | `yield_tonnes` | benefit | expected yield after the fuzzy confidence adjustment, tonnes |
| cost | `cost_rs` | cost | fertiliser + pesticide + labour, ₹ |
| water | `water_liters` | cost | irrigation water net of effective rainfall, litres |
| env | `env_impact_score` | cost | √(nitrogen leaching proxy × carbon proxy) |

All four are totals for the farm, so they share the land size and scale together.

## 3. The TOPSIS computation (`app/decision/ranking.py`)

For plans i = 1…m and criteria j = 1…4:

| Step | Formula | Code |
|---|---|---|
| 1. Normalisation | n_ij = (x_ij − min_i x_ij) / (max_i x_ij − min_i x_ij); 0.5 for every plan when the column is constant | `_minmax_norm` |
| 2. Benefit/cost | cost criteria are flipped, g_ij = 1 − n_ij, so 1 is always the best value in the set | `_minmax_norm(higher_is_better=False)` |
| 3. Weighting | v_ij = w_j · g_ij | `np.column_stack(goodness) * w` |
| 4. Ideal best | A⁺_j = max_i v_ij (= w_j unless the column is constant) | `M.max(axis=0)` |
| 5. Ideal worst | A⁻_j = min_i v_ij (= 0 unless the column is constant) | `M.min(axis=0)` |
| 6. Distances | D⁺_i = √Σ_j (v_ij − A⁺_j)², D⁻_i = √Σ_j (v_ij − A⁻_j)² | Euclidean, `np.sqrt(((M - ideal) ** 2).sum(axis=1))` |
| 7. Relative closeness | C_i = D⁻_i / (D⁺_i + D⁻_i); 0.5 when both are 0 | `np.divide(..., where=denom > 1e-12)` |
| 8. Ranking | sort by C_i rounded to 4 places, descending (stable), keep the top `MAX_RETURNED_PLANS` = 50, number 1…n | `rank_plans` |

Differences from textbook TOPSIS (Hwang & Yoon 1981):

* **Min–max instead of vector normalisation.** Every criterion spans exactly [0, 1] within the plan set, so the ideal is w and the anti-ideal 0 on every criterion. With vector normalisation a criterion with a narrow relative range would carry less effective weight than its nominal weight. The cost is that the scores are relative to this plan set only.
* **Ranking on the rounded score.** Plans whose closeness agrees to 4 decimals keep NSGA-II's order. This keeps the API's `composite_score` and the order consistent.

## 4. Functions and call sites

| Function | Input → output | Called by |
|---|---|---|
| `filter_plans(plans, max_cost, max_water_liters, min_yield_tonnes, max_env_impact)` | FarmPlans → FarmPlans within the request's hard limits | `plan_service.run_pipeline` |
| `preference_weights(preference)` | name → [yield, cost, water, env] weights (unknown → balanced) | `rank_plans`, `plan_service` (meta), `explanation_service`, `district_service`, `topsis_service` |
| `normalise_weights(weights)` | 4 non-negative numbers → weights summing to 1 | `rank_plans` (simulation priority sliders), `plan_service`, `explanation_service` |
| `topsis_scores(yields, costs, waters, envs, w)` | four columns + weights → (closeness, goodness columns) | `rank_plans`, `explanation_service._rank_under_all_preferences`, `district_service` (goodness only), `simulation_service` (goodness only, equal weights) |
| `rank_plans(plans, crop_confidence_map, preference, max_plans, weights)` | FarmPlans → RankedPlans: rank, composite_score (C rounded to 4), `normalized_scores` (the goodness columns), `confidence_label`, `trade_off_summary`, rounded allocation | `plan_service`, `dashboard_service` (Analytics front, Comparison plans A/B/C), `explanation_service` (comparison context), benchmark and profiling scripts |
| `to_dict_list(ranked)` | RankedPlans → dicts | everything that returns plans |

Outputs per plan besides the score:

* `normalized_scores`: the four goodness values (1 = best in this set).
* `confidence_label`: land-weighted crop confidence, bucketed.
* `trade_off_summary`: raw (unflipped) min–max position of each objective, worded High/Moderate/Low.
* `allocation_percent`: largest-remainder rounding so shares sum to 100.00.

### Where weights come from

| Source | Weights |
|---|---|
| `FarmPlanRequest.preference` (API, Run Optimization) | `_PREFERENCE_WEIGHTS[preference]` |
| Scenario Simulation priorities (0–100 sliders) | `normalise_weights([yield, cost, water, env])` via `PipelineAdjustments.topsis_weights` |
| Comparison page | balanced, max_yield and min_cost on one front (plans A, B, C) |
| Analytics, District Intelligence | balanced |

## 5. What the dynamic engine adds

```
                    ┌─────────────── app/decision/profiles.py ───────────────┐
request.profile ───►│ resolve(profile, custom_weights) → WeightSpec          │
                    └────────────────────────────────────────────────────────┘
                                         │ weights over 10 criteria
feasible front ──► app/decision/criteria.py plan_criteria() ──► raw criterion columns
                                         │
                   ranking.criteria_closeness() ──► closeness (same maths as §3)
                                         │
                   ranking.rank_plans(criteria_values, criteria_weights, criteria_directions)
                                         │
     app/decision/topsis_explain.py: breakdown · plan_terms · explain_pair · compare_profiles
                                         │
     app/services/topsis_service.py: rank_front · topsis_meta · profile_comparison · rerank_saved_run
```

* **`weighted_closeness(goodness, w)`** holds steps 3–7, unchanged. `topsis_scores` now calls it, and so does the new **`criteria_closeness(values, directions, weights)`**, which ranks over any criteria with a positive weight in the order given. With the four objectives and the balanced weights it returns exactly `topsis_scores`' array (tested bit for bit on real and random fronts).
* **`rank_plans`** gains `criteria_values`, `criteria_weights` and `criteria_directions`. Without them it runs the original code path. `normalized_scores` always report the four objectives.
* **Balanced is routed through the original path.** `topsis_service.rank_front` calls `rank_plans(preference="balanced")` for the Balanced profile, so its output is the published ranking by construction, not just by equivalence.
* **The ranked front is stored** with saved runs (`ranked_front`, not part of the API response), so a run can be re-ranked later over exactly the plans it was ranked from.

Every original call site in §4 is unchanged: Comparison, Analytics, District Intelligence and Scenario Simulation keep their preferences and slider weights.
