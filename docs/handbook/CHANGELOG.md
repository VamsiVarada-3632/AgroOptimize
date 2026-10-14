# Changelog

All code modifications made during the 2026-09-29 audit. All changes are submitted together on one branch for review. Frontend changes were made in the local working copy `stitch_agrooptimize_app/` and applied to the repo's `frontend/` (whose source was identical before the changes); the pre-change state is also in `_backups/stitch_agrooptimize_app_before_audit_2026-09-29.tar.gz`.

Verification after all changes: backend **205/205 tests pass** (was 165/165); output fingerprint over 48 endpoint/pipeline results is **identical to HEAD** apart from the new additive provenance fields; frontend `oxlint` 0 warnings (was 3 in `src` + noise), `vite build` succeeds; UI flows exercised in Chrome with no console errors.

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
