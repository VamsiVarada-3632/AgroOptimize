# AgroOptimize -- Backend

A fuzzy-evolutionary decision support system for agricultural farming under
uncertainty. Implements the methodology from *"A fuzzy-evolutionary decision
support system for agricultural farming under uncertainties"* (23CSE498
Project Phase II) as a working Python/FastAPI backend: Mamdani fuzzy
inference for climate/soil uncertainty, feeding a custom NSGA-II
multi-objective optimiser (yield, cost, water, environmental impact) over
real Tamil Nadu district agricultural data -- with every run's Pareto front
and generation-by-generation convergence history persisted to disk.

This is the **backend only**. A frontend will be built separately once the
UI is finalised; this API is designed to be consumed by it (or by Swagger UI
/ the CLI demo in the meantime).

## Quick start

```bash
cd agrooptimize-backend
pip install -r requirements.txt      # add --break-system-packages on some Linux setups

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
├── data/raw/                    # the 16 dataset CSVs (4 regions x 4 kinds)
├── results/                     # every run's saved output (JSON/CSV/PNG) -- created on first run
├── tests/test_pipeline.py       # 34 tests covering every module + the API + persistence
├── notes/
│   ├── methodology_notes.md     # full write-up: what each stage does & why
│   └── viva_prep.md             # Q&A style reference for reviews / viva
└── run_demo.py                  # CLI demo, no server required
```

## Pipeline (matches the paper's Section III, plus persistence)

1. **Data collection & preprocessing** (`app/data/`) -- loads soil, rainfall,
   crop-history and water-availability CSVs for Coimbatore, Erode, Salem and
   Pollachi (2020-2023); aggregates them into a `RegionSeasonProfile` for a
   given location/year/season.
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

## Status vs. the paper / current review

Done: data pipeline, fuzzy engine, NSGA-II optimiser (custom operators
matching the paper's parameters) with per-generation convergence/hypervolume
tracking, TOPSIS decision ranking, file-based results persistence, REST API
(6 endpoints), automated tests (34, all green). Not yet done: frontend
(deliberately deferred until the UI is finalised), auth, and calibration of
the economic/carbon assumption constants against real quotes (see
`app/config.py` and `notes/methodology_notes.md` for what's assumed vs.
dataset-derived).
