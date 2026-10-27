# Changelog

All code modifications made during the 2026-09-29 audit. All changes are submitted together on one branch for review. Frontend changes were made in the local working copy `stitch_agrooptimize_app/` and applied to the repo's `frontend/` (whose source was identical before the changes); the pre-change state is also in `_backups/stitch_agrooptimize_app_before_audit_2026-09-29.tar.gz`.

Verification after all changes: backend **205/205 tests pass** (was 165/165); output fingerprint over 48 endpoint/pipeline results is **identical to HEAD** apart from the new additive provenance fields; frontend `oxlint` 0 warnings (was 3 in `src` + noise), `vite build` succeeds; UI flows exercised in Chrome with no console errors.

## [Unreleased] – Dynamic TOPSIS engine

### Added
- Ranking criteria beyond the four objectives: market price, indicative income, budget headroom, soil suitability, land-use diversification, rainfall exposure (`app/decision/criteria.py`).
- Ranking profiles Balanced (published weights), Profit priority, Water saving, Sustainability, Low cost (rank-sum weights over importance tiers) and custom weights summing to 1 (`app/decision/profiles.py`).
- TOPSIS explanation and profile comparison (`app/decision/topsis_explain.py`, `app/services/topsis_service.py`); `explanation.topsis` section.
- `POST /api/farm-plans` `profile`, `custom_weights`, `compare_profiles`; `meta.topsis`, `meta.profile_comparison`; `GET /api/topsis/profiles`; `GET|POST /api/results/{run_id}/topsis`; `ranking` label on saved-run summaries and History.
- Run Optimization: profile selector with custom weight builder; TOPSIS ranking panel (weights, scores, reasoning, profile comparison, re-ranking the saved front); TOPSIS section in "Why this plan?".
- `scripts/benchmark_topsis.py`, `benchmarks/topsis_*`; `TOPSIS_ARCHITECTURE.md`, `TOPSIS_WEIGHT_ANALYSIS.md`, `TOPSIS_EXPLAINABILITY.md`, `TOPSIS_DYNAMIC_ENGINE.md`, `TOPSIS_PROFILE_GUIDE.md`, `TOPSIS_COMPARISON.md`; 120 backend and 21 frontend tests.

### Changed
- Saved runs store the ranked front (`ranked_front`) for exact re-ranking (≈ +70 KB per 80-plan run).
- Rankings without a profile are unchanged: 120/120 ranking fingerprints identical to `main`; Balanced is bit-identical to the published ranking on 120 benchmark fronts. NSGA-II, objectives and fuzzy outputs are untouched.

## [Unreleased] – Render deployment

### Added
- One-service deployment: FastAPI serves the built React app (`app/frontend.py`: `/assets` with a one-year cache, SPA fallback, API/docs paths keep JSON 404s); gzip for responses over 1 kB.
- Two-stage `Dockerfile` (Node build → Python 3.13 runtime, binary wheels only, non-root user, `$PORT`), `.dockerignore`, `render.yaml` Blueprint.
- `AGROOPTIMIZE_RESULTS_DIR` and `AGROOPTIMIZE_FRONTEND_DIST` settings; `requirements-dev.txt`.
- `scripts/smoke_test_deployment.py` (34 checks, 17 result fingerprints); `tests/test_deployment.py`; frontend tests for the API base and lazy loading.
- `DEPLOYMENT_GUIDE.md`, `DEPLOYMENT_REPORT.md`.

### Changed
- `requirements.txt` pins exact versions and no longer contains test tools.
- Production frontend builds call the API on the page origin; `VITE_API_BASE` still overrides it.
- Each page is a lazily loaded chunk: initial JavaScript 476 → 211 kB (122 → 66 kB gzipped).
- Optimisation, fuzzy and ranking results are unchanged (identical fingerprints against `main`).

## [Unreleased] – NSGA-II optimisation engine (second round)

