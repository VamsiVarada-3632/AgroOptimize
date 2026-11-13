# Configuration, Constants and Assumptions

All modelling constants live in `agrooptimize-backend/app/config.py`; a few more are local to modules. **Provenance** column: *Sourced* (traceable to a named public figure, as documented in the code comment – not re-verified here), *Convention* (standard unit/agronomic convention), *Assumption* (chosen by the team, no source), *Tuned* (adjusted by hand to get desired behaviour).

## 1. Environment variables

| Variable | Read by | Default | Purpose |
|---|---|---|---|
| `CORS_ALLOW_ORIGINS` | `app/main.py` | empty | comma-separated extra allowed origins (production sets `https://agrooptimize.vercel.app` in `fly.toml`/`render.yaml`) |
| `PORT` | – (set in fly.toml) | 8000 | **not read**; the Dockerfile CMD hard-codes `--port 8000` |
| `VITE_API_BASE` | frontend build (`import.meta.env`) | `http://localhost:8000` | backend URL; `.env.production` sets `https://agrooptimize-backend.fly.dev` |
| `FLY_API_TOKEN` | GitHub Actions secret | – | deploy |
| `AGROOPTIMIZE_DB_URL` | `app/db/session.py` | `sqlite:///<project>/data/official/official_v1.db` | official-data database (SQLAlchemy URL) |
| `AGROOPTIMIZE_FUZZY_MODEL` | `app/config.py` | `official` | default fuzzy model |
| `AGROOPTIMIZE_NSGA2_MODE` | `app/config.py` | `original` | NSGA-II engine mode |
| `AGROOPTIMIZE_RESULTS_DIR` | `app/config.py` | `<project>/results` | saved runs and simulations |

`agrooptimize-backend/.env.example` lists `DATA_DIR`, `RESULTS_DIR`, `LOG_LEVEL`, `NSGA2_*`, `API_*`, but **nothing reads them** (its own header says so). Making `RESULTS_DIR`, `NSGA2_SEED` and log level environment-configurable is TODO T-14.

## 2. `app/config.py`

### Paths and dataset structure
| Constant | Value | Provenance |
|---|---|---|
| `OFFICIAL_DATA_DIR` | `<project>/data/official` (`raw/` tracked; `official_v1.db` and `clean/` rebuilt by `scripts/preprocess_all.py`) | – |
| `RESULTS_DIR` | `<project>/results` | – (Fly volume mounts here) |
| `LOCATIONS` | the 38 districts with official crop statistics, resolved lazily from the database | official data |
| `AG_SEASONS` | Kharif, Rabi | official reports (no Summer season) |
| `SEASON_MONTH_MAP` | re-exported from `app/datasets/reference.py` (`SEASON_MONTHS`) | official reports |

