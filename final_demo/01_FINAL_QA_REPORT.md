# 01 – Final QA report (external-review audit)

Audit date: 14–16 November 2026. Code: `main` at `f0b9f5f` plus the three fixes on branch `qa/external-review-audit`. Environments: local server (macOS, Chrome) for the full functional and edge-case runs; production https://agrooptimize.onrender.com for the demo cases and performance. No algorithm, dataset, API or schema was changed.

## Summary

| Area | Checks | Result |
|---|---|---|
| Backend API: every endpoint, all 38 districts × 2 seasons, edge cases, profiles | 545 | 543 as expected; the 2 others were test assumptions, both correct behaviour (below) |
| Frontend: 14 pages × 4 widths, every workflow, exports, edge cases | 85 | 83 pass; 2 explained below (one test artefact, one documented limitation) |
| Frontend unit tests | 100 | 100 pass (was 99; one test added for a fix) |
| Lint (oxlint) | – | 0 warnings |
| Bugs found / fixed | 3 / 3 | see "Issues fixed" |

## Part A – Backend (`qa_scripts/api_audit.py`, in-process)

| Test | Result |
|---|---|
| `/health`, `/openapi.json`, `/api/catalog`, `/api/datasets`, `/api/fuzzy/models`, `/api/topsis/profiles`, `/api/soil-master`, `/api/fuzzy/audit`, `/api/fuzzy/explain` | PASS |
| `POST /api/farm-plans` for all 38 districts × Kharif/Rabi (76 runs) | PASS – 72 produce plans; Chennai and The Nilgiris (both seasons) return 400 with the reason ("fewer than 2 crops with complete official data"). Fuzzy stage applied in 9 district-seasons (Rabi). Median 280 ms, max 664 ms per run. No NaN/Infinity in any response |
| `GET /api/region-profile` for all 76 | PASS (same 4 return 400) |
| Per district: dashboard, history, soil-profile, soil-master, district-intelligence, weather (501), plans, comparison | PASS for all 38 (Chennai/Nilgiris: plans 503 and comparison 404 with the reason) |
| Budget 0 / negative | PASS – 422 "must be greater than 0" |
| Budget below the cheapest plan (₹1,000) | PASS – 200 with 0 plans (frontend fix, Issue 2) |
| Very high budget (₹10¹²) | PASS – 50 plans |
| Land 0 | PASS – 422 |
| Land 0.01 ha / 100,000 ha / 10⁹ ha | PASS – plans returned (no upper limit on farm-plans; `/api/plans` caps at 100,000) |
| Missing land / missing location / empty location | PASS – 422 / 422 / 400 with the list of districts |
| Invalid district "Atlantis" | PASS – 400 with the list of districts |
| Taluk "Pollachi" | PASS – 400 "Pollachi is a taluk of Coimbatore…" |
| Invalid season "Summer" | PASS – 400 "Choose one of ['Kharif', 'Rabi']" |
| Lower-case "salem"/"rabi" | PASS |
| Year 2024 / 2019 / 3000 | PASS – 200 / 400 / 400 "Available years: [2024]" |
| Text in a number field | PASS – 422 |
| Unknown fuzzy model | PASS – 422 with the list of models |
| Custom weights not summing to 1 / without custom profile / profile + other preference | PASS – 422 each with a clear message |
| pop_size 7, n_gen 501, client_id 129 chars | PASS – 422 |
| Profiles balanced, profit, water, sustainability, low cost; preferences max_yield, min_cost, min_water, min_env_impact | PASS |
| Saved run, result, results list, explanation rank 1 / 9999 / 0 | PASS – 200 / 400 / 422 |
| Re-rank 5 profiles, custom, bad custom, unknown profile | PASS – 200 ×6 / 422 / 422 |
| Unknown run id, unknown district (dashboard, soil-master, district-intelligence) | PASS – 404 |
| Comparison explanation plan C / plan Z | PASS – 200 / 422 |
| compare-fuzzy Salem Rabi and Kharif | PASS |
| fuzzy-explain NaN input / unknown model | PASS – 422 / 400 |
| Simulation run, invalid rainfall (−45 %), unknown district, infeasible budget | PASS – 200 / 422 / 422 / handled |
| Simulation fertiliser lever | PASS – 501 (feature disabled: no official fertiliser prices). My test expected 422; 501 is the documented behaviour |
| Simulation save / save from another browser / list / get / get from another browser / delete / delete again | PASS – 201 / 404 / 200 / 200 / 404 / 200 / 404 |
| `/api/results/../../etc` | PASS – the path is normalised to `/etc`, which is served the web app; no file access. My test expected 404 |
| Unknown `/api/nope` | PASS – 404 |
| Crop evidence | PASS – 10 criteria per crop: rainfall, soil, water, budget, fertiliser, market price, MSP, duration, yield, risks |

## Part B – Frontend (`qa_scripts/ui_flows.py`, Chrome, dev build so React warnings are visible)

### Page sweep – onboarding, login, register, profile setup and all 10 app pages at desktop 1440, laptop 1280, tablet 820, mobile 390 px

| Check | Result |
|---|---|
| Horizontal overflow on any page/width | PASS – none |
| Raw `undefined` / `NaN` / `null` / `ML/ha` / `[object Object]` text | PASS – none |
| Broken images | PASS – none |
| Icon font loaded (no icon names shown as words) | PASS at all 4 widths |
| Mobile menu drawer opens and navigates | PASS |
| Console errors / React warnings | PASS – none from the app; the only console lines are the browser's "failed to load resource" entries for the deliberate error tests (Chennai's 404/503 answers, aborted and offline requests) |
| Uncaught page errors | PASS – none |

