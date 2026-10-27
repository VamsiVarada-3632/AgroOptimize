# TOPSIS Profile Comparison

Comparison mode ranks one Pareto front under all five profiles at once: Balanced, Profit priority, Water saving, Sustainability and Low cost (plus the custom profile when one is used). This document describes what it reports and the benchmark of the profiles over 120 fronts.

## 1. Comparison mode

Available as:
* `POST /api/farm-plans` with `compare_profiles: true` (`meta.profile_comparison`);
* `GET/POST /api/results/{run_id}/topsis` (`comparison`, on by default);
* the **Compare profiles** tab of the TOPSIS ranking panel on Run Optimization.

The **reference** is the profile the run (or re-rank) used.

| Output | Meaning |
|---|---|
| `profiles[].best_plan` | each profile's #1 plan: crop mix, objectives, TOPSIS score, and its rank under the reference |
| `profiles[].reference_top_plan_rank` | where the reference's #1 lands under this profile |
| `profiles[].kendall_tau_vs_reference` | Kendall's τ between this profile's order and the reference's over all plans (1 = same order, −1 = reversed) |
| `profiles[].top_n_overlap` | how many of the reference's top 5 are also in this profile's top 5 |
| `profiles[].top_plans` | this profile's top 5 with scores |
| `profiles[].weights`, `weight_differences` | the profile's weights and their difference from the reference's |
| `rank_changes` | the reference's top 5 plans with their rank and score under every profile |
| `distinct_best_plans` | how many different plans come out on top across the profiles |

In the app this is shown as three things:
* a "Best plan under each profile" table;
* a "Ranking changes" table with ↑/↓ markers;
* a "Weight differences" chart comparing the reference with any other profile (with a table view).

Screenshots: [TOPSIS_DYNAMIC_ENGINE.md](TOPSIS_DYNAMIC_ENGINE.md) §8.

### Example

Salem Kharif, 5 ha, budget ₹400,000, reference Water saving, 80 plans:

| Profile | Best plan | Score | Its rank under Water saving | Water saving's #1 ranks | τ | Top-5 overlap |
|---|---|---|---|---|---|---|
| Balanced | Tapioca 91 %, Groundnut 5 %, Maize 3 % | 0.6319 | 32 | 34 | 0.52 | 0/5 |
| Profit priority | Tapioca 96 %, Maize 3 % | 0.5613 | 42 | 63 | −0.48 | 0/5 |
| **Water saving** | Groundnut 89 %, Maize 11 % | 0.7522 | 1 | 1 | 1.00 | 5/5 |
| Sustainability | Groundnut 89 %, Maize 11 % | 0.6412 | 1 | 1 | 0.95 | 5/5 |
| Low cost | Groundnut 67 %, Maize 32 % | 0.7565 | 6 | 3 | 0.83 | 3/5 |

Four different plans come out on top. Water saving and Sustainability agree almost completely (τ 0.95). Profit orders the plans nearly in reverse (τ −0.48).

## 2. Benchmark

### 2.1 Method

`python scripts/benchmark_topsis.py --seeds 5 --json … --charts docs/handbook/benchmarks`:

* **Fronts:** 120 Pareto fronts. That is 4 districts × 3 seasons, each without a budget and with a budget of 5 ha × the median single-crop cost, seeds 0–4. All fronts have 80 plans.
* **NSGA-II settings:** the published engine (population 80, 200 generations).
* **Ranking:** each front is ranked under each profile; NSGA-II runs once per front.
* **Statistics:** paired comparisons against Balanced's #1 on the same front with the Wilcoxon signed-rank test. There is no multiple-comparison correction; the effects below are far beyond any correction.

Results: `benchmarks/topsis_benchmark.json`. Charts:
* `benchmarks/topsis_profile_weights.png`
* `benchmarks/topsis_top_plan_changes.png`
* `benchmarks/topsis_top_plan_objectives.png`

### 2.2 Balanced reproduces the published ranking

| Check | Result |
|---|---|
| Balanced profile vs `rank_plans(preference="balanced")` (plans, order, scores) | identical on 120/120 fronts |
| General criteria path with the balanced weights | identical on 120/120 fronts |
| `POST /api/farm-plans` without a profile vs `main` (12 district-seasons × 5 preferences × with/without budget) | 120/120 ranking fingerprints identical |

### 2.3 How much each profile changes the ranking

