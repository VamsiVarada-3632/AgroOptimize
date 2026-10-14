# Scoring and Ranking

Every score, label and threshold the system produces, with its exact formula, code location, and an honesty rating: **Derived** (computed from data by a defensible formula), **Heuristic** (formula exists but constants are arbitrary), **Presentation** (a display convention with no analytical meaning).

## 1. Plan-level scores (`app/decision/ranking.py`)

| Output | Formula | Range | Type |
|---|---|---|---|
| `composite_score` | TOPSIS closeness C = d⁻/(d⁺+d⁻) over the weighted, min–max normalised objectives of the plan set (see [ALGORITHMS.md](ALGORITHMS.md) §5.2) | 0–1 | Derived (weights heuristic) |
| `rank` | order of `composite_score` descending, 1-based, after truncation to 50/100 | 1… | Derived |
| `normalized_scores.{yield,cost,water,env}` | per objective min–max within the returned set; flipped for cost/water/env so 1 = best | 0–1 | Derived, **relative to this run only** |
| `confidence_label` | Σ shareᵢ × crop_confidenceᵢ; ≥0.66 High, ≥0.33 Moderate, else Low (unknown crop → 0.7) | label | Heuristic; "Low" unreachable with current data |
| `trade_off_summary` | raw min–max position of each objective in the set → Low (<0.33) / Moderate / High (≥0.66) | text | Presentation (relative, not absolute) |
| `allocation_percent` | share × 100, largest-remainder rounding to 2 dp so the list sums to 100.00 | % | Derived |

Important: "High yield" means *high relative to the other plans in this run*, not high in agronomic terms.

## 2. Preference weights

| Preference | yield | cost | water | env | Source |
|---|---|---|---|---|---|
| balanced | 0.300 | 0.2333 | 0.2333 | 0.2333 | tuned by hand so rank-1 is mid-range (not a corner) |
| max_yield / min_cost / min_water / min_env_impact | 0.55 on the named objective, 0.15 on the others | | | | convention |

Unknown preference strings fall back to balanced (unreachable through the API because `Preference` is a `Literal`).

## 3. Comparison page (`GET /api/comparison`, `ComparisonView.jsx`)

### 3.1 Plan selection
One NSGA-II run (population 100) → three TOPSIS rankings of the same feasible front: **A** = balanced #1, **B** = max_yield #1, **C** = min_cost #1. The three can coincide (then the page shows the same plan three times).

### 3.2 Headline metrics (per hectare, area = Σ area_ha)
`yield_val = yield_tonnes/area` (t/ha) · `cost = cost_rs/area` (₹/ha) · `env_impact = env_impact_score/area`.
`water` label: lowest of the three → "Efficient", highest → "High usage", else "Moderate" (relative only).

### 3.3 Radar scores (0–100, `dashboard_service._radar_scores`)

| Axis | Formula | Type | Caveat |
|---|---|---|---|
| yield | 100 × (y − min)/(max − min) over A,B,C | Derived | With only 3 points, one plan always scores 0 and one 100 → exaggerated contrast |
| cost_eff | 100 × (1 − (c − min)/(max − min)) | Derived | same |
| water | same on water_liters | Derived | same |
| land | same on env_impact_score ("land impact" proxy) | Derived | label "Land" is loose – it is the fertiliser/pumping impact score |
| risk | 100 × (1 − irrigation_risk) | Heuristic | **identical for all three plans** (regional value) |
| market | 100 × (1 − mean RAINFALL_DEPENDENCY_FACTOR of crops with share > 1 %) | Heuristic | no market data exists; this is climate dependency relabelled |

If all three values are equal the axis is 50.

### 3.4 "Adjust Weights" re-recommendation (frontend only)
`score = (w_y/100)·radar.yield + (w_c/100)·radar.cost_eff + (w_w/100)·radar.water`, default weights 50/50/50, highest score gets the "Rec" badge. This **is a second recommender** that can disagree with TOPSIS's Plan A (e.g. Coimbatore on 2026-09-29: TOPSIS recommends A, the default weights badge C). See UI_UX_REVIEW U-9.

