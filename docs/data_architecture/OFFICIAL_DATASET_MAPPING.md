# Official Dataset Mapping (Task 1)

Inventory of every file in `GOVT DATASETS/`, profiled on 2026-11-12 by reading the files themselves (row counts, null counts, value ranges and unit sets below are measured, not assumed). These files are the only source of truth for the migration.

Provenance note: the seven CSVs carry `report_year = 2024-25` and `printed_page` columns (pages 96-356), i.e. they are tables extracted from one annual Tamil Nadu statistical publication. The CSVs do not say which publication, and the reservoir file has no source column other than `source_updated`. Record the exact publisher and URL for each file in `dataset_registry` (see MIGRATION_PLAN.md) before the viva.

## 1. Coverage at a glance

| Dimension | What the official files contain |
|---|---|
| Geography | 38 Tamil Nadu districts + a "Tamil Nadu (State)" total. **No Pollachi** (a taluk of Coimbatore district). Tiruppur is separate from Coimbatore. |
| Time (district tables) | One report year only: **2024-25**. Rainfall Jun-2024..May-2025; groundwater Jul-2024..Jun-2025. |
| Time (state series) | 1965-66 to 2024-25, 19 crops/aggregates. |
| Time (reservoirs) | Daily, 2025-01-01 to 2026-11-11 (587 days x 19 reservoirs, no gaps). |
| Seasons | Crop tables: Kharif, Rabi, Rice sub-seasons (Kar/Kuruvai/Sornavari, Samba/Thaladi/Pishanam, Navarai/Kodai). **No "Summer" season.** Area has no season split (only Total / Irrigated / Unirrigated). |
| NOT present | Soil pH, organic carbon, N/P/K status, soil type; crop water requirement; fertiliser doses; pesticide cost; labour days; crop duration, sowing/harvest months; temperature, humidity, rainy days; market (mandi) prices; cost of cultivation per hectare; groundwater status category. |

## 2. File-by-file mapping

### 2.1 `crops_by_district.csv` - district crop area / production / yield
- **Contains:** 12,558 rows. Columns: report_year, crop (52), group (7), measure (area / production / yield), season_or_split (9 values), unit (11), district_code, district (38 + State), value, printed_page.
- **Module:** candidate crops, yield coefficient (f1), crop suitability, rainfall dependency (derived), district overview, trends, dashboard KPIs, explainability.
- **Useful columns:** crop, measure, season_or_split, unit, district, value.
- **Unnecessary:** report_year (constant), group (keep only for crop-type label), printed_page (provenance only), district_code (keep as join key; NaN for the 322 State rows).
- **Cleaning:** 51 null `value` cells -> keep null, never zero-fill (null = not reported). Normalise units to a base (cotton bales of 170 kg lint -> tonnes lint = bales x 0.170; coconut lakh nuts -> nuts; sugarcane "tonnes of cane"; yield "tonnes / ha" -> kg / ha). Map crop names to a canonical crop id. Pivot season_or_split into `season` (Kharif/Rabi/All) and `rice_subseason`; `Irrigated`/`Unirrigated`/`Total` are area splits, not seasons. Validate production ~= area x yield (tolerance for rounding), yield within crop-specific plausible bounds, irrigated + unirrigated = total.
- **Update frequency:** annual (publication lags the season by ~1 year). Scraper cadence: yearly.
- **Joins:** district name/code with every other district table; crop name with MSP table (via `crop_alias`); district -> reservoir via `district_reservoir_map`.

### 2.2 `crops_state_series.csv` - state long-run series
- **Contains:** 3,420 rows, 19 crops/aggregates (Rice, Jowar, Bajra, Ragi, Maize, Cotton, Sugarcane, Groundnut, pulses, Foodgrains, Total cereals, ...), 1965-66..2024-25, area/production/yield (10 units, including "tonnes (in terms of rice)" and "kg of gur / ha").
- **Module:** fuzzy production ranges and yield variability (coefficient of variation), trend analysis, uncertainty bounds; explainability ("state yield has varied X-Y").
- **Useful:** crop, year, measure, value, unit. **Unnecessary:** report_year, printed_page.
- **Cleaning:** year "1965-66" -> integer start year; drop aggregate rows (Foodgrains, Total cereals/pulses) from crop-level stats; unit normalisation as above; check yield = production/area.
- **Update:** annual. **Joins:** crop name with 2.1 and the MSP table.

### 2.3 `ground_water_level.csv`
- **Contains:** 507 rows: district x 12 months (Jul-24..Jun-25) + "Yearly average"; `level_m` = depth to water level (metres below ground level; 0.87-11.2). 12 null level_m (13 null district_code = State rows).
- **Module:** water-security input to fuzzy water availability (new: groundwater feeds the water input), dashboard irrigation alert, district intelligence, scenario "water availability".
- **Useful:** district, period, level_m. **Unnecessary:** report_year, printed_page.
- **Cleaning:** parse "Jul-24" to a month date; drop the "Yearly average" row from the monthly series (keep as a check value); nulls stay null; range check 0 < level < 100 m. Deeper = scarcer: invert when building a 0-100 availability index. Derive a status category from *published CGWB depth bands* (to be scraped from CGWB), never from invented cut-offs.
- **Update:** monthly (CGWB / TN WRD). Scraper cadence: monthly. **Joins:** district.

