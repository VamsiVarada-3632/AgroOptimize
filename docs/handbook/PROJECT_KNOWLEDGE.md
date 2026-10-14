# AgroOptimize – Project Knowledge Handbook

Self-contained handbook. If you read only one file, read this one; it links to the detailed documents. State as of **2026-09-29** (after the audit described in [IMPROVEMENT_LOG.md](IMPROVEMENT_LOG.md)).

---

## 1. What the project is

AgroOptimize is a final-year project (Team 52, Amrita Vishwa Vidyapeetham, 23CSE498 Phase II; guide Dr. G. Jeyakumar; students VVS Vamsi, Vennela Harshini, Garudammagari Sreenithya, Gaddam Jahnavi). It is a web-based **decision-support system that recommends how a farmer should split land among candidate crops** (and how intensively to irrigate and fertilise each) for a chosen location, season and year, balancing four objectives:

1. maximise expected yield (tonnes),
2. minimise production cost (₹: fertiliser + pesticide + labour),
3. minimise irrigation water (litres),
4. minimise an environmental-impact index (nitrogen-leaching × carbon proxy).

Uncertainty about rainfall, water storage and soil is handled by a **Mamdani fuzzy inference system**, whose outputs reduce each crop's expected yield. **NSGA-II** finds the Pareto set of trade-off plans; **TOPSIS** ranks them by the farmer's stated preference. The team's paper (`reference_docs/Reference_Paper_AgroOptimize.pdf`) describes the method; the implementation differs from it in several places (§11).

Coverage: Coimbatore, Erode, Salem, Pollachi (Tamil Nadu); seasons Kharif, Rabi, Summer; years 2020–2023 (baseline) + 2024 (estimated).

## 2. Components and where they live

| Component | Path | Tech |
|---|---|---|
| Backend API + pipeline | `agrooptimize-backend/` (git repo, branch `main`) | Python 3.11, FastAPI, pandas, scikit-fuzzy, pymoo, matplotlib |
| Frontend | `frontend/` in the git repo (local working copy: `stitch_agrooptimize_app/`) | React 19, Vite 8, Tailwind 4, hand-drawn SVG charts |
| Dataset | `agrooptimize-backend/data/raw/*.csv` | 16 CSVs |
| Saved runs | `agrooptimize-backend/results/` (Fly volume in prod) | JSON/CSV/PNG |
| Deploy | Fly.io (backend), Vercel (frontend), GitHub Actions | Docker |
| Stale copies | `datasets/`, `AgroOptimize_Updated.zip` | ignore |

Full map: [FOLDER_STRUCTURE.md](FOLDER_STRUCTURE.md). Architecture diagrams: [ARCHITECTURE.md](ARCHITECTURE.md).

## 3. The dataset in one page ([DATASETS.md](DATASETS.md), [DATA_VALIDATION.md](DATA_VALIDATION.md))

| File kind | Grain | Key columns used |
|---|---|---|
| crop | location × year × season × crop (205 rows) | Yield_Kg_Ha, Water_Req_mm, Fertilizer_N/P/K_Kg_Ha, Pesticide_Cost_Rs_Ha, Labor_Days_Ha, Revenue_Rs_Lakh (ranking), Rainfall_Dependency |
| land | location × year × season (60) | Avg_Soil_pH, Organic_Carbon_Percent, N/P/K_Status, Irrigated/Agricultural ha |
| rainfall | location × year × month (240) | Monthly_Rainfall_mm, Deviation_Percent, temps, humidity |
| water_availability | location × year × month (240) | Storage_Percent, Groundwater_Status, Irrigation_Water_MCM, Total_Demand_MCM |

2–5 crops per location/season (Summer always 2). Clean (no nulls/duplicates) and internally consistent, **but**: 2024 rows are synthetic (2023 carried forward or ×1.03) and 2024 is the default year; storage % identical every year; yields flat 2020–23; pH/OC rise linearly; rainfall normals are flat per meteorological season (monthly deviations −93 % … +340 %); provenance of 2020–23 is "course-provided". The API/UI now flag estimated years (`data_year_estimated`).

