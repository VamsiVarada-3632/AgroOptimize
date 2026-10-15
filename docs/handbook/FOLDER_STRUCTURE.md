# Folder Structure

Every folder and every significant file in `final_year_project/`, what it is, and whether anything uses it.
Status legend: **Active** = part of the running system · **Reference** = documentation/design material, not executed · **Stale** = superseded copy, should not be edited · **Generated** = produced at runtime.

```
final_year_project/
├── agrooptimize-backend/          Active   Python/FastAPI backend (its own git repo, branch main)
├── stitch_agrooptimize_app/       Active   Local working copy of the React frontend (same source as frontend/ in the git repo)
├── datasets/                      Stale    Older copy of the 16 CSVs (differs from backend data/raw/)
├── docs/                          Active   This documentation set (added 2026-09-29)
├── reference_docs/                Reference Paper PDF, rubric PDF, viva-prep .docx
├── .github/workflows/             Inactive CI/CD file outside the git repo – GitHub never sees it (TODO T-9)
├── _backups/                      Reference Tarball of the frontend taken before the 2026-09-29 audit edits
└── AgroOptimize_Updated.zip       Stale    Snapshot archive of agrooptimize-backend (incl. .pytest_cache, results/)
```

## `agrooptimize-backend/`

| Path | Status | Purpose |
|---|---|---|
| `app/__init__.py` | Active | Empty package marker |
| `app/config.py` | Active | Every tunable constant and modelling assumption (paths, locations, season→month map, prices, wage, carbon factors, NSGA-II hyper-parameters). See [CONFIGURATION.md](CONFIGURATION.md) |
| `app/schemas.py` | Active | Pydantic v2 request/response models (`FarmPlanRequest`, `FarmPlanResponse`, …) |
| `app/main.py` | Active | FastAPI app, CORS, 13 route handlers. See [API_REFERENCE.md](API_REFERENCE.md) |
| `app/data/loader.py` | Active | Reads the 16 CSVs, concatenates per kind, `lru_cache(maxsize=1)` |
| `app/data/preprocessing.py` | Active | Builds `RegionSeasonProfile` (soil, rainfall, water, candidate crops); soil fertility index; `[0,1]` snapshot; provenance flag |
| `app/fuzzy/engine.py` | Active | Mamdani fuzzy inference system (3 inputs, 2 outputs, 26 rules) + per-crop confidence adjustment + rule-level explanation |
| `app/fuzzy/audit.py` | Active | Read-only audit of the fuzzy system (dominance, coverage, firing, monotonicity) |
| `scripts/benchmark_fuzzy.py` | Tool | Times the fuzzy layer and its callers |
| `app/optimization/problem.py` | Active | `FarmPlanProblem` (pymoo `Problem`): chromosome bounds + 4 vectorised objectives + budget constraint |
| `app/optimization/operators.py` | Active | Custom `SinglePointCrossover`, `GaussianMutation`, `AllocationRepair` |
| `app/optimization/nsga2_runner.py` | Active | Runs pymoo NSGA-II (serialised by a lock), decodes Pareto front, hypervolume convergence history |
| `app/decision/ranking.py` | Active | Hard-limit filters, TOPSIS ranking, trade-off wording, confidence labels |
| `app/services/plan_service.py` | Active | Orchestrates the 5-stage pipeline for `POST /api/farm-plans` and the CLI |
| `app/services/results_store.py` | Active | Persists runs to `results/` (JSON/CSV/PNG), lists and loads them |
| `app/services/district_service.py` | Active | District Intelligence aggregation (cached) |
| `app/services/simulation_service.py` | Active | Scenario Simulation and decision impact analysis |
| `results/simulations/` | Generated | Saved simulations (git-ignored with the rest of `results/`) |
| `app/services/dashboard_service.py` | Active | Logic for the 7 frontend-facing endpoints (weather, dashboard, history, soil, plans, comparison, fuzzy comparison) |
| `data/raw/*.csv` | Active | **The** dataset: 4 districts × {crop, land, rainfall, water_availability}. See [DATASETS.md](DATASETS.md) |
| `tests/test_api.py` | Active | 21 tests – core REST endpoints |
| `tests/test_dashboard.py` | Active | 52 tests – dashboard endpoints (weather incl. mocked Open-Meteo, history scoping, plans, comparison) |
| `tests/test_data.py` | Active | 36 tests – loader, catalog, profile building, fertility formula, snapshot |
| `tests/test_fuzzy.py` | Active | 22 tests – fuzzy ranges, rule directionality, per-crop penalty |
| `tests/test_pipeline.py` | Active | 34 tests – end-to-end pipeline, NSGA-II invariants, persistence |
| `tests/test_hardening.py` | Active | 40 tests added 2026-09-29 – path safety, caching, validation, provenance, determinism under concurrency |
| `run_demo.py` | Active | CLI: run the whole pipeline without a server and print a ranked table |
| `requirements.txt` | Active | Python dependencies (see [DEPENDENCIES.md](DEPENDENCIES.md)) |
| `Dockerfile`, `.dockerignore` | Active | Production image (python:3.11-slim, uvicorn on :8000) |
| `fly.toml` | Active | Fly.io app `agrooptimize-backend`, region `sin`, volume mounted at `/app/results` |
| `render.yaml` | Reference | Alternative Render.com deployment (free plan, no persistent disk declared) |
| `pytest.ini` | Active | Test discovery, `-v --tb=short`, suppresses Deprecation/User warnings |
| `.env.example` | Reference | Documents knobs; **nothing reads it** – `config.py` does not load env vars except `CORS_ALLOW_ORIGINS` in `main.py` |
| `results/` | Generated | Saved runs (`<run_id>.json`, `_plans.csv`, `_convergence.csv`, `_convergence.png`). Git-ignored. The 8 runs present were produced from an **older dataset version** (see [DATA_VALIDATION.md](DATA_VALIDATION.md) §D12) |
| `docs/*.md` | Reference (partly stale) | Team-written docs (architecture, API, assumptions, fuzzy rules, literature survey, results). Several numbers are outdated – see [TECHNICAL_DEBT.md](TECHNICAL_DEBT.md) TD-12 |
| `notes/methodology_notes.md`, `notes/viva_prep.md` | Reference (partly stale) | Narrative methodology and viva Q&A |
| `notes/AgroOptimize_Guide_Review_Status.docx` | Reference | Guide review tracker |
| `README.md`, `CONTRIBUTING.md` | Stale | README still says "34 tests", "6 endpoints", "frontend not built". Replacement: [README_UPDATED.md](README_UPDATED.md) |
| `frontend/` | Active | **The React app in version control** (GitHub `main`). Same source as the local `stitch_agrooptimize_app/` working copy described below. (A local checkout that is behind `origin/main` may show only part of it – always `git fetch` first.) |
| `.pytest_cache/`, `app/**/__pycache__/` | Generated | Tool caches (git-ignored) |

