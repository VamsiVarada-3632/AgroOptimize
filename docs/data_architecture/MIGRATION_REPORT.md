# Official-data migration report

Official government datasets are the only runtime data source. The synthetic v1 data is tagged `published-v1` and archived in `legacy/` (paper reproduction, comparison, debugging, history only). `tests/test_no_synthetic_runtime.py` fails if any runtime module imports it.

## 1. Synthetic datasets replaced

| Old file (now `legacy/data/raw/`) | Replaced by |
|---|---|
| coimbatore_crop.csv | crop_production + msp + agronomy_tnau + cost of cultivation |
| coimbatore_land.csv | land_use |
| coimbatore_rainfall.csv | IMD rainfall |
| coimbatore_water_availability.csv | reservoir storage |
| erode_crop.csv | crop_production + msp + agronomy_tnau + cost of cultivation |
| erode_land.csv | land_use |
| erode_rainfall.csv | IMD rainfall |
| erode_water_availability.csv | reservoir storage |
| pollachi_crop.csv | crop_production + msp + agronomy_tnau + cost of cultivation |
| pollachi_land.csv | land_use |
| pollachi_rainfall.csv | IMD rainfall |
| pollachi_water_availability.csv | reservoir storage |
| salem_crop.csv | crop_production + msp + agronomy_tnau + cost of cultivation |
| salem_land.csv | land_use |
| salem_rainfall.csv | IMD rainfall |
| salem_water_availability.csv | reservoir storage |

## 2. Official datasets in use

| Key | Source | File | Report year | Rows | Used by |
|---|---|---|---|---|---|
| crop_production | Tamil Nadu Data / Dept of Economics & Statistics - Season & Crop Report | crops_by_district.csv | 2024-25 | 12558 | Preprocessing (candidate crops, yields, rainfed share); NSGA-II (f1 yield, f2 cost, f3 irrigated area); TOPSIS; Explainability; District Intelligence; Comparison; History; Dashboard; Simulation |
| crop_state_series | Tamil Nadu Data / Dept of Economics & Statistics - Season & Crop Report | crops_state_series.csv | 2024-25 | 3420 | Explainability (historical context); District Intelligence (yield stability, trends); Simulation (historical) |
| land_use | Tamil Nadu Data / Dept of Economics & Statistics - Season & Crop Report | land_use.csv | 2024-25 | 1833 | Preprocessing; District Intelligence (overview); Dashboard |
| irrigation | Tamil Nadu Data / Dept of Economics & Statistics - Season & Crop Report | irrigation.csv | 2024-25 | 8775 | Preprocessing (irrigated share); Fuzzy (rainfed dependency); NSGA-II (f3); Dashboard; Explainability |
| rainfall | IMD district rainfall as published in the Season & Crop Report | rainfall_by_district.csv | 2024-25 | 663 | Fuzzy (rainfall deviation input); Preprocessing; Explainability; District Intelligence; Dashboard; Simulation (rainfall lever) |
| groundwater | Tamil Nadu Data - groundwater level (as supplied in GOVT DATASETS) | ground_water_level.csv | 2024-25 | 507 | Preprocessing (water profile); District Intelligence; Dashboard |
| reservoir_storage | Tamil Nadu Water Resources Department - daily reservoir levels | reservoir_daily.csv | 2024-25 | 11153 | Fuzzy (water-storage input); Preprocessing; Explainability; District Intelligence; Dashboard; Simulation (water lever) |
| msp_and_cost | CACP / Dept of Agriculture MSP notifications (official PDFs, KMS/RMS 2022-23 .. 2025-26) | msp_extracted.csv | 2024-25 | 88 | Preprocessing; NSGA-II (f2 cost); TOPSIS (market price, income); Explainability (economics); Simulation (market lever); District Intelligence (market) |
| agronomy_doses | TNAU Crop Production Guide (agritech.tnau.ac.in) | agronomy_tnau.csv | 2024-25 | 31 | Preprocessing (dose rules); NSGA-II (f4 fertiliser); TOPSIS (soil match); Explainability |
| soil_health | Soil Health Card portal (soilhealth.dac.gov.in) - nutrient dashboard 2024-25 | soil_health_tn.csv | 2024-25 | 37 | Fuzzy (soil fertility input); Preprocessing; TOPSIS (soil criterion); Explainability; District Intelligence; Dashboard |

## 3. Features still disabled (no fallback to synthetic data)

| Feature | Missing official dataset | Source to scrape | Scope |
|---|---|---|---|
| Live weather widget (/api/weather) | IMD district weather: observed temperature, humidity, forecast | mausam.imd.gov.in | weather widget only |
| Crop water requirement in mm / irrigation litres (NSGA-II f3) | Crop-wise water requirement (mm) - TNAU guide gives schedules, not totals | TNAU crop guides (per-crop pages) / Agriculture Dept | f3 uses irrigated area share instead |
| Fertiliser-price scenarios | Notified fertiliser prices (Dept. of Fertilizers) - not loaded | fert.nic.in | scenario lever only; cost objective uses CACP cost of cultivation |
| Labour / pesticide cost, crop duration, sowing & harvest months | Per-crop cultivation calendar and input costs (TNAU / CACP state cost tables) | TNAU, CACP | display fields only |
| Crops without TNAU dose or CACP cost (e.g. horticulture, coconut, sugarcane, pulses beyond MSP list) | TNAU horticulture guide doses; MSP/FRP and cost of cultivation for the report year | agritech.tnau.ac.in/pdf/HORTICULTURE.pdf, CACP | crop excluded from candidate lists (reason shown) |
| Cotton and rice as optimisation candidates | Official conversion factors: kapas to lint (ginning outturn) and paddy to rice (milling outturn); official yield is lint / rice, MSP and CACP cost are per quintal kapas / paddy | CACP / Dept. of Agriculture TN / Season & Crop Report notes | crop excluded from candidate lists (reason shown); nothing converted with an assumed factor |
| Reservoir storage for Kharif 2024 and for districts without a mapped reservoir | Reservoir daily levels before 2025-01-01; district command-area map | TN Water Resources Dept | fuzzy stage skipped for the district/season (yield left unadjusted, flagged) |
| District year-on-year trends and multi-year history | Season & Crop Reports of earlier years (district level) | Dept. of Economics & Statistics TN | trend widgets; state-level series is available |
| Taluk-level analysis (Pollachi) | Taluk-wise statistics | Dept. of Economics & Statistics TN | Pollachi reported as 'taluk data not available' |

## 4. Remaining TODO

- Frontend (React/Vite) not yet migrated: rename `water_liters`->`irrigated_ha`, drop hard-coded `DISTRICTS` (api.js) and `FALLBACK_CROPS` (Auth/ProfileSetup/Settings views), drive lists from `/api/catalog`, show 'Data not available' on 501/400 responses, weather widget 501 state.
- Load TNAU horticulture doses, official kapas->lint and paddy->rice conversion factors, reservoir->district map and pre-2025 reservoir levels, IMD weather, fertiliser prices, labour/pesticide costs, earlier Season & Crop Reports, taluk statistics.
- Chennai and The Nilgiris return HTTP 400 ('complete official data'): fewer than 2 crops have all required official fields.
- Fuzzy stage is applied only where official reservoir data exist (9 districts, Rabi); elsewhere flagged 'not applied' with neutral confidence 1.0.
