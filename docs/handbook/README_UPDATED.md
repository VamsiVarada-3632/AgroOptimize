# AgroOptimize

**A fuzzy-evolutionary decision-support system for crop planning under uncertainty** – the 38 Tamil Nadu districts with official crop statistics, a Mamdani fuzzy model of rainfall/water/soil conditions, NSGA-II multi-objective optimisation of land allocation and input intensity (yield, cultivation cost, irrigated area, nutrient load), and TOPSIS ranking of the resulting Pareto-optimal plans – delivered as a FastAPI backend and a React web app.

Team 52, Amrita Vishwa Vidyapeetham (23CSE498 Project Phase II) · Guide: Dr. G. Jeyakumar
VVS Vamsi · Vennela Harshini · Garudammagari Sreenithya · Gaddam Jahnavi

> **Data notice.** Since 2026-11 the runtime uses official government datasets only (TN Season & Crop Report 2024-25, IMD rainfall, WRD reservoir levels, groundwater, Soil Health Card, CACP MSP and cost, TNAU doses); features without an official dataset are disabled (HTTP 501), never estimated. The synthetic v1 data used for the published paper is archived in `legacy/` (tag `published-v1`). See [DATASETS.md](DATASETS.md) and [MIGRATION_REPORT.md](../data_architecture/MIGRATION_REPORT.md).

## Features
- Region profile per district/season: Soil Health Card fertility index, seasonal rainfall deviation from the IMD normal, reservoir storage, candidate crops with official sources and the reasons other crops are excluded.
- Mamdani fuzzy inference (3 inputs, 2 outputs, 26 rules) → yield confidence and irrigation risk, applied per crop by rainfall dependency.
- NSGA-II (pymoo) with the paper's single-point crossover (p = 0.85) and Gaussian mutation (p = 0.12), 200 generations, optional budget constraint, hypervolume convergence tracking; deterministic for a given seed.
- TOPSIS ranking under five preferences; plain-language trade-off summaries; hard-limit filters.
- Web app: dashboard (KPIs; the weather widget is disabled until an official IMD feed is loaded), Pareto-front analytics with live filters and CSV export, three-plan comparison with radar chart, personalised runs with history and downloadable reports.
- Every saved run persisted as JSON + CSV + convergence chart.
- District Intelligence Center: one page per district with climate, soil, water, crop history, crop suitability, historical prices and generated insights ([DISTRICT_INTELLIGENCE.md](DISTRICT_INTELLIGENCE.md)).
- Scenario Simulation: change rainfall, water, input costs, prices, land, budget or priorities and see how — and why — the optimised recommendation changes, with statistically tested impacts ([SCENARIO_SIMULATION.md](SCENARIO_SIMULATION.md)).
- Fuzzy system transparency: every fuzzy inference explained rule by rule (decisive vs masked rules, share and importance), plus a tested audit of the rule base and membership functions ([FUZZY_SYSTEM_ANALYSIS.md](FUZZY_SYSTEM_ANALYSIS.md)).
- Explainable recommendations: why a plan was chosen, trade-offs, constraint checks, risks, historical context and a decomposed confidence score – all derived from the pipeline's own numbers ([EXPLAINABILITY.md](EXPLAINABILITY.md)).

## Repository layout
```
final_year_project/
├── agrooptimize-backend/     FastAPI + pipeline (git repo)
│   ├── app/                  config, schemas, main, data/, fuzzy/, optimization/, decision/, services/
│   ├── data/official/raw/    official datasets (database rebuilt by scripts/preprocess_all.py)
│   ├── legacy/               archived synthetic v1 data and loader
│   ├── tests/                pytest suite
│   └── run_demo.py           CLI demo
├── stitch_agrooptimize_app/  React 19 + Vite 8 + Tailwind 4 frontend
├── docs/                     full documentation (start with PROJECT_KNOWLEDGE.md)
└── .github/workflows/        test + deploy backend to Fly.io
```

## Quick start

Backend
```bash
cd agrooptimize-backend
python3 -m pip install -r requirements.txt
python3 scripts/preprocess_all.py                # builds data/official/official_v1.db
uvicorn app.main:app --reload --port 8000        # API docs: http://localhost:8000/docs
python3 run_demo.py --location Salem --season Rabi --land 5 --budget 250000
python3 -m pytest -q
```

Frontend tests: `cd frontend && npm test`.

Frontend
```bash
cd stitch_agrooptimize_app
npm install
npm run dev                                      # http://localhost:5173 (expects the API on :8000)
# another API: VITE_API_BASE=http://localhost:8010 npm run dev
npm run lint && npm run build
```

## How it works
```mermaid
flowchart LR
    CSV[(Official database)] --> P[Region profile]
    P --> F[Mamdani fuzzy<br/>yield confidence · irrigation risk]
    F --> N[NSGA-II<br/>yield · cost · irrigated area · nutrient load]
    P --> N
    N --> T[TOPSIS ranking]
    T --> UI[Dashboard · Analytics · Comparison · Reports]
    T --> R[(results/)]
```
Details: [ALGORITHMS.md](ALGORITHMS.md), [OPTIMIZATION_PIPELINE.md](OPTIMIZATION_PIPELINE.md).

