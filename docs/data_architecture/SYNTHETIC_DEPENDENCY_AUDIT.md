# Synthetic / Hardcoded Dependency Audit (Task 2)

Read-only audit of `agrooptimize-backend` (branch `feature/fuzzy-logic-improvements` at 91f0607) against the official datasets. Nothing was modified. Line numbers are from that commit.

**Headline findings**

1. There is **no database**. Persistence is 16 CSVs in `data/raw/` plus JSON/CSV/PNG files in `results/`. The "database tables" and "migrations" in the task do not exist yet; they have to be created (SQLite via SQLAlchemy + Alembic is the proposal).
2. The code path is hard-wired to the old schema: `(Location, Year 2020-2024, Season Kharif/Rabi/Summer)` and 46 column names. The official data is `(district, report year 2024-25)` with no Summer season. Every module that reads `Year` or `Season` is affected.
3. Roughly half the model inputs have no counterpart in the uploaded official files (soil chemistry, crop water requirement, fertiliser doses, pesticide cost, labour days, duration/calendar, temperature/humidity). See OFFICIAL_DATASET_MAPPING.md section 4.

## A. Synthetic data files (to be retired)

| # | File(s) | Content | Evidence it is synthetic |
|---|---|---|---|
| A1 | `data/raw/{coimbatore,erode,salem,pollachi}_crop.csv` (205 rows) | 15 crops, 2020-2024, 3 seasons. Includes Wheat, Sorghum, Vegetables, Fodder Crops, Mango. | 2024 rows = 2023 x ~1.061 (`data_source` "Estimated (2024)"); Fertiliser/Pesticide/Labour identical across adjacent years; Wheat is not in the official TN crop list. |
| A2 | `.../{loc}_land.csv` (60 rows) | land split, soil type, pH, organic carbon, N/P/K status | one soil value set per district with linear trends; 2024 copied from 2023 |
| A3 | `.../{loc}_rainfall.csv` (240 rows) | monthly rainfall, temp, humidity, normals | 2024 = 2023 verbatim; normals rewritten to season-flat constants (Task of 2026-09-17) |
| A4 | `.../{loc}_water_availability.csv` (240 rows) | reservoir MCM, groundwater, demand | storage/groundwater overwritten with hand-entered per-district figures; Deficit_Surplus always 0 |
| A5 | `results/*.json, *_plans.csv, *_convergence.*` (38 files, 9 saved runs) | saved optimisation runs | computed on A1-A4 |
| A6 | `frontend/src/__fixtures__/*.json` (6 files, ~230 KB) | UI test fixtures (Salem) | derived from A1-A4 runs |
| A7 | `docs/handbook/PAPER_TABLES_4-7.md`, `docs/handbook/benchmarks/*`, `docs/results/*` | published paper tables / benchmarks | computed on A1-A4; keep as the frozen `published-v1` record, not as runtime inputs |

Note on the repo's own history: `docs/data_architecture/DATA_QUALITY_AUDIT.md` (2026-10-20) already catalogued 19 quality defects in A1-A4 (e.g. sugarcane MSP about 10x its FRP, year-invariant storage, mixed marketing years).

## B. Hardcoded values and assumptions in Python

### B1. `app/config.py`
| Line | Item | Kind |
|---|---|---|
| 31-32 | `LOCATIONS = [Coimbatore, Erode, Salem, Pollachi]`, `DATASET_KINDS` | hardcoded geography/schema |
| 37-42 | `DISTRICT_COORDINATES` (4 towns) | hand-entered; used for weather API |
| 45, 52-56 | `AG_SEASONS`, `SEASON_MONTH_MAP` (Kharif Jun-Sep, Rabi Oct-Mar, Summer Feb-May; overlapping) | assumption; official data has no Summer and different season definitions |
| 68-69 | `DEFAULT_MAX_CANDIDATE_CROPS = 6`, `MIN_CANDIDATE_CROPS = 2` | assumption (replace by data-driven candidate selection) |
| 92-96 | `FERTILIZER_PRICE_RS_PER_KG_NUTRIENT` N 12.87 / P 58.70 / K 56.67 | derived from quoted bag prices; sourced from PIB/IFFCO per comments but not in uploaded files |
| 103 | `LABOR_WAGE_RS_PER_DAY = 319` | MGNREGA FY24-25 wage used as farm wage |
| 117 | `WATER_COST_RS_PER_MM_PER_HA = 3.0` | admitted order-of-magnitude assumption (unwired) |
| 124, 129 | `LITERS_PER_MM_PER_HA` (physical constant, fine), `RAINFALL_UTILIZATION_FACTOR = 0.7` | assumption |
| 149-150 | `CARBON_FERTILIZER_FACTOR = 0.15`, `CARBON_PUMPING_FACTOR = 0.01` | "synthetic carbon-proxy units" (config comment) - f4 objective |
| 154-159 | `RAINFALL_DEPENDENCY_FACTOR` Very Low 0.1 / Low 0.3 / Medium 0.6 / High 1.0 | hand-assigned scores mapped from a hand-labelled column |
| 172-173 | `IRRIGATION_MULT 0.7-1.3`, `FERTILIZER_MULT 0.7-1.3` | decision-variable bounds (search design; keep, document) |
| 185 | `NSGA2_SEED = 42` | reproducibility seed (legitimate, not data) |

