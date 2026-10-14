# Architecture

AgroOptimize is a two-tier web application: a **React SPA** (`stitch_agrooptimize_app/`) talking JSON over HTTPS to a **stateless FastAPI service** (`agrooptimize-backend/`) that runs a data → fuzzy → NSGA-II → TOPSIS pipeline over 16 CSV files. There is **no database** and **no server-side user model**: user profiles live in browser `localStorage`, saved optimisation runs live as files on a disk volume.

## 1. System context

```mermaid
flowchart LR
    farmer([Farmer / examiner<br/>web browser])
    subgraph Vercel
        spa[React 19 SPA<br/>stitch_agrooptimize_app]
    end
    subgraph Fly.io["Fly.io (region sin, 1 shared CPU, 512 MB)"]
        api[FastAPI + Uvicorn<br/>agrooptimize-backend]
        vol[(Volume agrooptimize_results<br/>/app/results)]
        csv[(data/raw/*.csv<br/>baked into image)]
    end
    meteo[(Open-Meteo<br/>public forecast API)]
    gfont[(Google Fonts +<br/>googleusercontent images)]

    farmer -->|HTTPS| spa
    spa -->|fetch JSON, VITE_API_BASE| api
    spa --> gfont
    api --> csv
    api <-->|JSON/CSV/PNG files| vol
    api -->|GET /v1/forecast, 5 s timeout| meteo
```

## 2. Backend module structure

```mermaid
flowchart TB
    main[app/main.py<br/>FastAPI routes + CORS + query validation]
    schemas[app/schemas.py<br/>Pydantic models]
    ps[services/plan_service.py<br/>generate_farm_plans]
    ds[services/dashboard_service.py<br/>weather · dashboard · history · soil<br/>plans · comparison · compare-fuzzy]
    rs[services/results_store.py<br/>save / list / load runs]
    pre[data/preprocessing.py<br/>RegionSeasonProfile]
    load[data/loader.py<br/>CSV load + lru_cache]
    fz[fuzzy/engine.py<br/>Mamdani FIS, 26 rules]
    prob[optimization/problem.py<br/>FarmPlanProblem, 4 objectives]
    ops[optimization/operators.py<br/>crossover · mutation · repair]
    run[optimization/nsga2_runner.py<br/>run_nsga2 + HV history]
    rank[decision/ranking.py<br/>filters + TOPSIS]
    cfg[config.py]

    main --> schemas
    main --> ps
    main --> ds
    main --> rs
    main --> pre
    main --> fz
    ps --> pre & fz & prob & run & rank & rs
    ds --> load & pre & fz & prob & run & rank & rs
    pre --> load
    run --> ops & prob
    prob --> fz
    rank --> run
    pre & fz & prob & run & rank & rs & load --> cfg
```

Design properties:

* **Layered and acyclic.** Data → fuzzy → optimisation → decision → services → HTTP. Lower layers never import upward (`ranking.py` imports only the `FarmPlan` dataclass from the runner).
* **Two orchestrators.** `plan_service.generate_farm_plans` serves `POST /api/farm-plans` and the CLI (≤50 plans, persistence, filters, user preference). `dashboard_service._run_dashboard_pareto_front` serves the dashboard endpoints (population 100, up to 100 plans, no persistence, memoised). They deliberately share the same lower-level modules.
* **Deferred imports in `main.py`.** Route handlers import services inside the function body; it only affects import order, not behaviour.

## 3. Request lifecycle – `POST /api/farm-plans`

```mermaid
sequenceDiagram
    autonumber
    participant UI as RunOptimizationView
    participant API as main.post_farm_plans
    participant PS as plan_service
    participant PP as preprocessing
    participant FZ as fuzzy.engine
    participant GA as nsga2_runner (locked)
    participant RK as ranking
    participant RS as results_store

    UI->>API: POST {location, season, year?, total_land_ha, budget_rs?, preference, save_results:true, client_id}
    API->>API: Pydantic validation (422 on failure)
    API->>PS: generate_farm_plans(request)
    PS->>PP: get_region_season_profile(loc, season, year)
    PP-->>PS: RegionSeasonProfile (soil, rainfall, water, ≤6 crops, data_year_estimated)
    PS->>FZ: evaluate_uncertainty(rain_dev%, storage%, fertility)
    FZ-->>PS: yield_confidence, irrigation_risk, labels
    PS->>GA: run_nsga2(FarmPlanProblem, pop 80, gen 200, track_history)
    GA-->>PS: pymoo Result (final population + history)
    PS->>PS: extract_pareto_plans → keep feasible
    PS->>RK: filter_plans(max_cost, max_water, min_yield, max_env)
    PS->>RK: rank_plans(preference) — TOPSIS, top 50
    PS->>RS: save_run_results(response, history, client_id)
    RS-->>PS: run_id + 4 file paths
    PS-->>API: dict → FarmPlanResponse
    API-->>UI: 200 JSON (≈33 KB)
```

