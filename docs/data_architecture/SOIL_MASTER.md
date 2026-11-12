# soil_master.csv - Soil Health Card integration

Source: Soil Health Card portal (https://soilhealth.dac.gov.in/), district nutrient dashboard, cycle 2024-25 (`data/official/raw/soil_health_tn.csv`, 37 districts). Derived file: `data/official/raw/soil_master.csv` (`scripts/build_soil_master.py`). Loader `app/datasets/soil_master.py`, validator `app/datasets/soil_master_validator.py`, tests `tests/datasets/test_soil_master.py`.

## What the official feed contains
Counts of tested samples per class, per district: pH (acidic / neutral / alkaline), organic carbon, N, P, K (low / medium / high), electrical conductivity (saline / non-saline), and S, Fe, Zn, Cu, B, Mn (sufficient / deficient).

| Requested field | Status |
|---|---|
| District | 37 of 38 districts; **Chennai has no record -> "Official data unavailable"** |
| Soil type | **Not published by the feed -> "Official data unavailable"** (CSV column is NULL; validator forbids filling it) |
| pH, organic carbon, N, P, K, EC | class counts, shares and dominant class (no numeric values published) |
| Micronutrients | S, Fe, Zn, Cu, B, Mn sufficient/deficient counts |
| Numeric values (pH units, % OC, kg/ha, dS/m, ppm) | **Not published -> "Official data unavailable"**; never back-calculated from classes |

Shares are arithmetic on the counts (count / samples tested for that parameter). Per-parameter totals differ slightly in the source (max spread enforced <= 3 %), so each parameter carries its own `samples`.

## API
- `GET /api/soil-master` - districts with data and those without (`"Official data unavailable"`).
- `GET /api/soil-master/{location}` - full record with provenance. Unknown name: 404. District without a record: `{"available": false, "message": "Official data unavailable"}`.

## Explainability
`soil_master.explanation_support(district)` returns a sentence plus the official counts it rests on (dataset, cycle, samples tested, class counts, URL). `explanation_service._constraints` appends it to the "soil" item and stores it in `evidence.soil_master`; for a district without a record the evidence is the string "Official data unavailable".

## Validator rules
Exact columns; unique canonical district; integer non-negative counts; samples = sum of class counts; dominant class = argmax (`tie` on equality); `samples_tested` = max parameter total; totals within 3 %; `soil_type` NULL; counts identical to the raw Soil Health Card file; portal URL and provenance present.

## Known limits / TODO
Pre-existing fuzzy fertility index (`CLASS_SCORE`, `app/data/official_view.py`) maps classes to scores by a documented rule; it is derived from, not part of, this dataset. Soil type and numeric values would need the Soil Health Card card-level data or the Tamil Nadu Agriculture Department soil survey, neither of which is loaded.
