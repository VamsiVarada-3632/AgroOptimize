# AgroOptimize -- Backend

A fuzzy-evolutionary decision support system for agricultural farming under
uncertainty. Implements the methodology from *"A fuzzy-evolutionary decision
support system for agricultural farming under uncertainties"* (23CSE498
Project Phase II) as a working Python/FastAPI backend: Mamdani fuzzy
inference for climate/soil uncertainty, feeding a custom NSGA-II
multi-objective optimiser (yield, cost, water, environmental impact) over
real Tamil Nadu district agricultural data -- with every run's Pareto front
and generation-by-generation convergence history persisted to disk.

The React/Vite frontend lives in `frontend/`. The API serves its production
build (one deployment); `npm run dev` in `frontend/` runs it against a local
API. It takes every district, season, crop and model from the API and shows
"Official Data Not Available" where the official datasets have no value
(see "Frontend" below).

## Quick start

```bash
cd agrooptimize-backend
pip install -r requirements-dev.txt  # runtime + test tools; add --break-system-packages on some Linux setups

# Build the official-data database (data/official/official_v1.db) from data/official/raw/
python3 scripts/preprocess_all.py

# Option A: CLI demo, no server needed -- also saves results/ files
python3 run_demo.py --location Coimbatore --season Kharif --land 5 --budget 200000

# Option B: run the API + interactive Swagger docs
uvicorn app.main:app --reload --port 8000
# then open http://127.0.0.1:8000/docs

# Run the test suite
pytest -v
```

## Project layout

```
agrooptimize-backend/
├── app/
│   ├── config.py              # all tunable constants + documented assumptions
│   ├── schemas.py              # Pydantic request/response models
│   ├── main.py                 # FastAPI app & routes
│   ├── data/
│   │   ├── loader.py            # raw CSV loading (cached)
│   │   └── preprocessing.py     # Stage 1-2: build a RegionSeasonProfile
│   ├── fuzzy/
│   │   └── engine.py            # Stage 2: Mamdani fuzzy inference engine
│   ├── optimization/
│   │   ├── operators.py         # custom single-point crossover / Gaussian mutation / repair
│   │   ├── problem.py           # Stage 3: FarmPlanProblem (4 objectives)
│   │   └── nsga2_runner.py      # runs NSGA-II, tracks convergence/hypervolume, decodes the Pareto front
│   ├── decision/
│   │   └── ranking.py           # Stage 4: TOPSIS ranking, filters, trade-off text
│   └── services/
│       ├── plan_service.py      # orchestrates every stage end to end
│       └── results_store.py     # Stage 5: persists each run to results/
├── data/official/raw/           # official government datasets (the database is rebuilt from these)
├── legacy/                      # archived synthetic v1 data and loader (tag published-v1)
├── results/                     # every run's saved output (JSON/CSV/PNG) -- created on first run
├── tests/                       # pytest suite (pipeline, API, datasets, fuzzy, NSGA-II, TOPSIS, ...)
├── notes/
│   ├── methodology_notes.md     # full write-up: what each stage does & why
│   └── viva_prep.md             # Q&A style reference for reviews / viva
└── run_demo.py                  # CLI demo, no server required
```

## Pipeline (matches the paper's Section III, plus persistence)

1. **Data collection & preprocessing** (`app/data/`) -- reads the official
   datasets (TN Season & Crop Report 2024-25, IMD rainfall, WRD reservoir
   levels, groundwater, Soil Health Card, CACP MSP/cost, TNAU doses) for the
   38 Tamil Nadu districts and aggregates them into a `RegionSeasonProfile`
   for a given district and season (Kharif/Rabi). See
   `docs/handbook/DATASETS.md`.
2. **Fuzzy uncertainty modelling** (`app/fuzzy/`) -- triangular membership
   functions + a Mamdani rule base turn rainfall deviation, water storage
   and soil fertility into two scenario weights: `yield_confidence` and
   `irrigation_risk`.
3. **Multi-objective optimisation** (`app/optimization/`) -- NSGA-II (custom
   single-point crossover p=0.85, Gaussian mutation p=0.12, 200 generations,
   matching the paper) evolves land-allocation / irrigation / fertilizer
   decisions across candidate crops, optimising 4 objectives at once: yield
   (maximise), cost, water use, environmental impact (all minimise). Tracks
   a per-generation hypervolume indicator as evidence of convergence.
4. **Decision output** (`app/decision/`) -- ranks the resulting Pareto front
   with TOPSIS, applies optional preference filters (budget, max water,
   etc.), and attaches a plain-language trade-off summary to every plan.
5. **Results persistence** (`app/services/results_store.py`) -- every run
   is written to `results/<run_id>.json` (full record + convergence
   history), `<run_id>_plans.csv` (ranked plan table), and
   `<run_id>_convergence.{csv,png}` (generation-by-generation stats and
   chart). Can be disabled per-request (`save_results: false`).

## API

| Method | Path                     | What it does                                                |
|--------|--------------------------|---------------------------------------------------------------|
| GET    | `/health`                 | liveness check                                                |
| GET    | `/api/catalog`            | locations / years / seasons / crops available                 |
| GET    | `/api/region-profile`     | preprocessing + fuzzy stages only (fast, for inspection)      |
| POST   | `/api/farm-plans`         | full pipeline -> ranked Pareto-optimal farm plans (saves to disk by default) |
| GET    | `/api/results`            | list every run saved to `results/` so far                     |
| GET    | `/api/results/{run_id}`   | full saved record for one past run, incl. convergence history |

Full request/response schemas are in `app/schemas.py` and browsable live at
`/docs` once the server is running.

## Frontend

```bash
cd frontend
npm install
npm run dev                  # http://localhost:5173, expects the API on :8000
npm run lint && npm run build && npm test
```

Pages: Home, Analytics, Comparison, Run Optimization, District Intelligence,
Scenario Simulation, History, Reports, Official Data, Settings. Details:
`docs/handbook/FRONTEND.md`, `docs/handbook/FRONTEND_API_INTEGRATION.md`,
`docs/data_architecture/FRONTEND_MIGRATION_REPORT.md`.

## Status vs. the paper / current review

Done: data pipeline, fuzzy engine, NSGA-II optimiser (custom operators
matching the paper's parameters) with per-generation convergence/hypervolume
tracking, TOPSIS decision ranking, file-based results persistence, REST API
(see `docs/handbook/API_REFERENCE.md`), automated tests (backend pytest,
frontend Vitest), React frontend on the official data. Not yet done: auth, and calibration of
the economic/carbon assumption constants against real quotes (see
`app/config.py` and `notes/methodology_notes.md` for what's assumed vs.
dataset-derived).
