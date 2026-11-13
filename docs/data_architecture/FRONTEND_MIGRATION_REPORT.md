# Frontend migration to the official-data backend

The React/Vite frontend (`frontend/`) now works only with the official-data backend. No backend file, response or field name was changed; the UI layout and flows are the same, plus one new page (Official Data). The problems found before the change are listed in [FRONTEND_AUDIT.md](FRONTEND_AUDIT.md).

## 1. How the frontend gets its data

| What the user picks or sees | Source |
|---|---|
| Districts (38), seasons (Kharif, Rabi), report years, crops | `GET /api/catalog`, loaded once per page load by `useCatalog()` (`src/services/officialData.js`) |
| Fuzzy models and the default (`official`) | `GET /api/fuzzy/models` (`useFuzzyModels()`) |
| Loaded datasets, rows, import time, sha256; disabled features | `GET /api/datasets` (`useDatasets()`) |
| Soil Health Card coverage and district record | `GET /api/soil-master`, `GET /api/soil-master/{district}` |
| Backend version, optimisation engine | `GET /openapi.json` (`info.version`, `RunMeta.algorithm` default) |
| Per-crop evidence | `crop_evidence` of `GET /api/results/{id}/explanation` and `GET /api/comparison/{district}/explanation` |
| Run badges (model, data) | `meta.fuzzy_model` and `region_profile.candidate_crops[].sources` of `GET /api/results/{id}` |

Nothing in `src/` lists a district, season, crop, reservoir, price, soil value or weather reading. The remaining constant lists are request options defined by the backend schema: `PREFERENCES` (`FarmPlanRequest.preference`), the ranking profiles and criteria used until `GET /api/topsis/profiles` answers, and the scenario levers (`SimulationRequest`).

**Missing data.** `showValue()` prints **Official Data Not Available** for null, undefined, empty text and NaN; `isOfficialDataUnavailable()` treats HTTP 400, 404 and 501 the same way and adds the backend's reason. A metric the optimiser could not compute says "Not computed for this run". Zero is shown as zero.

**Labels.** Field names stay as the backend sends them; `FIELD_LABELS` and `EVIDENCE_LABELS` give the words shown (`irrigated_ha` → Irrigated Area, `crop_evidence` → Why this crop was selected, `composite_score` → Overall Score, `hypervolume` → Optimization Quality, `igd` → Solution Accuracy, `igd_plus` → Improved Solution Accuracy, `electrical_conductivity` → Soil Salinity, …).

## 2. Pages updated

| Page | Change |
|---|---|
| App shell | Profile guard uses the catalog; new sidebar item **Official Data**; the content column no longer widens past the viewport (`min-w-0`). |
| Onboarding / Auth / Profile setup | District, season and crop dropdowns from the catalog; fallback crop list removed. |
| Home (dashboard) | Weather card shows "Official Data Not Available" with the reason from `disabled_features` (no 501 request); the four-district weather tab is gone; KPIs show the official text when a value is null; "Water Utilization" is labelled Irrigated Area with its percentage. |
| Analytics | Irrigated-area labels and CSV column; fuzzy comparison uses `min_irrigated_ha_per_ha`; a district without official data shows the backend reason; the "fuzzy not applied" case is stated. |
| Comparison | Irrigated-area labels; synthetic "Getting Started" calendar replaced by "Crop Calendar: Official Data Not Available"; responsive header and table. |
| Run Optimization | Catalog districts/seasons/years; fuzzy models from the API with the server default preselected (`official`, previously `original`). |
| Explanations (all entry points) | New collapsible **Why this crop was selected** section: per crop, ten criteria (Rainfall, Soil, Water, Budget, Fertilizer, Market Price, MSP, Duration, Yield, Risks), each with Status, Evidence, Official source and a plain-language meaning of the status; irrigated-area and nutrient-load labels. |
| District Intelligence | Catalog districts; new **Soil Health Card** section (pH, organic carbon, N, P, K, salinity, micronutrient deficiency); charts whose official values are all missing (temperature, water demand, groundwater status) say so; suitability shows the irrigated share instead of the empty water requirement. |
| Scenario Simulation | Catalog lists; irrigated-area units (the page showed 0.00 ML before); fertiliser-price lever disabled with the missing dataset named. |
| History | Badges **Original Model / Improved Model / Official-Data Model** and **Official Data / Legacy Data** on every run and in its detail dialog. |
| Reports | Irrigated area and nutrient load instead of litres and an unlabelled score; model and data line; a "Why each crop was selected" section with sources; null region fields printed as the official text. |
| Settings | Catalog lists; read-only **System Information** (backend version, dataset version, optimisation engine, fuzzy model, official dataset mode); notification texts no longer promise sensors or weather. |
| **Official Data** (new, `DatasetsView`) | Dataset name and file, government source, coverage (report year), last updated, rows, availability, checksum; disabled features with the missing dataset, its source and effect; Soil Health Card coverage; geographic coverage and the Pollachi note. |

