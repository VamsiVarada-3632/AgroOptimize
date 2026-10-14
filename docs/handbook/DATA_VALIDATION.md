# Data Validation Review

Scope: the 16 files in `agrooptimize-backend/data/raw/`. Method: every check below was executed with pandas against the files on 2026-09-29; numbers are measured, not estimated. Column-level reference: [DATASETS.md](DATASETS.md).

## 1. Summary verdict

The files are **internally consistent** (derived columns match their formulas to <0.25 %) and **clean** (no missing values, no duplicates). But the time series show strong signatures of **synthetic construction**, the latest year is **explicitly estimated**, and the provenance of the 2020–2023 "course-provided" baseline is undocumented. For a system whose selling point is *uncertainty modelling*, the inputs carry almost no real year-to-year variation – so the fuzzy layer cannot demonstrate responding to real variability.

| ID | Finding | Severity | Affects |
|---|---|---|---|
| D1 | All 2024 rows are synthetic and 2024 is the default year | **High** | Every default request, dashboard trend |
| D2 | Reservoir storage identical in every year; groundwater level constant; Deficit_Surplus always 0 | **High** | Fuzzy water input is year-invariant |
| D3 | Crop yields flat 2020–2023; linear pH/OC trends | High | Research validity |
| D4 | Rainfall normals flat within met-seasons → extreme monthly deviations | High | Fuzzy rainfall input |
| D5 | Seasonal deviation computed as mean of monthly percentages | Medium | Fuzzy outputs shift up to 0.21 |
| D6 | Rabi uses Jan–Mar of the same calendar year; Rabi/Summer overlap | Medium | Seasonal aggregation |
| D7 | Pollachi rainfall ~40 % above its own stated normal every year | Medium | Plausibility |
| D8 | "MSP" for crops without a notified MSP; some values need checking | Medium | Unused today, matters if revenue is ever optimised |
| D9 | Agronomic oddities (wheat in TN Rabi, sugarcane as Kharif with January sowing, "Any" months) | Low | Credibility in viva |
| D10 | Provenance of the baseline undocumented; paper says "government" data | **High (integrity)** | Report / paper claims |
| D11 | Duplicate, divergent `datasets/` folder | Low | Confusion |
| D12 | Saved results & results write-ups come from an older dataset | Medium | Reproducibility of reported numbers |

## 2. Checks that pass

| Check | Result |
|---|---|
| Missing values (all 4 kinds) | 0 |
| Exact duplicate rows | 0 |
| `Production = Area_Harvested × Yield / 1000` | max rel. error 0.06 % |
| `Revenue(lakh) = Production × 10 × MSP / 10⁵` | max rel. error 0.22 % |
| `Area_Harvested ≤ Area_Sown` | 205/205 rows |
| `Irrigated + Rainfed = Agricultural` | exact |
| `Irrigation_Percent = Irrigated / Agricultural` | within 0.06 pp |
| `Deviation_mm = Monthly − Normal` | exact |
| `Storage% = Storage / Capacity` | within 0.014 pp |
| `Total_Demand = Irrigation + Drinking + Industrial` | exact |
| 12 months per location-year | yes |
| Every (location, season, year) has ≥2 crops | yes (Summer has exactly 2) |

## 3. Findings in detail

### D1 – Synthetic 2024 is the default
`data_source` for every 2024 row states the value was produced from 2023 (crop: ×1.03 yield and area; land: copied; rainfall and water: "repeated verbatim"). `preprocessing._resolve_year(year=None)` returns the latest year, 2024. Consequences:
* Every dashboard/analytics/comparison request and every farm-plan request without `year` runs on estimated inputs.
* `GET /api/dashboard/*` reports `yield_trend = "+3.0%"` for **every district** – that is the estimation factor, not an observed trend.
* Fuzzy outputs for 2024 are identical to 2023 (same rainfall/water inputs).

Mitigation implemented: `data_year_estimated` flag in region-profile, farm-plans and dashboard responses, plus a warning banner on the dashboard and a note in the Run Optimization result and downloaded report. **Decision for the team (TODO T-1):** either default to the latest *observed* year or remove the 2024 rows.

### D2 – Year-invariant water data
For all 48 location-months, `Storage_Percent` has one value across 2020–2024; `Groundwater_Level_mbgl` likewise. Season means per district (identical every year):

| | Kharif | Rabi | Summer |
|---|---|---|---|
| Coimbatore | 85.0 | 69.7 | 61.5 |
| Erode | 78.0 | 62.5 | 53.8 |
| Salem | 62.0 | 45.8 | 38.3 |
| Pollachi | 72.0 | 57.5 | 48.8 |

`Deficit_Surplus_MCM` is 0.0 in all 240 rows, and `Total_Demand_MCM == Canal_Release_MCM` exactly – i.e. demand was generated to equal supply.