## 4. The pipeline ([ALGORITHMS.md](ALGORITHMS.md), [OPTIMIZATION_PIPELINE.md](OPTIMIZATION_PIPELINE.md))

**Stage 1 – profile** (`app/data/preprocessing.py`). For (location, season, year): soil fertility index `0.3·pH_score + 0.3·OC_score + 0.4·NPK_score` (0–100); mean seasonal rainfall deviation % and storage % over the season's months (Kharif Jun–Sep, Rabi Oct–Mar same calendar year, Summer Feb–May); effective rainfall = mean monthly rain × months × 0.7; candidate crops = top-N (6) by historical revenue.

**Stage 2 – fuzzy** (`app/fuzzy/engine.py`). Inputs: rainfall deviation [−60, 60] %, storage [0, 100] %, fertility [0, 100]; three triangular sets each (deficit/normal/surplus; low/medium/high; poor/medium/good). Outputs yield_confidence and irrigation_risk (low/medium/high on 0–100, centroid ÷ 100). 26 rules (9-rule rain×water grid, 5 soil interactions, 12 three-way extensions); min/max Mamdani; **5 rules (15, 19, 21, 25, 26) provably have no effect**. Per crop: `confidence = yield_confidence × (1 − irrigation_risk × dep × 0.4)`, dep ∈ {0.1, 0.3, 0.6, 1.0} for Very Low…High rainfall dependency. Observed on real data: yield_confidence 0.55–0.88, irrigation_risk 0.12–0.50.

**Stage 3 – NSGA-II** (`app/optimization/`). Chromosome = n land shares ∈ [1e−4, 1] (renormalised to sum 1) + n irrigation multipliers ∈ [0.7, 1.3] + n fertiliser multipliers ∈ [0.7, 1.3]. Objectives with area aᵢ:
- f1 = −Σ aᵢ·Yieldᵢ/1000·confᵢ
- f2 = Σ aᵢ·(fertᵢ·(12.87·N + 58.70·P + 56.67·K) + pesticide + 319·labour_days)
- f3 = Σ aᵢ·irrᵢ·max(WaterReqᵢ − effective_rain, 0)·10 000
- f4 = √(Σaᵢ·fertᵢ·Nᵢ × Σaᵢ·[0.15·fertᵢ·(N+P+K)ᵢ + 0.01·irrᵢ·WaterReqᵢ])
- optional constraint f2 ≤ budget.

pymoo NSGA2 with random uniform sampling, binary tournament, custom single-point crossover (p 0.85), custom per-gene Gaussian mutation (p 0.12, σ = 0.12 × range), repair (renormalise shares, clip), rank-and-crowding survival, duplicate elimination; population 80 (farm-plans) or 100 (dashboard), 200 generations, seed 42; ≈0.3 s per run. Runs are serialised by a lock because the custom operators use NumPy's global RNG (concurrency previously broke reproducibility). Optional per-generation history → run-normalised 4-D hypervolume (ref point 1.1).

**Stage 4 – decision** (`app/decision/ranking.py`). Optional hard filters, then TOPSIS on min–max normalised objectives (cost/water/impact flipped) with preference weights (balanced 0.30/0.233/0.233/0.233; the other four put 0.55 on their objective); closeness = d⁻/(d⁺+d⁻); top 50. Each plan gets normalised scores, a confidence label (land-weighted crop confidence ≥0.66 High, ≥0.33 Moderate), and a relative trade-off sentence.

**Stage 5 – persist** (`app/services/results_store.py`). `<location>_<season>_<year>_<UTC timestamp>[-n]` → JSON (atomic), plans CSV, convergence CSV and PNG.

