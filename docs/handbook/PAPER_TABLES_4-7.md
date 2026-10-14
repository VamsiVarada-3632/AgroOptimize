# Paper Tables 4–7: values taken from the implementation

Extracted 2026-10-01 from `agrooptimize-backend/` (app/config.py, app/fuzzy/engine.py, app/optimization/*, app/data/*, data/raw/*.csv). Table 7 numbers come from real runs of the system's own pipeline (same functions as `POST /api/farm-plans`).

**Experiment setting for Table 7:** Kharif season 2023 (latest *observed* year; 2024 rows are estimates); 5 ha farm; no budget; "balanced" preference; NSGA-II at the configured settings (population 80, 200 generations, seed 42). Robustness rows use 10 additional independent runs (seeds 1–10).

## TABLE 4 – Dataset and input configuration

| Item | Value |
|---|---|
| Dataset / source | Project baseline dataset for 2020–2023, provided with the course (original agency sources not documented). 2024 rows are estimates derived from 2023 (crop ×1.03 yield and area; land, rainfall and water copied from 2023). |
| Study region | Coimbatore, Erode, Salem and Pollachi, Tamil Nadu, India (Pollachi is a taluk of Coimbatore district) |
| Crops considered | 15 crops: Banana, Coconut, Cotton, Fodder crops, Groundnut, Maize, Mango, Paddy, Sorghum, Sugarcane, Sunflower, Tapioca, Turmeric, Vegetables, Wheat. 2–5 candidate crops per location and season (top-ranked by historical revenue; maximum 6). |
| Planning period | 2020–2023 observed (+2024 estimated); single-season planning for Kharif (Jun–Sep), Rabi (Oct–Mar) or Summer (Feb–May) |
| Number of observations | 745 records in 16 CSV files: crop 205, land/soil 60, rainfall 240 (monthly), water availability 240 (monthly) |
| Land availability | User input `total_land_ha` > 0 (5 ha in the experiments). District context data: agricultural land 96,240–296,480 ha; irrigated land 58,820–168,840 ha. |
| Water availability | Reservoir storage 35–85 % of capacity (monthly; capacity 248.6–320.4 MCM). Entered into the fuzzy model as the seasonal mean storage %. Irrigation need = max(crop water requirement − effective rainfall, 0), where effective rainfall = mean monthly rainfall × number of months × 0.7. |
| Budget limit | No fixed value in the configuration. Optional user-supplied hard constraint (total cost ≤ budget, in ₹). |
| Environmental-impact calculation | EI = √(L × C). L = Σ area × fertiliser multiplier × N dose (nitrogen-leaching proxy). C = Σ area × [0.15 × fertiliser multiplier × (N+P+K) + 0.01 × irrigation multiplier × crop water requirement] (carbon proxy). EI is a unitless index; lower is better. |
| Missing-value handling | The dataset has no missing values (0 nulls in all 745 records), so no imputation is applied. If a requested location/season/year has no data, or fewer than 2 candidate crops, the request is rejected with an error. Unrecognised N/P/K status scores 50/100 and unrecognised rainfall dependency uses a factor of 0.5. |

## TABLE 5 – Fuzzy model configuration (Mamdani; min/max inference; centroid defuzzification; 26 rules)

All membership functions are **triangular**; there are no trapezoidal functions. Triangular parameters are (a, b, c). Where a = b or b = c the function is a left- or right-shoulder triangle.

| Variable | Role | Universe | Linguistic term | MF type | Parameters (a, b, c) |
|---|---|---|---|---|---|
| Rainfall deviation (%) | Input | [−60, 60] | Deficit | Triangular | (−60, −60, −5) |
| | | | Normal | Triangular | (−15, 0, 15) |
| | | | Surplus | Triangular | (5, 60, 60) |
| Water storage (%) | Input | [0, 100] | Low | Triangular | (0, 0, 35) |
| | | | Medium | Triangular | (20, 50, 75) |
| | | | High | Triangular | (60, 100, 100) |
| Soil fertility index (0–100) | Input | [0, 100] | Poor | Triangular | (0, 0, 40) |
| | | | Medium | Triangular | (25, 50, 75) |
| | | | Good | Triangular | (60, 100, 100) |
| Yield confidence (%) | Output | [0, 100] | Low | Triangular | (0, 0, 45) |
| | | | Medium | Triangular | (30, 55, 75) |
| | | | High | Triangular | (65, 100, 100) |
| Irrigation risk (%) | Output | [0, 100] | Low | Triangular | (0, 0, 35) |
| | | | Medium | Triangular | (25, 50, 75) |
| | | | High | Triangular | (60, 100, 100) |

Soil fertility index = 0.3·pH score + 0.3·organic-carbon score + 0.4·N/P/K score. Inputs are clipped to their universes. Outputs are divided by 100. Per-crop yield confidence = yield confidence × (1 − irrigation risk × d × 0.4), where d = 0.1/0.3/0.6/1.0 for Very Low/Low/Medium/High rainfall dependency.

## TABLE 6 – NSGA-II configuration

| Parameter | Value |
|---|---|
| Implementation | pymoo 0.6 NSGA-II (rank-and-crowding survival, binary tournament selection) with custom crossover, mutation and repair operators |
| Decision variables | 3n real genes for n candidate crops: land share [0.0001, 1] (repaired to sum to 1), irrigation multiplier [0.7, 1.3], fertiliser multiplier [0.7, 1.3] |
| Objectives | 4: maximise yield; minimise cost, irrigation water and environmental impact |
| Constraint | Optional: total cost ≤ budget (constraint-domination handling) |
| Population size | 80 |
| Number of generations | 200 |
| Initialisation | Uniform random within bounds, then repaired |
| Crossover operator / probability | Single-point crossover, 0.85 per mating |
| Mutation operator / probability | Gaussian mutation, 0.12 per gene; σ = 0.12 × (upper − lower bound); clipped to bounds |
| Duplicate elimination | Yes |
| Independent runs / random seeds | System default: 1 run with seed 42 (deterministic). Robustness evaluation for this paper: 10 independent runs, seeds 1–10. |
| Stopping criterion | Fixed budget of 200 generations (no early stopping). Convergence is monitored with the normalised hypervolume (reference point 1.1 on each normalised objective). |
| Post-processing | Feasible non-dominated solutions ranked by TOPSIS ("balanced" weights 0.30 / 0.233 / 0.233 / 0.233); top 50 returned |

## TABLE 7 – Evaluation results (Kharif 2023, 5 ha, no budget)

| Metric | Coimbatore | Erode | Salem | Pollachi |
|---|---|---|---|---|
| Fuzzy inputs: rainfall deviation / storage / soil fertility | −41.1 % / 85.0 % / 70.3 | −40.1 % / 78.0 % / 71.5 | −21.1 % / 62.0 % / 67.8 | +20.4 % / 72.0 % / 76.5 |
| Dominant fuzzy labels | deficit / high / good | deficit / high / good | deficit / medium / medium | surplus / high / good |
| Fuzzy yield confidence | 0.620 | 0.641 | 0.636 | 0.858 |
| Fuzzy irrigation risk | 0.430 | 0.435 | 0.465 | 0.152 |
| Hypervolume, generation 1 → 200 (seed 42) | 0.388 → 0.634 | 0.354 → 0.647 | 0.257 → 0.781 | 0.327 → 0.744 |
| Final hypervolume, 10 runs (mean ± SD) | 0.633 ± 0.006 | 0.637 ± 0.025 | 0.776 ± 0.016 | 0.724 ± 0.013 |
| Convergence generation* (seed 42) | 71 | 44 | 33 | 88 |
| Convergence generation*, 10 runs (mean ± SD) | 54.4 ± 15.9 | 44.5 ± 12.8 | 56.0 ± 19.4 | 45.0 ± 26.7 |
| Pareto-optimal plans generated | 80 | 80 | 80 | 80 |
| Feasibility rate, no budget | 100 % (80/80) | 100 % (80/80) | 100 % (80/80) | 100 % (80/80) |
| Feasibility rate, ₹40,000/ha budget cap | 100 % (80/80) | 100 % (80/80) | 100 % (80/80) | 100 % (80/80) |
| Yield range across front (t/ha) | 1.08–57.09 | 1.09–59.02 | 1.09–13.56 | 8.20–80.91 |
| Cost range across front (₹/ha) | 25,547–79,929 | 29,334–79,933 | 29,329–43,525 | 29,149–77,851 |
| **Representative plan** (TOPSIS rank 1) – crop mix | Sugarcane 54 %, Sorghum 46 % | Sugarcane 52 %, Groundnut 48 % | Tapioca 77 %, Groundnut 23 % | Coconut 76 %, Sugarcane 24 % |
| Yield | 31.75 t/ha (158.8 t) | 31.42 t/ha (157.1 t) | 10.74 t/ha (53.7 t) | 38.40 t/ha (192.0 t) |
| Cost | ₹50,319/ha (₹2,51,648) | ₹52,891/ha (₹2,64,507) | ₹37,681/ha (₹1,88,445) | ₹39,321/ha (₹1,96,605) |
| Irrigation water | 6.98 ML/ha (34.91 ML) | 6.93 ML/ha (34.66 ML) | 3.80 ML/ha (18.99 ML) | 6.94 ML/ha (34.70 ML) |
| Environmental impact (index) | 70.32/ha (351.7) | 61.96/ha (309.9) | 33.75/ha (168.8) | 64.17/ha (320.9) |
| TOPSIS closeness / confidence label | 0.608 / Moderate | 0.610 / Moderate | 0.649 / Moderate | 0.630 / High |

\*Convergence generation = the first generation in which hypervolume reaches 99 % of its final (generation-200) value.

Notes for interpretation:
- **Hypervolume normalisation.** Hypervolume is normalised within each run by that run's own objective bounds. Values are comparable within a district's seeds but not strictly across districts.
- **Feasibility rate.** This is the share of the final non-dominated set that satisfies the budget. Infeasible plans are eliminated during evolution, so the final set is fully feasible.
- **Crops with < 1 % share.** Every candidate crop receives at least a 0.01 % share; the crop mixes above list only crops with ≥ 1 %.
- **Input multipliers.** In the representative plans, the irrigation and fertiliser multipliers sit at or near their 0.7 lower bound. The yield model does not reward higher inputs (see docs/RESEARCH_REVIEW.md, R-1).