The v1 constants (`RAW_DATA_DIR`, `DATASET_KINDS`, `DISTRICT_COORDINATES`, fertiliser prices, labour wage, litres per mm, rainfall utilisation, carbon factors, rainfall-dependency factors) were removed with the migration; they live on in `legacy/config_v1.py`. The objectives now use official values only (`app/optimization/problem.py`): f2 = yield × CACP cost of cultivation (₹/q), f3 = irrigated hectare-equivalents (area × multiplier × the crop's official irrigated share), f4 = kg of N+P₂O₅+K₂O from the TNAU dose.

### Candidate crops
| `DEFAULT_MAX_CANDIDATE_CROPS` | 6 | Assumption (binding on the official data: each of the six benchmark cases has 6 candidates, [OFFICIAL_DATA_PERFORMANCE.md](OFFICIAL_DATA_PERFORMANCE.md)) |
| `MIN_CANDIDATE_CROPS` | 2 | Assumption; fewer complete crops → 400 (Chennai, The Nilgiris) |

### Decision-variable bounds
| `ALLOC_MIN, ALLOC_MAX` | 0.0, 1.0 (lower bound overridden to 1e−4 in `problem.py`) | Assumption |
| `IRRIGATION_MULT_MIN/MAX` | 0.7 / 1.3 | Assumption |
| `FERTILIZER_MULT_MIN/MAX` | 0.7 / 1.3 | Assumption |

### NSGA-II
| `NSGA2_POP_SIZE` | 80 | Assumption (paper gives none) |
| `NSGA2_N_GEN` | 200 | Paper |
| `NSGA2_CROSSOVER_PROB` | 0.85 | Paper |
| `NSGA2_MUTATION_PROB` | 0.12 | Paper |
| `NSGA2_MUTATION_SIGMA` | 0.12 (× gene range) | Assumption |
| `NSGA2_SEED` | 42 | Convention |
| `NSGA2_FAST_POP_SIZE / FAST_N_GEN` | 24 / 15 | tests only |
| `NSGA2_ENGINE_MODE` | `"original"` (env `AGROOPTIMIZE_NSGA2_MODE`) | `original` reproduces published results; `enhanced` is experimental ([NSGAII_IMPROVEMENTS.md](NSGAII_IMPROVEMENTS.md)) |
| `FUZZY_MODEL` | `"official"` (env `AGROOPTIMIZE_FUZZY_MODEL`) | `official` is calibrated on the official data (`app/fuzzy/calibration.py`); `original` is the published system, `improved` and the single-improvement models are described in [FUZZY_MODEL_IMPROVEMENTS.md](FUZZY_MODEL_IMPROVEMENTS.md); a request's `fuzzy_model` overrides it |
| `NSGA2_ENGINE_FEATURES` | per-mode switches | enhanced: smart initialisation, adaptive mutation, constraint-aware initialisation, duplicate avoidance; available but off: adaptive crossover, tolerance duplicate removal, early stopping, LHS initialisation, parallel evaluation ([NSGAII_BENCHMARK_RESULTS.md](NSGAII_BENCHMARK_RESULTS.md)) |
| `NSGA2_ENGINE_MUTATION_PROB` | original 0.12, enhanced 0.05 | Parameter study (NSGAII_PROFILE.md §4) |
| `NSGA2_ADAPTIVE_MUTATION` | min 0.02, max 0.30, diversity floor 0.5, converged scale 0.2 | Tuned on seeds 100–104 |
| `NSGA2_ADAPTIVE_CROSSOVER` | schedule `linear` (0.95 → 0.70) or `diversity` (0.85 at the diversity peak → 0.95 at half of it) | Off in both modes |
| `NSGA2_SMART_INIT_FRACTION` | 0.2 | Tuned |
| `NSGA2_DUPLICATE_TOLERANCE` | 1e-4 | Off in both modes |
| `NSGA2_EARLY_STOPPING` | criterion `hypervolume` (patience 30, tolerance 1e-4 relative, min 60) or `objective_space` (pymoo: xtol 0.0005, ftol 0.005, period 50, n_skip 5) | Off in both modes; patience/tolerance also define stagnation for adaptive mutation |
| `NSGA2_PARALLEL_WORKERS` | 4 | Threads for `parallel_evaluation` (off) |
| `MAX_RETURNED_PLANS` | 50 | Assumption (paper: 20–50 plans) |

## 3. Constants outside `config.py`

| Location | Constant | Value | Provenance |
|---|---|---|---|
| `official_view.py` | `CLASS_SCORE` for the fertility index (share-weighted Soil Health Card classes, mean of N, P, K, OC) | Low 0 / Medium 0.5 / High 1 | Documented rule |
| `preprocessing.py` | `_ranges()` | rain 0–max observed, dev ±60, storage 0–100 | Assumption (display only) |
| `fuzzy/engine.py` | all MF breakpoints; universes; 26 rules; fallback 0.5/0.5; max penalty 0.4 | see ALGORITHMS §2 | Assumption |
| `optimization/problem.py` | allocation lower bound | 1e−4 | Implementation detail |
| `nsga2_runner.py` | HV reference point, clip | 1.1 ×4, 1.5 | Convention |
| `ranking.py` | `_YIELD_GROUP_WEIGHT` and preference weights | 0.30; 0.55/0.15 | Tuned / Assumption |
| `ranking.py` | bucket thresholds | 0.33 / 0.66 | Assumption |
| `ranking.py` | default crop confidence if missing | 0.7 | Assumption |
| `dashboard_service.py` | `_DEMO_POP_SIZE` | 100 | Assumption |
| `dashboard_service.py` | soil status thresholds | 70 / 45 | Assumption |
| `dashboard_service.py` | irrigation action threshold | storage < 40 % | Assumption |
| `dashboard_service.py` | action urgency windows | "Next 24 hours" … | Assumption (text) |
| `dashboard_service.py` | `_REFERENCE_FARM_HA` | 10 ha | Presentation |
| `dashboard_service.py` | `_cached_pareto_front` size | 32 | Implementation |
| `main.py` | land upper bound, client_id length | 100,000 ha, 128 | Validation |
| `schemas.py` | pop 8–300, gen 5–500, candidate crops 2–12 | | Validation |
| Frontend `DashboardView` | water label thresholds | 70 / 40 | Presentation |
| Frontend `RunOptimizationView` | progress timers | 900 / 1300 ms | Presentation |
| Frontend `officialData.js` | text for missing official values | "Official Data Not Available" | Presentation |
| Frontend `officialData.js` | HTTP statuses treated as "no official data" | 400, 404, 501 | Implementation |

## 4. Deployment configuration

| File | Key settings |
|---|---|
| `Dockerfile` | two stages: `node:22-slim` builds `frontend/dist` (`npm ci`, `vite build`); `python:3.13-slim` installs pinned binary wheels from `requirements.txt`, copies `app/ data/` and the build, rebuilds the official database from `data/official/raw` (`build_database()`), runs as user `agro` (uid 10001), `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers`, 1 worker. See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) |
| `.dockerignore` | excludes `.git`, `tests/`, `docs/`, `notes/`, `scripts/`, `results/`, caches, `frontend/node_modules`, `frontend/dist`, `frontend/.env*` |
| `fly.toml` | app `agrooptimize-backend`, region `sin`, `force_https`, `auto_stop_machines=false`, `min_machines_running=1`, 1 shared CPU / 512 MB, health `/health` 15 s, volume `agrooptimize_results → /app/results` |
| `render.yaml` | one Docker web service `agrooptimize` (frontend + API), free plan, Singapore, health `/health`, auto-deploy with build filters, `AGROOPTIMIZE_NSGA2_MODE=original`; optional persistent disk documented in comments |
| `vercel.json` | `npm run build`, output `dist`, SPA rewrite |
| `.github/workflows/deploy-backend.yml` | on push to `main` under `agrooptimize-backend/**`: `test` job (Python 3.11, pytest) → `deploy` job (`needs: test`) |
| Environment | `AGROOPTIMIZE_RESULTS_DIR` (saved runs/simulations folder, default `results/`), `AGROOPTIMIZE_FRONTEND_DIST` (frontend build served by the API, default `frontend/dist`), `AGROOPTIMIZE_NSGA2_MODE`, `AGROOPTIMIZE_FUZZY_MODEL`, `CORS_ALLOW_ORIGINS`, `PORT`; frontend build: `VITE_API_BASE` (optional; production default is the page origin) |
| `requirements.txt` / `requirements-dev.txt` | pinned runtime dependencies / runtime + pytest, httpx |
| `pytest.ini` | testpaths `tests`, `-v --tb=short`, ignore Deprecation/User warnings |
| `.oxlintrc.json` | react + oxc plugins; `rules-of-hooks` error; ignores `dist/**`, `*/code.html` |

