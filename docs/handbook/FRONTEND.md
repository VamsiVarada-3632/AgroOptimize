# Frontend

`frontend/` – React 19.2, Vite 8.2, Tailwind CSS 4.3 (via `@tailwindcss/vite`), oxlint, Vitest. No router, no state library, no chart library (all charts are hand-written SVG). The app works only with the official-data backend: every district, season, crop and model it offers comes from the API, and anything the official datasets do not publish is shown as **Official Data Not Available**. Migration details: [FRONTEND_MIGRATION_REPORT.md](../data_architecture/FRONTEND_MIGRATION_REPORT.md).

```bash
cd frontend
npm install
npm run dev                                   # http://localhost:5173, talks to http://localhost:8000
VITE_API_BASE=http://localhost:8010 npm run dev   # point at another backend
npm run lint && npm run build                 # oxlint + production build to dist/
npm test                                      # Vitest (99 tests)
node scripts/refresh-fixtures.mjs             # re-record test fixtures from a running backend
```

## 1. Application shell (`src/App.jsx`)

| State | Stored | Purpose |
|---|---|---|
| `currentView` | `localStorage.agro_currentView` | onboarding, login, register, profile-setup, dashboard, analytics, comparison, run-optimization, district-intelligence, scenario-simulation, history, reports, datasets, settings |
| `user` | `localStorage.agro_user` | profile `{fullName, phoneNumber, email, location, landSize, primaryCrop, avatar, season}` |
| `selectedLanguage` | memory | en/hi/ta – no translations exist |
| `dashboardLayout` | memory | 'sidebar' / 'topbar' |
| `backendOnline` | memory | one `GET /health` at start-up (footer dot) |

Guard: a shell view needs a district the catalog lists (`isCatalogDistrict`). A district saved by the v1 app that the catalog does not list (e.g. the taluk Pollachi) returns the user to profile setup. Until the catalog has loaded, or if it cannot be loaded, the saved district is trusted and each page reports its own error. Layouts: fixed 256 px sidebar (desktop), sticky top bar (toggle on Home), mobile header and drawer (< 768 px). The content column has `min-w-0`, so wide tables scroll inside their cards instead of widening the page.

## 2. Data layer

### `src/services/api.js`
* `resolveApiBase(env, origin)`: `VITE_API_BASE` if set, else the page origin in a production build (the backend serves the build), else `http://localhost:8000`.
* `districtPath(name)`: lower-cased, URL-encoded district for path parameters.
* `getOrCreateClientId()`: browser id (`agro_client_id`) sent with dashboard, history, farm-plan and simulation calls.
* `ApiError {status, detail}`, `describeApiError(err)`, `BACKEND_UNREACHABLE_MSG`.
* `PREFERENCES`: the `FarmPlanRequest.preference` values (request options, not data).
* Methods: `checkHealth, getCatalog, getDatasets, getOpenApi, getFuzzyModels, getSoilMaster, getSoilMasterDistrict, getWeather, getDashboard, getHistory, getSoilProfile, getResult, getPlans, getComparison, getFuzzyComparison, getDistrictIntelligence, getResultExplanation, getComparisonExplanation, runOptimization, getTopsisProfiles, rerankResult, runSimulation, saveSimulation, listSimulations, getSimulation, deleteSimulation`. Page-by-page use: [FRONTEND_API_INTEGRATION.md](FRONTEND_API_INTEGRATION.md).

### `src/services/officialData.js`
* `useCatalog()`, `useFuzzyModels()`, `useDatasets()`, `useOpenApi()`: one cached request per resource per page load (a failed request is retried on the next use); each returns `{data, error, loading}`.
* `catalogCrops(catalog)`, `isCatalogDistrict(catalog, name)`.
* `OFFICIAL_DATA_NA`, `isMissing(v)` (null, undefined, empty text, NaN – not 0), `showValue(v, format)`, `isOfficialDataUnavailable(err)` (HTTP 400/404/501).
* `FIELD_LABELS`, `EVIDENCE_LABELS`, `fuzzyModelLabel(name)`: words shown for backend field names, crop-evidence criteria and fuzzy models.
* `describeRun(run)`: fuzzy model (`meta.fuzzy_model`, missing = original) and whether the run used official data (candidate crops cite official sources).

`src/utils/download.js`: `downloadFile`, `toCsv` (neutralises formula prefixes), `slug`.

## 3. Pages