### 3.5 Table column "Env. Impact/ha"
Since 2026-09-29 shows the real `env_impact` per hectare (lower is better) with a bar relative to the largest of the three. Previously it showed `round(radar.land/5)/20` – a *goodness* score presented as impact (the gentlest plan showed "20/20").

## 4. Dashboard (`GET /api/dashboard`, `DashboardView.jsx`)

| Card / field | Formula | Type | Caveat |
|---|---|---|---|
| Estimated Yield (t/ha) | mean of `Yield_Kg_Ha` over **all crops and seasons** of the latest year ÷ 1000 | Presentation | Averages sugarcane (~95 t/ha) with cotton (1.5 t/ha): not a yield of any real farm |
| Yield trend | (mean latest − mean previous)/mean previous × 100 | Derived | 2024 is 2023 × 1.03 → always "+3.0 %" (estimation artefact, now flagged) |
| Active Plans | # saved runs for this district with this browser's `client_id` | Derived | |
| Soil Health % | round(fertility index) of latest-year, current-season land row | Heuristic | |
| Soil status | ≥70 Optimal, ≥45 Moderate, else Needs Attention (backend) | Heuristic | same thresholds duplicated in AnalyticsView |
| Water Utilization % | Σ Irrigation_Water_MCM / Σ Total_Demand_MCM × 100 over the latest year | Derived | It is irrigation's *share of demand*, not how well water is used |
| Water badge | ≥70 "Optimal", ≥40 "Moderate", else "Low" (frontend `waterLabel`) | Presentation | A higher irrigation share is not "optimal" in any agronomic sense |
| Recommended actions | Low N/P/K status → apply fertiliser action; mean latest-year storage < 40 % → irrigation action; otherwise "No urgent action" | Heuristic | Urgency windows ("Next 48 hours", "Next 5 days") are hard-coded text; "Schedule" buttons only toggle local state |
| Crop Allocation Overview | top-3 candidate crops by district revenue for the current season; pct = revenue share; ha = share × 10 ha reference | Presentation | A revenue share, not an optimised allocation |
| `data_year`, `data_year_estimated` | latest crop year and whether its rows are "Estimated" | Derived | new |

## 5. Analytics page (`AnalyticsView.jsx`)

| Element | Rule |
|---|---|
| Scatter points | every plan from `/api/plans` (cost/ha vs yield/ha); gold = TOPSIS balanced rank 1 |
| Slider bounds | min/max of the plotted values padded by 10 % |
| "Valid Plans" | plans with cost ≤ max-cost slider, yield ≥ min-yield slider, water ≤ max-water slider |
| "Best Compliant Plan" | **cheapest** valid plan (not TOPSIS) |
| Soil Suitability | `fertility_index × 100` → ≥70 Optimal, ≥45 Moderate, else Needs Attention |
| Convergence chart | `hypervolume_history` (run-relative normalised HV, y-axis from 0) |
| Fuzzy vs non-fuzzy table | `/api/compare-fuzzy` per-hectare best/min values |

## 6. History and Reports

| Field | Formula |
|---|---|
| `target_yield` | top-ranked plan's `yield_tonnes / Σ area_ha` → "x.xx t/ha" |
| `est_cost` | top plan `cost_rs / Σ area_ha` → "₹n/ha" |
| History "Yield confidence / irrigation risk %" | stored fuzzy assessment × 100 |
| Report file | top 3 plans of the saved run, totals and per-ha, plus region snapshot and fuzzy assessment (see [REPORT_PIPELINE.md](REPORT_PIPELINE.md)) |

## 7. Recommendation logic – which "recommended" is which

| Where | "Recommended" means |
|---|---|
| `/api/farm-plans` rank 1 | TOPSIS #1 under the user's chosen preference |
| Analytics gold dot / `is_recommended` | TOPSIS balanced #1 of the dashboard front (pop 100) |
| Analytics "Best Compliant Plan" | cheapest plan passing the sliders |
| Comparison `recommended: true` | Plan A (TOPSIS balanced #1) |
| Comparison "Rec" badge | frontend weighted sum over three radar axes |
| Dashboard actions | rule-based soil/water checks |

Consolidating these (TODO T-11) would remove the most common source of examiner confusion.