### B2. `app/data/preprocessing.py`
| Line | Item |
|---|---|
| 94, 98 | `_STATUS_SCORE` Low 30 / Medium 60 / High 90; unknown status silently scores 50.0 (a hidden default) |
| 117-122 | Fertility index: pH optimum 6.5 with slope 40/unit, OC target 1.0 %, weights 0.3/0.3/0.4 |
| 357-363 | `_REFERENCE_RANGES` "domain-informed plausible ranges" for the [0,1] snapshot (rainfall 0-150, deviation +-50, ...) |
| 139-160 | `ESTIMATED_SOURCE_PREFIX` / `is_estimated_year` logic for carried-forward 2024 rows |
| 300-310 | candidate crops = top-N by `Revenue_Rs_Lakh` (a synthetic column) |
| 228-300 | the `Year`/`Season`/`Month` filter logic (land_rows, rain_rows, water_rows, crop_rows) that assumes the old schema |

### B3. `app/fuzzy/engine.py`
| Line | Item |
|---|---|
| 56-62 | `MEMBERSHIP_FUNCTIONS` - triangular breakpoints (rainfall -60..60 %, storage 0-100, fertility 0-100, outputs) not derived from data |
| 100-117 | `STRONG_PARTITION_SETS`, `IMD_RAINFALL_SETS` (IMD category bands are official, 19.5 % normal limit is from IMD) |
| ~150-395 | 26 hand-authored rules (`RULE_COUNT = 26` at 345) and `RULE_SCENARIOS` labels (381) |
| 375 | `INPUT_BOUNDS` |
| 571-580 (penalty at 579) | `crop_yield_confidence`: penalty cap 0.4 and `RAINFALL_DEPENDENCY_FACTOR` fallback 0.5 for unknown dependency |

### B4. `app/optimization/problem.py` (NSGA-II objectives)
| Line | Item |
|---|---|
| 147-150 | f1 yield uses `Yield_Kg_Ha` x fuzzy confidence |
| 127-159 | f2 cost = fert dose x config prices + `Pesticide_Cost_Rs_Ha` + `Labor_Days_Ha` x wage: **all four from synthetic columns/config** |
| 161-164 | f3 water = (`Water_Req_mm` - effective rainfall) x multiplier: `Water_Req_mm` synthetic, factor 0.7 assumed |
| 166-175 | f4 = sqrt(leaching x carbon proxy) with synthetic factors, `Fertilizer_N/P/K` synthetic |

### B5. `app/decision/` (TOPSIS)
| Item | Location |
|---|---|
| Preference weights incl. `_YIELD_GROUP_WEIGHT = 0.30`, tuned by hand ("empirically correlates 0.7-0.85") | `ranking.py:52-75` (`_YIELD_GROUP_WEIGHT` at 52, weights from 54) |
| Profile weight tiers `TIER_POINTS` | `profiles.py:24-45` |
| `SOIL_DEFICIT` Low 1.0 / Medium 0.5 / High 0.0 | `criteria.py:61` |
| `market_price`, `income` criteria use `MSP_Rs_Qtl` (synthetic column) | `criteria.py:113-152` |
| `rainfall` criterion uses `RAINFALL_DEPENDENCY_FACTOR`, default 0.6 | `criteria.py:116` |