### Added
- `app/optimization/metrics.py`: hypervolume, GD, IGD, IGD+, spread, spacing, reference fronts; `meta.quality_metrics` on every run (API, saved runs) and shown in Reports.
- Engine switches: `lhs_initialization`, `constraint_aware_initialization` (`BudgetAwareSampling`), `duplicate_avoidance`, `parallel_evaluation` (`app/optimization/parallel.py`); adaptive crossover `schedule="diversity"`; early-stopping `criterion="objective_space"`.
- `scripts/benchmark_tight_budget.py`, `scripts/report_nsga2_benchmark.py`; benchmark: GD/IGD, text parameters, comparisons against both modes, `--memory`; profiler: constraint violations, dominated solutions, monitoring time, `--switch`.
- `NSGAII_ARCHITECTURE.md`, `NSGAII_IMPROVEMENTS.md`, `NSGAII_BENCHMARK_RESULTS.md`, `benchmarks/` charts and summaries; `tests/test_nsga2_optimization.py` (51 tests), `frontend/src/utils/qualityMetrics.test.js`.

### Changed
- Enhanced mode also enables constraint-aware initialisation and duplicate avoidance: same front quality as before, better spread, 13–52 % faster; better than the original on HV in 150/160 paired runs.
- Exact speed-ups (both modes): front hypervolume from cached arrays; parent X cached in duplicate checks.
- The original engine's results are unchanged (same 96-run fingerprint as `main`).

## [Unreleased] – NSGA-II engine optimisation

### Added
- Engine modes: `original` (published, default, bit-identical results) and `enhanced` (experimental), selected by `config.NSGA2_ENGINE_MODE` or `AGROOPTIMIZE_NSGA2_MODE`; one switch per improvement (`app/optimization/engine_settings.py`).
- Enhanced features: smart initialisation (`SmartSampling`), adaptive mutation (`AdaptiveGaussianMutation` + `monitoring.adaptive_mutation_prob`), adaptive crossover, tolerance-based duplicate removal, early stopping (`FrontStagnationTermination`). Enhanced mode enables smart initialisation and adaptive mutation from p = 0.05; the other three are available but off (no benefit or lower quality).
- `app/optimization/monitoring.py` (`EngineMonitor`): diversity statistics, runtime profile, convergence history; every run carries `result.engine_report`, saved as `meta.optimizer` (not in the API response) and logged.
- `scripts/profile_nsga2.py`, `scripts/benchmark_nsga2.py`; `tests/test_nsga2_engine.py` (38).
- `NSGAII_ANALYSIS.md`, `NSGAII_PROFILE.md`, `NSGAII_RESEARCH_REVIEW.md`, `NSGAII_IMPROVEMENT_SUMMARY.md`.

### Changed
- Vectorised single-point crossover and binary tournament (same random draws); per-crop constants of `FarmPlanProblem` computed once; convergence history recorded by the monitor instead of pymoo `save_history`. Saved runs 748 → 287 ms, peak memory 57.8 → 1.6 MB; results bit-identical on 96 fingerprinted runs.

## [Unreleased] – Fuzzy system optimisation

### Added
- `fuzzy.engine.explain_inference`: exact rule-level attribution (status, limiting condition, area share, leave-one-out importance, ranking); included in plan explanations as `fuzzy_reasoning.inference` and shown in the explanation panel.
- `app/fuzzy/audit.py`, `GET /api/fuzzy/explain`, `GET /api/fuzzy/audit`, `scripts/benchmark_fuzzy.py`.
- `FUZZY_SYSTEM_ANALYSIS.md`, `FUZZY_EXPLAINABILITY.md`, `FUZZY_RESEARCH_REVIEW.md`, `FUZZY_IMPROVEMENT_SUMMARY.md`; `tests/test_fuzzy_audit.py` (170) and 2 frontend tests.

### Changed
- Fuzzy inference memoised per clipped input; rule base read once into `rule_specs()`; membership functions and input bounds in single tables. Outputs bit-identical on 9,321 inputs; optimisation fingerprint identical.

### Fixed (documentation)
- Six fuzzy rules are inert (13 was missed); effective rule count 20, not 21.

## [Unreleased] – Scenario Simulation & Decision Impact Analysis

