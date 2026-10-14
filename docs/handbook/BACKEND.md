# Backend

`agrooptimize-backend/` – Python 3.11 (Docker) / 3.10+ (local), FastAPI, pymoo 0.6, scikit-fuzzy 0.5, pandas 2. ~3,250 lines of application code, 205 tests. Endpoint contracts: [API_REFERENCE.md](API_REFERENCE.md). Algorithms: [ALGORITHMS.md](ALGORITHMS.md).

## 1. Running it

```bash
cd agrooptimize-backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000     # Swagger at /docs
python3 run_demo.py --location Erode --season Rabi --land 3 --preference max_yield --top 3
python3 -m pytest -q                            # 205 tests, ~15 s
```

## 2. Module reference

### `app/config.py`
Constants only (no functions, no env loading). Grouped: paths (`RAW_DATA_DIR`, `RESULTS_DIR`), dataset structure (`LOCATIONS`, `DATASET_KINDS`, `AG_SEASONS`, `SEASON_MONTH_MAP`, `DISTRICT_COORDINATES`), candidate selection, economics, water, environment, rainfall-dependency factors, decision-variable bounds, NSGA-II hyper-parameters, `MAX_RETURNED_PLANS`. Full table with provenance: [CONFIGURATION.md](CONFIGURATION.md).

### `app/schemas.py`
| Model | Used as | Notes |
|---|---|---|
| `FarmPlanRequest` | body of POST /api/farm-plans | validation bounds listed in API_REFERENCE; `client_id ≤ 128`, filters ≥ 0 (added) |
| `SoilOut`, `RainfallOut`, `WaterOut`, `CropCandidateOut`, `RegionProfileOut` | nested in `FarmPlanResponse` | `RegionProfileOut.data_year_estimated` defaults False so older saved runs validate |
| `FuzzyAssessmentOut`, `RankedPlanOut`, `RunMeta`, `ConvergencePointOut`, `SavedFilesOut` | nested | |
| `FarmPlanResponse` | response of POST /api/farm-plans and GET /api/results/{id} | acts as a filter: stored keys `saved_at`, `client_id` are dropped |
| `SavedRunSummaryOut` | GET /api/results | |
| `CatalogOut` | GET /api/catalog | |

The seven dashboard endpoints and `/api/region-profile` return plain dicts with **no response_model** (TD-7).

### `app/main.py`
Creates `FastAPI(title="AgroOptimize API", version="0.1.0")`, adds CORS (localhost dev origins + `CORS_ALLOW_ORIGINS`), defines shared `Query` validators (`_LAND_HA_QUERY` 0 < x ≤ 100 000, `_BUDGET_QUERY` > 0, `_CLIENT_ID_QUERY` ≤ 128 chars) and 13 handlers. Each handler is a thin wrapper: call a service, map `ValueError` → 400/404 and `PlanGenerationError` → 503. `list_results` redacts `client_id`.

### `app/data/loader.py`
| Function | Behaviour |
|---|---|
| `_read_kind(kind)` | For each location reads `data/raw/<loc>_<kind>.csv`; raises `FileNotFoundError` naming the missing file; `pd.concat` |
| `load_all()` | `lru_cache(maxsize=1)`; returns `{"crop","land","rainfall","water"}` DataFrames |
| `clear_cache()` | clears the above (tests) |
| `available_locations/years/seasons()` | used only by tests |

