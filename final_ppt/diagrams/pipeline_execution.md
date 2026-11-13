# Pipeline execution snapshot

One complete optimisation on the official data, recorded by `final_ppt/assets/scripts/run_pipeline_snapshot.py` through the real FastAPI app and pipeline modules. Raw record: `final_ppt/assets/data/pipeline_run.json`.

**Request:** `{"location": "Salem", "season": "Rabi", "year": 2024, "total_land_ha": 5.0, "preference": "balanced", "save_results": true, "client_id": "ppt-snapshot"}`  
**Engine:** NSGA-II mode `original`, seed 42, fuzzy model `official`. Re-running the same request reproduced the same top plan: True.

| # | Stage | Time | What happened |
|---|---|---|---|
| 1 | Input | – | POST /api/farm-plans  {location: Salem, season: Rabi, year: 2024, total_land_ha: 5, preference: balanced, save_results: true} |
| 2 | Validation | 63.2 ms | Request accepted by the Pydantic FarmPlanRequest model and the district / season checks.<br>Rejected example → HTTP 422: Salem, Rabi, -1 ha — Input should be greater than 0<br>Rejected example → HTTP 400: Salem, Summer, 5 ha — Unknown season 'Summer'.<br>Rejected example → HTTP 400: Pollachi, Rabi, 5 ha — Pollachi is a taluk of Coimbatore district. |
| 3 | Official dataset loading | 668.1 ms | 10 registered official datasets, 39,065 clean rows (report year 2024-25), each with a sha256 in dataset_registry.<br>Pipeline frames built from the database: crop 985, land 76, rainfall 456, water 456 rows.<br>9 features disabled because their official dataset is missing (no estimates). |
| 4 | Preprocessing & crop filtering | 2.9 ms | Salem · Rabi 2024 · months Oct, Nov, Dec, Jan, Feb<br>Rainfall 544.8 mm vs IMD normal 341.6 mm (+59.5 %) · reservoir storage 87.44 % (Mettur) · Soil Health Card fertility index 30.57 (N Low, P Medium, K High)<br>Candidates (6): maize, groundnut, jowar, ragi, red gram, green gram<br>Excluded (8): cotton, cowpea, horse gram, onion, other pulses, rice, samai, varagu — e.g. cotton: no official kapas-to-lint conversion factor loaded |
| 5 | Fuzzy inference | 166.3 ms | Model 'official': rainfall surplus, water high, soil medium → yield confidence 0.532, irrigation risk 0.12 (applied: True) |
| 6 | NSGA-II optimisation | 329.0 ms | Population 80 × 200 generations = 16,000 evaluations · crossover 0.85, mutation 0.12 · seed 42<br>80 Pareto-optimal plans, constraint satisfaction 100% · hypervolume ratio 0.876, IGD+ 0.116, spread 0.527 |
| 7 | TOPSIS ranking | inside the API call | 50 plans ranked with the 'Balanced' profile: weights yield 0.300, production cost 0.233, irrigated area 0.233, environmental impact 0.233<br>Top closeness: #1 0.6398 · #2 0.6354 · #3 0.6350 · #4 0.6266 · #5 0.6227 |
| 8 | Recommendation | 515.8 ms | Rank 1: ragi 82.5 % + green gram 17.5 % · yield 15.776 t · cost ₹880,840 · irrigated 1.244 ha-eq. · nutrients 377.253 kg<br>High yield, High cost, Low water use, Low environmental impact (confidence: moderate) · saved as run salem_rabi_2024_20261112T185732Z (HTTP 200; time = whole API call) |
| 9 | Explanation | 34.3 ms | GET /api/results/{run_id}/explanation → Recommended, confidence 60.7 %, 5 reasons, 4 risks, 19 sections<br>Reasons: Best balance for the chosen preference; High yield; Low irrigation demand; Low fertiliser load; Soil supports the crops<br>Confidence components: climate_soil 51.4, data_quality 100, convergence 92.7, constraints 100, historical 0, robustness 20<br>Per-crop official evidence: ragi — rainfall supported, soil caution, water supported, budget info, fertiliser info, market_price unavailable, msp supported, duration info, yield caution, risks caution; green gram — rainfall supported, soil caution, water supported, budget info, fertiliser info, market_price unavailable, msp supported, duration info, yield caution, risks caution |

## Excluded crops and reasons

