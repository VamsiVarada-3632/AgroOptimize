# Dynamic TOPSIS Engine

The ranking stage, made user-adaptive. A farmer chooses what matters (a ranking profile or their own weights), and the same Pareto front is ranked with those weights, explained criterion by criterion, and compared across profiles. NSGA-II, its four objectives and the fuzzy assessment are inputs and are never changed. Balanced, the default, is the published ranking bit for bit.

Related documents:
* [TOPSIS_ARCHITECTURE.md](TOPSIS_ARCHITECTURE.md): the ranking code before this work.
* [TOPSIS_WEIGHT_ANALYSIS.md](TOPSIS_WEIGHT_ANALYSIS.md): audit of the published weights.
* [TOPSIS_PROFILE_GUIDE.md](TOPSIS_PROFILE_GUIDE.md): the profiles and custom weights.
* [TOPSIS_EXPLAINABILITY.md](TOPSIS_EXPLAINABILITY.md): how rankings are explained.
* [TOPSIS_COMPARISON.md](TOPSIS_COMPARISON.md): comparison mode and benchmark.

## 1. Summary

| | Before | After |
|---|---|---|
| Criteria | yield, cost, water, environmental impact | the same four plus market price, income, budget, soil suitability, land use, rainfall exposure |
| Weights | 5 fixed preferences, or 4 simulation sliders | the same, plus 5 ranking profiles and custom weights over 10 criteria |
| Default | balanced preference | Balanced profile = the balanced preference, identical output |
| Explanation | weights and closeness | weight → normalised value → contribution → distances → closeness per criterion; why each plan beats the next; rank under every profile |
| Comparison | Comparison page: 3 preferences | any run under all 5 profiles: best plan, rank changes, Kendall's τ, top-5 overlap, weight differences |
| Re-ranking a saved run | not possible | `GET/POST /api/results/{run_id}/topsis`, exact, no NSGA-II re-run |

## 2. Architecture

```
app/decision/criteria.py        CRITERIA, CRITERIA_META, crop_attributes(), plan_criteria(), soil_fit()
app/decision/profiles.py        PROFILES, rank_sum_weights(), validate_custom_weights(), resolve() → WeightSpec, catalogue()
app/decision/ranking.py         weighted_closeness(), criteria_closeness(), rank_plans(criteria_*) — plus the unchanged original path
app/decision/topsis_explain.py  breakdown(), plan_terms(), explain_pair(), compare_profiles(), ranks_from_closeness()
app/services/topsis_service.py  rank_front(), topsis_meta(), profile_comparison(), ranking_explanation(), rerank_saved_run()
app/services/plan_service.py    request.profile / custom_weights / compare_profiles; meta.topsis; ranked_front
app/services/explanation_service.py  explanation.topsis section; profile-aware weights and wording
app/main.py                     GET /api/topsis/profiles; GET|POST /api/results/{run_id}/topsis
frontend/src/components/topsis/ ProfileSelector.jsx (selector + custom builder), TopsisPanel.jsx (ranking, reasoning, comparison)
frontend/src/utils/topsisView.js     validation and formatting
```

Data flow of a run with a profile:

1. NSGA-II returns the feasible front.
2. `filter_plans` applies the request's hard limits.
3. `resolve(profile, custom_weights)` gives a `WeightSpec` (weights over the 10 criteria, summing to 1).
4. If the spec weights any criterion beyond the four objectives, `crop_attributes(region_profile, fuzzy)` reads each candidate crop's price, N/P/K doses and rainfall dependency from the crop rows the run used. `plan_criteria` then computes the criterion columns.
5. `rank_plans` ranks over the criteria with a positive weight.
6. `meta.topsis` records the spec, and the filtered front is stored with the saved run as `ranked_front`.

Balanced skips steps 3–5 and calls the original `rank_plans(preference="balanced")`.

## 3. Criteria

### 3.1 Definitions

For a plan with crop areas aᵢ (shares sᵢ = aᵢ/Σa), expected tonnes tᵢ = aᵢ · yieldᵢ · confidenceᵢ (exactly the NSGA-II yield, per crop), price pᵢ (dataset `MSP_Rs_Qtl`, ₹/quintal):