Errors: `ValueError` anywhere in stages 1–4 (unknown location, no data for the year/season, <2 candidate crops) → HTTP 400. Pydantic → 422.

## 4. Frontend architecture

```mermaid
flowchart TB
    main[main.jsx] --> App
    App[App.jsx<br/>currentView state machine<br/>user in localStorage]
    App -->|no shell| Onb[OnboardingView]
    App -->|no shell| Auth[AuthView]
    App -->|no shell| Prof[ProfileSetupView]
    App -->|shell: sidebar / topbar / mobile drawer| Shell
    Shell --> Dash[DashboardView]
    Shell --> Ana[AnalyticsView]
    Shell --> Cmp[ComparisonView]
    Shell --> Run[RunOptimizationView]
    Shell --> Hist[HistoryView]
    Shell --> Rep[ReportsView]
    Shell --> Set[SettingsView]
    Dash & Ana & Cmp & Run & Hist & Rep & Set & Auth & Prof --> api[services/api.js]
    Ana & Cmp & Rep --> dl[utils/download.js]
    api -->|fetch| BE[(FastAPI)]
```

* **No router library.** Navigation is `setCurrentView(id)`; the current view name is persisted to `localStorage['agro_currentView']`, so a reload returns to the same page but browser Back/Forward and deep links do not work.
* **No global store.** `App` owns `user`, `currentView`, layout and language; each view fetches its own data in `useEffect` with a `cancelled` flag to ignore late responses.
* **Guard:** any shell view without a valid district on file bounces to profile setup/onboarding.

## 5. Data at rest

| Store | Where | Content | Lifetime |
|---|---|---|---|
| CSV dataset | Docker image `/app/data/raw` | 761 rows over 16 files | Immutable per deploy |
| Loader cache | Process memory (`lru_cache`) | 4 concatenated DataFrames | Process lifetime |
| Dashboard front cache | Process memory (`lru_cache(32)`) | Pareto fronts per (district, season, year, land, budget, history flag) | Process lifetime |
| Saved runs | `/app/results` (Fly volume) | `<run_id>.json` (+ CSV, convergence CSV/PNG) | Unbounded – never pruned |
| Run summary cache | Process memory | Parsed summaries keyed by file mtime/size | Process lifetime |
| User profile | Browser `localStorage['agro_user']` | name, phone, email, district, land size, crop, avatar (data-URL) | Until logout / site-data clear |
| Demo credential | `localStorage['agro_register_password_sha256']` | SHA-256 of password | Same |
| Client id | `localStorage['agro_client_id']` | random UUID, scopes History | Same |

## 6. Deployment topology

| Component | Platform | Config file | Notes |
|---|---|---|---|
| Frontend | Vercel (project `agrooptimize`) | `vercel.json`, `.env.production` | Static build; `VITE_API_BASE` baked in at build time |
| Backend | Fly.io app `agrooptimize-backend` | `fly.toml`, `Dockerfile` | `min_machines_running = 1`, health check `GET /health` every 15 s, `CORS_ALLOW_ORIGINS=https://agrooptimize.vercel.app` |
| Backend (alt.) | Render.com | `render.yaml` | Free plan, no persistent disk → saved runs lost on restart |
| CI | GitHub Actions | `.github/workflows/deploy-backend.yml` | On push to `main` touching `agrooptimize-backend/**`: `pytest` job, then `flyctl deploy` (deploy now `needs: test`) |

## 7. Concurrency model

Uvicorn runs one worker process. FastAPI runs the synchronous route handlers in a thread pool (default 40 threads). All optimisation runs go through `nsga2_runner._NSGA2_RUN_LOCK`, so at most **one NSGA-II run executes at a time**; others queue. This is required for correctness because the custom operators use NumPy's global RNG (see [PERFORMANCE_REVIEW.md](PERFORMANCE_REVIEW.md) §2 and [CHANGELOG.md](CHANGELOG.md)). Horizontal scaling = more Fly machines (each with its own lock and caches); saved runs would then need shared storage, because a Fly volume attaches to one machine.

## 8. Architectural decisions and trade-offs

| Decision | Rationale | Cost / risk |
|---|---|---|
| Files instead of a database | Explicit project requirement: runs must be inspectable, attachable to reports, versionable | No querying, no multi-machine sharing, no retention policy |
| No server-side accounts; `client_id` scoping | Scope of a final-year project | Not a security boundary (anyone who knows a `client_id` sees that history) |
| pymoo for NSGA-II mechanics, custom operators | Correct non-dominated sort/crowding from a vetted library; operators match the paper's text | Custom operators use the global NumPy RNG → needs the lock |
| scikit-fuzzy `ControlSystem` | Readable Mamdani rule syntax | ~600 ms first-call build; per-call simulation object allocation |
| Two orchestration paths (`plan_service` vs `dashboard_service`) | Dashboard needs 100 plans and no persistence without altering the tested path | Duplicated pipeline wiring (TD-4) |
| State-machine navigation instead of react-router | Simplicity | No URLs per page, no Back button, no deep links |