### `app/data/preprocessing.py`
| Symbol | Behaviour |
|---|---|
| dataclasses `CropCandidate`, `SoilProfile`, `RainfallProfile`, `WaterProfile`, `RegionSeasonProfile` | typed pipeline input; `RegionSeasonProfile.data_year_estimated` added |
| `compute_soil_fertility_index(...)` | 0–100 index (ALGORITHMS §1) |
| `canonical_choice(value, options, kind)` | case/whitespace-insensitive match → canonical spelling; `ValueError` otherwise (added) |
| `ESTIMATED_SOURCE_PREFIX`, `is_estimated_year(loc, year)` | True if all crop rows for (loc, year) have `data_source` starting "Estimated" (added) |
| `_resolve_year` | None → latest year for the location; unknown year → `ValueError` listing available years |
| `list_catalog()` | locations, seasons, sorted years, crops per season (across all locations) |
| `get_region_season_profile(location, season, year, max_candidate_crops)` | the Stage-1 builder: land row (first match), rainfall/water rows for the season's months, top-N crops by revenue; raises `ValueError` for any empty slice or <2 crops |
| `_REFERENCE_RANGES`, `_minmax`, `normalized_snapshot(profile)` | display-only [0,1] values |

### `app/fuzzy/engine.py`
| Symbol | Behaviour |
|---|---|
| `UncertaintyAssessment` | `yield_confidence`, `irrigation_risk` (0–1, 3 dp) + three dominant labels |
| `_build_system()` | `lru_cache(1)`: defines universes, MFs, 26 rules, returns `ControlSystem` + antecedents (first call ≈0.6 s) |
| `evaluate_uncertainty(rain_dev, storage, fertility)` | clips inputs, new `ControlSystemSimulation` per call, centroid outputs ÷ 100; falls back to 0.5/0.5 on `KeyError/ValueError` |
| `_dominant_label` | argmax membership |
| `crop_yield_confidence(base, risk, dependency)` | per-crop penalty (≤ 40 %) |

### `app/optimization/problem.py`
`CropVector.from_candidates(crops, assessment, use_fuzzy)` precomputes per-crop NumPy arrays (confidence = 1.0 when `use_fuzzy=False`). `FarmPlanProblem(profile, assessment, total_land_ha, budget_rs, use_fuzzy)` sets bounds (allocation lower bound 1e−4), 4 objectives, optional 1 inequality constraint; `_evaluate` is fully vectorised; `decode(x)` → dict of lists.

### `app/optimization/operators.py`
`AllocationRepair`, `SinglePointCrossover(prob)`, `GaussianMutation(prob, sigma)` – see ALGORITHMS §4.1. All use `np.random` (global RNG).

### `app/optimization/nsga2_runner.py`
| Symbol | Behaviour |
|---|---|
| `_NSGA2_RUN_LOCK` | process-wide lock serialising runs (added) |
| `FarmPlan` | decoded plan with rounded objective values and `feasible` |
| `run_nsga2(problem, pop_size, n_gen, …, seed=42, track_history)` | builds pymoo `NSGA2` with custom operators, seeds global RNG and runs `minimize` under the lock |
| `run_nsga2_with_fuzzy_toggle(profile, assessment, land, budget, use_fuzzy, **kw)` | builds the problem with `use_fuzzy`, returns `(problem, result)` |
| `extract_convergence_history(result)` | per-generation best/mean objectives + normalised hypervolume; `[]` without history |
| `extract_pareto_plans(result, problem)` | decode `result.X/F/G` into `FarmPlan`s |

### `app/decision/ranking.py`
`filter_plans`, `rank_plans` (TOPSIS), `RankedPlan`, `to_dict_list`, helpers `_minmax_norm`, `_plain_minmax`, `_bucket`, `_round_percentages_to_100`, `_PREFERENCE_WEIGHTS`.

### `app/services/plan_service.py`
`generate_farm_plans(request, results_dir=None)` – Stages 1–5; see [OPTIMIZATION_PIPELINE.md](OPTIMIZATION_PIPELINE.md). Returns a plain dict shaped like `FarmPlanResponse`.

