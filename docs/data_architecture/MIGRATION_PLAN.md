# Official-Data Migration Plan (Task 3)

Branch: `feature/official-data-migration` (cut from `feature/fuzzy-logic-improvements` @ 91f0607).
Companions: OFFICIAL_DATASET_MAPPING.md (what the files contain), SYNTHETIC_DEPENDENCY_AUDIT.md (what must go).

## 0. Constraints discovered that shape the plan

| # | Finding | Consequence |
|---|---|---|
| C1 | No database exists today (CSV + JSON files). | Create one: SQLite via SQLAlchemy 2 + Alembic, so the same code can move to Postgres. Official data is loaded into it by importers; the API reads it. |
| C2 | Official district tables are a single year (2024-25); old grid was 5 years x 3 seasons x 4 districts. | `year` becomes a data-driven catalogue (initially one value). History/trend views use the 60-year state series plus reservoir/rainfall series, and say "single-year district data" where that is the truth. |
| C3 | No "Summer" season; official seasons are Kharif, Rabi and rice sub-seasons. | Seasons become data-driven. Summer is reported as "Data not available" - never synthesised. |
| C4 | **Pollachi is not an official district** (taluk of Coimbatore). | Decision D1 below. |
| C5 | No official soil chemistry, crop water requirement, fertiliser dose, pesticide cost, labour days, duration, temperature or humidity in the upload. | Decision D2. These are required by f2/f3/f4 and the soil fuzzy input, so the optimiser cannot be "100 % uploaded-data" without scraping TNAU / Soil Health Card. |
| C6 | Every government host I tried (Agmarknet, data.gov.in, TNAU, IMD, Soil Health, PIB, India-WRIS, CACP, DES, tn.gov.in) is unreachable from this workspace and from the shell on your Mac (proxy allowlist; HTTP 000). The previous session saw 403/maintenance for four of them. | Scrapers are built against recorded fixtures with parser unit tests; each one is marked **unverified live** until run from a network that can reach the site (or via the browser pane). No live figure will be claimed that was not fetched. |
| C7 | 5 of the 7 MSP PDFs are scanned images; OCR output is unreliable. | MSP values are transcribed from the page images, cross-checked (increase = new - old, margin = MSP/cost - 1), and stored with page references. |

## 1. Target architecture

```
GOVT DATASETS/*.csv|pdf ──► raw/ (immutable copy + sha256 in dataset_registry)
        │                       │
   scrapers (reusable) ─────────┤
        ▼                       ▼
  validators ► cleaners ► transformers ► importers ► SQLite (official_v1.db)
                                                        │
                       app/data/official.py (repository + TTL cache)
                                                        │
     profile builder ► fuzzy (calibrated from data) ► NSGA-II ► TOPSIS ► explanation
                                                        │
                       FastAPI (same routes, + /api/datasets, /api/provenance)
```

Per dataset, one package `app/datasets/<name>/` with `validator.py`, `cleaner.py`, `loader.py`, `importer.py`, `service.py` (API/cache) and `tests/datasets/test_<name>.py`. A shared `app/datasets/base.py` defines the interfaces; `scripts/preprocess_all.py` runs the pipeline and writes `data/clean/*.csv` + a validation report.

### Database tables (all new)
`dataset_registry`, `ingestion_log`, `district`, `crop`, `crop_alias`, `crop_stat`, `state_crop_series`, `land_use`, `irrigation`, `rainfall_monthly`, `rainfall_season`, `groundwater_monthly`, `reservoir`, `reservoir_reading`, `district_reservoir_map`, `msp`, `agronomy_reference` (TNAU, empty until scraped), `soil_health` (Soil Health Card, empty until scraped), `market_price` (Agmarknet), `fuzzy_calibration`, `optimisation_run`, `simulation_run`. Every fact row carries `dataset_id`, `source_page`/`source_url` and `retrieved_at`, so explanations can cite them.

## 2. Migration matrix

Format: old synthetic artefact -> official replacement -> cleaning -> transformation -> DB tables -> Python files -> frontend -> API -> optimisation.