### B6. Services
| File:line | Item |
|---|---|
| `dashboard_service.py:104-110` | `_condition_for_rainfall` thresholds 50/100 mm |
| `dashboard_service.py:114-216` | **mock/fallback weather**: `_get_weather_from_csv` builds a 5-day "forecast" from monthly CSV averages labelled Mon..Fri; live path uses Open-Meteo (not an official source) |
| `dashboard_service.py:224-229` | `_ACTION_LIBRARY` fixed advisory texts and fixed timings ("Next 48 hours") |
| `dashboard_service.py:252` | `_REFERENCE_FARM_HA = 10.0` illustrative farm |
| `dashboard_service.py:265-370` (`get_dashboard`) | KPIs (estimated_yield, soil_health_pct, water_utilization_pct) from synthetic columns |
| `dashboard_service.py:461` | `_DEMO_POP_SIZE = 100` |
| `dashboard_service.py:700-715` | radar `market` axis = (1 - rainfall-dependency factor) x 100, a proxy not a market measure |
| `dashboard_service.py:728` | `_PLOT_LABELS` "Plots 1, 2, 4"... deprecated placeholder text returned by the API |
| `simulation_service.py:69-71, 81` | `RAINFALL_STEPS`, `FERTILIZER_STEPS`, `WATER_LEVEL_STORAGE_PCT {10,25,50,70,90}` hand-picked scenario levels |
| `simulation_service.py:105-111` | `market_price_step_pct` = max YoY change of the synthetic MSP column |
| `simulation_service.py:91` | `ENSEMBLE_SEEDS` (reproducibility, fine) |
| `explanation_service.py:46-57` | `STRONG_GOODNESS 0.60`, `WEAK_GOODNESS 0.30`, `PERENNIAL_DAYS 300`, `PRICE_SHOCK 0.10`, `HISTORICAL_TOP_N 3` ... explanation thresholds |
| `explanation_service.py:269-298, 650-664` | revenue = tonnes x synthetic MSP |
| `district_service.py:47-52` | `STABLE_CHANGE_PCT 5`, `LOW_CV 0.10`, `HIGH_CV 0.25`, `LOW_STORAGE_PCT 40` ... analytics thresholds |
| `fuzzy/audit.py:176` | reports `data_year_estimated` |
| `results_store.py` | stores runs as local JSON (no DB) |

### B7. Random generators
Only legitimate ones in `app/`: `np.random.seed(seed)` in `optimization/nsga2_runner.py:182` and the operators (NSGA-II stochastic search), `results_store.py:269` random id suffix. There is **no random data generation** in the backend. In the frontend: `AuthView.jsx:104` generates a client-side OTP with `Math.random` (a dummy authentication flow, not a data issue), `api.js:95` client id, `ParticleBackground.jsx` cosmetic animation.

### B8. Dummy / mock APIs
- No mock endpoints in `app/main.py` (24 routes, all computed from CSV + live NSGA-II).
- Authentication/OTP is entirely client-side (`AuthView.jsx`, localStorage): no backend auth exists. Out of scope for data migration; flagged.
- `run_demo.py` is a CLI demo over the same pipeline (will keep working but must stop referencing the 4 hardcoded locations).

## C. Frontend hardcoded data
| File:line | Item |
|---|---|
| `frontend/src/services/api.js:27` | `DISTRICTS = ['Coimbatore','Erode','Salem','Pollachi']` |
| `AuthView.jsx:7`, `ProfileSetupView.jsx:10`, `SettingsView.jsx:8` | `FALLBACK_CROPS = [Sugarcane, Wheat, Paddy, Maize, Cotton, Groundnut, Sorghum, Tapioca]` - Wheat and Sorghum are not in the official TN crop list (Sorghum = Jowar) |
| `src/__fixtures__/*.json` | see A6 |
| `frontend/dist/` | built bundle of the old data; regenerate |
| `frontend/_to_delete/` | stale scaffold build and `weatherData.js` (already isolated) |
| `AccountAuthOverlay`, `CountryCodeModal` | static UI lists (phone codes) - not data |

## D. Tests coupled to the synthetic data
20 test modules; `tests/test_data.py` asserts the 16 CSVs and the 4x3x5 grid, 55 lines mention specific years/locations/CSV names, and `test_district.py`, `test_simulation.py`, `test_dashboard.py` assert against synthetic values (e.g. 165 passing tests as of 2026-09-17). These need regenerating against the official-data loader, not deleting.

## E. Items that look synthetic but are NOT data (keep)
NSGA-II hyperparameters and seeds, decision-variable bounds, fuzzy rule structure, TOPSIS method, physical constants (`LITERS_PER_MM_PER_HA`). They are method parameters; the plan documents each one's justification instead of removing it.
