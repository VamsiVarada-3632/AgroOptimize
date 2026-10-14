# Project Review (senior engineering)

## 1. Scorecard

| Dimension | Rating | Comment |
|---|---|---|
| Architecture | Good | Clear layers (data → fuzzy → optimisation → decision → services → HTTP), acyclic imports, pure functions, single config module |
| Code quality | Good | Readable, heavily commented with rationale; some very long comments and one 750-line service module |
| Correctness | Fair → Good | Two real concurrency/integrity bugs found and fixed (RNG race, run-id collision); model-level defects remain (see RESEARCH_REVIEW) |
| Testing | Good backend / none frontend | 205 backend tests incl. invariants and concurrency; no golden-master; no UI tests |
| Documentation | Good but stale | Extensive team docs, several now out of date; this docs set supersedes them |
| Security | Acceptable for a demo | Key data-exposure bug fixed; no auth by design |
| Performance | Good | Sub-second optimisation; memoisation added |
| Operability | Fair | Health check, CI (now test-gated), Docker; no structured logging/metrics; unbounded storage |
| Repository hygiene | Fair | Frontend is versioned in the repo's `frontend/`, but a second, unversioned working copy (`stitch_agrooptimize_app/`) and a local checkout that had fallen 6 commits behind GitHub make it easy to edit the wrong copy; divergent dataset copy; zip snapshot |
| Data integrity | **Poor** | See DATA_VALIDATION |

## 2. Code review findings

### Dead / unused
| Item | Where | Action |
|---|---|---|
| `ShaderBackground.jsx`, `src/assets/*`, `_to_delete/`, empty `src/data/` | frontend | **Removed** (backed up) |
| `is_fallback` UI branch | AnalyticsView | **Removed** (backend always false) |
| `weatherFailed` state, `selectedLanguage` prop in AuthView | frontend | **Removed** |
| `loader.available_locations/years/seasons` | backend | used only by tests – keep or move to tests |
| `WATER_COST_RS_PER_MM_PER_HA` | config | documented as intentionally unwired |
| `CropCandidate.msp_rs_qtl`, 26 CSV columns never read | data | keep; candidates for a profit objective |
| `_PLOT_LABELS` / `allocations[].plots` | dashboard_service | marked deprecated; UI no longer renders |
| `is_estimated` in history rows, `is_fallback` in plans | API | always false; kept for compatibility |
| `stitch_agrooptimize_app/` | local disk | duplicate working copy of the repo's `frontend/` – work only in the repo (TODO T-7) |
| `public/favicon.svg`, `public/icons.svg` | frontend | Vite scaffold, unused |

### Duplication
* Pipeline wiring duplicated in `plan_service.generate_farm_plans` and `dashboard_service._cached_pareto_front` (profile → fuzzy → problem → run → feasible).
* Fertility-index call with the same five kwargs in 3 places; "current land row" logic in 2.
* `FALLBACK_CROPS` list copied into AuthView, ProfileSetupView, SettingsView; soil-status thresholds (70/45) in backend and AnalyticsView; `SEASONS` in api.js and ProfileSetupView; district dropdown markup in 3 views.
* Error banners/empty states repeated per view (now at least share one message constant).

### Naming / clarity
* `env_impact_score` vs radar "land" vs UI "Land Impact" – three names for one thing.
* `estimated_yield` (dashboard) is a district average, not an estimate for the user.
* `water_utilization_pct` is irrigation's share of demand.
* `get_region_profile` in `main.py` vs `RegionProfileOut` schema not used as its response model.
* `FarmPlanRequest.save_results` also controls history tracking (documented but surprising).

### Large units
* `dashboard_service.py` (≈770 lines) mixes weather, KPIs, history, optimisation caching, comparison and radar scoring → split into `weather.py`, `dashboard.py`, `history.py`, `analytics.py`.
* `AuthView.jsx` (≈700 lines) holds four sub-screens; `AnalyticsView.jsx` (≈600) mixes fetching, maths and SVG.

### Magic numbers
Catalogued with provenance in [CONFIGURATION.md](CONFIGURATION.md) §3. The worst offenders are UI-meaning thresholds that are duplicated (70/45 soil, 70/40 water) and the fixed 5 ha used by Analytics/Comparison.

### Error handling
* `get_plans` wraps everything in `except Exception` → bad season/year becomes 503 instead of 400.
* Weather fallback swallows all exceptions (intentional, now logged via `logging`).
* No global exception handler / request-id logging.

## 3. Testing gaps
1. No golden-master test pinning numeric outputs – model changes can drift silently (the fingerprint script used in this audit is a template: TODO T-13).
2. Operators not unit-tested in isolation.
3. Weather tests depend on network availability (they pass either way, but the "live" branch isn't deterministic).
4. No frontend tests (Vitest + React Testing Library for `api.js`, `download.js`, and view rendering with mocked fetch).
5. No end-to-end test (Playwright: register → run → history → report).

## 4. Documentation gaps (now addressed by `/docs`)
Stale statements in team docs: 34 tests (now 205), 14 rules (26), fertiliser ₹6.5/27/17 and wage ₹400 (now 12.87/58.70/56.67 and 319), "frontend not built", "2020–2023 only", `docs/frontend_integration.md` referenced but missing, results tables from an older dataset.

## 5. Top 10 recommendations
1. Put `stitch_agrooptimize_app/` under git (same repo as the backend or a monorepo) and delete the stale `agrooptimize-backend/frontend/`.
2. Settle data provenance; default to the latest observed year.
3. Fix the inert multipliers with agronomic response functions.
4. Replace tonnage with a profit objective.
5. Add a golden-master regression test and multi-seed evaluation script.
6. Remove the RNG lock by threading pymoo's `random_state` through the operators.
7. Split `dashboard_service.py`; unify the two orchestration paths.
8. Add react-router, accessibility fixes, and pass user land size to Analytics/Comparison.
9. Rate-limit and add a retention policy for `results/`.
10. Refresh the team's viva/methodology notes against these docs.