| Profile | Fronts whose #1 differs from Balanced's | Kendall's τ with Balanced (median) | Top-5 overlap with Balanced (median) | Balanced's #1 ranks (median) |
|---|---|---|---|---|
| Profit priority | 93 % | −0.22 | 0 | 41 |
| Water saving | 95 % | 0.61 | 0 | 26 |
| Sustainability | 93 % | 0.75 | 0 | 17 |
| Low cost | 84 % | 0.67 | 0 | 19 |

Every profile picks a different plan from Balanced on most fronts, from a different part of the front (no overlap in the top 5). Profit runs opposite to the three footprint-oriented profiles, which agree with Balanced on the overall order more than on the top.

### 2.4 Does each profile deliver what it promises?

Paired against Balanced's #1 on the same front. "better/worse" counts the fronts where the profile's #1 is better or worse on that criterion. Only criteria the profile weights are shown.

| Profile | Criterion | better/worse | p |
|---|---|---|---|
| Profit priority | income | **112/0** | 4 × 10⁻²⁰ |
| | yield | 112/0 | 4 × 10⁻²⁰ |
| | market price | 49/63 | 0.07 |
| | cost | 24/88 | 1 × 10⁻¹⁶ |
| | water | 0/112 | 4 × 10⁻²⁰ |
| | environmental impact | 18/94 | 3 × 10⁻¹⁶ |
| Water saving | water | **110/4** | 6 × 10⁻²⁰ |
| | environmental impact | 97/17 | 4 × 10⁻¹⁶ |
| | cost | 80/34 | 3 × 10⁻⁶ |
| | yield | 0/114 | 2 × 10⁻²⁰ |
| | income | 4/110 | 3 × 10⁻²⁰ |
| Sustainability | water | **107/5** | 3 × 10⁻¹⁸ |
| | environmental impact | **93/19** | 4 × 10⁻¹⁵ |
| | soil suitability | **68/21** | 7 × 10⁻¹² |
| | cost | 71/41 | 2 × 10⁻⁵ |
| | rainfall exposure | 29/62 | 0.005 |
| | yield | 1/111 | 1 × 10⁻¹⁹ |
| | income | 5/107 | 5 × 10⁻¹⁹ |
| Low cost | cost | **94/7** | 2 × 10⁻¹⁷ |
| | budget headroom | 49/0 (budget fronts) | 1 × 10⁻⁹ |
| | water | 91/10 | 6 × 10⁻¹⁷ |
| | environmental impact | 84/17 | 1 × 10⁻¹⁴ |
| | yield | 10/91 | 5 × 10⁻¹⁷ |

Each profile improves its high-tier criteria on the large majority of fronts and gives up its low-tier ones, as designed. Two results need saying explicitly:

* **Profit does not raise the market price.** Its #1 has a higher price per quintal on only 49 of 112 fronts, not significant. On these fronts income comes from tonnage, and the high-tonnage crops (tapioca, sugarcane) are cheap per quintal (ρ(income, price) = −0.39).
* **Sustainability increases rainfall exposure.** It worsens on 62 fronts against 29, even though the profile weights rainfall exposure (medium). Saving irrigation water favours rain-fed crops, and the high-tier water weight outweighs the medium-tier rainfall weight. A farmer who cares more about monsoon risk can raise rainfall exposure in a custom profile.

### 2.5 Sensitivity of the weighting rule

Rank-sum weights (used) against rank-order-centroid weights (Barron & Barrett 1996) for the same tiers:

| Profile | Same #1 | ROC's #1 under rank-sum (median rank) | Closeness gap (median) | Largest objective difference (median) |
|---|---|---|---|---|
| Profit | 76 % | 1 | 0.0000 | 0 % |
| Low cost | 45 % | 2 | 0.0002 | 1.3 % |
| Water saving | 22 % | 3 | 0.0019 | 12 % |
| Sustainability | 5 % | 6.5 | 0.0035 | 25 % |

Balanced's #1 under a yield weight of 0.27 or 0.33 (±10 %):
* it is unchanged on 3 % of fronts;
* the new #1 ranks 4th under 0.30 (median; worst 37th), with a closeness gap of 0.0028;
* it differs by up to 17.8 % on one objective (median).

Conclusion: the tiers decide the region of the front a profile recommends. The exact weights decide between close neighbours there, as for the published Balanced weights. This is why the panel shows the top plans and their scores, not a single plan.

### 2.6 Performance

Median per 80-plan front:

| Operation | Time |
|---|---|
| published ranking | 0.48 ms |
| profile ranking | 0.59 ms |
| five-profile comparison | 1.36 ms |
| ranking explanation | 0.76 ms |

A whole `POST /api/farm-plans` takes ≈ 0.29 s with or without a profile or the comparison; NSGA-II dominates.