## `stitch_agrooptimize_app/` (frontend; in the git repo this is `frontend/`)

| Path | Status | Purpose |
|---|---|---|
| `index.html` | Active | Vite entry; loads Google Fonts (Inter, Montserrat, Material Symbols) and `/src/main.jsx`. Favicon is an external `googleusercontent.com` URL |
| `src/main.jsx` | Active | `createRoot` + `<StrictMode>` |
| `src/App.jsx` | Active | State-machine router (`currentView` string), user state in `localStorage`, layout shell (sidebar/top bar/mobile drawer), health check |
| `src/index.css` | Active | Tailwind v4 `@theme` design tokens (Material-3-style colour roles, typography scale) + keyframes |
| `src/services/api.js` | Active | The only module that calls the backend; `ApiError`, `describeApiError`, per-browser `client_id` |
| `src/views/DistrictIntelligenceView.jsx`, `src/components/district/` | Active | District Intelligence page and its sections |
| `src/views/SimulationView.jsx`, `src/components/simulation/` | Active | Scenario Simulation page and its sections |
| `src/utils/simulationView.js`, `src/utils/simulationReport.jsx` | Active | Simulation helpers and HTML report |
| `src/components/charts/` | Active | Reusable LineChart, BarChart, ChartCard, chart theme |
| `src/utils/districtView.js` | Active | District page selection/formatting helpers |
| `src/**/*.test.js(x)`, `src/__fixtures__/` | Active | Vitest tests and a real API payload fixture |
| `src/utils/download.js` | Active (new) | `downloadFile`, `toCsv` (with CSV-injection guard), `slug` |
| `src/views/*.jsx` | Active | 10 page components – see [FRONTEND.md](FRONTEND.md) |
| `src/components/DataSourceNotice.jsx` | Active | "historical vs live vs personalised" banner |
| `src/components/CountryCodeModal.jsx` | Active | Phone country-code picker (Auth) |
| `src/components/AccountAuthOverlay.jsx` | Active | Mock "authorisation" dialog (Settings → unlink Google, demo only) |
| `src/components/ParticleBackground.jsx` | Active | Canvas particle animation on onboarding |
| `src/components/SuccessCheckSvg.jsx` | Active | Animated check mark (profile complete) |
| `public/favicon.svg`, `public/icons.svg` | Unused | Vite scaffold assets, not referenced |
| `package.json`, `package-lock.json` | Active | React 19.2, Tailwind 4.3, Vite 8.2, oxlint 1.75 |
| `vite.config.js` | Active | `react()` + `tailwindcss()` plugins |
| `.oxlintrc.json` | Active | Lint rules; now ignores `dist/` and the mock-up HTML |
| `vercel.json` | Active | SPA rewrite `/(.*) → /index.html`, output `dist` |
| `.env.production` | Active | `VITE_API_BASE=https://agrooptimize-backend.fly.dev` |
| `.vercel/project.json` | Active | Vercel project link (`agrooptimize`) |
| `<screen_name>/code.html` (28 folders) | Reference | Static HTML mock-ups exported from Google Stitch (Tailwind CDN). Design source for the React views; not built or served |
| `agrooptimize_structural_system/DESIGN.md` | Reference | Design-token spec (colours, type scale) the Tailwind theme mirrors |
| `agrooptimize_brand_logo/screen.png`, `a_realistic_profile_photo…/screen.png` | Reference | Mock-up images |
| `node_modules/` | Generated | npm install output |

