# Frontend audit (before the official-data migration)

Scope: every file in `frontend/src` on branch `feature/official-data-migration` (commit `fd336f2`), checked against the official-data backend on the same branch. Searches covered hard-coded districts, crops, seasons, fallback lists, mock data, synthetic assumptions, old endpoints, old field names, unused components and duplicated logic. The replacement column is what the migration did ([FRONTEND_MIGRATION_REPORT.md](FRONTEND_MIGRATION_REPORT.md)).

## Hard-coded reference data

| File | Problem | Replacement |
|---|---|---|
| `services/api.js` | `DISTRICTS = ['Coimbatore', 'Erode', 'Salem', 'Pollachi']`: the v1 districts. The backend has 38 official districts, and Pollachi is a taluk (HTTP 400). | Removed; every district list comes from `GET /api/catalog` (`locations`) through `useCatalog()` in `services/officialData.js`. |
| `services/api.js` | `SEASONS = ['Kharif', 'Rabi', 'Summer']`: the official reports have no Summer season (HTTP 400 "Unknown season"). | Removed; seasons come from `GET /api/catalog` (`seasons`). |
| `services/api.js` | `extractDistrict()` mapped any string onto one of the four districts and fell back to Coimbatore, silently changing the user's district. | Removed; `districtPath()` lower-cases and URL-encodes the catalog name (needed for "The Nilgiris"). |
| `services/api.js` | `FUZZY_MODELS` listed only `original` and `improved`; the UI sent `original` by default, so runs did not use the backend default `official` model. | Removed; models come from `GET /api/fuzzy/models`, and the default is the server's `default` (`official`). |
| `services/api.js` | `runOptimization` defaulted `season` to `'Kharif'`. | No default; the season comes from the form, which uses the catalog. |
| `views/ProfileSetupView.jsx` | Own `SEASONS` list with Summer; `FALLBACK_CROPS` (Sugarcane, Wheat, Paddy, Maize, Cotton, Groundnut, Sorghum, Tapioca) used when the catalog failed; `DISTRICTS` dropdown. | Catalog districts, seasons and crops only (`catalogCrops()`); no fallback list. |
| `views/AuthView.jsx` | `FALLBACK_CROPS` and `DISTRICTS` in the register form; "Our models currently cover these 4 districts". | Catalog lists; the count shown is the catalog's. |
| `views/SettingsView.jsx` | `FALLBACK_CROPS`, `DISTRICTS`, `extractDistrict(user.location)`. | Catalog lists; an unlisted saved district must be chosen again. |
| `views/RunOptimizationView.jsx` | `DISTRICTS`, `SEASONS`, `FUZZY_MODELS`; season defaulted to Kharif; fuzzy model defaulted to `original`. | Catalog and fuzzy-model API; the profile's season if the catalog lists it; the server's default model. |
| `views/SimulationView.jsx`, `utils/simulationView.js` | `DISTRICTS`, `SEASONS`; `defaultForm()` fixed `season: 'Kharif'`. | Catalog lists; `defaultForm(district, land, season)`. |
| `views/DistrictIntelligenceView.jsx` | `DISTRICTS` for the district and compare selectors. | Catalog list. |
| `components/district/DistrictSections.jsx` | Suitability season filter hard-coded `['Kharif', 'Rabi', 'Summer']`. | Seasons present in the backend's rankings. |
| `views/DashboardView.jsx` | Weather "Districts" tab fetched `/api/weather` for the four hard-coded districts. | Tab removed (the endpoint is disabled for every district). |
| `App.jsx` | Profile guard `DISTRICTS.includes(user.location)`. | `isCatalogDistrict(catalog, location)`; a saved v1 district (e.g. Pollachi) sends the user back to profile setup. |

## Old field names and units

| File | Problem | Replacement |
|---|---|---|
| `views/ReportsView.jsx` | `plan.water_liters` "litres"; the field no longer exists (the backend sends `irrigated_ha`), so the report printed NaN. | `plan.irrigated_ha` as "Irrigated area … ha". |
| `utils/qualityMetrics.js` | `mean_objectives.water_liters` "L". | `mean_objectives.irrigated_ha` "ha irrigated". |
| `views/AnalyticsView.jsx` | `fuzzy.min_water_liters_per_ha` (removed by the backend, so the table showed "--"); "ML/ha" labels on the irrigated-area slider, KPI and tooltip; CSV column `water_million_litres_per_ha`. | `min_irrigated_ha_per_ha`; "ha irrigated per ha" labels; CSV column `irrigated_ha_per_ha`. |
| `components/ExplanationPanel.jsx` | `summary.per_ha.water` shown as "ML/ha" (twice). | "Irrigated Area … ha/ha". |
| `utils/simulationView.js` | `formatMetric('water')` divided by 10⁶ and printed "ML"; the value is irrigated hectares, so it showed 0.00 ML. | Hectares, "ha irrigated". |
| `utils/topsisView.js` | `formatCriterionValue('water')` divided by 10⁶ ("ML"); criterion label "Water". | Hectares; label "Irrigated area" (as `GET /api/topsis/profiles`). |
| `views/ComparisonView.jsx` | "Water Usg." column, "Water" radar axis, "Water Conservation Weight". | "Irrigated Area", "Irrigation", "Less Irrigation Weight". |
| `components/district/DistrictSections.jsx` | Suitability "Water need" column printed `water_req_mm` (always null: " mm"); fertility-index subtitle described the v1 pH/OC formula. | "Irrigated share" from `irrigated_share`; Soil Health Card wording. |