### Added
- `app/services/simulation_service.py`; `POST /api/simulations/run`, `POST/GET /api/simulations`, `GET/DELETE /api/simulations/{id}`; `SimulationRequest`, `SimulationOut` and saved-simulation schemas.
- Scenario Simulation page (sidebar, after District Intelligence): scenario controls, recommendation comparison, impact with paired-test verdicts, decision impact, trade-offs, optimisation difference, crop effects, historical comparison, saved scenarios, HTML report with charts, JSON export.
- `GroupedBarChart`, `DeltaBarChart`, `RadarChart`.
- `tests/test_simulation.py` (61) and 24 frontend tests; `SCENARIO_SIMULATION.md`.

### Changed
- `plan_service.run_pipeline` (with `PipelineAdjustments`) now runs stages 1–7; `generate_farm_plans` calls it.
- Default-neutral hooks: rainfall factor and storage override (preprocessing), fertiliser price factor and `single_crop_metrics()` (problem), explicit weights (ranking), custom weights and price factor (explanations), `indicative_economics` extracted.
- `scipy` listed in requirements (already installed transitively).

### Verified
- 387 backend tests and 55 frontend tests pass; 48 optimisation outputs identical to `main`; lint clean; build passes (main bundle +43 KB; report module loaded on demand).

## [Unreleased] – District Intelligence Center

### Added
- `app/services/district_service.py` and `GET /api/district-intelligence/{district}` (`DistrictIntelligenceOut`).
- District Intelligence page with overview, coverage, climate, soil, water, crop history (filters), suitability ranking, historical prices, insights, summary and quick actions (run optimization preselected, compare, report, analytics, CSV/JSON export).
- Reusable `LineChart`, `BarChart`, `ChartCard`; `navigateTo(view, params)`; Run Optimization `initialDistrict`.
- Vitest with 31 frontend tests; `tests/test_district.py` (96 tests); `DISTRICT_INTELLIGENCE.md`.

### Changed
- `preprocessing.observed_rows` and `explanation_service.make_item` are now shared helpers (no behaviour change).

### Verified
- 326 backend tests and 31 frontend tests pass; 48 optimisation outputs identical to `main`; lint clean; build passes.

## [Unreleased] – Explainable recommendations

### Added
- `app/services/explanation_service.py` and endpoints `GET /api/results/{run_id}/explanation`, `GET /api/comparison/{district}/explanation` (typed `ExplanationOut`).
- `ranking.topsis_scores` / `preference_weights` (shared TOPSIS maths), fuzzy `input_memberships` / `fired_rules` / `output_term`, `plan_service.region_profile_payload`.
- Saved runs record `meta.total_land_ha` and `meta.budget_rs`.
- Frontend `ExplanationPanel`, `ExplanationModal`, `ExplanationComparison`; explanation entry points on Comparison, Run Optimization, History and Reports; explanation section in downloaded reports.
- `tests/test_explanation.py` (25 tests); `docs/handbook/EXPLAINABILITY.md`.

### Verified
- 230 backend tests pass; 48 optimisation outputs identical to `main`; frontend lint clean and build passes; all explanation sections render against real API payloads.

## [Unreleased] – 2026-09-29

