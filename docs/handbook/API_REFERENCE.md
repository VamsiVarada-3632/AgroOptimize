# API Reference

Base URL: local `http://localhost:8000`; production `https://agrooptimize-backend.fly.dev` (from `stitch_agrooptimize_app/.env.production`). Interactive schema: `GET /docs` (Swagger) and `/openapi.json`. No authentication on any endpoint. All bodies are JSON. Latencies are measured in-process (TestClient, Apple Silicon laptop); network adds to them. Rows marked † were re-measured on the official data on 2026-11-13 ([OFFICIAL_DATA_PERFORMANCE.md](OFFICIAL_DATA_PERFORMANCE.md)); the others are from 2026-09-29. The first data request in a new process also pays a one-off ≈0.75 s to load the official datasets.

All data comes from the official database (`data/official/official_v1.db`, built from `data/official/raw/`); see [DATASETS.md](DATASETS.md). Features whose official dataset is missing return **501** instead of an estimate; `GET /api/datasets` lists them.

| Method | Path | Purpose | Used by frontend | Cold / warm latency |
|---|---|---|---|---|
| GET | `/health` | Liveness | App.jsx startup | 0.6 ms † |
| GET | `/api/datasets` | Provenance of every loaded official dataset + disabled features | – | – |
| GET | `/api/catalog` | Districts, seasons, years, crops, taluk notes, data sources | Auth, ProfileSetup, Settings, RunOptimization | 1.3 ms † |
| GET | `/api/region-profile` | Stages 1–2 only (data + fuzzy) | – | 2.4 ms † warm |
| POST | `/api/farm-plans` | Full pipeline, optionally saved | RunOptimization | 280 ms † (pop 80 × 200 gen) |
| GET | `/api/results` | List saved runs | – | O(#runs), cached by mtime |
| GET | `/api/results/{run_id}` | One saved run | Reports | ~1 ms |
| GET | `/api/topsis/profiles` | Ranking profiles, weights, criteria, custom-weight rules | – | ~1 ms |
| GET / POST | `/api/results/{run_id}/topsis` | Re-rank a saved run under a ranking profile or custom weights | Run Optimization | a few ms |
| GET | `/api/weather/{district}` | **Disabled (501)**: needs an official IMD weather feed | Dashboard (×5 calls) | – |
| GET | `/api/dashboard/{district}` | KPI cards, actions, crop split | Dashboard | 2.7 ms † |
| GET | `/api/history/{district}` | This browser's saved runs | History, Reports | ~1 ms |
| GET | `/api/soil-profile/{district}` | Soil snapshot | Analytics | 0.9 ms † |
| GET | `/api/soil-master` | Districts with / without a Soil Health Card record | – | – |
| GET | `/api/soil-master/{district}` | Soil Health Card class counts and shares for one district | – | – |
| GET | `/api/plans/{district}` | ≤100 Pareto plans + HV history | Analytics | 966 ms cold / 3 ms cached |
| GET | `/api/comparison/{district}` | Plans A/B/C + radar | Comparison | 369 ms cold / 3 ms cached |
| GET | `/api/compare-fuzzy/{district}` | Fuzzy vs non-fuzzy study | Analytics | 746 ms (2 runs, not cached) |
| GET | `/api/results/{run_id}/explanation?rank=` | Explanation of one plan in a saved run | Run Optimization, History, Reports | tens of ms |
| GET | `/api/comparison/{district}/explanation?plan=` | Explanation of Plan A/B/C | Comparison | ~1 s cold, fast when the front is cached |
| GET | `/api/district-intelligence/{district}` | Aggregated district profile | District Intelligence | 1.4 ms † cached |
| GET | `/api/fuzzy/explain?rainfall_dev=&water_storage=&soil_fert=&model=` | Rule-level explanation of one fuzzy inference | – | ≈5 ms |
| GET | `/api/fuzzy/audit?model=` | Rule-base and membership-function audit + firing on the dataset | – | ≈0.7 s cold, cached per model |
| GET | `/api/fuzzy/models` | Fuzzy models (official default, published, each improvement, improved), their switches, rules and membership functions | – | < 5 ms |
| POST | `/api/simulations/run` | Run a scenario simulation (baseline + scenario, 5 seeds each) | Scenario Simulation | ~4 s, never cached |
| POST | `/api/simulations` | Save a simulation result by token | Scenario Simulation | fast |
| GET | `/api/simulations?client_id=` | This browser's saved simulations | Scenario Simulation | fast |
| GET | `/api/simulations/{id}?client_id=` | One saved simulation | Scenario Simulation | fast |
| DELETE | `/api/simulations/{id}?client_id=` | Delete a saved simulation | Scenario Simulation | fast |

`{district}` is one of the 38 official districts (`GET /api/catalog`), case-insensitive (`coimbatore`, `Salem`, ` ERODE `). Unknown → 404. Pollachi is a taluk of Coimbatore, not a district: the core endpoints return 400 with a note to use Coimbatore. Seasons are `Kharif` and `Rabi` (the official reports have no Summer season).

## Error model

| Status | When | Body |
|---|---|---|
| 400 | `ValueError` in the pipeline for core endpoints (unknown location/season, a taluk such as Pollachi, <2 crops with complete official data, e.g. Chennai and The Nilgiris) | `{"detail": "Unknown season 'Summer'. Choose one of ['Kharif', 'Rabi']."}` |
| 404 | Unknown district on dashboard endpoints; unknown/invalid `run_id`; `ValueError` in comparison/compare-fuzzy | `{"detail": "..."}` |
| 422 | Pydantic/Query validation | `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}` |
| 501 | Feature disabled because its official dataset is missing (`FeatureUnavailable`) | `{"detail": "Live weather widget is unavailable: official dataset missing - ...", "feature": "Live weather widget", "missing_dataset": "...", "available": false}` |
| 503 | `/api/plans` optimisation failure | `{"detail": {"error": "Optimization failed", "message": "...", "location": "..."}}` |
| 500 | Unhandled exception | FastAPI default |

The frontend's `describeApiError` (src/services/api.js) turns any of these into user text.

---

## GET /health
`200 {"status": "ok"}`

## GET /api/catalog
```json
{"locations": ["Ariyalur", "Chengalpattu", "Chennai", "Coimbatore", "...", "Virudhunagar"],
 "seasons": ["Kharif", "Rabi"],
 "years": [2024],
 "crops_by_season": {"Kharif": ["bajra", "black gram", "gingelly", "green gram", "groundnut", "jowar", "maize", "ragi", "red gram", "sunflower"],
                     "Rabi": ["bajra", "black gram", "gingelly", "green gram", "groundnut", "jowar", "maize", "ragi", "red gram", "sunflower"]},
 "taluk_notes": {"pollachi": "Pollachi is a taluk of Coimbatore district. The official datasets are published per district, so taluk data is not available; use 'Coimbatore'."},
 "data_sources": [{"dataset": "crops_by_district", "file": "crops_by_district.csv", "report_year": "2024-25"}, "..."]}
```
38 districts. `crops_by_season` lists only crops with a complete official record (yield, TNAU dose, MSP and CACP cost); `2024` is the 2024-25 report year.

## GET /api/region-profile
Query: `location` (required, case-insensitive), `season` (required, Kharif/Rabi), `year` (optional, default latest). Abbreviated real response (Salem Rabi):
```json
{"location":"Salem","year":2024,"season":"Rabi",
 "soil":{"soil_type":null,"avg_ph":null,"organic_carbon_percent":null,"n_status":"Low","p_status":"Medium","k_status":"High",
         "irrigation_percent":59.44,"fertility_index":30.57,"samples_tested":14986,"shares":{"n_shares":{"low":0.996,"medium":0.004,"high":0.0003},"...":"p, k, oc, ph"}},
 "rainfall":{"avg_monthly_rainfall_mm":108.96,"avg_deviation_percent":59.48,"avg_humidity_percent":null,"avg_max_temp_c":null,"avg_min_temp_c":null,
             "months_used":["October","November","December","January","February"],"effective_rainfall_mm":null,"season_actual_mm":544.8,"season_normal_mm":341.6},
 "water":{"avg_storage_percent":87.44,"groundwater_status":null,"avg_deficit_surplus_mcm":null,"groundwater_level_m_bgl":4.34,"reservoirs":["Mettur"]},
 "candidate_crops":["maize","groundnut","jowar","ragi","red gram","green gram"],
 "fuzzy_assessment":{"yield_confidence":0.532,"irrigation_risk":0.12,"rainfall_label":"surplus","water_label":"high","soil_label":"medium","applied":true,"reason":null},
 "fuzzy_available":true,"fuzzy_unavailable_reason":null,
 "excluded_crops":[{"crop":"cotton","reasons":["price/yield unit basis differs and no official conversion factor is loaded: ..."]}],
 "notes":["Reservoir storage covers 2 of the season's 5 months (the official daily reservoir record starts 2025-01-01).", "..."],
 "candidate_sources":{"maize":{"dose_rule":"TNAU 'varieties' (irrigated share 85%)","agronomy":"https://agritech.tnau.ac.in/pdf/AGRICULTURE.pdf p.105 (pdf p.117)","price":"...","crop_statistics":"TN Season & Crop Report 2024-25"}}}
```
Fields the official data does not publish are `null` (soil type, pH and organic carbon values, humidity, temperature, effective rainfall, groundwater status). Where no official reservoir reading exists for the district and season (e.g. Salem Kharif) the fuzzy stage is not applied: `fuzzy_assessment` has `applied: false`, `yield_confidence` 1.0 (yield unadjusted), labels `n/a`, and `fuzzy_unavailable_reason` says why. Note: here `candidate_crops` is a list of names; in `POST /api/farm-plans` it is a list of objects.

## POST /api/farm-plans
Request (`FarmPlanRequest`):

| Field | Type | Constraint | Default | Meaning |
|---|---|---|---|---|
| location | str | one of catalog locations (case-insensitive) | required | |
| season | str | Kharif/Rabi (case-insensitive) | required | |
| year | int | must exist for location | latest (2024) | |
| total_land_ha | float | > 0 | required | farm size |
| budget_rs | float | > 0 | none | hard constraint cost ≤ budget |
| preference | enum | balanced, max_yield, min_cost, min_water, min_env_impact | balanced | TOPSIS weights (classic preferences) |
| profile | enum | balanced, profit, water, sustainability, low_cost, custom | none | ranking profile ([TOPSIS_PROFILE_GUIDE.md](TOPSIS_PROFILE_GUIDE.md)); cannot be combined with a preference other than balanced |
| custom_weights | object | criterion → 0–1, summing to 1; criteria: yield, market_price, income, cost, water, env, budget, soil, land, rainfall | none | required for, and only allowed with, profile custom |
| compare_profiles | bool | | false | also return `meta.profile_comparison` |
| max_candidate_crops | int | 2–12 | 6 | top-N among crops with a complete official record |
| max_cost_rs, max_irrigated_ha, min_yield_tonnes, max_env_impact | float | ≥ 0 | none | post-hoc filters |
| fuzzy_model | str | a name from `GET /api/fuzzy/models` | server default (`official`) | |
| pop_size | int | 8–300 | 80 | |
| n_gen | int | 5–500 | 200 | |
| save_results | bool | | true | persist to results/ and track convergence |
| client_id | str | ≤128 chars | none | scopes History |

Response (`FarmPlanResponse`). Abbreviated real response (Salem Rabi, 5 ha):
```json
{"region_profile": {"...": "as region-profile, but candidate_crops are objects:",
                    "candidate_crops":[{"name":"maize","crop_type":"Cereals","yield_kg_ha":7184.0,"water_req_mm":null,"rainfall_dependency":"15% rainfed",
                                        "irrigation_type":"Irrigated","sowing_month":null,"harvest_month":null,"crop_duration_days":null,
                                        "msp_rs_qtl":2225.0,"cost_rs_qtl":1447.0,"fert_n_kg_ha":135.0,"fert_p_kg_ha":62.5,"fert_k_kg_ha":50.0,
                                        "rainfed_share":0.152,"area_ha":51516.0,"dose_rule":"TNAU 'varieties' (irrigated share 85%)",
                                        "sources":{"agronomy":"https://agritech.tnau.ac.in/pdf/AGRICULTURE.pdf p.105 (pdf p.117)","price":"...","crop_statistics":"TN Season & Crop Report 2024-25"}}]},
 "fuzzy_assessment": {"yield_confidence":0.532,"irrigation_risk":0.12,"rainfall_label":"surplus","water_label":"high","soil_label":"medium","applied":true,"reason":null},
 "plans": [{"rank":1,"crop_names":["maize","groundnut","jowar","ragi","red gram","green gram"],
            "allocation_percent":[0.01,0.01,0.01,82.46,0.01,17.5],"area_ha":["..."],
            "irrigation_multiplier":["..."],"fertilizer_multiplier":["..."],
            "yield_tonnes":15.776,"cost_rs":880840.24,"irrigated_ha":1.244,"env_impact_score":377.253,
            "feasible":true,"composite_score":0.6398,
            "normalized_scores":{"...":"..."},"confidence_label":"...","trade_off_summary":"..."}],
 "convergence_history": [{"generation":1,"population_size":80,"best_yield_tonnes":0.0,"mean_yield_tonnes":0.0,"best_cost_rs":0.0,"mean_cost_rs":0.0,"best_irrigated_ha":0.0,"mean_irrigated_ha":0.0,"best_env_impact":0.0,"mean_env_impact":0.0,"hypervolume":0.0}],
 "meta": {"algorithm":"NSGA-II","pop_size":80,"n_gen":200,"optimize_seconds":0.278,"fuzzy_model":"official","...":"as below"},
 "run_id": null,
 "saved_files": null}
```
Crops are named as in the official reports (lower case). `water_req_mm`, sowing/harvest months and duration are `null`: no official per-crop totals are loaded ([MIGRATION_REPORT.md](../data_architecture/MIGRATION_REPORT.md) §3). The water objective is the **irrigated area** (`irrigated_ha`), which replaced `water_liters`.

`meta.topsis` (optional; absent in runs saved before it existed) records the weights that ranked the run: `profile` (null for a classic preference other than balanced, or for simulation priorities), `label`, `preference`, `weights` (all ten criteria), `criteria` (those with a positive weight, with label and direction), `method`, `budget_active`. With `compare_profiles: true`, `meta.profile_comparison` holds the front ranked under every standard profile ([TOPSIS_COMPARISON.md](TOPSIS_COMPARISON.md)). Saved runs also store the ranked front (`ranked_front`, not returned by the API) so they can be re-ranked exactly.

`meta.quality_metrics` (optional; absent in runs saved before it existed) describes the quality of the run's Pareto front: hypervolume and its ratio to a reference front, generational distance (GD), inverted generational distance (IGD), IGD+, generalised spread and spacing, on objectives normalised to the reference front's ideal and nadir, where the reference is the front plus each plan's copy with irrigation and fertiliser multipliers at 0.7 (never worse in this model). Lower is better for GD, IGD, IGD+, spread and spacing. Values that cannot be computed (no feasible plan, fewer than two plans) are `null`. See [NSGAII_IMPROVEMENTS.md](NSGAII_IMPROVEMENTS.md) §2.3.

(`convergence_history` values above are placeholders showing the shape; it has one entry per generation when `save_results` is true and is `[]` otherwise. `run_id`/`saved_files` are `null` when not saved.) Units: `yield_tonnes`, `cost_rs`, `irrigated_ha`, `env_impact_score` are **totals over `total_land_ha`**, not per hectare. `saved_files` exposes absolute server paths (minor information disclosure – see [SECURITY_REVIEW.md](SECURITY_REVIEW.md)).

## GET /api/results
List of `{run_id, location, season, year, preference, ranking, saved_at, n_plans, client_id}` (`ranking`: label of the weights that ranked the run, null for runs saved before ranking profiles) newest-first by filename. `client_id` is **always null** in this response (redacted 2026-09-29).

## GET /api/results/{run_id}
The stored record validated through `FarmPlanResponse` (so extra stored keys such as `saved_at`, `client_id` are dropped). `run_id` must match `^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$`; anything else, a missing file, or a corrupt file → 404.

## GET /api/weather/{district}
**Disabled.** Returns 501 for every district until an official IMD district weather feed is loaded (the Open-Meteo call and the CSV fallback were removed):
```json
{"detail":"Live weather widget is unavailable: official dataset missing - IMD district weather (temperature, humidity, forecast) - not yet scraped. Official monthly rainfall is shown elsewhere.",
 "feature":"Live weather widget","missing_dataset":"IMD district weather (temperature, humidity, forecast) - not yet scraped","available":false}
```

## GET /api/dashboard/{district}?client_id=
Abbreviated real response (Salem):
```json
{"location":"Salem","data_year":2024,"data_year_estimated":false,
 "estimated_yield":3.3,"yield_trend":null,"active_plans":0,
 "soil_health_pct":31,"water_utilization_pct":59.4,"soil_status":"Needs Attention",
 "recommended_actions":[{"id":"nitrogen","title":"Apply nitrogen fertilizer","description":"Soil N status from the land survey is Low.","priority":"high","window":"Next 48 hours"}],
 "crop_allocations":[{"crop":"maize","pct":57.8,"ha":5.8},{"crop":"groundnut","pct":27.7,"ha":2.8},{"crop":"jowar","pct":14.5,"ha":1.4}],
 "data_sources":[{"dataset":"crops_by_district","file":"crops_by_district.csv","report_year":"2024-25"},"..."]}
```
`yield_trend` is `null`: district-level statistics are loaded for one report year only. Field derivations: [SCORING_AND_RANKING.md](SCORING_AND_RANKING.md) §4. `client_id` ≤128 chars.

## GET /api/history/{district}?client_id=
```json
{"history":[{"id":"salem_rabi_2024_20261112T184810Z","season":"Rabi 2024","date":"2026-11-12","location":"Salem",
             "target_yield":"3.15 t/ha","est_cost":"₹176,098/ha","status":"Completed","num_plans":50,
             "preference":"balanced","ranking":"Balanced","fuzzy_weights":{"yield_confidence":0.532,"irrigation_risk":0.12,"...":"labels, applied, reason"},"is_estimated":false}]}
```
Only runs whose stored `client_id` equals the query parameter; none without it. Ordered newest save first. Details: [HISTORY_PIPELINE.md](HISTORY_PIPELINE.md).

## GET /api/soil-profile/{district}
Abbreviated real response (Salem):
```json
{"location":"Salem","soil_pH":null,"organic_carbon_pct":null,"N_status":"Low","P_status":"Medium","K_status":"High",
 "fertility_index":0.306,"irrigated_ha":98243.0,"total_agricultural_ha":202402.0,"net_area_sown_ha":208492.0,
 "area_basis":"Irrigated and total area are both summed over the district's crops in the Season & Crop Report (gross cropped area).",
 "class_shares":{"n_shares":{"low":0.996,"medium":0.004,"high":0.0003},"...":"p, k, oc, ph"},"samples_tested":14986,
 "source":"Soil Health Card portal (soilhealth.dac.gov.in); TN Season & Crop Report 2024-25 (land use, irrigation)","available":true}
```
The N/P/K status is the dominant Soil Health Card class; numeric pH and organic carbon are not published by the source (`null`). `fertility_index` here is 0–1 (elsewhere 0–100).

## GET /api/soil-master  and  GET /api/soil-master/{district}
`GET /api/soil-master` → `{"cycle":"2024-25","available":[37 districts],"unavailable":[{"district":"Chennai","message":"Official data unavailable"}]}`.
`GET /api/soil-master/{district}` → the Soil Health Card record: `district, available, cycle, samples_tested, soil_type` (always "Official data unavailable"), and per parameter (`ph, organic_carbon, nitrogen, phosphorus, potassium, electrical_conductivity`, micronutrients) `{label, unit, samples, counts, share_pct, dominant_class}`. A district without a record returns `{"available": false, "message": "Official data unavailable", "reason": "..."}`; an unknown district → 404. See [SOIL_MASTER.md](../data_architecture/SOIL_MASTER.md).

## GET /api/datasets
`{"datasets": [{id, name, filename, sha256, report_year, rows_clean, imported_at}, ...10], "disabled_features": [...]}` – the provenance of every table in the official database and the features switched off because their dataset is missing.

## GET /api/plans/{district}?total_land_ha=5&budget_rs=
`total_land_ha` > 0 and ≤ 100 000 (default 5); `budget_rs` > 0. Abbreviated real response (Salem):
```json
{"location":"Salem","total_land_ha":5.0,"num_plans":100,
 "fuzzy_weights":{"yield_confidence":0.532,"irrigation_risk":0.12,"applied":true},
 "plans":[{"id":0,"cost":70678,"yield_val":2.42,"water_val":0.383,"irrigated_ha_per_ha":0.383,"env_impact":121.36,"is_recommended":true,
           "crops":{"maize":0.6226,"green gram":0.3735},"rank":1}],
 "best_plan":{"...":"..."},
 "is_fallback":false,
 "hypervolume_history":[{"generation":1,"hypervolume":"..."},"…"]}
```
Per-hectare units: `cost` ₹/ha, `yield_val` t/ha, `water_val` = `irrigated_ha_per_ha` (irrigated hectares per hectare of farm; was million litres/ha before the migration), `env_impact` score/ha. `crops` omits shares ≤ 0.5 %. Season = current calendar season; year = latest. `is_fallback` is always false (kept for compatibility).

## GET /api/comparison/{district}?total_land_ha=5&budget_rs=
Abbreviated real response (Salem):
```json
{"location":"Salem","total_land_ha":5.0,"plans":{
  "A":{"name":"Plan A -- Balanced","crops":"maize, green gram","yield_val":2.42,"cost":70678,"env_impact":121.36,
       "water":"High usage","recommended":true,
       "allocations":[{"crop":"maize","pct":"62%","ha":"3.1 Ha","plots":"Plots 1, 2, 4"}],
       "radar_scores":{"yield":64,"cost_eff":71,"water":0,"land":0,"risk":88,"market":44}},
  "B":{"name":"Plan B -- Max Yield","...":"..."},
  "C":{"name":"Plan C -- Lowest Cost","...":"..."}}}
```
`allocations[].plots` is a **deprecated placeholder** with no data behind it (no plot geometry exists); the current UI ignores it. `water` is relative among A/B/C (irrigated area): Efficient (lowest), High usage (highest), Moderate.

## GET /api/compare-fuzzy/{district}?season=&year=&total_land_ha=5&budget_rs=
Real response (Salem Rabi):
```json
{"location":"Salem","season":"Rabi","year":2024,"total_land_ha":5.0,
 "fuzzy_assessment":{"yield_confidence":0.532,"irrigation_risk":0.12,"rainfall_label":"surplus","water_label":"high","soil_label":"medium","applied":true,"reason":null},
 "fuzzy":{"n_plans":100,"best_yield_tonnes_per_ha":3.798,"min_cost_rs_per_ha":14399.17,"min_irrigated_ha_per_ha":0.0,"min_env_impact_per_ha":35.036},
 "non_fuzzy":{"n_plans":100,"best_yield_tonnes_per_ha":7.36,"min_cost_rs_per_ha":14399.17,"min_irrigated_ha_per_ha":0.0,"min_env_impact_per_ha":35.037}}
```
Cost/irrigated-area/impact minima are identical by construction up to rounding (fuzzy only scales yield) – see [ALGORITHMS.md](ALGORITHMS.md) §4.6. Where the fuzzy stage is not applied (no official reservoir reading) both columns describe the same unadjusted problem.

## CORS
Allowed origins: `http://localhost:5173`, `http://localhost:5174`, `http://localhost:3000` plus comma-separated `CORS_ALLOW_ORIGINS` (production: `https://agrooptimize.vercel.app`). All methods and headers; `allow_credentials=True` (not needed – no cookies are used).

## GET /api/topsis/profiles

`{default_profile, profiles: [{profile, label, summary, weights, tiers?, method}], criteria: [{key, label, direction, unit, source}], custom: {default_weights, sum_to, tolerance, min, max}}`.

## GET /api/results/{run_id}/topsis?profile=&compare=  and  POST /api/results/{run_id}/topsis

Re-ranks a saved run's front with TOPSIS only (no NSGA-II re-run). GET takes a standard `profile` (default balanced) and `compare` (default true). POST takes `{"profile": "custom", "custom_weights": {...}, "compare": true}` (or any standard profile). Response (`TopsisRankingOut`):

| Field | Meaning |
|---|---|
| `topsis` | as `meta.topsis` |
| `plans` | ranked plans (`RankedPlanOut`, top 50) |
| `ranked_over` | `ranked_front` (the stored front) or `returned_plans` (older runs: the 50 saved plans) |
| `plans_ranked` | number of plans ranked |
| `explanation` | `ideal_best`, `ideal_worst`, the top 10 plans with weight → contribution → score per criterion, and `pairs` explaining each plan against the next ([TOPSIS_EXPLAINABILITY.md](TOPSIS_EXPLAINABILITY.md)) |
| `comparison` | the front under all five profiles, when `compare` |

Errors: 404 unknown run; 422 invalid profile or weights (e.g. not summing to 1); 400 a run without feasible plans.

## GET /api/results/{run_id}/explanation  and  GET /api/comparison/{district}/explanation

Structured, data-derived explanation of one recommended plan (`ExplanationOut`, ≈19 KB). Query: `rank` (saved runs, 1–500, default 1) or `plan` = A | B | C plus `total_land_ha`, `budget_rs` (comparison). Top-level keys: `subject, summary, reasons, objectives, trade_offs, constraints, benefits, risks, historical_context, confidence, insights, alternatives, economics, crop_breakdown, consistency_checks, timeline, fuzzy_reasoning, crop_evidence` (per crop, ten source-cited criteria; [EXPLAINABILITY.md](EXPLAINABILITY.md)), and optional `topsis` (the plan's weight → contribution → score, `versus_previous`, `versus_next`, `rank_by_profile`). Every list item has `id, title, detail, source, evidence` (+ `status` for constraints, `severity` for risks). Abbreviated real example (Salem Plan A, `GET /api/comparison/Salem/explanation?plan=A`):

```json
{"summary": {"location": "Salem", "season": "Rabi", "year": 2024, "data_year_estimated": false, "preference": "balanced",
             "rank": 1, "plans_compared": 100, "closeness": 0.6668, "recommendation": "Recommended", "confidence_pct": 72.4,
             "crop_mix": [{"crop": "maize", "share_pct": 62.26, "area_ha": 3.113}, {"crop": "green gram", "share_pct": 37.35, "area_ha": 1.868}]},
 "confidence": {"overall_pct": 72.4,
                "components": [{"id": "data_quality", "score": 100.0, "detail": "100% of the season's monthly official rainfall and reservoir records are present for Salem; all values are official 2024-25 records."}, "..."]},
 "crop_evidence": [{"crop": "maize", "criteria": [{"id": "rainfall", "label": "...", "status": "...", "statement": "...", "sources": [{"dataset": "..."}], "evidence": {}}, "... 10 criteria"]}]}
```
Errors: 404 unknown run/district, 400 rank beyond the run's plans, 422 invalid parameters. Full description: [EXPLAINABILITY.md](EXPLAINABILITY.md).

## GET /api/district-intelligence/{district}

One aggregated district profile (`DistrictIntelligenceOut`, ≈55 KB): `district, overview, coverage, climate, soil, water, crops, suitability, market, insights[], summary`. Built from observed rows only; fields the dataset lacks are `null` with a note; sections without data return `{"available": false, "note": "Data not available"}`. Case-insensitive district; 404 for unknown districts. Cached per district. Full field description and an example: [DISTRICT_INTELLIGENCE.md](DISTRICT_INTELLIGENCE.md).

## Scenario Simulation

`POST /api/simulations/run` takes `{base, scenario, client_id}` (`SimulationRequest`) and returns `SimulationOut`: `token, inputs, conditions, baseline, scenario, comparison, impact, crop_effects, fuzzy_changes, optimization, constraints, historical, decision_impact[], trade_offs, summary, meta`. Invalid controls, an unknown district or an infeasible baseline → 422. `POST /api/simulations {token, name, client_id}` saves a result computed in this process (201; 404 if the token expired or belongs to another browser). `GET /api/simulations`, `GET /api/simulations/{id}` and `DELETE /api/simulations/{id}` require `client_id` and only see that browser's simulations. Controls, validation and an example: [SCENARIO_SIMULATION.md](SCENARIO_SIMULATION.md).

## Fuzzy system transparency

`GET /api/fuzzy/explain` returns `fuzzy.engine.explain_inference` for one input triple (clipped like the engine; non-finite → 422): `inputs`, `outputs` (value, term and its membership, term cuts with setting rules, term area shares, `matches_engine`), `rules` (strength, status decisive/masked/not fired, `masked_by`, `tied_with`, limiting condition, `contribution_pct`, `leave_one_out_change`, `importance`), `ranking`, `summary`, `method`. Plan explanations carry the same object as `fuzzy_reasoning.inference`. `GET /api/fuzzy/audit` returns `model`, `dominance`, `coverage`, `output_bounds`, `dataset_firing`. See [FUZZY_EXPLAINABILITY.md](FUZZY_EXPLAINABILITY.md) and [FUZZY_SYSTEM_ANALYSIS.md](FUZZY_SYSTEM_ANALYSIS.md).

**Fuzzy models.** `GET /api/fuzzy/models` returns `{default, models: [{name, description, switches: {strong_partition, imd_rainfall, prune_inert}, rules, membership_functions}]}`. Models: `official` (the default: calibrated on the official data, [FUZZY_SYSTEM_ANALYSIS.md](FUZZY_SYSTEM_ANALYSIS.md)), `original` (published), `strong_partition`, `imd_rainfall`, `pruned_rules` (one improvement each) and `improved` (all three); see [FUZZY_MODEL_IMPROVEMENTS.md](FUZZY_MODEL_IMPROVEMENTS.md). `/api/fuzzy/explain` and `/api/fuzzy/audit` take `model` (unknown name → 400) and report it as `model`. `POST /api/farm-plans` and the simulation `base` take an optional `fuzzy_model` (unknown name → 422); the run records it as `meta.fuzzy_model` (simulations: `meta.fuzzy_model`), and saved-run explanations recompute the fuzzy reasoning with it (runs saved earlier → `original`). Omitting it uses the server default (`AGROOPTIMIZE_FUZZY_MODEL`, `official` unless set).