| Criterion | Direction | Value | Source |
|---|---|---|---|
| Yield | benefit | Σ tᵢ (t) | NSGA-II f1 |
| Production cost | cost | ₹ | NSGA-II f2 |
| Water | cost | irrigation litres | NSGA-II f3 |
| Environmental impact | cost | index | NSGA-II f4 |
| Market price | benefit | Σ tᵢ pᵢ / Σ tᵢ, the tonnage-weighted price (₹/qtl) | crop.csv `MSP_Rs_Qtl` |
| Income | benefit | 10 Σ tᵢ pᵢ − cost, indicative net income (₹) | as the explanation's indicative economics |
| Budget | benefit | budget − cost (₹); 0 for every plan without a budget | request |
| Soil suitability | benefit | Σ sᵢ · fitᵢ, fitᵢ = 1 − ⅓ Σ_{N,P,K} (doseᵢ / max dose) × deficit(status) | crop.csv doses, land.csv N/P/K status: Low 1, Medium 0.5, High 0 |
| Land use | benefit | Shannon evenness −Σ sᵢ ln sᵢ / ln n (0 = one crop, 1 = equal shares) | allocation |
| Rainfall exposure | cost | Σ sᵢ · RAINFALL_DEPENDENCY_FACTORᵢ (Very Low 0.1 … High 1.0) | crop.csv `Rainfall_Dependency`, config |

### 3.2 Rationale and sources

* **Market price** captures which crops fetch more per quintal, independent of tonnage. **Income** combines tonnage and price minus cost. Both use the dataset's unvalidated price column; the explanation service already flags those prices (some crops have no notified MSP).
* **Budget headroom** lets a profile prefer plans well under the cap. Every ranked plan already satisfies the budget, because NSGA-II enforces it as a hard constraint.
* **Soil suitability** follows the FAO land-evaluation idea of matching crop requirements to land qualities (FAO 1976; Sys et al. 1993), with nutrient availability as the quality. It is a proxy built from the data the project has (no per-crop soil data exists), not a validated suitability class.
* **Land use** rewards crop diversification, which spreads production risk (Di Falco & Perrings 2005; Lin 2011).
* **Rainfall exposure** penalises land in rain-dependent crops. It is the same dependency factor the fuzzy layer uses for crop confidence.

### 3.3 Correlations: read before weighting

Median Spearman ρ over 120 fronts (`benchmarks/topsis_benchmark.json`):

| pair | ρ | consequence |
|---|---|---|
| income ~ yield | +1.00 | on one front, income orders plans like yield |
| budget ~ cost | −1.00 | budget headroom orders plans exactly opposite to cost, i.e. it is extra cost weight |
| soil ~ env | −0.86 | soil-suited plans are the low-impact ones |
| rainfall ~ water | −0.74 | rain-fed crops need less irrigation, but are more exposed to rainfall shortfalls |
| income ~ market price | −0.39 | high-tonnage crops in this data are the cheaper ones per quintal |
| land ~ yield | −0.16 | diversification is nearly independent of yield |

Weighting two strongly correlated criteria acts like extra weight on one. Rainfall exposure deliberately pulls against water saving: a farmer can trade irrigation water against rainfall risk.

## 4. Mathematics

Identical to the published ranking (TOPSIS_ARCHITECTURE.md §3) over the criteria with wⱼ > 0:

```
gᵢⱼ  = (xᵢⱼ − minᵢ xᵢⱼ) / (maxᵢ xᵢⱼ − minᵢ xᵢⱼ)      flipped (1 − ·) for cost criteria; 0.5 if constant
vᵢⱼ  = wⱼ gᵢⱼ
A⁺ⱼ = maxᵢ vᵢⱼ,  A⁻ⱼ = minᵢ vᵢⱼ
D⁺ᵢ = √Σⱼ (vᵢⱼ − A⁺ⱼ)²,  D⁻ᵢ = √Σⱼ (vᵢⱼ − A⁻ⱼ)²
Cᵢ  = D⁻ᵢ / (D⁺ᵢ + D⁻ᵢ)
```

Properties the tests check:

* Zero-weight criteria do not enter the matrix.
* A constant criterion (for example budget without a budget) contributes nothing.
* Scaling all weights leaves C unchanged.
* C ∈ [0, 1], and identical plans score 0.5.
* A hand-computed three-plan example gives C = (0.25, 0.5, 0.75).

**Mathematical validation of Balanced.** `criteria_closeness` with the four objectives and the balanced weights returns `topsis_scores`' array bit for bit:

