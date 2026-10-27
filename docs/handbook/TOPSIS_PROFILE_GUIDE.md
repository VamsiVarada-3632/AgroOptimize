# TOPSIS Profile Guide

Which ranking profile to choose, what each one weights, and how to build your own. Profiles change only the order of the Pareto-optimal plans: every profile ranks the same plans, found by the same NSGA-II run. Criterion definitions: [TOPSIS_DYNAMIC_ENGINE.md](TOPSIS_DYNAMIC_ENGINE.md) §3.

## 1. Choosing a profile

| If you want… | Choose | What usually happens to the top plan (vs Balanced) |
|---|---|---|
| the published recommendation, a central trade-off | **Balanced** | — |
| the most income from the season | **Profit priority** | yield +37 %, income +78 %, but water +59 % and cost +21 % |
| to save irrigation water | **Water saving** | water −54 %, impact −31 %, yield −56 % |
| low impact, low water use and crops that suit your soil | **Sustainability** | water −40 %, impact −12 %, yield −41 % |
| to spend as little as possible | **Low cost** | cost −18 %, yield −71 % |
| your own priorities | **Custom** | whatever your weights imply |

Percentages compare the median #1 plan of each profile with Balanced's median #1 over the same 120 fronts (`benchmarks/topsis_benchmark.json`, chart `benchmarks/topsis_top_plan_objectives.png`). Sustainability's #1 also has a better soil fit (+8 %) at slightly higher rainfall exposure (+9 %).

## 2. Profile definitions

Each profile except Balanced lists criteria in three importance tiers. The weights follow from one rule, **rank-sum weights over the tiers**: high = 3 points, medium = 2, low = 1, divided by the total (Stillwell, Seaver & Edwards 1981). Unlisted criteria get 0.

| Profile | High | Medium | Low |
|---|---|---|---|
| Balanced | published weights: yield 0.30; cost, water, impact 0.70/3 each ([TOPSIS_WEIGHT_ANALYSIS.md](TOPSIS_WEIGHT_ANALYSIS.md)) | | |
| Profit priority | income, market price, yield | production cost | water, environmental impact |
| Water saving | water, environmental impact | production cost | yield, income |
| Sustainability | environmental impact, water, soil suitability | yield, production cost, rainfall exposure | income |
| Low cost | production cost, budget | water, environmental impact | yield |

Design choices:

* **Every profile keeps all four optimiser objectives.** Production cost and the other footprint objectives always count for something, so no profile can pick a plan that is absurd on an objective the optimiser traded off.
* **Profit includes cost (medium).** Income already subtracts cost, but cost also stands for the money at risk before harvest.
* **Sustainability includes rainfall exposure (medium).** Saving irrigation water pushes towards rain-fed crops. Rainfall exposure keeps the cost of that, dependence on the monsoon, in view (ρ(rainfall, water) = −0.74).
* **Low cost includes budget (high).** On one front budget headroom ranks plans exactly like cost, so it doubles the emphasis on cost when a budget is set. Without a budget it is constant and neutral.

## 3. Weight table (percent)

| Criterion | Balanced | Profit | Water saving | Sustainability | Low cost |
|---|---|---|---|---|---|
| Yield | 30.0 | 23.1 | 10.0 | 12.5 | 9.1 |
| Market price | – | 23.1 | – | – | – |
| Income | – | 23.1 | 10.0 | 6.2 | – |
| Production cost | 23.3 | 15.4 | 20.0 | 12.5 | 27.3 |
| Water | 23.3 | 7.7 | 30.0 | 18.8 | 18.2 |
| Environmental impact | 23.3 | 7.7 | 30.0 | 18.8 | 18.2 |
| Budget | – | – | – | – | 27.3 |
| Soil suitability | – | – | – | 18.8 | – |
| Land use | – | – | – | – | – |
| Rainfall exposure | – | – | – | 12.5 | – |

Chart: `benchmarks/topsis_profile_weights.png`. Machine-readable: `GET /api/topsis/profiles`.

**Sensitivity to the weighting rule.** A different rule for the same tiers, rank-order-centroid weights (Barron & Barrett 1996), gives the same #1 plan on:

| Profile | same #1 | ROC's #1 under rank-sum (median rank) | closeness gap (median) | largest objective difference (median) |
|---|---|---|---|---|
| Profit | 76 % of fronts | 1 | 0.0000 | 0 % |
| Low cost | 45 % | 2 | 0.0002 | 1.3 % |
| Water saving | 22 % | 3 | 0.0019 | 12 % |
| Sustainability | 5 % | 6.5 | 0.0035 | 25 % |

The tiers decide the kind of plan, and the rule decides between close neighbours. For Sustainability, with seven weighted criteria, the rule matters most.

## 4. Custom weights

Give each of the ten criteria a weight.

| Rule | Detail |
|---|---|
| Range | each weight between 0 and 1 (0–100 % in the app) |
| Sum | the weights must sum to 1 (tolerance 10⁻⁶; the app requires 100.0 % ± 0.01) |
| Omitted criteria | weight 0 |
| Unknown criteria | rejected |
| Defaults | the Balanced weights (`custom.default_weights` in `GET /api/topsis/profiles`; "Reset to Balanced" in the app) |
| Errors | `422` with the reason, e.g. "Custom weights must sum to 1 (they sum to 0.9)" |

In the app, **Scale to 100%** rescales the sliders proportionally.

API:

```json
POST /api/farm-plans
{"location": "Salem", "season": "Kharif", "total_land_ha": 5,
 "profile": "custom", "custom_weights": {"yield": 0.3, "water": 0.3, "soil": 0.2, "rainfall": 0.2}}
```

Tips:

* **Avoid redundant pairs.** Weighting income and yield together, or budget and cost together, counts one thing twice (ρ = +1.00 and −1.00).
* **Expect large swings from one criterion.** A single criterion with a large weight usually picks a corner of the front: the best plan for that criterion, whatever the rest.
* **Land use is nearly independent of the other criteria** (ρ with yield −0.16). It is the criterion for "don't put everything in one crop".

## 5. Profiles and classic preferences

The five classic preferences (balanced, max yield, min cost, min water, min environmental impact) still work in the API and in the app's "Classic preference" drop-down. They weight the four objectives only (0.55 on the named one). A request may use a preference or a profile, not both. Balanced is the same in both.
