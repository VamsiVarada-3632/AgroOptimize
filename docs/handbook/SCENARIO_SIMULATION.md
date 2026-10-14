# Scenario Simulation & Decision Impact Analysis

Lets a user change farming conditions and see how the optimised recommendation responds, and why. Every simulation runs the real pipeline (preprocessing → fuzzy → NSGA-II → TOPSIS → explanation engine) for both the original and the modified conditions; nothing is approximated, cached or hard-coded. Backend: `app/services/simulation_service.py`. Frontend: `frontend/src/views/SimulationView.jsx`, `frontend/src/components/simulation/SimulationSections.jsx`.

## 1. Where scenario inputs enter the pipeline

The pipeline was reverse-engineered stage by stage; each control is applied at the single point where the corresponding quantity is used, through default-neutral hooks (defaults reproduce every existing result exactly — verified on 48 stored outputs).

| Control | Values | Enters at | Hook |
|---|---|---|---|
| Rainfall | −30 … +30 % in 10 % steps | Stage 1: monthly rainfall scaled before the season is aggregated; each month's deviation recomputed against the dataset's own normal (the CSV's `Deviation_Percent` follows the same formula, max difference 0.05). Changes both the fuzzy rainfall input and the effective rainfall in the water objective | `get_region_season_profile(rainfall_factor=)` |
| Water availability | Current, Very low … Very high | Stage 2: fuzzy water-storage input (seasonal storage %) | `get_region_season_profile(storage_override_pct=)` |
| Fertiliser cost | −20 … +30 % | Stage 3: N/P/K prices in the cost objective | `FarmPlanProblem(fertilizer_price_factor=)` |
| Land, budget | any | Stage 3: hectares allocated; budget constraint | existing request fields |
| Preference / priority sliders | named preference or four 0–100 sliders | Stage 7: TOPSIS weights (sliders scaled to sum to 1). NSGA-II is Pareto-based and has no weights | `rank_plans(weights=)` |
| Market price | Decrease / Stable / Increase | Indicative revenue and profit only. Price is not an optimiser objective, so on its own it cannot change the plan | `ExplanationContext.price_factor` |

`plan_service.run_pipeline(request, adjustments, track_history, seed)` runs stages 1–7 with a `PipelineAdjustments` value; `generate_farm_plans` now calls it, so Run Optimization and the simulator share one code path.

### Value definitions
* **Water levels → storage %** placed in distinct regions of the fuzzy model's own water-storage sets (low [0,0,35], medium [20,50,75], high [60,100,100]): Very low 10 (only *low*), Low 25 (overlap, *low* dominant), Medium 50 (peak of *medium*), High 70 (overlap, *high* dominant), Very high 90 (only *high*). A test checks each level's dominant set.
* **Market step** = the largest one-year change in the district's price column over observed years (Salem 11.4 %, Coimbatore 12.9 %, Erode and Pollachi 11.4 %). The data contains no year-on-year price decline, so *Decrease* is labelled a stress test.

## 2. Why each side runs five times

NSGA-II is stochastic. With identical inputs and different seeds, the recommended plan differs markedly — for Salem Kharif, 5 ha, balanced, the top plan's yield ranged from 50.2 to 69.8 t and Tapioca's share from 65 % to 100 % across seeds 42, 1, 2, 3, 4. Comparing one baseline run with one scenario run would attribute that search variation to the scenario.

Each side is therefore optimised with the same seeds `ENSEMBLE_SEEDS = (42, 1, 2, 3, 4)` (common random numbers), and every change is judged with a **paired t-test** over the five pairs:

| Verdict | Rule |
|---|---|
| improved / worsened | p < 0.05 and |change of means| ≥ 1 % (direction by objective) |
| unchanged | every pair identical, or |change| < 1 % |
| within search variation | moved, but p ≥ 0.05 — not attributed to the scenario |

The displayed recommendation of each side is the **first seed's run** (seed 42, the one Run Optimization uses, with convergence history tracked), so the original recommendation, its explanation and its confidence are exactly what Run Optimization shows for the same inputs (tested).

## 3. Flow

```mermaid
flowchart LR
    UI[SimulationView form] -->|POST /api/simulations/run| R[resolve: validate,<br/>map controls]
    R --> B[baseline: run_pipeline × 5 seeds]
    R --> S[scenario: run_pipeline × 5 seeds<br/>with PipelineAdjustments]
    B & S --> SIDE[_side: explanation of seed-42 run,<br/>per-run metrics, single-crop metrics]
    SIDE --> A[analysis: conditions · comparison · impact (paired) ·<br/>crop effects · fuzzy changes · optimisation difference ·<br/>constraints · historical · statements · trade-offs · summary]
    A --> T[token kept in memory, 32 newest]
    A --> UI2[sections + charts render the payload]
    T -->|POST /api/simulations| SV[results/simulations/sim_*.json]
```

## 4. Result sections

| Section | Content | Computed from |
|---|---|---|
| Conditions | every condition, original vs scenario, where it enters the pipeline | request, both region profiles |
| Recommendation comparison | both recommended crop plans, TOPSIS closeness, recommendation strength, confidence and its components; per-crop mean shares over the runs with p-values | seed-42 runs, explanation engine, paired tests |
| Impact summary | yield, cost, water, environmental impact (totals, or per hectare when land differs), indicative profit, confidence: means, seed ranges, recommended-plan values, change %, p, verdict; baseline run-to-run spread | per-run top plans; `explanation_service.indicative_economics` |
| Decision impact | generated statements (§5) | all sections |
| Trade-offs | improved / worsened / unchanged / within variation; constraints whose status became harder (explanation-engine constraint statuses, budget use ≥ 95 %, infeasibility) | impact, explanation constraints |
| Optimization difference | Pareto sizes and per-hectare ranges, TOPSIS weights and dominant objective, whether the front is identical, weight × goodness contributions, both plans on a common 0–1 scale (min–max over the union of both fronts, the TOPSIS normalisation), fuzzy inputs/outputs, rules whose firing changed by ≥ 0.05 | fronts, `ranking.topsis_scores`, `fuzzy.fired_rules` |
| Condition vs re-optimisation | each seed's baseline plan re-evaluated with the scenario's objective function: *same plan, new conditions* (deterministic) vs *re-optimising* (paired test) | `FarmPlanProblem.evaluate` |
| Crop suitability changes | per crop, grown alone at baseline inputs per hectare (no search): fuzzy confidence, yield, cost, irrigation, impact under each side's conditions; mean land share | `FarmPlanProblem.single_crop_metrics` |
| Historical comparison | recommended crops vs the district's observed cropping pattern and yields; alignment = Σ min(plan share, historical share) with historical shares rescaled over the candidate crops | `district_service` trends (observed years) |
| Scenario summary | 3–7 sentences from the computed facts | all sections |

An infeasible scenario (e.g. budget below the cheapest possible plan) returns `scenario.available = false` with the reason and the cheapest possible plan's cost (all land in the cheapest crop at the lowest fertiliser level — cost is linear in the allocation, so this is the true minimum). An infeasible baseline is a 422.

## 5. Generated statements
Rainfall (effective rainfall, deviation, fuzzy set, the crop whose irrigation need changed most); water availability (storage, fuzzy set, irrigation risk); crop suitability (most and least affected fuzzy confidence, with rainfall dependency); fertiliser (cost change per hectare by crop); priorities (dominant TOPSIS weight); market (profit only); land shifts — only for shifts that are ≥ 5 pp **and** p < 0.05, prefixed "With only X changed" when exactly one condition changed, with the crop's own per-hectare changes and how it compared with the crop that lost land; "within search variation" for large but unreliable shifts; no reliable change in the crop mix; carry-over of the baseline plan. Format `{id, title, detail, source, evidence}` (`explanation_service.make_item`).

## 6. Example (Salem, Kharif, 5 ha, balanced; rainfall −20 %, water Low, priorities 30/20/40/10)
4.1 s for 10 optimisations. Original Tapioca 91 % / Maize 3 % / Groundnut 5 % → simulated Tapioca 42 % / Maize 54 % / Groundnut 4 % (shift consistent for Tapioca and Maize). Means of 5 runs: yield −57.2 % (p 0.0004), cost −12.2 % (p 0.0003), irrigation water −17.9 % (p 0.006), environmental impact +15.5 % (p 0.0009), indicative profit −55.7 %; confidence 73.6 % → 68.4 %. Without the priority change (rainfall −20 % and water Low only) the same comparison gave cost −6.6 % (p 0.11) and irrigation water −6.7 % (p 0.47) — within search variation — while the yield (−48.0 %) and profit changes were reliable.

## 7. API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/simulations/run` | run a simulation (`SimulationRequest` → `SimulationOut` + `token`); 422 on invalid input |
| POST | `/api/simulations` | save a result of this session by `token` (`SimulationSaveIn`) → 201 summary; 404 if expired or another browser's |
| GET | `/api/simulations?client_id=` | this browser's saved simulations, newest first |
| GET | `/api/simulations/{id}?client_id=` | full saved record (inputs + result) |
| DELETE | `/api/simulations/{id}?client_id=` | delete one |

Request:
```json
{"base": {"location": "Salem", "season": "Kharif", "year": null, "total_land_ha": 5, "budget_rs": null, "preference": "balanced"},
 "scenario": {"rainfall_change_pct": -20, "water_availability": "low", "fertilizer_cost_change_pct": 0, "market_price": "stable",
              "total_land_ha": null, "budget_rs": null, "preference": null,
              "priorities": {"yield": 30, "cost": 20, "water": 40, "env": 10}},
 "client_id": "…"}
```
Validation: rainfall ∈ {−30,−20,−10,0,10,20,30}; fertiliser ∈ {−20,−10,0,10,20,30}; water ∈ {current, very_low, low, medium, high, very_high}; market ∈ {decrease, stable, increase}; priorities 0–100, not all zero; land 0–100 000 ha. Saving uses a server-held token, so a stored result is exactly what was computed (the client cannot submit its own numbers). Saved ids are timestamped with a random suffix and scoped to the browser's `client_id`, like saved runs.

## 8. Frontend

| Piece | Role |
|---|---|
| `views/SimulationView.jsx` | form (original conditions + scenario controls + priority sliders), saved scenarios (open / delete), run, save with a name, export report (HTML) and JSON |
| `components/simulation/SimulationSections.jsx` | `RecommendationSection`, `ImpactSection`, `DecisionImpactSection`, `TradeOffSection`, `OptimizationSection`, `CropEffectsSection`, `HistoricalSection`, `ConditionsSection`, `VerdictBadge` |
| `components/charts/GroupedBarChart.jsx` | two series per category with min–max whiskers (crop plan, confidence components, objective contributions, indexed objective comparison) |
| `components/charts/DeltaBarChart.jsx` | % change around zero, value and verdict written next to each bar |
| `components/charts/RadarChart.jsx` | both plans on the common objective scale |
| `utils/simulationView.js` | request building, reopening, formatting, chart data selection (no outcome is computed) |
| `utils/simulationReport.jsx` | self-contained HTML report with the charts rendered to static SVG; loaded on demand so `react-dom/server` stays out of the main bundle |

Charts reuse the validated accent/gray pair (simulated = accent green, original = gray; CVD ΔE 18.8). Both series are always named in a legend, verdicts carry text and an icon, and every chart has a table view. Yield, cost, water and impact have different units, so they share one chart **indexed to the original mean = 100**; absolute values are in the impact cards and the table view. Bar charts keep a 480 px minimum width and scroll inside their card on phones.

## 9. Tests
* Backend `tests/test_simulation.py` (61): hooks neutral by default and exact when used (rainfall and deviation recomputed from the CSV, storage, fertiliser cost recomputed from CSV rows and config prices, single-crop metrics, explicit weights = preference weights); `run_pipeline` = a normal run; water levels in their fuzzy sets; market step recomputed; parameter validation; paired comparison (identical, constant shift, noisy, missing runs; p-value equals `scipy.stats.ttest_rel`); end-to-end scenarios — unchanged (no change reported, same plan as Run Optimization, same confidence), drought (inputs reach the pipeline, crop water needs from the CSV, impact = paired means, seed runs reproduce independently, decomposition re-evaluation), market (profit only), priorities (identical front, weights), infeasible budget (cheapest plan recomputed from the CSV), land change (per-hectare basis); historical alignment recomputed; statements only attribute reliable shifts; trade-offs follow verdicts; explanation weights and price factor; persistence (scoping, path safety, delete); pending-result bound; all endpoints.
* Frontend (Vitest, 24 new): request building and reopening, formatting, selection helpers, the three chart components, every section against real payloads (drought and infeasible), the exported report, the empty page.

## 10. Limitations
* Five seeds per side is a compromise between rigour and response time (~4 s); small effects can be reported as "within search variation" that more runs might resolve.
* Market price changes cannot alter the plan because price is not an objective; prices are the dataset's unvalidated MSP column.
* Water availability acts only through the fuzzy model (the optimiser has no water-availability constraint); irrigation water itself is driven by crop requirements and effective rainfall.
* Rainfall scaling is uniform across the season's months; temperature, humidity and soil stay at the dataset values.
* The default data year is 2024, which is estimated; the page says so.
* Unsaved results are kept in process memory (32 newest) for saving; they are lost on restart.

## 11. Future improvements
1. Adaptive run count (add seeds until the confidence interval of the headline change is narrow enough).
2. Optional water-availability constraint in `FarmPlanProblem` so scarce water can bind the plan directly.
3. Month-level rainfall patterns (e.g. delayed onset) rather than a uniform factor.
4. Profit as an optional fifth objective once prices are validated.
5. Sensitivity sweeps (e.g. rainfall −30 → +30 in one request) with a response curve.
6. Server-side PDF report.