Monorepo note: the workflow's `paths: agrooptimize-backend/**` assumes the GitHub repository root is `final_year_project/`, but locally only `agrooptimize-backend/` is a git repository (and it contains `frontend/`, not `stitch_agrooptimize_app/`). Confirm which layout the GitHub remote actually has (TODO T-9).

## Frontend configuration

| Setting | Where | Default | Meaning |
|---|---|---|---|
| `VITE_API_BASE` | build-time env (`frontend/.env*` or the shell) | page origin in a production build, `http://localhost:8000` in `npm run dev` | backend URL (`resolveApiBase` in `src/services/api.js`) |
| District, season, year and crop lists | `GET /api/catalog` | – | nothing is configured in the frontend; adding a district or crop to the official database adds it to every dropdown |
| Default fuzzy model | `GET /api/fuzzy/models` → `default` (backend `AGROOPTIMIZE_FUZZY_MODEL`) | `official` | preselected on Run Optimization |
| Disabled features | `GET /api/datasets` → `disabled_features` | – | weather card and fertiliser-price lever follow this list |
| Test fixtures | `frontend/scripts/refresh-fixtures.mjs [base URL]` | `http://localhost:8000` | re-records `src/__fixtures__/` from a running backend (saves one run; set `AGROOPTIMIZE_RESULTS_DIR` to a scratch folder) |