### M1. `{loc}_crop.csv` (Yield, Area, Production, MSP, Revenue)
| Step | Plan |
|---|---|
| Replacement | `crops_by_district.csv` (yield, area, production per season) + MSP PDFs for price |
| Cleaning | unit normalisation, null preservation, production = area x yield check, crop-name canonicalisation (Paddy<->Rice, Jowar<->Sorghum, Tapioca, Lady's finger...) |
| Transformation | pivot to (district, crop, season) with `yield_kg_ha`, `area_ha` (total/irrigated/unirrigated), `production_t`; derive `unirrigated_share` (-> rainfall dependency), `revenue_rs_ha = yield x MSP` only where an MSP exists |
| DB | `crop`, `crop_alias`, `crop_stat`, `msp` |
| Python | `data/preprocessing.py` (rewrite `get_region_season_profile`), `data/loader.py` (replace by repository), `optimization/problem.py` (CropVector), `decision/criteria.py`, `services/{dashboard,district,explanation,simulation,plan}_service.py` |
| Frontend | crop lists in Auth/ProfileSetup/Settings views come from `/api/catalog` only; remove `FALLBACK_CROPS` |
| API | `/api/catalog`, `/api/region-profile`, `/api/farm-plans`, `/api/dashboard`, `/api/district-intelligence` (same shapes; new `provenance` block) |
| Optimisation | f1 yield from official yield; candidate set from crops with official season yield; MSP crops get revenue |

### M2. `{loc}_land.csv` (land split + soil columns)
| Step | Plan |
|---|---|
| Replacement | land part: `land_use.csv`, `irrigation.csv`; soil part: **no official file uploaded** (Soil Health Card, D2) |
| Cleaning | category-sum check, gross = net + multi-cropped, % recomputed |
| Transformation | `total_ha`, `net_sown_ha`, `fallow_ha`, `forest_ha`, `waste_ha`, `non_agri_ha`, `irrigated_ha`, `irrigation_pct`, `cropping_intensity` |
| DB | `land_use`, `irrigation`, `soil_health` |
| Python | `preprocessing.py` (SoilProfile), `dashboard_service._current_land_row`, `district_service`, `decision/criteria.py` (`SOIL_DEFICIT`) |
| Frontend | District Intelligence land/soil sections; soil card shows "Data not available" until Soil Health data exists |
| API | `/api/soil-profile/{location}`, `/api/district-intelligence/{location}` |
| Optimisation | soil fuzzy input; `soil` TOPSIS criterion |

### M3. `{loc}_rainfall.csv` (rainfall, normals, temp, humidity)
| Step | Plan |
|---|---|
| Replacement | `rainfall_by_district.csv` (actual, IMD normal, % departure) |
| Cleaning | separate monthly vs total rows, recompute % departure, reconcile season totals, treat month normals < 5 mm as unreliable for departure |
| Transformation | seasonal actual/normal/departure per crop season via the IMD-season -> crop-season crosswalk (reference table, documented); effective rainfall = seasonal actual x utilisation factor |
| DB | `rainfall_monthly`, `rainfall_season` |
| Python | `preprocessing.py` (RainfallProfile), `fuzzy/engine.py` inputs, `dashboard_service.get_weather` history, `district_service` climate |
| Frontend | weather card history label; climate charts |
| API | `/api/weather/{location}`, `/api/district-intelligence/{location}` |
| Optimisation | fuzzy `rainfall_dev` = official seasonal departure; f3 effective rainfall. Temperature/humidity: no official upload -> fields become null and the UI hides them; IMD scraper (S4) fills them |

### M4. `{loc}_water_availability.csv`
| Step | Plan |
|---|---|
| Replacement | `reservoir_daily.csv` (storage %, inflow) + `ground_water_level.csv` |
| Cleaning | storage_pct = storage/capacity, flag > 100 %, strip footnote marks, unit conversion MCFT -> MCM, cusecs -> m3/s |
| Transformation | season-mean and latest storage % per district through `district_reservoir_map`; groundwater depth -> availability index using published CGWB bands; year-on-year storage change from `last_year_storage_mcft` |
| DB | `reservoir`, `reservoir_reading`, `district_reservoir_map`, `groundwater_monthly` |
| Python | `preprocessing.py` (WaterProfile), `fuzzy/engine.py`, `dashboard_service` (irrigation alert), `simulation_service.WATER_LEVEL_STORAGE_PCT`, `district_service` |
| Frontend | dashboard water card, scenario water-level selector (levels become observed percentiles of the district's own reservoir record) |
| API | `/api/dashboard/{location}`, `/api/simulations/*` |
| Optimisation | fuzzy `water_storage` (reservoir) and a new groundwater term; districts with no mapped reservoir use groundwater only and say so |

### M5. `config.py` constants
| Constant | Replacement |
|---|---|
| `LOCATIONS`, `DATASET_KINDS`, `DISTRICT_COORDINATES` | `district` table (names/codes from the CSVs; coordinates from LGD/Census via scraper S12 - until fetched, weather panel disabled for that district) |
| `AG_SEASONS`, `SEASON_MONTH_MAP` | season crosswalk reference table (IMD seasons <-> crop seasons) |
| `DEFAULT_MAX_CANDIDATE_CROPS`, `MIN_CANDIDATE_CROPS` | derived: crops with official yield > 0 in the season, ranked by official revenue/area; limit becomes an optimiser parameter, not a data assumption |
| `FERTILIZER_PRICE_RS_PER_KG_NUTRIENT`, `LABOR_WAGE_RS_PER_DAY` | official notified prices (Dept of Fertilizers MRP; MGNREGA/Labour-bureau wage) in a `price_reference` table, scraper S9 |
| `RAINFALL_UTILIZATION_FACTOR`, `CARBON_*` | published coefficients (IMD/ICAR effective-rainfall method; IPCC EF1 + CEA grid emission factor) stored with citation; otherwise f3/f4 are reported as "not computable" |
| `RAINFALL_DEPENDENCY_FACTOR` (labels -> 0.1..1.0) | continuous `unirrigated_share` from official irrigated/unirrigated area; the label table disappears |

### M6. Fuzzy / TOPSIS / explanation parameters
| Item | Replacement |
|---|---|
| Fuzzy membership breakpoints (rainfall, storage, groundwater, soil, irrigation, production) | `fuzzy_calibration`: breakpoints = percentiles (e.g. P10/P50/P90) of the official distributions across 38 districts, except rainfall which keeps the **official IMD category bands**; calibrated by `scripts/calibrate_fuzzy.py`, stored with the dataset version |
| 26 rules and rule scenarios | expert-authored structure; kept and documented as method, not data (a rule base is not a dataset) |
| TOPSIS preference weights | decision-maker preferences; kept and documented as method parameters |
| Explanation thresholds (`STRONG_GOODNESS`, ...) | presentation thresholds; kept, listed in one place |
| `HISTORICAL_TOP_N`, district analytics thresholds | kept, documented |

### M7. Saved runs, fixtures, docs
| Artefact | Plan |
|---|---|
| `results/*` (9 runs) | move to `legacy/published-v1/results/`; new runs go to `optimisation_run` (DB) with the dataset versions used |
| `frontend/src/__fixtures__` | regenerate from official-data runs |
| paper tables/benchmarks | left frozen in docs, tagged `published-v1`; never imported at runtime |

## 3. Scrapers (Tasks 7-8) - all behind `app/scrapers/base.py`

Interface: `fetch() -> raw bytes + metadata`, `parse() -> DataFrame`, `validate()`, `store()`; robots.txt respected, rate-limited, ETag/If-Modified-Since caching, every call logged to `ingestion_log`, only an allow-list of official hostnames accepted (anything else raises).

| # | Scraper | Official source (to verify) | Format | Cadence | Fills |
|---|---|---|---|---|---|
| S1 | MSP | PIB press releases / DA&FW / cacp.gov.in | HTML, PDF | per season (Jun, Oct) | latest MSP (Kharif/Rabi 2026-27 missing from upload) |
| S2 | Crop prices & market arrivals | Agmarknet / data.gov.in resource API | JSON/CSV | daily | modal prices, arrivals |
| S3 | Weather | IMD (mausam.imd.gov.in) district forecast/observations | JSON/HTML | daily | replaces Open-Meteo (non-official) |
| S4 | Rainfall | IMD district-wise rainfall | HTML/XLS | monthly | rainfall_monthly beyond 2024-25, temperature |
| S5 | Reservoir levels | TN WRD / CWC | HTML/PDF | daily | reservoir_reading |
| S6 | Groundwater | CGWB / India-WRIS / TN WRD | CSV/HTML | monthly | groundwater_monthly + CGWB categories |
| S7 | Soil health | soilhealth.dac.gov.in | portal export | per cycle | soil_health |
| S8 | Crop advisories + fertiliser recommendations + crop agronomy | TNAU Agritech portal / TNAU crop production guide | HTML | yearly | agronomy_reference (water, N-P-K, duration) |
| S9 | Fertiliser prices, labour wage | Dept of Fertilizers, MoRD (MGNREGA) | PDF/HTML | yearly | price_reference |
| S10 | Government schemes | agricoop.gov.in / tn agriculture dept | HTML | quarterly | scheme list for advisories |
| S11 | Production & yield reports | DES / TN Dept of Economics & Statistics | PDF/XLS | yearly | crop_stat for further years, taluk level (Pollachi) |
| S12 | Seasonal advisories / district geography | IMD agromet advisories; LGD/Census | HTML/CSV | seasonal | advisories, district codes |

## 4. Optimisation redesign (Tasks 10-12)

- **f1 yield:** official season yield (kg/ha) x fuzzy confidence. Fully official.
- **f2 cost:** needs per-hectare inputs. Proposed: fertiliser (TNAU dose x notified price) + labour (official labour days x official wage) + irrigation (official electricity tariff/pumpset data) ; the official CACP cost of production (Rs/qtl, A2+FL) is used as an independent sanity check on the total, and as the cost basis directly for crops where TNAU data is missing. Crops with neither are excluded from the candidate set with an explicit "insufficient official data" reason.
- **f3 water:** crop water requirement (TNAU) minus effective rainfall (official actual rainfall x published factor), bounded by reservoir/groundwater availability from official data.
- **f4 environment:** leaching and carbon use published emission/leaching coefficients with citations; otherwise reported as "not computable".
- **Constraints:** land from official land use (a farm cannot exceed the district's net sown area); budget from the user.
- **Fuzzy:** membership functions calibrated from official distributions (M6); inputs rainfall departure, reservoir %, groundwater depth, irrigated share, production variability (state series CV), soil fertility (when Soil Health data exists), MSP margin and profitability.
- **Explainability:** every recommendation returns `datasets_used` (registry ids, report year, file hash), `values_used` (the exact numbers and units), `fuzzy_rules_fired` (existing rule trace), `why_ranked_higher` and `why_ranked_lower` (TOPSIS closeness decomposition against the adjacent districts/plans), plus data-quality caveats.

## 5. Execution order (each step is a separate commit; tests green before moving on)

1. Docs + branch (this commit).
2. DB layer, registry, base interfaces, Alembic migration `0001`.
3. District + crop canonicalisation tables (district names/codes from the CSVs).
4. Dataset pipelines: land_use, irrigation, rainfall, groundwater, reservoir, crops (district + state), each with validator/cleaner/loader/importer/service/cache/tests.
5. MSP extraction (text PDFs by parser, scanned PDFs transcribed and cross-checked) + `msp` pipeline.
6. Repository layer `app/data/official.py`; rewrite `preprocessing.py` on it with compatibility adapters so the services keep working.
7. Scrapers S1-S12 with fixture-based parser tests.
8. Fuzzy calibration; NSGA-II objectives; criteria/TOPSIS inputs.
9. Services, API (`provenance`, `/api/datasets`), explainability.
10. Frontend: catalogue-driven lists, provenance display, "Data not available" states; rebuild.
11. Move synthetic artefacts to `legacy/`, tag `published-v1`, delete loader paths to them; add a test that fails if any runtime code imports from `legacy/` or reads `data/raw/*_{crop,land,rainfall,water_availability}.csv`.
12. Full pytest + frontend tests + live server smoke test.

## 6. Decisions needed from you

| ID | Question | Proposed default |
|---|---|---|
| D1 | Pollachi has no official district record. | Official mode covers all 38 districts; Pollachi is listed as "taluk of Coimbatore - taluk data via S11 when available" and is not given invented figures. |
| D2 | Soil chemistry, crop water, fertiliser, labour, pesticide, duration are missing from the upload. | Scrape TNAU + Soil Health through the browser pane; crops/districts lacking official values are excluded or shown "Data not available". No gap is filled with an estimate. |
| D3 | The published paper results depend on the synthetic CSVs. | Tag `published-v1`, move the files to `legacy/` outside every import path, keep the paper tables frozen in docs. |