| Page | API | Notes |
|---|---|---|
| Onboarding | – | splash, carousel; images hosted on `lh3.googleusercontent.com` |
| Auth (demo, device-local) | catalog | register step 2: catalog district and crop; OTP is generated in the browser |
| Profile setup | catalog | district, season, crop from the catalog; land size in hectares |
| Home | dashboard, datasets | KPIs (active plans, estimated yield, irrigated area, soil health); top three candidate crops by official production at MSP; recommended actions; weather card shows the reason from `disabled_features` while live weather is disabled |
| Analytics | plans, soil-profile, compare-fuzzy | cost-vs-yield scatter, constraint sliders (cost, yield, irrigated ha per ha), convergence, fuzzy vs non-fuzzy table; CSV export |
| Comparison | comparison (+ explanation) | radar, metrics table, allocations, crop calendar (Official Data Not Available), browser-side "Adjust weights", CSV export |
| Run Optimization | catalog, fuzzy/models, farm-plans, topsis | the only page that creates a saved run; server-default fuzzy model preselected; TOPSIS re-ranking panel |
| District Intelligence | catalog, district-intelligence, soil-master/{district} | overview, climate, soil, Soil Health Card, water, crops, suitability, market, insights; compare districts; text/CSV/JSON export |
| Scenario Simulation | catalog, datasets, simulations | levers the backend has disabled (fertiliser price) are shown as unavailable; save/reopen/delete; HTML report and JSON export |
| History | history, results/{id} | model and data badges per run; explanation of the top plan |
| Reports | history, results/{id}, explanation | plain-text report with crop evidence; copy summary |
| Official Data | datasets, catalog, soil-master | registry, disabled features, Soil Health Card and geographic coverage |
| Settings | catalog, openapi, datasets, fuzzy/models | profile; read-only System Information |

### Explanations
Every recommended plan has a "Why?" entry point (Run Optimization, Comparison, History, Reports). `ExplanationPanel` lays out the backend's explanation; the **Why this crop was selected** section (`CropEvidenceSection`) shows per crop the ten criteria with Status, Evidence, Official source and a plain-language meaning of the status, as collapsible cards. Details: [EXPLAINABILITY.md](EXPLAINABILITY.md).

## 4. Shared components

| Component | Used by | Notes |
|---|---|---|
| `DataSourceNotice` | Home, Analytics, Comparison | official district data vs personalised runs |
| `ExplanationPanel`, `ExplanationModal`, `ExplanationComparison`, `CropEvidenceSection`, `FuzzyRulesSection`, `TopsisSection` | explanation entry points | render the backend JSON only |
| `charts/*` (`LineChart`, `BarChart`, `GroupedBarChart`, `DeltaBarChart`, `RadarChart`, `ChartCard`, `chartTheme`) | District Intelligence, Simulation, TOPSIS | chart/table toggle; missing values print the official text |
| `district/DistrictSections` | District Intelligence | sections incl. `SoilHealthCardSection`, `NotAvailable` |
| `simulation/SimulationSections` | Scenario Simulation | result sections |
| `topsis/ProfileSelector`, `topsis/TopsisPanel` | Run Optimization | ranking profiles and custom weights |
| `CountryCodeModal`, `AccountAuthOverlay`, `ParticleBackground`, `SuccessCheckSvg`, `ViewLoading` | Auth, Settings, Onboarding, Profile setup, shell | |

## 5. Styling

`src/index.css` defines Tailwind v4 `@theme` tokens (Material-3 colour roles, Montserrat/Inter, type scale, spacing, shadows, keyframes). Icons are the Material Symbols web font from Google Fonts.

## 6. Loading, empty, error and missing-data states

Every data section has a skeleton while loading and an explicit empty state. Server faults show the backend's `detail` or `BACKEND_UNREACHABLE_MSG`; "no official data" answers (400/404/501) show **Official Data Not Available** with the backend's reason. No page substitutes estimated or sample values.

## 7. Tests

Vitest, 13 files, 99 tests: API base and district paths, official-data helpers, charts, district, simulation and TOPSIS helpers and sections, fuzzy rules and crop evidence rendering, quality metrics, lazy loading. Fixtures in `src/__fixtures__/` are real responses of the official backend, re-recorded with `scripts/refresh-fixtures.mjs`.

## 8. Known weaknesses

No URL routing; language switcher without translations; Comparison re-weights A/B/C in the browser; external image and font hosts; large views (AuthView, AnalyticsView) mixing data and layout. See [FRONTEND_MIGRATION_REPORT.md](../data_architecture/FRONTEND_MIGRATION_REPORT.md) §7.