### `app/services/results_store.py`
| Symbol | Behaviour |
|---|---|
| `is_valid_run_id` | regex `^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$` (added) |
| `make_run_id(loc, season, year)` | `<loc>_<season>_<year>_<YYYYMMDDTHHMMSSZ>` (slugified, UTC) |
| `_reserve_run_id(out_dir, base)` | exclusive-create claim; `-2`, `-3`… on same-second collision (added) |
| `save_run_results(response, history, out_dir, client_id)` | writes JSON (atomic), plans CSV (list/dict cells JSON-encoded), and if history: convergence CSV + PNG |
| `_atomic_write_text` | temp file + `os.replace` (added) |
| `_plot_convergence` | matplotlib Agg; two panels (HV; best yield & best cost on twin axes); 130 dpi |
| `_summarise`, `_SUMMARY_CACHE` | per-file summary cached by (mtime_ns, size) (added) |
| `list_saved_runs(out_dir)` | summaries newest-first by filename; corrupt/incomplete files skipped |
| `load_run(run_id, out_dir)` | validated id → dict or None (corrupt → None) |

### `app/services/dashboard_service.py`
| Symbol | Behaviour |
|---|---|
| `resolve_location` | case-insensitive district → canonical; `ValueError` (→404) |
| `_current_season(today)` | month → first matching season in `SEASON_MONTH_MAP` |
| `_latest_year_for(df, loc)` | max year |
| `_WMO_CODE_TO_CONDITION`, `_CONDITION_TEXT`, `_condition_for_rainfall` | weather icon mapping; CSV fallback thresholds >100 mm rainy, >50 partly cloudy |
| `_get_weather_live(loc)` | Open-Meteo `/v1/forecast` (current + 6 daily, Asia/Kolkata, timeout 5 s) |
| `_get_weather_from_csv(loc)` | current-month and next-5-month averages |
| `get_weather(loc)` | live, else CSV; failure logged with `logging` |
| `_ACTION_LIBRARY`, `_soil_status_label`, `_current_land_row`, `_REFERENCE_FARM_HA` | dashboard helpers |
| `PlanGenerationError` | raised by `get_plans` → 503 |
| `get_dashboard(loc, client_id)` | KPI payload (SCORING_AND_RANKING §4) incl. `data_year(_estimated)` |
| `get_soil_profile(loc)` | latest-year current-season soil |
| `get_history(loc, client_id)` | HISTORY_PIPELINE |
| `_run_dashboard_pareto_front(...)` → `_cached_pareto_front(...)` (`lru_cache(32)`), `clear_pareto_cache()` | pop-100 run, memoised; returns profile, assessment, feasible plans, confidence map, convergence history |
| `_summarize_pareto_front`, `get_fuzzy_comparison` | fuzzy vs non-fuzzy study |
| `get_plans` | ≤100 ranked plans per hectare + HV history |
| `_radar_scores`, `_PLOT_LABELS` (deprecated), `get_comparison` | Plans A/B/C |

### `app/services/explanation_service.py`
| Symbol | Behaviour |
|---|---|
| `ExplanationContext` | everything needed to explain one plan: region profile, fuzzy, ranked set, index, preference, land, budget (+ whether recorded), convergence history, meta, subject |
| `context_from_saved_run(record, rank)` | from a stored run (budget "not recorded" for older runs) |
| `context_from_comparison(location, plan, land, budget)` | from the memoised dashboard front ranked under A/B/C's preference |
| `explain(ctx)` | builds all sections (see EXPLAINABILITY.md); helpers `_crop_breakdown`, `_objective_analysis`, `_rank_under_all_preferences`, `_trade_offs`, `_constraints`, `_historical`, `_confidence`, `_risks` |
| `explain_saved_run`, `explain_comparison_plan` | convenience wrappers used by `main.py` |

Supporting additions: `ranking.topsis_scores`, `ranking.preference_weights`, `ranking.OBJECTIVES`; `fuzzy.engine.input_memberships`, `fired_rules`, `output_term`; `plan_service.region_profile_payload`; `RunMeta.total_land_ha / budget_rs`.

### `app/services/district_service.py`
| Symbol | Behaviour |
|---|---|
| `get_district_intelligence(location)` | canonical district → cached `_build` payload |
| `_coverage`, `_climate`, `_soil`, `_water`, `_crops`, `_suitability`, `_market`, `_overview`, `_insights`, `_summary` | one section each (see DISTRICT_INTELLIGENCE.md) |
| `trend(years, values)`, `variability_label(cv)` | first-to-last change, slope, CV, direction and variability labels |
| `clear_cache()` | drop cached payloads |

