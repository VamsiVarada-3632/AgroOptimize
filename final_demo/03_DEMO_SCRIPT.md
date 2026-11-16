# 03 – Live demonstration script (target 6 minutes)

Site: https://agrooptimize.onrender.com. Inputs and expected values: `02_DEMO_CASES.md`. The free server sleeps when idle: open the site and Official Data **10 minutes before** the review so the first request does not take 30–60 s.

**Before you start (2 min, off-stage):** profile set to **Salem, Rabi, 5 ha**; in a second tab, Scenario Simulation already **run** (Salem, Rabi, rainfall −20 %) because it takes ≈70 s; one Salem Rabi run already saved so History is not empty.

---

### 0:00 – Home (30 s)
**Click:** Home in the sidebar.
**Say:** "AgroOptimize recommends a crop plan for a Tamil Nadu district and season. Every number comes from official 2024-25 government data. The weather card says *Official Data Not Available* – we have no official IMD weather feed, so we show the gap instead of a fake forecast."
**Point at:** Estimated yield, irrigated area 59.4 %, soil health; the weather card.

### 0:30 – Official Data (40 s)
**Click:** Official Data.
**Say:** "These are the ten datasets the system loads: the Season & Crop Report, IMD rainfall, reservoir levels, groundwater, MSP and CACP cost, TNAU fertiliser doses and the Soil Health Card – 39,065 rows. Each file is registered with a checksum. Below are nine features we deliberately switched off because their official data does not exist yet."
**Point at:** 39,065 rows; the checksum column; the disabled-features list (fertiliser prices, crop calendar, cotton/rice).

### 1:10 – Run Optimization, Demo 1 (1 min 20 s)
**Click:** Run Optimization → District **Salem**, Season **Rabi**, Year 2024, Land **5**, Budget empty, profile **Balanced**, fuzzy model **Official (default)** → **Run Optimization**.
**Say while it runs (≈10 s):** "The pipeline: official data → Mamdani fuzzy assessment of rainfall, reservoir and soil → NSGA-II with four objectives – yield, cost, irrigated area, nutrient load – a population of 80 over 200 generations, giving 80 Pareto plans → TOPSIS ranks all 80 and the page lists the top 50."
**Point at:** top plan **maize 37 %, ragi 45 %, red gram 8 %, green gram 10 %**, TOPSIS **0.6485**; "Top plans by TOPSIS score" – plans 2 and 3 have nearly the same score with different mixes.
**Click:** profile **Sustainability** → **Re-rank plans**.
**Say:** "Re-ranking is instant – TOPSIS runs on the same 80 plans; NSGA-II is not repeated."

### 2:30 – Explainability (1 min 10 s)
**Click:** profile back to **Balanced** → Re-rank → **Why this plan?**
**Say:** "Confidence 64.8 %, 'Recommended'. Reasons and risks are computed from the run, not written by hand."
**Scroll to:** **Why this crop was selected** → open **Ragi** → open **Rainfall**.
**Say:** "For each crop there are ten checks. Rainfall: 545 mm against a 342 mm normal, citing IMD and the TNAU guide. Market price says *Official Data Not Available* – there is no official mandi price, so we don't invent one."
**Press:** Escape.

### 3:40 – Low budget, Demo 4 (40 s)
**Click:** Run Another → Budget **100000** → Run Optimization.
**Point at:** jowar 24 % / green gram 76 %, cost **₹84,287**, confidence **"Use with caution"**.
**Say:** "The budget is a hard constraint inside the optimiser. The plan becomes cheap pulses and millets, and the system warns the yield is low."

### 4:20 – District Intelligence (40 s)
**Click:** District Intelligence (Salem).
**Say:** "A district profile before any optimisation: rainfall against the normal, crop history, suitability ranking."
**Scroll to:** **Soil Health Card**.
**Point at:** 14,996 samples; nitrogen 99.6 % Low, potassium 57.8 % High, salinity 97.8 % non-saline.

### 5:00 – Scenario Simulation (40 s)
**Switch to:** the prepared second tab (Salem Rabi, rainfall −20 %).
**Say:** "What if rainfall drops 20 %? Both sides are optimised with the same five random seeds, and a change is called real only if a paired t-test gives p < 0.05 and it is at least 1 %. Otherwise it is labelled *within search variation* – we separate scenario effects from optimiser noise."
**Point at:** original vs simulated recommendation; the verdict chips; the fertiliser lever marked *Official Data Not Available*.

### 5:40 – History and close (20 s)
**Click:** History.
**Point at:** "Official-Data Model" and "Official Data" badges.
**Say:** "Every run is saved with its model and data source, and Reports turns it into a downloadable report. That's AgroOptimize: official data only, multi-objective optimisation, and explanations that cite their sources."

---

### If something goes wrong

| Situation | Do |
|---|---|
| First request takes 30–60 s | Say "the free server is waking up" and talk through Official Data while it loads |
| A different crop mix than above | Fine – results depend on the machine; explain that NSGA-II is stochastic and the seed is fixed per platform |
| Simulation spinner > 2 min | Use the prepared tab; mention the free server is slow (≈70 s vs 3 s locally) |
| Kharif with Profit, Sustainability or Low cost returns HTTP 500 | Fixed in PR #24; until it is deployed, demo Kharif with Balanced or Water saving |
| Examiner asks for Chennai | Show it: "fewer than two crops have complete official data, so the system refuses to plan instead of guessing" |
