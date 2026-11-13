# Frontend API integration

Which backend endpoint each page calls, what it reads from the response, and how missing data is shown. Endpoint shapes: [API_REFERENCE.md](API_REFERENCE.md). Client code: `frontend/src/services/api.js` and `frontend/src/services/officialData.js`.

## Endpoints by page

| Endpoint | Client method | Pages | Fields read |
|---|---|---|---|
| `GET /health` | `checkHealth` | shell | status (footer dot) |
| `GET /api/catalog` | `getCatalog` via `useCatalog()` | shell guard, Auth, Profile setup, Settings, Run Optimization, District Intelligence, Scenario Simulation, Official Data | `locations`, `seasons`, `years`, `crops_by_season`, `taluk_notes` |
| `GET /api/datasets` | `getDatasets` via `useDatasets()` | Home (weather card), Scenario Simulation (fertiliser lever), Official Data, Settings | `datasets[]` (`name, filename, report_year, rows_clean, imported_at, sha256`), `disabled_features[]` (`feature, missing_dataset, source, scope`) |
| `GET /api/fuzzy/models` | `getFuzzyModels` via `useFuzzyModels()` | Run Optimization, Settings | `default`, `models[].name`, `models[].description` |
| `GET /openapi.json` | `getOpenApi` via `useOpenApi()` | Settings | `info.version`, `components.schemas.RunMeta.properties.algorithm.default` |
| `GET /api/soil-master` | `getSoilMaster` | Official Data | `cycle`, `available`, `unavailable[]` |
| `GET /api/soil-master/{district}` | `getSoilMasterDistrict` | District Intelligence | `available`, `cycle`, `samples_tested`, `ph`, `organic_carbon`, `nitrogen`, `phosphorus`, `potassium`, `electrical_conductivity` (`share_pct`, `dominant_class`, `samples`), `micronutrients` |
| `GET /api/weather/{district}` | `getWeather` | Home, only when `disabled_features` does not list the weather widget | – |
| `GET /api/dashboard/{district}` | `getDashboard` | Home | `active_plans, estimated_yield, yield_trend, water_utilization_pct, soil_health_pct, soil_status, recommended_actions, crop_allocations` |
| `GET /api/plans/{district}` | `getPlans` | Analytics | `plans[]` (`cost, yield_val, water_val` = irrigated ha per ha, `env_impact, crops, is_recommended`), `hypervolume_history` |
| `GET /api/soil-profile/{district}` | `getSoilProfile` | Analytics | `fertility_index` (0–1) |
| `GET /api/compare-fuzzy/{district}` | `getFuzzyComparison` | Analytics | `fuzzy` / `non_fuzzy` (`best_yield_tonnes_per_ha, min_cost_rs_per_ha, min_irrigated_ha_per_ha, min_env_impact_per_ha`), `fuzzy_assessment` |
| `GET /api/comparison/{district}` | `getComparison` | Comparison | `plans.A/B/C` |
| `GET /api/comparison/{district}/explanation` | `getComparisonExplanation` | Comparison | explanation incl. `crop_evidence` |
| `POST /api/farm-plans` | `runOptimization` | Run Optimization | `region_profile, plans, meta (fuzzy_model, topsis), run_id` |
| `GET /api/topsis/profiles`, `GET/POST /api/results/{id}/topsis` | `getTopsisProfiles`, `rerankResult` | Run Optimization | profiles, ranked plans, explanation, comparison |
| `GET /api/history/{district}` | `getHistory` | History, Reports | `history[]` |
| `GET /api/results/{id}` | `getResult` | History (badges), Reports | `meta.fuzzy_model`, `region_profile.candidate_crops[].sources`, plans |
| `GET /api/results/{id}/explanation` | `getResultExplanation` | Run Optimization, History, Reports | explanation incl. `crop_evidence` |
| `GET /api/district-intelligence/{district}` | `getDistrictIntelligence` | District Intelligence | all sections |
| `POST /api/simulations/run`, `POST /api/simulations`, `GET /api/simulations`, `GET/DELETE /api/simulations/{id}` | `runSimulation`, `saveSimulation`, `listSimulations`, `getSimulation`, `deleteSimulation` | Scenario Simulation | full result |

District path parameters are the catalog name, lower-cased and URL-encoded (`districtPath`).

## Labels

Backend field names are not renamed; only the words shown change (`FIELD_LABELS`, `EVIDENCE_LABELS` in `officialData.js`).

| Field | Shown as |
|---|---|
| `irrigated_ha`, `water_val`, `per_ha.water`, criterion `water` | Irrigated Area (ha, or ha per ha) |
| `water_liters` (v1 runs only) | Water Requirement |
| `env_impact_score`, `env_impact` | Nutrient load (kg N+P+K) |
| `crop_evidence` | Why this crop was selected |
| `ph` / `soil_ph`, `organic_carbon`, `electrical_conductivity` / `ec`, `npk` | Soil pH, Organic Carbon, Soil Salinity, Fertilizer Recommendation |
| `composite_score` / `topsis_score`, `nsga_rank` | Overall Score, Optimization Rank |
| `hypervolume` (ratio), `igd`, `igd_plus` | Optimization Quality, Solution Accuracy, Improved Solution Accuracy |
| crop-evidence status `supported`, `caution`, `concern`, `info`, `unavailable` | Supports this crop, Worth checking, Concern, For your information, Official Data Not Available |
| fuzzy model `official`, `original`, `improved` | Official (calibrated on official data), Original (published), Improved; History badges Official-Data Model, Original Model, Improved Model |

## Missing data

| Backend answer | Shown |
|---|---|
| value `null`, missing key, empty text, NaN | Official Data Not Available |
| HTTP 400 (e.g. Chennai, The Nilgiris: fewer than two crops with complete official data; unknown season) | Official Data Not Available: *backend detail* |
| HTTP 404 (unknown district or record) | Official Data Not Available: *backend detail* |
| HTTP 501 / feature in `disabled_features` | Official Data Not Available: *feature, missing dataset, source* |
| `fuzzy_assessment.applied: false` | "Fuzzy stage not applied: *reason*" |
| quality metric `null` | Not computed for this run |
| network failure, 5xx | the backend's detail or "Couldn't reach the AgroOptimize server…" |

A chart whose series are all missing is replaced by the same text; 0 is a value and is shown.