### Workflows

| Workflow | Result |
|---|---|
| Register: password under 8 characters blocked | PASS |
| Register step 2: 38 districts and crops from the catalog (no fallback list) | PASS |
| Register → OTP (auto-fill) → profile setup with the district kept | PASS (by design the season is chosen in profile setup) |
| Login with a wrong password shows an error | PASS |
| Stored v1 district (Pollachi) sends the user back to profile setup | PASS |
| Profile setup offers Kharif and Rabi only | PASS |
| Run Optimization: 6 fuzzy models from the API, official preselected | PASS |
| Double-click on Run Optimization sends one request | PASS |
| Result: official model, top plan, TOPSIS panel | PASS |
| Re-rank: profit, water saving, sustainability, low cost, custom | PASS |
| Reasoning tab, compare profiles tab | PASS |
| Explanation: 10 crop-evidence criteria; market price "Official Data Not Available"; Escape closes | PASS |
| History: run with Official-Data Model / Official Data badges; details; explain; search empty state | PASS |
| Reports: generate, download (irrigated area, crop evidence, no NaN), copy summary to clipboard | PASS |
| Comparison: table, CSV export, Explain Plan B, compare explanations, adjust weights | PASS |
| Analytics: scatter, fuzzy table, CSV export, sliders | PASS |
| District Intelligence: Salem, Erode, Coimbatore, Thanjavur, Madurai, Tiruchirappalli, Namakkal, Viluppuram, Chennai, The Nilgiris – summary + Soil Health Card, no raw nulls | PASS |
| District Intelligence: text report, CSV, JSON exports; compare districts; "Run optimization" preselects the district | PASS |
| Scenario Simulation: fertiliser lever shown as unavailable; run (double-click → one request); irrigated-area units; save; HTML and JSON export; reopen; delete | PASS (save fixed, Issue 1) |
| Official Data page: registry 39,065 rows, disabled features, Pollachi note | PASS |
| Settings: change district → dashboard uses it | PASS |
| Budget below the cheapest plan | PASS (fixed, Issue 2) |
| Chennai profile on all 10 pages: no raw nulls, no false "server unreachable" | PASS (fixed, Issue 3) |
| Browser refresh keeps the current page | PASS |
| Browser back button | Known limitation – the app has no URL routing, so Back leaves the app; opening it again restores the last page |
| API unavailable (requests aborted): dashboard and District Intelligence show "Couldn't reach…", no crash | PASS |
| Slow backend | Run Optimization shows its progress screen and the result arrives (verified separately; the automated 20 s delay test blocked the test browser itself, a test artefact) |
| Network offline on a page already opened: "Couldn't reach…" | PASS |
| Network offline on a page never opened | Known limitation – its code cannot be downloaded, the app reloads once and Chrome shows its offline page; the app works again when the connection returns |

## Part C – Performance (production, measured 16 Nov 2026 from the test machine)

| Measure | Value |
|---|---|
| First page load (TTFB / DOMContentLoaded / load) | 177 / 404 / 405 ms, 77 kB transferred |
| Page ready after reload | 0.8–1.1 s for every page; Analytics 17.6 s (its fuzzy vs non-fuzzy table runs two live optimisations; the rest of the page shows within a second) |
| In-app page switch | 82–182 ms |
| JS heap | 3.4–13.6 MB |
| API latency (catalog, datasets, dashboard, District Intelligence 46 kB, soil master, plans, comparison) | 147–251 ms including network |
| One optimisation (`POST /api/farm-plans`) | 9.4–12.3 s on the free instance (280 ms median locally) |
| Scenario simulation (10 optimisations) | ≈70 s on the free instance (2.9 s locally) |
| Backend memory | peak RSS 233 MB (OFFICIAL_DATA_PERFORMANCE.md) |
| Largest dataset response | District Intelligence 46 kB; dataset load once per process ≈0.75 s |

## Issues fixed

| # | Bug | Fix | Commit author |
|---|---|---|---|
| 1 | Saving a scenario that changed several conditions (e.g. custom priorities) failed with HTTP 422: the suggested name was the 86-character title, the backend accepts 80 | suggested name shortened with an ellipsis; unit test added | Sreenithya Garudammagari |
| 2 | A budget below the cheapest plan showed "Optimization complete and saved" with only a ranking error, and Reports then claimed the server was unreachable | result says "No feasible plan found" with the budget and land; ranking, explanation and report actions hidden; Reports explains the run has no plan | jahnavi-25-cmd |
| 3 | For Chennai and The Nilgiris, Analytics said "Couldn't reach the server" although the server answered (503 with the no-data reason) | Analytics and Comparison show the backend's message for any HTTP error | Sreenithya Garudammagari |

## Screenshots required for the review

Production screenshots are in `docs/deployment/screenshots/` (12) and `final_ppt/screenshots/` (27). QA evidence in `final_demo/screenshots/`: `qa_edge_low_budget.png` (Issue 2 fixed), `qa_chennai_analytics.png` and `qa_chennai_comparison.png` (Issue 3), `qa_mobile_official_data.png` (mobile layout). After the fixes are deployed, retake `04_optimization_result.png` only if the slide shows a low-budget case.

## Remaining known limitations

See `04_COMMON_FAILURES.md`: one report year; district level; fuzzy stage only where official reservoir data exists (9 districts, Rabi); Chennai and The Nilgiris have no plans; missing datasets (IMD weather, mandi and fertiliser prices, crop calendars, cotton/rice conversion factors); platform-dependent NSGA-II results; free-hosting speed and the intermittent simulation timeout; back button leaves the app; offline on a never-opened page; no real authentication (demo, device-local accounts); the language switcher has no translations.