### D3 – Flat or linear series
Median year-over-year yield ratio is exactly 1.00 for 2020→21, 21→22, 22→23. Soil pH increases by exactly 0.1 per year and organic carbon by 0.01 per year in all four districts. Real district statistics do not behave this way. The median coefficient of variation of monthly rainfall across 2020–2023 is 0.09 – very low for Tamil Nadu monsoon rainfall.

### D4 – Flat rainfall normals
`Normal_Rainfall_mm` is one value per meteorological season, e.g. Coimbatore Jun–Sep = 95 mm each month. Summing gives exactly the stated `Annual_Normal_mm`. Real monthly normals vary within a season, so monthly `Deviation_Percent` ranges from −93 % to +339.5 %. The fuzzy input universe is clipped to ±60 %, so Pollachi Summer (+105 % to +121 %) is saturated at +60.

Structural effect: every Kharif season of Coimbatore and Erode shows a ~−40 % "deficit" in every year, and every Summer a surplus – the classification reflects how the normals were built, not weather.

### D5 – Averaging percentages
`avg_deviation_percent = mean(monthly Deviation_Percent)`. The hydrologically standard seasonal deviation is `(Σ actual − Σ normal) / Σ normal`. Re-running the fuzzy engine for all 60 location-season-years with the total-based deviation changes:

| Metric | Max absolute change |
|---|---|
| yield_confidence | 0.059 |
| irrigation_risk | **0.213** (Erode Summer 2020: 0.152 → 0.365) |

Examples: Coimbatore Rabi 2023 is −11.1 % by the current method but +1.8 % by totals; Salem Summer 2023 +12.3 % vs −3.1 % (label flips surplus→normal). Kharif is unaffected because its four normals are equal. Not changed in code because it alters every result; recommended fix in TODO T-3.

### D6 – Season windows
Rabi (Oct–Mar) takes January–March from the **same** calendar year as October–December, so "Rabi 2023" mixes early-2023 and late-2023 weather rather than one contiguous season (Oct 2023–Mar 2024). February and March are counted in both Rabi and Summer.

### D7 – Pollachi rainfall vs normal
Observed annual totals 1,016–1,055 mm against a stated annual normal of 750 mm (+35–41 % every year), while the other three districts are consistently 5–15 % *below* their normals. Either the normal or the observations are mis-specified.

### D8 – Price column
`MSP_Rs_Qtl` is filled for banana, coconut, mango, tapioca, vegetables, turmeric and fodder, for which the Government of India does not notify an MSP (coconut is supported as *copra*, not per quintal of nuts). For notified crops some values match published MSPs for the stated marketing year and others appear to be from different years (e.g. maize 2023 = ₹1,962, sunflower 2023 = ₹6,015). These should be checked against the CACP / PIB MSP notifications before any revenue objective is introduced. **Currently the column is loaded but not used by any objective.**

### D9 – Agronomic plausibility
* Wheat is listed in Coimbatore Rabi; wheat is a very minor crop in Tamil Nadu.
* Sugarcane appears under Kharif (Coimbatore, Erode, Pollachi) and Rabi (Salem) with January sowing and 365-day duration – a 12-month crop cannot be a seasonal option alongside 100-day crops without land-occupancy constraints.
* Banana, coconut, mango: perennial crops treated as seasonal land allocations.
* Sowing/Harvest "Any".

### D10 – Provenance
Rows 2020–2023 say "course-provided". The team's own `docs/dataset_description.md` flags that the origin "was not independently verified" and warns against claiming data.gov.in/CGWB/TNAU sources. The reference paper's abstract states the system "makes use of agricultural databases given by the government", and `docs/literature_survey.md` claims validation on "real … Tamil Nadu district-level data". Findings D2–D4 are hard to reconcile with real statistics. **This is the single most important item to settle before the viva** (TODO T-2).

### D11 – Divergent duplicate
`final_year_project/datasets/` differs from `data/raw/` in schema, row count and rainfall normals. Nothing loads it.

### D12 – Non-reproducible reported results
All 8 JSON runs in `results/` and the tables in `agrooptimize-backend/docs/results/*.md` / `docs/api_docs.md` report e.g. Coimbatore Kharif 2023 storage 94.7 %, yield confidence 0.775. The current data yields 85.0 % and 0.620. Those write-ups must be regenerated from the current code and data.

## 4. What is actually validated at runtime

Only file existence (`loader._read_kind`) and the presence of rows for the requested slice (`get_region_season_profile` raises `ValueError` → HTTP 400). There is no schema, type or range validation.

## 5. Recommended actions (ordered)

1. Decide and document the provenance of the 2020–2023 data (D10).
2. Make the default year the latest observed year, or drop 2024 (D1).
3. Replace water and rainfall with official series (IMD monthly rainfall and normals; CWC/India-WRIS reservoir storage; CGWB groundwater) – this is what gives the fuzzy layer genuine variability (D2, D4).
4. Compute seasonal deviation from totals and make Rabi span Oct(Y)–Mar(Y+1) (D5, D6).
5. Add a schema/range validation step (pandera or explicit asserts) at load time.
6. Delete or clearly archive `datasets/` (D11) and regenerate the results write-ups (D12).