* on 5 preferences × a real front, and on 50 random sets (`tests/test_topsis_ranking.py`);
* on all 120 benchmark fronts.

The full API response of `profile=balanced` equals the default request's apart from wall-clock timings, and the 120 recorded ranking fingerprints of the default request match `main` exactly (all districts × seasons × preferences, with and without a budget).

## 5. API

| Endpoint | Change |
|---|---|
| `POST /api/farm-plans` | optional `profile` (balanced, profit, water, sustainability, low_cost, custom), `custom_weights` (criterion → weight, required for custom, must sum to 1), `compare_profiles`. A profile and a non-balanced `preference` cannot be combined (422). Response: `meta.topsis` always; `meta.profile_comparison` when requested |
| `GET /api/topsis/profiles` | new: profiles, weights, tiers, criteria definitions, custom-weight rules and defaults |
| `GET /api/results/{run_id}/topsis?profile=…&compare=…` | new: re-rank a saved run's front under a standard profile |
| `POST /api/results/{run_id}/topsis` | new: the same with `{"profile": "custom", "custom_weights": {...}}` |
| `GET /api/results/{run_id}/explanation`, `GET /api/comparison/{district}/explanation` | new optional `topsis` section |
| `GET /api/results`, `GET /api/history/{district}` | new optional `ranking` label |

Everything is additive: requests without the new fields get the same plans as before, and no field was removed or renamed. Reference: [API_REFERENCE.md](API_REFERENCE.md).

## 6. Before and after: an example

Salem Kharif 2024, 5 ha, budget ₹400,000, one NSGA-II run (80 Pareto-optimal plans), ranked under each profile. The plans are the same 80 in every row:

| Profile | #1 plan | TOPSIS score | its rank under Balanced |
|---|---|---|---|
| Balanced (before and after) | Tapioca 91 %, Groundnut 5 %, Maize 3 % | 0.6319 | 1 |
| Profit priority | Tapioca 96 %, Maize 3 % | 0.5613 | 8 |
| Water saving | Groundnut 89 %, Maize 11 % | 0.7522 | 34 |
| Sustainability | Groundnut 89 %, Maize 11 % | 0.6412 | 34 |
| Low cost | Groundnut 67 %, Maize 32 % | 0.7565 | 32 |

Profit picks the high-tonnage tapioca plan (13.6 t/ha, ₹39,895/ha). Water saving picks a groundnut-maize plan using a fraction of the water (1.4 t/ha, ₹33,492/ha). Both are on the same Pareto front: the profile only decides which trade-off comes first.

Across the 120 benchmark fronts ([TOPSIS_COMPARISON.md](TOPSIS_COMPARISON.md)), each profile moves the #1 plan in the direction it claims (paired against Balanced's #1):

| Profile | Moves the #1 plan towards | better / worse fronts |
|---|---|---|
| Profit | higher income | 112 / 0 |
| Water saving | less water | 110 / 4 |
| Sustainability | less water | 107 / 5 |
| Sustainability | lower impact | 93 / 19 |
| Sustainability | better soil fit | 68 / 21 |
| Low cost | lower cost | 94 / 7 |

## 7. Performance

Median per 80-plan front (benchmark, one laptop):

| Operation | Time |
|---|---|
| published ranking (`rank_plans`, balanced) | 0.48 ms |
| ranking with a 10-criterion profile | 0.59 ms |
| five-profile comparison | 1.36 ms |
| ranking explanation (top 10, pairs) | 0.76 ms |
| whole `POST /api/farm-plans` (unsaved, Salem Kharif) | ≈ 0.29 s with or without a profile or comparison (NSGA-II dominates) |

A saved run grows by the stored front: 134 KB → 207 KB for 80 plans.

## 8. Screenshots

| | |
|---|---|
| Profile selector with the custom weight builder | ![custom weights](screenshots/topsis_custom_weights.jpg) |
| Ranking: selected profile, weight distribution, TOPSIS scores | ![ranking](screenshots/topsis_ranking.jpg) |
| Reasoning: why each plan beats the next; weight → contribution → score | ![reasoning](screenshots/topsis_reasoning.jpg) |
| Compare profiles: best plan per profile, ranking changes | ![compare](screenshots/topsis_compare_profiles.jpg) |
| Weight differences between profiles | ![weights](screenshots/topsis_weight_differences.jpg) |
| "Why this plan?": TOPSIS score section | ![explanation](screenshots/topsis_explanation.jpg) |