### 2.4 `irrigation.csv`
- **Contains:** 8,775 rows in five tables (III-A canals/tanks/reservoirs/wells counts, III-B..III-E net and gross area irrigated by source, irrigation intensity, % irrigated). 21 groups, 17 items, 23 measures, units ha / km / number / % / ratio. 225 null district_code (State rows), 117 null values.
- **Module:** irrigation share per district (-> irrigated land, rainfed share, rainfall dependency), irrigation-source mix (canal/tank/well), irrigation cost context, fuzzy irrigation ranges, district intelligence.
- **Useful:** net area irrigated by source, gross area irrigated, irrigation intensity, % of net area irrigated to net area sown, pumpset counts (electric/diesel). **Unnecessary:** canal length/number detail, wells not in use, domestic/industrial wells (kept in the warehouse, not loaded into the optimiser).
- **Cleaning:** tidy long form on (table, group, item, measure); the item/measure labels are not unique across tables, so key on all four; nulls stay null; validate net <= gross, % in [0,100], intensity >= 1 (ratio).
- **Update:** annual. **Joins:** district; with 2.5 (net area sown) for % irrigated.

### 2.5 `land_use.csv`
- **Contains:** 1,833 rows, 16 land-use categories (total geographical area, forest, barren, non-agricultural uses incl. sub-items, cultivable waste, pastures, tree crops, current fallow, other fallow, net area sown, area sown more than once, gross area sown), each as area_ha, pct_of_district_area, pct_of_state_area.
- **Module:** total / agricultural / fallow / forest / waste land, land budget for the farm-size sanity check, cropping intensity (gross/net sown), district overview.
- **Useful:** area_ha rows (the two pct measures are re-derivable). **Unnecessary:** pct_of_state_area (derivable).
- **Cleaning:** validate that the categories sum to total geographical area (the Salem rows do: forest 125,682 + barren 38,198 + non-agri 67,904 + waste 5,617 + pasture 4,200 + tree crops 2,696 + fallows 67,741 + net sown 208,492 = 520,530); gross sown = net sown + sown more than once.
- **Update:** annual. **Joins:** district; cropping intensity with 2.4.

### 2.6 `rainfall_by_district.csv`
- **Contains:** 663 rows; district x {Jun-24..May-25 monthly, 4 season totals, whole-year}; actual_mm, **normal_mm (official IMD normal)**, pct_deviation. actual 0-2,382.9 mm; pct_deviation -100..+801.9.
- **Module:** fuzzy `rainfall_dev` input (now the official % departure), effective rainfall for the water objective (f3), rainfall scenarios, district climate, weather panel history.
- **Useful:** district, season, period, actual_mm, normal_mm, pct_deviation. **Unnecessary:** printed_page; recompute pct_deviation from actual/normal and keep the printed one as a check.
- **Cleaning:** parse "Jun 2024" to a month; separate monthly rows from "... total" rows; check season totals equal the sum of their months; a month with a very small normal (e.g. 2.7 mm) produces departures of +800 %: use *seasonal* departure for the fuzzy input, not the monthly one. Map IMD seasons (South-West Monsoon, North-East Monsoon, Winter, Hot-Weather) onto crop seasons through a documented crosswalk table.
- **Update:** monthly (IMD district-wise rainfall); the file is a yearly snapshot. **Joins:** district.

### 2.7 `reservoir_daily.csv`
- **Contains:** 11,153 rows; 19 reservoirs (15 Tamil Nadu, 4 Karnataka Cauvery-basin), 587 days. level_ft, storage_mcft, capacity_mcft, full_depth_ft, inflow/outflow cusecs (537/745 nulls), last-year level and storage for the same date.
- **Module:** reservoir storage % (fuzzy `water_storage` input), inflow trend, year-on-year storage comparison, dashboard irrigation alert, district intelligence, water scenarios.
- **Useful:** all except `source_updated` (equals date). **Unnecessary:** the four Karnataka reservoirs for district modelling (Harangi, Hemavathy, KRS, Kabini) - keep for Mettur inflow context.
- **Cleaning:** storage_pct = storage_mcft / capacity_mcft x 100, clamped and flagged when storage exceeds capacity (Mettur reaches 93,678 vs capacity 93,470); Parambikulam has two capacity values (use the capacity on each date); strip footnote asterisks from names ("Amaravathi*", "Periyar**"); 1 MCFT = 0.0283168 MCM; cusecs -> m3/s x 0.0283168.
- **Update:** daily. Scraper cadence: daily. **Joins:** district via `district_reservoir_map` (reference table, to be verified against TN WRD command-area lists): Aliyar & Parambikulam & Sholayar -> Coimbatore; Thirumurthy & Amaravathi -> Tiruppur; Bhavanisagar -> Erode; Mettur -> Salem; others listed in the plan.

