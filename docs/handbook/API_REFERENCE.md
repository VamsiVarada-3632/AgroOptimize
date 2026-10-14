# API Reference

Base URL: local `http://localhost:8000`; production `https://agrooptimize-backend.fly.dev` (from `stitch_agrooptimize_app/.env.production`). Interactive schema: `GET /docs` (Swagger) and `/openapi.json`. No authentication on any endpoint. All bodies are JSON. Latencies are measured in-process (TestClient, Apple Silicon laptop, 2026-09-29); network adds to them.

| Method | Path | Purpose | Used by frontend | Cold / warm latency |
|---|---|---|---|---|
| GET | `/health` | Liveness | App.jsx startup | 1–18 ms |
| GET | `/api/catalog` | Locations, seasons, years, crops | Auth, ProfileSetup, Settings, RunOptimization | 16 ms |
| GET | `/api/region-profile` | Stages 1–2 only (data + fuzzy) | – | 632 ms first call (builds FIS), then ~10 ms |
| POST | `/api/farm-plans` | Full pipeline, optionally saved | RunOptimization | ≈300 ms (pop 80 × 200 gen) |
| GET | `/api/results` | List saved runs | – | O(#runs), cached by mtime |
| GET | `/api/results/{run_id}` | One saved run | Reports | ~1 ms |
| GET | `/api/weather/{district}` | Live weather (Open-Meteo) or CSV fallback | Dashboard (×5 calls) | network-bound, ≤5 s timeout |
| GET | `/api/dashboard/{district}` | KPI cards, actions, crop split | Dashboard | 42 ms |
| GET | `/api/history/{district}` | This browser's saved runs | History, Reports | ~1 ms |
| GET | `/api/soil-profile/{district}` | Soil snapshot | Analytics | ~1 ms |
| GET | `/api/plans/{district}` | ≤100 Pareto plans + HV history | Analytics | 966 ms cold / 3 ms cached |
| GET | `/api/comparison/{district}` | Plans A/B/C + radar | Comparison | 369 ms cold / 3 ms cached |
| GET | `/api/compare-fuzzy/{district}` | Fuzzy vs non-fuzzy study | Analytics | 746 ms (2 runs, not cached) |
| GET | `/api/results/{run_id}/explanation?rank=` | Explanation of one plan in a saved run | Run Optimization, History, Reports | tens of ms |
| GET | `/api/comparison/{district}/explanation?plan=` | Explanation of Plan A/B/C | Comparison | ~1 s cold, fast when the front is cached |
| GET | `/api/district-intelligence/{district}` | Aggregated district profile | District Intelligence | 30–120 ms cold, ≈0 cached |
| POST | `/api/simulations/run` | Run a scenario simulation (baseline + scenario, 5 seeds each) | Scenario Simulation | ~4 s, never cached |
| POST | `/api/simulations` | Save a simulation result by token | Scenario Simulation | fast |
| GET | `/api/simulations?client_id=` | This browser's saved simulations | Scenario Simulation | fast |
| GET | `/api/simulations/{id}?client_id=` | One saved simulation | Scenario Simulation | fast |
| DELETE | `/api/simulations/{id}?client_id=` | Delete a saved simulation | Scenario Simulation | fast |

`{district}` is case-insensitive (`coimbatore`, `Salem`, ` ERODE `). Unknown → 404.

## Error model

| Status | When | Body |
|---|---|---|
| 400 | `ValueError` in the pipeline for core endpoints (unknown location/season, no data for year, <2 crops) | `{"detail": "No data for location='Salem', year=2019. Available years: [...]"}` |
| 404 | Unknown district on dashboard endpoints; unknown/invalid `run_id`; `ValueError` in comparison/compare-fuzzy | `{"detail": "..."}` |
| 422 | Pydantic/Query validation | `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}` |
| 503 | `/api/plans` optimisation failure | `{"detail": {"error": "Optimization failed", "message": "...", "location": "..."}}` |
| 500 | Unhandled exception | FastAPI default |

The frontend's `describeApiError` (src/services/api.js) turns any of these into user text.

---

## GET /health
`200 {"status": "ok"}`

## GET /api/catalog
```json
{"locations": ["Coimbatore","Erode","Salem","Pollachi"],
 "seasons": ["Kharif","Rabi","Summer"],
 "years": [2020,2021,2022,2023,2024],
 "crops_by_season": {"Kharif": ["Banana","Coconut","Cotton","Groundnut","Maize","Paddy","Sorghum","Sugarcane","Tapioca","Turmeric","Vegetables"],
                     "Rabi": ["Banana","Groundnut","Paddy","Sugarcane","Sunflower","Turmeric","Wheat"],
                     "Summer": ["Banana","Coconut","Fodder Crops","Maize","Mango","Vegetables"]}}
```
`years` includes 2024, which is estimated (see [DATASETS.md](DATASETS.md) §1).

## GET /api/region-profile
Query: `location` (required, case-insensitive), `season` (required), `year` (optional, default latest).
```json
{"location":"Salem","year":2024,"season":"Kharif",
 "soil":{"soil_type":"Red Loam","avg_ph":6.8,"organic_carbon_percent":0.58,"n_status":"Medium","p_status":"Medium","k_status":"Medium","irrigation_percent":60.4,"fertility_index":67.8},
 "rainfall":{"avg_monthly_rainfall_mm":63.1,"avg_deviation_percent":-21.1,"avg_humidity_percent":70.5,"avg_max_temp_c":35.5,"avg_min_temp_c":24.05,"months_used":["June","July","August","September"],"effective_rainfall_mm":176.68},
 "water":{"avg_storage_percent":62.0,"groundwater_status":"Very High","avg_deficit_surplus_mcm":0.0},
 "candidate_crops":["Paddy","Tapioca","Maize","Groundnut","Cotton"],
 "normalized_snapshot":{"soil_ph_norm":0.56,"organic_carbon_norm":0.387,"rainfall_norm":0.421,"rainfall_deviation_norm":0.289,"water_storage_norm":0.62,"soil_fertility_index_norm":0.678},
 "data_year_estimated":true,
 "fuzzy_assessment":{"yield_confidence":0.636,"irrigation_risk":0.465,"rainfall_label":"deficit","water_label":"medium","soil_label":"medium"}}
```
Note: here `candidate_crops` is a list of names; in `POST /api/farm-plans` it is a list of objects.

## POST /api/farm-plans
Request (`FarmPlanRequest`):

| Field | Type | Constraint | Default | Meaning |
|---|---|---|---|---|
| location | str | one of catalog locations (case-insensitive) | required | |
| season | str | Kharif/Rabi/Summer (case-insensitive) | required | |
| year | int | must exist for location | latest (2024) | |
| total_land_ha | float | > 0 | required | farm size |
| budget_rs | float | > 0 | none | hard constraint cost ≤ budget |
| preference | enum | balanced, max_yield, min_cost, min_water, min_env_impact | balanced | TOPSIS weights |
| max_candidate_crops | int | 2–12 | 6 | top-N by revenue |
| max_cost_rs, max_water_liters, min_yield_tonnes, max_env_impact | float | ≥ 0 | none | post-hoc filters |
| pop_size | int | 8–300 | 80 | |
| n_gen | int | 5–500 | 200 | |
| save_results | bool | | true | persist to results/ and track convergence |
| client_id | str | ≤128 chars | none | scopes History |

Response (`FarmPlanResponse`, ≈33 KB with 50 plans):
```json
{"region_profile": {"...": "as region-profile, but candidate_crops are objects:",
                    "candidate_crops":[{"name":"Paddy","crop_type":"Cereal","yield_kg_ha":5871.0,"water_req_mm":1236.0,"rainfall_dependency":"Low","irrigation_type":"Flood","sowing_month":"June","harvest_month":"November","crop_duration_days":145}],
                    "data_year_estimated": true},
 "fuzzy_assessment": {"yield_confidence":0.636,"irrigation_risk":0.465,"rainfall_label":"deficit","water_label":"medium","soil_label":"medium"},
 "plans": [{"rank":1,"crop_names":["Paddy","Tapioca","Maize","Groundnut","Cotton"],
            "allocation_percent":[0.01,91.33,3.26,5.39,0.01],"area_ha":[0.001,4.566,0.163,0.269,0.001],
            "irrigation_multiplier":[0.853,0.7,0.7,0.7,0.7],"fertilizer_multiplier":[0.845,0.7,0.7,0.7,0.7],
            "yield_tonnes":64.764,"cost_rs":197947.86,"water_liters":21504151.5,"env_impact_score":194.346,
            "feasible":true,"composite_score":0.6319,
            "normalized_scores":{"yield":0.921,"cost":0.352,"water":0.603,"env":0.586},
            "confidence_label":"Moderate",
            "trade_off_summary":"High yield, Moderate cost, Moderate water use, Moderate environmental impact (confidence: moderate)"}],
 "convergence_history": [{"generation":1,"population_size":80,"best_yield_tonnes":0.0,"mean_yield_tonnes":0.0,"best_cost_rs":0.0,"mean_cost_rs":0.0,"best_water_liters":0.0,"mean_water_liters":0.0,"best_env_impact":0.0,"mean_env_impact":0.0,"hypervolume":0.0}],
 "meta": {"algorithm":"NSGA-II","pop_size":80,"n_gen":200,"crossover_prob":0.85,"mutation_prob":0.12,"preference":"balanced","n_pareto_solutions_found":80,"n_plans_returned":50,"optimize_seconds":0.291},
 "run_id": "salem_kharif_2024_<UTC timestamp>",
 "saved_files": {"run_id":"…","json_path":"…/results/….json","plans_csv_path":"…","convergence_csv_path":"…","convergence_plot_path":"…"}}
```
(`convergence_history` values above are placeholders showing the shape; it has one entry per generation when `save_results` is true and is `[]` otherwise. `run_id`/`saved_files` are `null` when not saved.) Units: `yield_tonnes`, `cost_rs`, `water_liters`, `env_impact_score` are **totals over `total_land_ha`**, not per hectare. `saved_files` exposes absolute server paths (minor information disclosure – see [SECURITY_REVIEW.md](SECURITY_REVIEW.md)).

## GET /api/results
List of `{run_id, location, season, year, preference, saved_at, n_plans, client_id}` newest-first by filename. `client_id` is **always null** in this response (redacted 2026-09-29).

## GET /api/results/{run_id}
The stored record validated through `FarmPlanResponse` (so extra stored keys such as `saved_at`, `client_id` are dropped). `run_id` must match `^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$`; anything else, a missing file, or a corrupt file → 404.

## GET /api/weather/{district}
Captured live on 2026-09-29 (values change daily):
```json
{"location":"Salem","temp":33,"condition":"cloud","conditionText":"Cloudy","rainfall_mm":7.1,"humidity":54,
 "source":"Live (Open-Meteo)","forecast":[{"day":"Wed","icon":"rainy","temp":"32° / 24°"}, "... 5 entries"]}
```
`condition`/`icon` are Material Symbols icon names mapped from WMO weather codes. On any Open-Meteo failure the fallback uses rainfall.csv averages for the current month (current) and the next 5 **months** (labelled "Mon…Fri" – see UI_UX_REVIEW), with `source = "Historical CSV average (live weather unavailable)"`. Not cached: every call hits Open-Meteo.

## GET /api/dashboard/{district}?client_id=
```json
{"location":"Salem","data_year":2024,"data_year_estimated":true,
 "estimated_yield":19.1,"yield_trend":"+3.0%","active_plans":0,
 "soil_health_pct":68,"water_utilization_pct":74.3,"soil_status":"Moderate",
 "recommended_actions":[{"id":"monitor","title":"No urgent action needed","description":"Soil N/P/K status and water storage are all within normal range.","priority":"low","window":"Routine monitoring"}],
 "crop_allocations":[{"crop":"Paddy","pct":35.6,"ha":3.6},{"crop":"Tapioca","pct":35.3,"ha":3.5},{"crop":"Maize","pct":29.1,"ha":2.9}]}
```
Field derivations: [SCORING_AND_RANKING.md](SCORING_AND_RANKING.md) §4. `client_id` ≤128 chars.

## GET /api/history/{district}?client_id=
```json
{"history":[{"id":"salem_kharif_2023_20260907T181135Z","season":"Kharif 2023","date":"2026-09-07","location":"Salem",
             "target_yield":"11.28 t/ha","est_cost":"₹37,421/ha","status":"Completed","num_plans":50,
             "preference":"balanced","fuzzy_weights":{"yield_confidence":0.742,"irrigation_risk":0.12,"...":"labels"},"is_estimated":false}]}
```
Only runs whose stored `client_id` equals the query parameter; none without it. Ordered newest save first. Details: [HISTORY_PIPELINE.md](HISTORY_PIPELINE.md).

## GET /api/soil-profile/{district}
```json
{"location":"Salem","soil_pH":6.8,"organic_carbon_pct":0.58,"N_status":"Medium","P_status":"Medium","K_status":"Medium",
 "fertility_index":0.678,"irrigated_ha":93840.0,"total_agricultural_ha":155480.0}
```
Row = latest year, current season. `fertility_index` here is 0–1 (elsewhere 0–100).

## GET /api/plans/{district}?total_land_ha=5&budget_rs=
`total_land_ha` > 0 and ≤ 100 000 (default 5); `budget_rs` > 0.
```json
{"location":"Salem","total_land_ha":5.0,"num_plans":100,
 "fuzzy_weights":{"yield_confidence":0.636,"irrigation_risk":0.465},
 "plans":[{"id":0,"cost":38858,"yield_val":12.11,"water_val":4.11,"env_impact":38.99,"is_recommended":true,
           "crops":{"Tapioca":0.834,"Maize":0.0917,"Groundnut":0.0741},"rank":1}],
 "best_plan":{"id":0,"cost":38858,"yield_val":12.11},
 "is_fallback":false,
 "hypervolume_history":[{"generation":1,"hypervolume":0.2603},"…",{"generation":200,"hypervolume":0.8114}]}
```
Per-hectare units: `cost` ₹/ha, `yield_val` t/ha, `water_val` **million litres/ha**, `env_impact` score/ha. `crops` omits shares ≤ 0.5 %. Season = current calendar season; year = latest. `is_fallback` is always false (kept for compatibility).

## GET /api/comparison/{district}?total_land_ha=5&budget_rs=
```json
{"location":"Salem","total_land_ha":5.0,"plans":{
  "A":{"name":"Plan A -- Balanced","crops":"Tapioca, Maize, Groundnut","yield_val":12.11,"cost":38858,"env_impact":38.99,
       "water":"Moderate","recommended":true,
       "allocations":[{"crop":"Tapioca","pct":"83%","ha":"4.2 Ha","plots":"Plots 1, 2, 4"}],
       "radar_scores":{"yield":83,"cost_eff":12,"water":17,"land":100,"risk":53,"market":23}},
  "B":{"name":"Plan B -- Max Yield","...":"..."},
  "C":{"name":"Plan C -- Lowest Cost","...":"..."}}}
```
`allocations[].plots` is a **deprecated placeholder** with no data behind it (no plot geometry exists); the current UI ignores it. `water` is relative among A/B/C: Efficient (lowest), High usage (highest), Moderate.

## GET /api/compare-fuzzy/{district}?season=&year=&total_land_ha=5&budget_rs=
```json
{"location":"Salem","season":"Kharif","year":2024,"total_land_ha":5.0,
 "fuzzy_assessment":{"yield_confidence":0.636,"irrigation_risk":0.465,"rainfall_label":"deficit","water_label":"medium","soil_label":"medium"},
 "fuzzy":{"n_plans":100,"best_yield_tonnes_per_ha":13.963,"min_cost_rs_per_ha":30209.3,"min_water_liters_per_ha":1648307.1,"min_env_impact_per_ha":16.633},
 "non_fuzzy":{"n_plans":100,"best_yield_tonnes_per_ha":26.955,"min_cost_rs_per_ha":30209.3,"min_water_liters_per_ha":1648307.1,"min_env_impact_per_ha":16.633}}
```
Cost/water/impact minima are identical by construction (fuzzy only scales yield) – see [ALGORITHMS.md](ALGORITHMS.md) §4.6.

## CORS
Allowed origins: `http://localhost:5173`, `http://localhost:5174`, `http://localhost:3000` plus comma-separated `CORS_ALLOW_ORIGINS` (production: `https://agrooptimize.vercel.app`). All methods and headers; `allow_credentials=True` (not needed – no cookies are used).

## GET /api/results/{run_id}/explanation  and  GET /api/comparison/{district}/explanation

Structured, data-derived explanation of one recommended plan (`ExplanationOut`, ≈19 KB). Query: `rank` (saved runs, 1–500, default 1) or `plan` = A | B | C plus `total_land_ha`, `budget_rs` (comparison). Top-level keys: `subject, summary, reasons, objectives, trade_offs, constraints, benefits, risks, historical_context, confidence, insights, alternatives, economics, crop_breakdown, consistency_checks, timeline, fuzzy_reasoning`. Every list item has `id, title, detail, source, evidence` (+ `status` for constraints, `severity` for risks). Abbreviated example (Salem Plan A):

```json
{"summary": {"location": "Salem", "season": "Rabi", "year": 2024, "data_year_estimated": true, "preference": "balanced",
             "rank": 1, "plans_compared": 100, "closeness": 0.6152, "recommendation": "Recommended", "confidence_pct": 74.9,
             "crop_mix": [{"crop": "Sugarcane", "share_pct": 53.03, "area_ha": 2.652}, {"crop": "Sunflower", "share_pct": 46.96, "area_ha": 2.348}]},
 "risks": [{"id": "rainfall-deficit", "title": "Rainfall below normal", "severity": "high", "source": "dataset + fuzzy",
            "detail": "Season rainfall is -36.8% vs normal (fuzzy set: deficit); effective rainfall of 208 mm covers 18% of this plan's land-weighted crop water need (1153 mm).",
            "evidence": {"deviation_pct": -36.75, "rainfall_coverage_pct": 18.0}}],
 "confidence": {"overall_pct": 74.9, "method": "Unweighted mean of the available components ...",
                "components": [{"id": "data_quality", "score": 50.0, "detail": "... 2024 values are estimates ... (×0.5)."}]}}
```
Errors: 404 unknown run/district, 400 rank beyond the run's plans, 422 invalid parameters. Full description: [EXPLAINABILITY.md](EXPLAINABILITY.md).

## GET /api/district-intelligence/{district}

One aggregated district profile (`DistrictIntelligenceOut`, ≈55 KB): `district, overview, coverage, climate, soil, water, crops, suitability, market, insights[], summary`. Built from observed rows only; fields the dataset lacks are `null` with a note; sections without data return `{"available": false, "note": "Data not available"}`. Case-insensitive district; 404 for unknown districts. Cached per district. Full field description and an example: [DISTRICT_INTELLIGENCE.md](DISTRICT_INTELLIGENCE.md).

## Scenario Simulation

`POST /api/simulations/run` takes `{base, scenario, client_id}` (`SimulationRequest`) and returns `SimulationOut`: `token, inputs, conditions, baseline, scenario, comparison, impact, crop_effects, fuzzy_changes, optimization, constraints, historical, decision_impact[], trade_offs, summary, meta`. Invalid controls, an unknown district or an infeasible baseline → 422. `POST /api/simulations {token, name, client_id}` saves a result computed in this process (201; 404 if the token expired or belongs to another browser). `GET /api/simulations`, `GET /api/simulations/{id}` and `DELETE /api/simulations/{id}` require `client_id` and only see that browser's simulations. Controls, validation and an example: [SCENARIO_SIMULATION.md](SCENARIO_SIMULATION.md).