## 9. Testing

| Suite | Tests | Covers |
|---|---|---|
| `tests/test_topsis_ranking.py` | 16 | bit-identity with the published maths, hand-computed example, TOPSIS properties |
| `tests/test_topsis_criteria.py` | 19 | each criterion against its definition and against the pipeline's own numbers |
| `tests/test_topsis_profiles.py` | 30 | weights, tiers, the brief's priorities, custom weight validation, catalogue |
| `tests/test_topsis_engine.py` | 55 | Balanced unchanged; profile switching changes only the ranking; explanation maths; comparison; saved-run re-ranking; request validation; API; explanation section; speed |
| `frontend/src/utils/topsisView.test.js` | 14 | builder validation, fractions, rows |
| `frontend/src/components/topsis/topsis.test.jsx` | 7 | selector, builder, weight chart, contribution card, comparison, explanation section |

All earlier suites pass unchanged: 797 backend tests (677 before) and 89 frontend tests (68 before).

## 10. Limitations

* **Scores are relative to the plan set.** Min–max normalisation makes every score relative to the front being ranked, as before. A re-ranked older run without a stored front is ranked over its 50 returned plans and says so (`ranked_over: returned_plans`).
* **The #1 plan is sensitive to small weight changes** (TOPSIS_WEIGHT_ANALYSIS.md §2.1). The interface shows the top plans and the comparison for that reason.
* **Prices are unvalidated.** Market price and income use the dataset's price column, flagged elsewhere as unvalidated.
* **Soil suitability is a nutrient-demand proxy,** not a validated FAO suitability class.
* **Some criteria are redundant on one front** (§3.3). The standard profiles avoid double-counting, but a custom profile can still do it.
* **Profile weights come from importance tiers,** not from eliciting farmers' preferences.
* **Rank reversal.** TOPSIS can reverse ranks when plans are added or removed (García-Cascales & Lamata 2012), so the order depends on the filters applied before ranking.
* **Classic preferences are a separate path.** max_yield and the other classic preferences rank over the four objectives only, and cannot be combined with a profile.

## 11. Future improvements

1. Elicit weights from farmers with AHP or swing weighting, and store them per user.
2. A robust recommendation: the plan that stays in the top k under weight perturbations (stochastic multicriteria acceptability analysis, Lahdelma & Salminen 2001).
3. Validated prices (Agmarknet modal prices) for market price and income.
4. Crop-specific soil suitability from soil-survey data.
5. Show the profile comparison on the Comparison page as well, in place of the fixed plans A/B/C.
6. A rank-reversal-free variant (for example a fixed reference point) for comparisons across runs.

## References

* Barron, F. H. & Barrett, B. E. (1996). Decision quality using ranked attribute weights. *Management Science* 42(11).
* Di Falco, S. & Perrings, C. (2005). Crop biodiversity, risk management and the implications of agricultural assessments. *Ecological Economics* 55(4).
* Diakoulaki, D., Mavrotas, G. & Papayannakis, L. (1995). Determining objective weights in multiple criteria problems: the CRITIC method. *Computers & Operations Research* 22(7).
* FAO (1976). *A Framework for Land Evaluation.* FAO Soils Bulletin 32.
* García-Cascales, M. S. & Lamata, M. T. (2012). On rank reversal and TOPSIS method. *Mathematical and Computer Modelling* 56(5–6).
* Hwang, C.-L. & Yoon, K. (1981). *Multiple Attribute Decision Making: Methods and Applications.* Springer.
* Lahdelma, R. & Salminen, P. (2001). SMAA-2: stochastic multicriteria acceptability analysis for group decision making. *Operations Research* 49(3).
* Lin, B. B. (2011). Resilience in agriculture through crop diversification. *BioScience* 61(3).
* Stillwell, W. G., Seaver, D. A. & Edwards, W. (1981). A comparison of weight approximation techniques in multiattribute utility decision making. *Organizational Behavior and Human Performance* 28(1).
* Sys, C., Van Ranst, E., Debaveye, J. & Beernaert, F. (1993). *Land Evaluation, Part III: Crop Requirements.* General Administration for Development Cooperation, Brussels.