### 2.8 MSP / price PDFs (8 files, 7 distinct - the two `MSP 2025-2026_241017_102537` files are byte-identical, same md5)

| File | Content | Text layer? | Use |
|---|---|---|---|
| `MSP 2025-2026_241017_102537.pdf` (+ `(1)` duplicate) | PIB 16-Oct-2024: Rabi MSP, marketing season 2025-26, with cost of production, margin over cost %, previous-year MSP | yes | RMS 2025-26 MSP + cost (A2+FL) |
| `Press Release_Press Information Bureau.pdf` | PIB 19-Jun-2024: Kharif MSP 2024-25 with cost, margin, 2023-24 MSP | yes | KMS 2024-25 MSP + cost |
| `MSP-Notification-KMS-2025-26-English.pdf` | DA&FW notification 2-Jun-2025: Kharif MSP 2025-26 | **scanned** (OCR needed) | KMS 2025-26 MSP |
| `MSP price 2023- 2024.pdf` | Kharif MSP 2023-24 + 2018-19..2023-24 history table | scanned | MSP history |
| `Revised MSP notification_1_230322_223200.pdf` | Kharif MSP 2022-23 + 2018-19..2022-23 table | scanned | MSP history |
| `English MSP 2021 new.pdf` | Rabi MSP RMS 2022-23 + table 2017-18..2021-22 | scanned | MSP history |
| `Copra Report - 2024 Season.pdf` | CACP Price Policy for Copra, 2024 season (148 pp): wholesale prices, recommended MSP (milling copra Rs 11,160/qtl, ball copra Rs 12,000/qtl), cost of cultivation (Table 5.1, all-India average) | yes | coconut/copra MSP and cost |

- **Module:** price floor and indicative revenue (`criteria.market_price` / `income`), explainability economics, scenario "market price" step (replaces the old synthetic year-on-year step), comparison "market" axis.
- **Useful:** crop, variety, MSP Rs/quintal, cost of production Rs/quintal (A2+FL), margin %, marketing season.
- **Cleaning:** text PDFs -> table extraction; scanned PDFs -> OCR **plus manual verification of every figure against the page image** (OCR output on these scans is unreliable: e.g. "Wheat 2015 / 1635", garbled rows). Normalise crop names (Paddy Common/Grade A, Jowar Hybrid/Maldandi, cotton medium/long staple -> canonical ids), season (KMS/RMS) and marketing year; validate MSP(t) - MSP(t-1) = published increase and margin = MSP/cost - 1.
- **Gaps:** the newest announcements (Rabi 2026-27, announced Oct 2025, and Kharif 2026-27, announced mid-2026) are not in the upload, and Rabi 2024-25 only appears as the "previous year" column in the 2025-26 release. MSP covers only 22 mandated crops + copra + sugarcane FRP: **there is no official price for banana, tapioca, turmeric (not MSP crops), vegetables, etc.** Those need Agmarknet modal prices (scraper) or must be reported as "no official price".
- **Update:** twice a year (Kharif ~June, Rabi ~October) + copra annually. **Joins:** crop id.

## 3. Join graph

```
district (38 + State)  <-- canonical key: LGD-style district_code + normalised name
 |-- crops_by_district --(crop id)--> msp_price --(crop id)--> crops_state_series
 |-- land_use  --(net area sown)--> irrigation (% irrigated, intensity)
 |-- rainfall_by_district (season crosswalk to crop seasons)
 |-- ground_water_level
 `-- district_reservoir_map --> reservoir_daily (storage %, inflow)
```

## 4. Which model input each official file now feeds

| Optimiser / fuzzy input | Official source | Status |
|---|---|---|
| Yield per crop (f1) | crops_by_district yield (season-wise) | covered |
| Confidence via fuzzy rainfall deviation | rainfall_by_district seasonal % departure | covered |
| Confidence via fuzzy water storage | reservoir_daily storage % (+ groundwater depth) | covered |
| Confidence via fuzzy soil fertility | *none* | **missing** (Soil Health Card needed) |
| Rainfall dependency | derived: unirrigated share of crop area (2.1) | covered (derived) |
| Effective rainfall (f3) | rainfall actual_mm x utilisation factor | factor is a modelling parameter, see plan |
| Crop water requirement (f3, f4) | *none* | **missing** (TNAU crop guides) |
| Fertiliser doses (f2, f4) | *none* | **missing** (TNAU / ICAR recommendations) |
| Production cost (f2) | cost of production Rs/quintal from MSP releases (all-India) | partial (not district-specific; see plan for the f2 redesign decision) |
| Labour days, pesticide cost | *none* | **missing** |
| Prices / revenue | MSP PDFs (22 crops + copra) | partial |
| Irrigation, land | irrigation.csv, land_use.csv | covered |
