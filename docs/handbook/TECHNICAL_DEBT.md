# Technical Debt Register

Interest = ongoing cost of not fixing. Effort: S (<½ day), M (1–3 days), L (>3 days).

| ID | Debt | Location | Interest | Effort |
|---|---|---|---|---|
| TD-1 | Custom GA operators use NumPy's global RNG → all optimisation serialised behind `_NSGA2_RUN_LOCK` | `optimization/operators.py`, `nsga2_runner.py` | Head-of-line blocking; hidden coupling | M (changes outputs → re-baseline results) |
| TD-2 | Two copies of the frontend (repo `frontend/` and local `stitch_agrooptimize_app/`) | `stitch_agrooptimize_app/`, `frontend/` | Edits made in the wrong copy are lost; risk of confusion about which UI is deployed | S |
| TD-3 | Two dataset copies with different content | `datasets/`, `data/raw/` | Wrong file edited; unreproducible results | S |
| TD-4 | Pipeline wiring duplicated (plan_service vs dashboard_service) | services | Divergent behaviour (pop 80 vs 100, filters, persistence) | M |
| TD-5 | `dashboard_service.py` is a 770-line grab-bag | services | Hard to test/change | M |
| TD-6 | No lock file for Python; test tools in production image | requirements.txt, Dockerfile | Non-reproducible builds, larger image | S |
| TD-7 | Eight endpoints return untyped dicts (no `response_model`) | main.py | No schema in OpenAPI; silent contract drift with the UI | M |
| TD-8 | State-machine navigation instead of a router | App.jsx | No deep links/back button; App grows with each page | M |
| TD-9 | Duplicated UI constants and thresholds (fallback crops, soil 70/45, water 70/40, seasons) | views | Inconsistent labels when one copy changes | S |
| TD-10 | Hard-coded 5 ha and current season for Analytics/Comparison | api.js callers, dashboard_service | Results not personalised | S |
| TD-11 | File-based persistence without retention, indexing or multi-machine support | results_store | Disk growth; O(n) scans; blocks horizontal scaling | L |
| TD-12 | Stale team documentation and notes | agrooptimize-backend/README.md, docs/, notes/ | Wrong answers in viva/report | S (point to /docs) |
| TD-13 | External runtime assets (logo, images, favicon, icon font) | index.html, views | Broken UI if URLs expire / fonts blocked | S |
| TD-14 | `.env.example` documents variables nothing reads | backend | Misleading operators | S |
| TD-15 | Simulated progress timing in RunOptimizationView | frontend | 5.7 s artificial wait | S |
| TD-16 | No frontend tests; no e2e tests | frontend | Regressions found manually | M |
| TD-17 | Model debt: inert multipliers, tonnage objective, yield-only fuzzy coupling, redundant rules | problem.py, engine.py | Research validity | L |
| TD-18 | Hypervolume normalised per run | nsga2_runner | Incomparable convergence numbers | S |
| TD-19 | Deprecated response fields kept for compatibility (`plots`, `is_fallback`, `is_estimated`) | dashboard_service | Payload noise | S (after a frontend release) |
| TD-20 | CI workflow path assumes a monorepo layout that does not match local repos | .github/workflows | Deploys may never trigger | S |
