# Production verification – official-data release

Verified on 13 November 2026 (15:16–16:06 UTC) against the live deployment of `main` at commit `37813c5` (merge of PR #17, which contains PR #18). Frontend and backend are one Render web service: the API serves the built React app on the same origin.

## Deployed URLs

| What | URL |
|---|---|
| Application | https://agrooptimize.onrender.com/ |
| Swagger UI | https://agrooptimize.onrender.com/docs |
| OpenAPI schema | https://agrooptimize.onrender.com/openapi.json |
| API catalog | https://agrooptimize.onrender.com/api/catalog |
| Dataset registry | https://agrooptimize.onrender.com/api/datasets |
| Health check | https://agrooptimize.onrender.com/health |

## Deployment

| Step | Result |
|---|---|
| Latest `main` pulled | `37813c5` – PRs #17 and #18 merged |
| Render branch | the service was still deploying `feature/render-deployment` (last deploy 23 Oct, v1 code: 4 districts, Summer season, `/api/datasets` 404). The service branch was switched to `main` in the Render dashboard and deployed manually |
| Build | completed; the official database was rebuilt inside the image (`/api/datasets` → `imported_at` 2026-11-13T15:15:42Z) |
| Live | 15:16:33 UTC: `/api/datasets` 200, catalog 38 districts, seasons Kharif and Rabi |
| Pre-deploy check | the image contents (`app/`, `data/`, `requirements.txt`, pinned wheels only, frontend built from a clean export of `main`) were run locally: database build succeeds, 16/16 browser checks pass |

## Smoke test (`scripts/smoke_test_deployment.py`)

Final run, finished 16:06 UTC, compared with the first production run:

```
37/37 checks passed against https://agrooptimize.onrender.com
18/18 result fingerprints identical to the earlier production run
```

| Group | Checks (all PASS) | Production time |
|---|---|---|
| Service | health, openapi, swagger-ui, frontend-index, frontend-spa-fallback, frontend-asset, api-unknown-404 | 0.15–0.33 s |
| Official data | catalog, datasets, region-profile, soil-profile, soil-master, weather-disabled (501 as designed), taluk-pollachi-404 | 0.15–0.28 s |
| Optimisation | farm-plans, farm-plans-budget, farm-plans-saved, result, result-explanation, history, results-list, dashboard | 6.7–9.8 s per optimisation; others ≤ 0.2 s |
| Analysis | plans, comparison, comparison-explanation, compare-fuzzy, district-intelligence, fuzzy-explain, fuzzy-audit | compare-fuzzy 17.1 s (two optimisations); others ≤ 0.25 s (cached) |
| Scenario simulation | simulation-run, -save, -list, -get, -delete | run 69.6 s (10 optimisations); others ≤ 0.3 s |
| Errors | validation-422, unknown-district-404, bad-run-id-404 | ≤ 0.24 s |

**Reproducibility.** Two production runs gave identical fingerprints for all 18 recorded results. Compared with a Mac, the NSGA-II results (farm plans, plans, comparison, simulation: 10 of 18) differ, as documented in [DEPLOYMENT_REPORT.md](../handbook/DEPLOYMENT_REPORT.md) §4 (floating-point differences between arm64 macOS and x86-64 Linux); every non-NSGA-II result is identical. Consequence for the slides: production recommends maize 37 % / ragi 45 % / red gram 8 % / green gram 10 % (TOPSIS 0.6485) for Salem Rabi 2024, 5 ha, while the Mac run in `final_ppt/` gives ragi 82.5 % / green gram 17.5 % (0.6398). Both are real results of the same code.

## Feature verification in the browser (`scripts/verify_production_ui.py`)

Google Chrome, 1440 px, run end to end against production (190 s):

| Check | Result | Evidence |
|---|---|---|
| Official datasets load | PASS | Official Data page lists 10 datasets, 39,065 rows, 9 disabled features |
| Dashboard | PASS | KPIs; weather card states "Official Data Not Available" with the reason |
| Optimization works | PASS | Salem Rabi 2024 run saved; top plan maize 37 %, ragi 45 %, red gram 8 %, green gram 10 %, official fuzzy model |
| Explainability loads | PASS | "Why this plan?" with reasons and "Why this crop was selected" (10 criteria per crop) |
| History works | PASS | saved run listed with the Official-Data Model and Official Data badges |
| Reports work | PASS | report generated and downloaded (145 lines, includes crop evidence, no NaN) |
| District Intelligence works | PASS | summary, climate, soil, water, crops, suitability, market, insights |
| Soil Health Card loads | PASS | Salem, 2024-25 cycle, 14,996 samples: pH, organic carbon, N, P, K, salinity, micronutrients |
| Scenario Simulation works | PASS | rainfall −20 %: original vs simulated recommendation |
| Analytics, Comparison | PASS | |
| Settings | PASS | System Information: backend 0.1.0, report year 2024-25, NSGA-II + TOPSIS, official fuzzy model, 10 datasets |
| Swagger / OpenAPI | PASS | `/docs` renders; `/openapi.json` lists `/api/farm-plans` (smoke test) |
| API catalog, dataset registry | PASS | smoke test `catalog`, `datasets`; Official Data page |
| No console errors | PASS | 0 errors or warnings |
| No API failures | PASS | 0 failed API responses |
| No raw null / NaN / undefined text | PASS | none on any page |

**All network requests.** A second pass opened all 13 pages (onboarding, login, profile setup and the 10 app pages) plus Swagger: **234 requests, 0 failed** (including fonts, icons and the onboarding images).

## Screenshots

All taken from production, in [`screenshots/`](screenshots/):

| File | Shows |
|---|---|
| `01_home_page.png` | landing page |
| `02_official_datasets.png` | Official Data page: registry, disabled features, coverage |
| `03_dashboard.png` | Home with official KPIs and the weather notice |
| `04_optimization_result.png` | saved optimisation and TOPSIS ranking |
| `05_explainability_crop_evidence.png` | "Why this crop was selected" |
| `06_history.png` | history with model and data badges |
| `07_reports.png` | generated report card |
| `08_district_intelligence.png` | District Intelligence, Salem |
| `09_soil_health_card.png` | Soil Health Card section |
| `10_scenario_simulation.png` | scenario simulation result |
| `11_settings.png` | settings with system information |
| `12_api_docs.png` | Swagger UI |

## Issues found and what was done

| Issue | Status |
|---|---|
| Production was still serving the v1 app because the Render service deployed `feature/render-deployment`, not `main` | fixed: service branch switched to `main` and deployed |
| Smoke test reported false differences between two identical production runs: `meta.quality_metrics.runtime_seconds` (a wall-clock time) was not excluded from the fingerprints | fixed in `scripts/smoke_test_deployment.py` (`runtime_seconds` added to the volatile keys) |
| A request that never answered stopped the whole smoke test with a traceback | fixed: a timeout or connection error is now reported as a failed check and the run continues |
| **Intermittent:** in 2 of 7 smoke-test runs the simulation request (`POST /api/simulations/run`) got no response body within the 300 s read timeout (stopped at 370.9 s and 371.2 s). The same request answered in 69.6–77.1 s in the other 5 runs, 3 direct calls (70.2–72.8 s) and the browser run; the instance did not restart (saved runs kept) | **open, not reproducible on demand.** Render's logs are needed to see whether the response was cut by the proxy or the instance stalled. Not a code change: the backend was not modified. Recommended: check the Render logs for the two requests (started ≈15:37 and ≈15:51 UTC, runs ending 15:43:37 and 15:56:59 UTC), and consider running simulations as a background job or on a paid instance |

## Performance on the free instance (measured)

| Request | Production | Local (Mac) |
|---|---|---|
| one optimisation (`POST /api/farm-plans`) | 6.7–9.9 s | 0.28 s |
| scenario simulation (10 optimisations) | 69.6–77.1 s | 2.9 s |
| cached / data endpoints | 0.15–0.33 s | ≈ 1–3 ms |

The frontend's simulation message ("This takes a few seconds") understates the production time.

## Final status

**READY FOR FINAL REVIEW**

All required features work on production: official datasets, optimisation, explainability, District Intelligence, Soil Health Card, scenario simulation, history, reports, Swagger/OpenAPI, the API catalog and the dataset registry; the final smoke test passed 37/37 with 18/18 reproducible results, and the browser run had no console errors and no failed network requests. One intermittent infrastructure issue (a simulation response that occasionally does not arrive on the free instance) is open and documented above.