- **cotton**: price/yield unit basis differs and no official conversion factor is loaded: official yield is kg of lint/ha; MSP and CACP cost are per quintal of kapas (seed cotton)
- **cowpea**: no complete TNAU fertiliser recommendation (no TNAU dose for this crop); no MSP for the report year in the official MSP notifications
- **horse gram**: no complete TNAU fertiliser recommendation (no TNAU dose for this crop); no MSP for the report year in the official MSP notifications
- **onion**: no complete TNAU fertiliser recommendation (no TNAU dose for this crop); no MSP for the report year in the official MSP notifications
- **other pulses**: no complete TNAU fertiliser recommendation (no TNAU dose for this crop); no MSP for the report year in the official MSP notifications; irrigated/unirrigated area not reported
- **rice**: price/yield unit basis differs and no official conversion factor is loaded: official production/yield is in terms of rice; MSP and CACP cost are per quintal of paddy
- **samai**: no complete TNAU fertiliser recommendation (no TNAU dose for this crop); no MSP for the report year in the official MSP notifications
- **varagu**: no complete TNAU fertiliser recommendation (no TNAU dose for this crop); no MSP for the report year in the official MSP notifications

## Notes from the preprocessing stage

- Reservoir storage covers 2 of the season's 5 months (the official daily reservoir record starts 2025-01-01).
- Seasons follow the official reports (Kharif/Rabi); rice uses Kar/Kuruvai/Sornavari for Kharif and Samba/Thaladi/Pishanam for Rabi.

## Disabled features reported by GET /api/datasets

- **Live weather widget (/api/weather)**: missing IMD district weather: observed temperature, humidity, forecast (source: mausam.imd.gov.in; scope: weather widget only)
- **Crop water requirement in mm / irrigation litres (NSGA-II f3)**: missing Crop-wise water requirement (mm) - TNAU guide gives schedules, not totals (source: TNAU crop guides (per-crop pages) / Agriculture Dept; scope: f3 uses irrigated area share instead)
- **Fertiliser-price scenarios**: missing Notified fertiliser prices (Dept. of Fertilizers) - not loaded (source: fert.nic.in; scope: scenario lever only; cost objective uses CACP cost of cultivation)
- **Labour / pesticide cost, crop duration, sowing & harvest months**: missing Per-crop cultivation calendar and input costs (TNAU / CACP state cost tables) (source: TNAU, CACP; scope: display fields only)
- **Crops without TNAU dose or CACP cost (e.g. horticulture, coconut, sugarcane, pulses beyond MSP list)**: missing TNAU horticulture guide doses; MSP/FRP and cost of cultivation for the report year (source: agritech.tnau.ac.in/pdf/HORTICULTURE.pdf, CACP; scope: crop excluded from candidate lists (reason shown))
- **Cotton and rice as optimisation candidates**: missing Official conversion factors: kapas to lint (ginning outturn) and paddy to rice (milling outturn); official yield is lint / rice, MSP and CACP cost are per quintal kapas / paddy (source: CACP / Dept. of Agriculture TN / Season & Crop Report notes; scope: crop excluded from candidate lists (reason shown); nothing converted with an assumed factor)
- **Reservoir storage for Kharif 2024 and for districts without a mapped reservoir**: missing Reservoir daily levels before 2025-01-01; district command-area map (source: TN Water Resources Dept; scope: fuzzy stage skipped for the district/season (yield left unadjusted, flagged))
- **District year-on-year trends and multi-year history**: missing Season & Crop Reports of earlier years (district level) (source: Dept. of Economics & Statistics TN; scope: trend widgets; state-level series is available)
- **Taluk-level analysis (Pollachi)**: missing Taluk-wise statistics (source: Dept. of Economics & Statistics TN; scope: Pollachi reported as 'taluk data not available')

## Official datasets in the registry

| Dataset | File | Report year | Clean rows | sha256 (first 12) |
|---|---|---|---|---|
| crops_by_district | crops_by_district.csv | 2024-25 | 12,558 | 67415e6a9ea2 |
| crops_state_series | crops_state_series.csv | 2024-25 | 3,420 | e5db6eca1a41 |
| land_use | land_use.csv | 2024-25 | 1,833 | 22a9488e919d |
| irrigation | irrigation.csv | 2024-25 | 8,775 | 49f47e6a1e60 |
| rainfall_by_district | rainfall_by_district.csv | 2024-25 | 663 | e4e98b9e6aeb |
| ground_water_level | ground_water_level.csv | 2024-25 | 507 | 10f22112238a |
| reservoir_daily | reservoir_daily.csv | 2024-25 | 11,153 | 4a2cd24d7c0a |
| msp_extracted | msp_extracted.csv | 2024-25 | 88 | f9891161881d |
| agronomy_tnau | agronomy_tnau.csv | 2024-25 | 31 | 1835903c3c6c |
| soil_health_tn | soil_health_tn.csv | 2024-25 | 37 | d036673888be |

Timing notes: times are measured with `time.perf_counter` in one process. The fuzzy time includes building the `official` model on first use; the NSGA-II time is the run's own `optimize_seconds`; the recommendation time is the whole `POST /api/farm-plans` call (preprocessing, fuzzy, NSGA-II with convergence tracking, TOPSIS and saving the run).