### Known model behaviour you must understand
- **Multipliers are inert**: yield does not depend on irrigation or fertiliser, so NSGA-II pushes them to 0.7 (74–99 % of fertiliser genes, 52–100 % of irrigation genes).
- **Yield is tonnage summed across crops**, dominated by sugarcane/tapioca/banana/coconut.
- **Fuzzy only rescales yield**; the fuzzy vs non-fuzzy study shows identical min-cost/min-water/min-impact.
- Yield correlates 0.85–1.0 with cost in 3–5-crop problems; 2-crop Summer problems have no yield–cost trade-off.

## 5. Backend API ([API_REFERENCE.md](API_REFERENCE.md))

| Endpoint | What |
|---|---|
| `GET /health` | `{"status":"ok"}` |
| `GET /api/catalog` | locations, seasons, years (2020–2024), crops per season |
| `GET /api/region-profile?location&season&year` | stages 1–2 only |
| `POST /api/farm-plans` | full pipeline; body `FarmPlanRequest` (location, season, year?, total_land_ha>0, budget_rs?, preference, filters, pop_size 8–300, n_gen 5–500, save_results, client_id) |
| `GET /api/results`, `/api/results/{run_id}` | saved runs (client ids redacted in the list) |
| `GET /api/weather/{district}` | Open-Meteo live, CSV fallback |
| `GET /api/dashboard/{district}?client_id` | KPIs, actions, crop revenue split, provenance |
| `GET /api/history/{district}?client_id` | this browser's saved runs, newest first |
| `GET /api/soil-profile/{district}` | soil snapshot |
| `GET /api/plans/{district}?total_land_ha&budget_rs` | ≤100 per-hectare plans + hypervolume history (memoised) |
| `GET /api/comparison/{district}` | Plans A (balanced), B (max yield), C (min cost) + 6-axis radar (memoised) |
| `GET /api/compare-fuzzy/{district}` | fuzzy vs non-fuzzy summary |

Errors: 400 pipeline `ValueError` (core), 404 unknown district/run, 422 validation, 503 optimisation failure. Dashboard endpoints use the **current calendar season**, **latest year**, **5 ha** unless told otherwise.

## 6. Frontend ([FRONTEND.md](FRONTEND.md), [USER_FLOW.md](USER_FLOW.md))

Single-page app with a `currentView` state machine (no router). Flow: Onboarding → Register/Login (**demo, device-local**: password stored as SHA-256 in localStorage, OTP shown on screen) → Profile setup (district, season, crop, land) → shell with Home, Analytics, Comparison, Run Optimization, History, Reports, Settings. User profile and a random `client_id` live in localStorage; `client_id` scopes History.

- **Home**: KPI cards (active plans, district-average yield + trend, irrigation share of demand, soil fertility), estimated-data banner, recommended actions from soil N/P/K and storage, weather (live/fallback), crop revenue split.
- **Analytics**: scatter of all Pareto plans (₹/ha vs t/ha), cost/yield/water sliders, cheapest compliant plan, hypervolume chart, fuzzy vs non-fuzzy table, CSV export.
- **Comparison**: plans A/B/C table (t/ha, ₹/ha, impact/ha, water label), radar, weight sliders (a second, frontend-only recommender), crop allocations, CSV export.
- **Run Optimization**: the only action that saves a personalised run (animated ≈5.7 s progress over a ≈0.3 s request).
- **History / Reports**: saved runs; downloadable plain-text decision report and clipboard summary.

## 7. Scores and labels ([SCORING_AND_RANKING.md](SCORING_AND_RANKING.md))
Radar axes: yield/cost_eff/water/land = min–max over the three compared plans ×100; risk = (1 − irrigation_risk)×100 (same for all plans); market = (1 − mean rainfall-dependency factor)×100 (no market data). Dashboard: estimated_yield = mean Yield_Kg_Ha of all crops/1000; yield_trend = year-over-year % (+3.0 % for 2024 is the estimation factor); water_utilization = Σ irrigation / Σ demand; soil status 70/45 thresholds. "Recommended" means different things on different pages (TOPSIS, cheapest compliant, weighted radar badge).