## API at a glance
`GET /health` · `GET /api/catalog` · `GET /api/datasets` · `GET /api/soil-master[/{district}]` · `GET /api/region-profile` · `POST /api/farm-plans` · `GET /api/results` · `GET /api/results/{run_id}` · `GET /api/dashboard|history|soil-profile|plans|comparison|compare-fuzzy/{district}`; `GET /api/weather/{district}` returns 501 (disabled) – see [API_REFERENCE.md](API_REFERENCE.md).

## Deployment
Frontend on Vercel (`vercel.json`, `VITE_API_BASE` in `.env.production`); backend on Fly.io (`fly.toml`, Docker, volume for `results/`); GitHub Actions runs the tests, then deploys. See [ARCHITECTURE.md](ARCHITECTURE.md) §6.

## Known limitations
Irrigation/fertiliser multipliers currently have no yield benefit (optimiser keeps them at the minimum); the yield objective sums tonnes across crops; fuzzy output affects only expected yield; district-level data for one report year (2024-25), two seasons, no taluk data; features without an official dataset are disabled ([MIGRATION_REPORT.md](../data_architecture/MIGRATION_REPORT.md) §3); demo-only client-side authentication. Full list and roadmap: [RESEARCH_REVIEW.md](RESEARCH_REVIEW.md), [TODO.md](TODO.md).

## Documentation index
[PROJECT_KNOWLEDGE](PROJECT_KNOWLEDGE.md) · [ARCHITECTURE](ARCHITECTURE.md) · [FOLDER_STRUCTURE](FOLDER_STRUCTURE.md) · [FRONTEND](FRONTEND.md) · [BACKEND](BACKEND.md) · [DATASETS](DATASETS.md) · [ALGORITHMS](ALGORITHMS.md) · [API_REFERENCE](API_REFERENCE.md) · [DATA_FLOW](DATA_FLOW.md) · [USER_FLOW](USER_FLOW.md) · [OPTIMIZATION_PIPELINE](OPTIMIZATION_PIPELINE.md) · [REPORT_PIPELINE](REPORT_PIPELINE.md) · [HISTORY_PIPELINE](HISTORY_PIPELINE.md) · [SCORING_AND_RANKING](SCORING_AND_RANKING.md) · [CONFIGURATION](CONFIGURATION.md) · [DEPENDENCIES](DEPENDENCIES.md) · [PROJECT_REVIEW](PROJECT_REVIEW.md) · [DATA_VALIDATION](DATA_VALIDATION.md) · [PERFORMANCE_REVIEW](PERFORMANCE_REVIEW.md) · [SECURITY_REVIEW](SECURITY_REVIEW.md) · [UI_UX_REVIEW](UI_UX_REVIEW.md) · [RESEARCH_REVIEW](RESEARCH_REVIEW.md) · [TECHNICAL_DEBT](TECHNICAL_DEBT.md) · [IMPROVEMENT_LOG](IMPROVEMENT_LOG.md) · [CHANGELOG](CHANGELOG.md) · [TODO](TODO.md) · [EXPLAINABILITY](EXPLAINABILITY.md) · [DISTRICT_INTELLIGENCE](DISTRICT_INTELLIGENCE.md) · [SCENARIO_SIMULATION](SCENARIO_SIMULATION.md) · [FUZZY_SYSTEM_ANALYSIS](FUZZY_SYSTEM_ANALYSIS.md) · [FUZZY_EXPLAINABILITY](FUZZY_EXPLAINABILITY.md) · [FUZZY_RESEARCH_REVIEW](FUZZY_RESEARCH_REVIEW.md) · [FUZZY_IMPROVEMENT_SUMMARY](FUZZY_IMPROVEMENT_SUMMARY.md) · [FUZZY_MODEL_IMPROVEMENTS](FUZZY_MODEL_IMPROVEMENTS.md) · [FUZZY_BENCHMARK_RESULTS](FUZZY_BENCHMARK_RESULTS.md) · [NSGAII_ANALYSIS](NSGAII_ANALYSIS.md) · [NSGAII_PROFILE](NSGAII_PROFILE.md) · [NSGAII_RESEARCH_REVIEW](NSGAII_RESEARCH_REVIEW.md) · [NSGAII_IMPROVEMENT_SUMMARY](NSGAII_IMPROVEMENT_SUMMARY.md) · [OFFICIAL_DATA_PERFORMANCE](OFFICIAL_DATA_PERFORMANCE.md)

Official-data migration: [MIGRATION_REPORT](../data_architecture/MIGRATION_REPORT.md) · [MIGRATION_PLAN](../data_architecture/MIGRATION_PLAN.md) · [OFFICIAL_DATASET_MAPPING](../data_architecture/OFFICIAL_DATASET_MAPPING.md) · [SYNTHETIC_DEPENDENCY_AUDIT](../data_architecture/SYNTHETIC_DEPENDENCY_AUDIT.md) · [SOIL_MASTER](../data_architecture/SOIL_MASTER.md) · [AGRONOMY_MASTER](../data_architecture/AGRONOMY_MASTER.md) · [CONVERSION_FACTORS](../data_architecture/CONVERSION_FACTORS.md) · [FINAL_CONVERSION_DECISION](../data_architecture/FINAL_CONVERSION_DECISION.md)

Documents not listed under the migration were written for the v1 synthetic data; each one that still describes v1 behaviour says so at the top.