Removed on 2026-09-29 (all preserved in `_backups/stitch_agrooptimize_app_before_audit_2026-09-29.tar.gz`): `_to_delete/` (stale scaffold build + an intentionally-empty `weatherData.js`), `src/components/ShaderBackground.jsx` (never imported), `src/assets/{hero.png,react.svg,vite.svg}` (scaffold leftovers), empty `src/data/`.

## `datasets/` (top level)

16 CSVs with the same names as `agrooptimize-backend/data/raw/` but an **older schema**: no `data_source` / `Annual_Normal_mm` columns, no 2024 rows (612 lines vs 761), and different `Normal_Rainfall_mm` values (e.g. Coimbatore January normal 7.5 mm here vs 37.5 mm in `data/raw`). Nothing reads it. Keep only as an archive, or delete to avoid confusion (TODO T-8).

## `reference_docs/`

| File | Content |
|---|---|
| `Reference_Paper_AgroOptimize.pdf` | The team's own 6-page paper (*A fuzzy-evolutionary decision support system for agricultural farming under uncertainties*). The implementation diverges from it in several places – see [RESEARCH_REVIEW.md](RESEARCH_REVIEW.md) §3 |
| `Phase 2 Project Rubrics.pdf` | Guide Review 1 (7), Panel Review 1 (20), Guide Review 2 (8) rubrics for research/application/software projects |
| `AgroOptimize_Panel_Viva_Prep.docx` | Viva preparation notes |