## 3. Components and files

New: `src/services/officialData.js` (cached reference loaders, missing-value and label rules, run classification), `src/services/officialData.test.js`, `src/views/DatasetsView.jsx`, `CropEvidenceSection` and `SoilHealthCardSection` / `NotAvailable` components, `scripts/refresh-fixtures.mjs`, fixture `crop-evidence-salem.json`.

Changed: `App.jsx`, `services/api.js`, all views except Onboarding, `ExplanationPanel`, `DistrictSections`, `SimulationSections`, `TopsisPanel`, `ChartCard`, `chartTheme`, `DeltaBarChart`, `DataSourceNotice`, `utils/{districtView,qualityMetrics,simulationReport,simulationView,topsisView}.js`, every test file that used a fixture, and the six fixtures (re-recorded from the official backend).

## 4. Removed legacy code

`DISTRICTS`, `SEASONS`, `FUZZY_MODELS`, `extractDistrict()` (api.js); three `FALLBACK_CROPS` lists; the local `SEASONS` in ProfileSetupView; three duplicated catalog fetches plus two year-list fetches; the dashboard's multi-district weather loop and the Open-Meteo reading layout; Comparison's generated two-step schedule; the hard-coded `['Kharif', 'Rabi', 'Summer']` filter; the ML/litre conversions. No component or asset was unused, so none was deleted.

## 5. Verification (2026-11-13)

| Check | Result |
|---|---|
| Unit tests (`npm test`, Vitest) | **99 passed** (12 → 13 files; 91 → 99 tests; fixtures re-recorded from the official backend) |
| Lint (`npm run lint`, oxlint) | 0 warnings, 0 errors |
| Build (`npm run build`) | succeeds |
| Type checking | not applicable: the project is plain JavaScript with no TypeScript or JSDoc type-check configuration |
| Browser check, dev build (React warnings visible), 10 pages × desktop 1440 / tablet 820 / phone 390 px | 0 console errors or warnings, 0 page errors, 0 failed requests, 0 horizontal overflow, no "undefined", "NaN", "null" or "ML/ha" text (first pass found the overflow, the NaN and the 501 console entry; all fixed) |
| Interactive flows (production build) | profile setup, run optimisation, TOPSIS reasoning, explanation with crop evidence, history, reports, comparison and its explanation, district intelligence, scenario simulation, settings, Official Data page, Swagger: all captured in `final_ppt/screenshots/` |
| Backend | not modified (`git diff` of `app/`, `tests/`, `data/` is empty) |

## 6. Performance observations (measured)

| Item | Before | After |
|---|---|---|
| Main bundle `index-*.js` | 212.24 kB (66.45 kB gzip) | 214.28 kB (67.24 kB gzip) |
| `DashboardView` chunk | 19.10 kB | 16.24 kB |
| `ExplanationPanel` chunk | 21.69 kB | 26.02 kB (crop evidence section) |
| New `DatasetsView` chunk | – | 7.25 kB |
| Weather requests on Home | 5 (all 501) | 0 |
| Catalog requests per page load | one per form (Auth, Profile setup, Settings, Run Optimization, Simulation) | one, cached |

Warm in-process latency of the reference endpoints the frontend now calls (curl against `uvicorn` on the same laptop, three requests each): `/api/catalog` 3.1–9.5 ms (1.8 kB), `/api/datasets` 2.3–2.9 ms (4.8 kB), `/api/fuzzy/models` 2.4–2.9 ms (4.2 kB), `/openapi.json` 2.2–2.8 ms (56.8 kB), `/api/soil-master/salem` 2.7–2.9 ms (3.4 kB). History makes one extra `GET /api/results/{id}` per listed run to read its model and data source.

## 7. Remaining limitations

- `GET /api/datasets` does not return a publisher per dataset, so the Official Data page shows "Official Data Not Available" in the Government source column (the backend was not to be changed).
- `GET /api/history` does not return the fuzzy model or data source; History reads each run's record (one request per run). A run is classed as official data when its candidate crops cite official sources.
- Backend text still says "irrigation water" or "Low water use" in a few generated sentences (simulation summary, trade-off summary); it is shown as sent.
- Comparison's "Adjust weights" still re-picks A/B/C in the browser from the backend's radar scores, because the comparison endpoint takes no weights.
- The language switcher has no translations; the onboarding and profile images are hosted on `lh3.googleusercontent.com` (blank when that host is unreachable).
- Weather, fertiliser prices, crop calendars, market prices and taluk statistics stay unavailable until their official datasets are loaded (`disabled_features`).

## 8. Recommendation

**READY FOR FINAL REVIEW.** Every dropdown and value comes from the backend, missing data is labelled as such, the new explanation evidence and dataset information are shown, and tests, lint, build and the three-width browser check pass. The limitations above are data gaps or backend-side fields, not frontend defects.