## 8. Configuration ([CONFIGURATION.md](CONFIGURATION.md), [DEPENDENCIES.md](DEPENDENCIES.md))
Everything in `app/config.py`. Sourced constants: fertiliser ₹12.87/kg N, ₹58.70/kg P₂O₅, ₹56.67/kg K₂O (from bag prices); labour ₹319/day (MGNREGA TN 2024-25). Assumptions: rainfall utilisation 0.7, carbon proxies 0.15/0.01, dependency factors, multiplier bounds 0.7–1.3, all fuzzy breakpoints, TOPSIS weights. Paper-given: 200 generations, p_c 0.85, p_m 0.12. Env vars actually read: `CORS_ALLOW_ORIGINS` (backend), `VITE_API_BASE` (frontend build).

## 9. Quality status
- Tests: 205 backend (pytest), 0 frontend. Lint clean. Build green.
- Security ([SECURITY_REVIEW.md](SECURITY_REVIEW.md)): no auth by design; client-id leak, path validation, plaintext password, run-id overwrite fixed; rate limiting, retention, non-root container open.
- Performance ([PERFORMANCE_REVIEW.md](PERFORMANCE_REVIEW.md)): sub-second; memoised dashboard fronts; open: weather caching, lock contention for large requests, unbounded results.
- UX ([UI_UX_REVIEW.md](UI_UX_REVIEW.md)): honest states; alert stubs replaced with real exports; open: routing, accessibility, i18n, personalisation of Analytics.
- Debt ([TECHNICAL_DEBT.md](TECHNICAL_DEBT.md)), remaining work ([TODO.md](TODO.md)).

## 10. Research standing ([RESEARCH_REVIEW.md](RESEARCH_REVIEW.md))
Strong engineering; the research case needs (a) settled data provenance, (b) input-response functions so the multipliers matter, (c) a profit or nutrition objective instead of summed tonnes, (d) uncertainty that shapes the trade-off rather than only scaling yield, (e) multi-seed statistics and baselines (NSGA-III, ε-constraint LP). The honest viva answers are listed in RESEARCH_REVIEW §10.

## 11. Paper vs implementation (short)
Implemented as stated: NSGA-II with 200 generations, single-point crossover 0.85, Gaussian mutation 0.12, four objectives, Mamdani engine, ranked plans with trade-off text and preference filters, web interface. Different or missing: trapezoidal MFs / 5-set soil moisture, probability-weighted scenarios, fertiliser type and harvest timing genes, per-plot assignment, [0,1] scaling inside optimisation, robustness confidence intervals, parallel-coordinates chart, printable PDF report with irrigation schedule; the paper's result tables are not reproducible from the current code/data; reference [2] conflicts with the repo's verified literature survey.

## 12. Glossary

| Term | Meaning here |
|---|---|
| Kharif / Rabi / Summer | Indian cropping seasons (monsoon / winter / pre-monsoon) |
| Candidate crops | crops on record for the slice, top-N by district revenue |
| Plan | land shares + multipliers for the candidate crops, with four objective values |
| Pareto front | set of plans none of which is better on all four objectives than another |
| Hypervolume | volume of normalised objective space dominated by the population, vs ref point 1.1 |
| TOPSIS closeness | relative distance to the ideal vs anti-ideal plan (0–1, higher better) |
| Yield confidence | fuzzy estimate (0–1) of how much of book yield is realised this season |
| Irrigation risk | fuzzy estimate (0–1) of extra irrigation pressure |
| `client_id` | random per-browser id that scopes History |
| `data_year_estimated` | the resolved year's rows are estimates (2024) |

## 13. How to verify anything in this handbook
```bash
cd agrooptimize-backend && python3 -m pytest -q              # 205 passing
python3 run_demo.py --location Salem --season Kharif --land 5 # stage-by-stage printout
uvicorn app.main:app --port 8000 && open http://localhost:8000/docs
```