## Synthetic assumptions and mock content

| File | Problem | Replacement |
|---|---|---|
| `views/ComparisonView.jsx` | "Getting Started" two-step calendar generated in the browser ("Land preparation & … sowing", "First irrigation & fertilizer application"); no dataset behind it, and the official data has no sowing or harvest months. | "Crop Calendar: Official Data Not Available" with the reason. |
| `views/DashboardView.jsx` | Weather card rendered live/"historical estimate" readings (Open-Meteo fields) that the backend no longer produces. | Card states "Official Data Not Available" and the reason from `GET /api/datasets` (`disabled_features`). |
| `views/DashboardView.jsx` | Crop allocation caption "from historical crop data". | States what the backend computes: top three candidates by official production valued at MSP, not an optimised plan. |
| `components/DataSourceNotice.jsx` | "Historical district data … from past seasons". | "Official district data … from the government datasets". |
| `views/SettingsView.jsx` | "Irrigation reminders: alerts based on moisture sensors" (no sensors exist); "Weather warnings: frost, heavy rain…" (no weather data). | Text says the preference is stored on the device only; weather warnings say the IMD feed is not available. |
| `views/SimulationView.jsx` | Fertiliser-cost lever offered although the backend disables it (no notified fertiliser prices). | Lever replaced by "Official Data Not Available: <missing dataset>" when `disabled_features` lists it; the request sends 0. |
| `views/ReportsView.jsx` | Limitations paragraph cited "district-level averages and documented modelling assumptions". | Cites the official 2024-25 datasets and the "Official Data Not Available" rule. |
| `src/__fixtures__/*.json` | Test fixtures recorded from the v1 synthetic backend (Coimbatore/Erode crops, 2020-2024 years, `water_liters`). | Re-recorded from the official backend by `frontend/scripts/refresh-fixtures.mjs`; one new fixture `crop-evidence-salem.json`. |

## Missing values

| File | Problem | Replacement |
|---|---|---|
| Dashboard, Analytics, Comparison, History, Reports, Explanation, Simulation, District sections, `ChartCard`, `chartTheme.formatNumber`, `TopsisPanel`, `DeltaBarChart` | Missing values were shown as `--`, `–`, `—`, "n/a", "Data not available", or as empty strings; nulls inside template strings printed "null" ("variation coefficient null", "groundwater status \"null\"", "Humidity: 2024 null%"). | `showValue()` / `isMissing()` (`services/officialData.js`) print **Official Data Not Available** for null, undefined, empty text and NaN; charts whose series are all missing (temperature, water demand, groundwater status) show the same text instead of an empty chart. Quality metrics the backend could not compute say "Not computed for this run". |
| Analytics, Comparison, District Intelligence | A 400/404 (e.g. Chennai, The Nilgiris: fewer than two complete crops) was shown as "Couldn't reach the server". | `isOfficialDataUnavailable(err)` → "Official Data Not Available: <backend detail>". |
| `components/district/DistrictSections.jsx` | New Soil Health Card table passed a class name through the number formatter (NaN), found by the UI check. | Text value shown as is. |

## Endpoints

| File | Problem | Replacement |
|---|---|---|
| `services/api.js` | No client for `/api/datasets`, `/api/soil-master`, `/api/soil-master/{district}`, `/api/fuzzy/models`; no page showed the dataset registry, the disabled features or the Soil Health Card record. | Methods `getDatasets`, `getSoilMaster`, `getSoilMasterDistrict`, `getFuzzyModels`, `getOpenApi`; new Official Data page; Soil Health Card section on District Intelligence; read-only System Information on Settings. |
| `components/ExplanationPanel.jsx` | `crop_evidence` (ten official criteria per crop) returned by both explanation endpoints but never rendered. | Collapsible "Why this crop was selected" section. |
| `views/HistoryView.jsx` | No indication of the fuzzy model or the data a run used. | Badges from each run's record (`GET /api/results/{id}`). |
| (none) | No call to a removed or renamed endpoint was found; all paths in `api.js` exist on the backend. | – |

## Unused code and duplicated logic

| File | Finding | Action |
|---|---|---|
| `components/*`, `utils/*` | Every component and helper is imported by at least one view (checked by import search). | Nothing removed. |
| `views/AuthView.jsx`, `views/ProfileSetupView.jsx`, `views/SettingsView.jsx` | Three copies of the catalog fetch and of the crop-list builder. | One cached loader (`useCatalog`) and `catalogCrops()`. |
| `views/RunOptimizationView.jsx`, `views/SimulationView.jsx` | Two more catalog fetches for the year list. | `useCatalog`. |
| `views/ComparisonView.jsx` | "Adjust weights" re-picks A/B/C by a weighted sum of the backend's radar scores in the browser. | Kept: the comparison endpoint takes no weights, and the backend is not to be changed. Listed as a limitation. |
| `utils/topsisView.js` | `PROFILE_OPTIONS` and `CRITERIA` are local copies of `GET /api/topsis/profiles` used until it answers (the request schema's enum values). | Kept; the water label now matches the backend ("Irrigated area"). |
| `services/api.js` | `PREFERENCES` lists the `FarmPlanRequest.preference` enum. No endpoint lists it. | Kept as request options; "Min Water Use" renamed "Least Irrigated Area". |