Shared helpers added for it: `preprocessing.observed_rows`, `explanation_service.make_item`.

### `app/services/simulation_service.py`
| Symbol | Behaviour |
|---|---|
| `simulate(request)` | baseline and scenario through `plan_service.run_pipeline` with `ENSEMBLE_SEEDS`; returns every analysis section |
| `resolve(request)` | validation and control mapping (`WATER_LEVEL_STORAGE_PCT`, `market_price_step_pct`, priorities → weights) |
| `_paired(...)` | means, ranges, paired t-test, verdict |
| `_side`, `_run_metrics`, `_cheapest_plan`, `_evaluate_plan` | per-side payload, per-run outcomes, cost lower bound, plan re-evaluation |
| `_conditions`, `_comparison`, `_share_tests`, `_impact`, `_crop_effects`, `_fuzzy_changes`, `_optimization`, `_constraints`, `_historical`, `_decision_impact`, `_trade_offs`, `_summary` | one section each (see SCENARIO_SIMULATION.md) |
| `remember`, `pending` | in-memory results awaiting save |

Supporting changes: `plan_service.run_pipeline` / `PipelineAdjustments` / `PipelineRun` (`generate_farm_plans` calls it); `preprocessing.get_region_season_profile(rainfall_factor, storage_override_pct)`; `FarmPlanProblem(fertilizer_price_factor)` and `single_crop_metrics()`; `ranking.rank_plans(weights)` and `normalise_weights`; `ExplanationContext.weights / price_factor` and `explanation_service.indicative_economics`; `results_store.save_simulation / list_simulations / load_simulation / delete_simulation`. All defaults leave existing outputs unchanged.

## 3. Error handling summary

| Layer | Strategy |
|---|---|
| Data | `ValueError` with explicit message for every empty slice |
| Fuzzy | clip inputs; neutral 0.5/0.5 on inference failure |
| Optimiser | infeasible solutions flagged, callers drop them; empty list is a valid result |
| `/api/plans` | broad `except Exception` → `PlanGenerationError` → 503 (also swallows `ValueError` for bad season/year into 503) |
| Weather | broad `except` → CSV fallback, logged |
| Persistence | corrupt files skipped; atomic writes |
| HTTP | ValueError→400 (core) / 404 (dashboard), validation→422 |

Not handled: disk full during save (500), Open-Meteo slowness (up to 5 s per call × 5 calls on the dashboard), extremely large `pop_size × n_gen` requests (bounded at 300 × 500).

## 4. Testing

| File | Focus | Count |
|---|---|---|
| test_api.py | core endpoints, validation, budget constraint | 21 |
| test_dashboard.py | dashboard endpoints, weather parsing (mocked), history scoping | 52 |
| test_data.py | CSV presence, loader cache, catalog, profile, fertility formula | 36 |
| test_fuzzy.py | output ranges, rule directionality, per-crop penalty | 22 |
| test_pipeline.py | end-to-end, NSGA-II invariants, persistence, convergence | 34 |
| test_hardening.py | run-id safety, cache, atomic save, validation, provenance, determinism, concurrency, run-id collisions, client_id redaction | 40 |
| test_explanation.py | explanation structure, traceability, confidence, constraints, honesty rules, endpoints | 25 |
| test_district.py | district aggregations vs raw CSVs, suitability, market, missing data, caching, endpoint | 96 |
| test_simulation.py | pipeline hooks, validation, paired comparison, end-to-end scenarios vs CSV, history, statements, persistence, endpoints | 61 |

Gaps: operators unit-tested only indirectly; no test pins numeric outputs (a golden-master test would catch unintended model drift – TODO T-13); weather tests call the real Open-Meteo API when network is available; no frontend tests at all.