### Fixed
- **NSGA-II determinism under concurrent requests** (`app/optimization/nsga2_runner.py`). Runs now hold `_NSGA2_RUN_LOCK` while seeding and using NumPy's global RNG. Before: 20 of 40 concurrent runs returned a different Pareto front than the same seed run alone; after: 0 of 40.
- **Saved-run overwrite on same-second collisions** (`results_store._reserve_run_id`): the JSON filename is claimed with exclusive create; collisions get `-2`, `-3`… suffixes.
- **Client-id exposure**: `GET /api/results` now returns `client_id: null` for every run (`app/main.py`).
- **History ordering**: newest saved run first (was alphabetical by the "Season Year" string) (`dashboard_service.get_history`).
- **Unvalidated `run_id` path join**: allow-list regex in `results_store.is_valid_run_id`; invalid ids → 404.
- **Corrupt run files** no longer 500 the listing/loading (skipped / `None`).
- **Dashboard query parameters**: `total_land_ha` must be > 0 and ≤ 100,000, `budget_rs` > 0, `client_id` ≤ 128 chars (422 instead of 500/503 on division by zero).
- **POST body**: preference filters must be ≥ 0; `client_id` ≤ 128.
- Frontend **Comparison "Land Impact"** showed an inverted goodness score as impact → now the real per-hectare impact (lower is better).
- Frontend **Analytics KPI label** "Avg Yield Target" → "Min Yield Target" (it shows the slider minimum).
- Frontend **Run Optimization errors**: 400/422 now show the backend's reason instead of "couldn't reach the backend".
- `/api/weather` docstring claimed there was no live weather API (there is: Open-Meteo).
- `config.DEFAULT_MAX_CANDIDATE_CROPS` comment described a 3-crop limit that does not exist.

### Added
- `data_year_estimated` on region profile (`/api/region-profile`, `/api/farm-plans`) and `data_year` + `data_year_estimated` on `/api/dashboard`; `preprocessing.is_estimated_year()`.
- Case-insensitive `location`/`season` for all endpoints (`preprocessing.canonical_choice`).
- Memoisation of the dashboard Pareto front (`dashboard_service._cached_pareto_front`, `clear_pareto_cache`).
- mtime-keyed run-summary cache and atomic JSON writes (`results_store`).
- `tests/test_hardening.py` (40 tests).
- CI: `test` job gating `deploy` in `final_year_project/.github/workflows/deploy-backend.yml`. That file lives outside the git repository, so it is **not** part of the repo changes and has never run on GitHub (TODO T-9).
- Frontend: `ApiError`, `describeApiError`, `BACKEND_UNREACHABLE_MSG` (`services/api.js`); `utils/download.js`; real CSV export (Analytics, Comparison); real text report download and clipboard copy (Reports); estimated-data banner (Dashboard); time-of-day greeting; inline status in Settings; trade-off sentence and estimated-year note on the Run Optimization result.
- Demo password stored as SHA-256 with migration of legacy plaintext (`AuthView.jsx`); `minLength=8` on registration password.
- `/docs` (27 documents).

### Changed
- `print` → `logging` in `dashboard_service`.
- Magic `reference_land_ha = 10.0` → module constant `_REFERENCE_FARM_HA`.
- `_run_dashboard_pareto_front` now returns the convergence history instead of the pymoo result object (internal API).
- UI wording: footer offline text, profile "Verification completed" → "Profile complete", Settings Google section "Demo only", Comparison "Irrigation Schedule" → "Getting Started (generic template)", "Plot Crop Allocations" → "Crop Allocations", "Export Report" → "Export CSV".
- `.oxlintrc.json` ignores `dist/` and Stitch mock-up HTML.

### Removed
- Frontend `alert()` stubs (7): PDF download, share link, CSV export ×2, plan activated, calendar, Google link/unlink/profile saved.
- Fabricated "Plots 1, 2, 4" labels from the UI (API field kept, marked deprecated).
- Arbitrary ₹50,000/ha red highlight.
- Dead code/files: `ShaderBackground.jsx`, `src/assets/{hero.png,react.svg,vite.svg}`, `_to_delete/`, empty `src/data/`, unused `weatherFailed` state, unused `selectedLanguage` prop, unused `isFallback` state and banner.

### Files touched
Backend: `app/config.py`, `app/main.py`, `app/schemas.py`, `app/data/preprocessing.py`, `app/optimization/nsga2_runner.py`, `app/services/plan_service.py`, `app/services/results_store.py`, `app/services/dashboard_service.py`, `tests/test_hardening.py` (new).
Frontend: `src/App.jsx`, `src/services/api.js`, `src/utils/download.js` (new), `src/views/{Dashboard,Analytics,Comparison,Reports,RunOptimization,History,ProfileSetup,Settings,Auth}View.jsx`, `.oxlintrc.json`.
CI: `.github/workflows/deploy-backend.yml`.
