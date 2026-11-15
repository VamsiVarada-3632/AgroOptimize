# 02 – Demo cases

Five ready inputs, each run on **production** (https://agrooptimize.onrender.com) on 16 Nov 2026. The expected outputs below are what the live site returns. Results are reproducible on the same server, but a Mac gives a different (equally good) crop mix for the same inputs, so always demo on the live site. Every case uses Year 2024 (the only official report year), fuzzy model "Official" (default) and classic preference "None – use the ranking profile". Each run takes about 10 s on the free server.

Recorded with `qa_scripts/demo_cases.py`.

---

## Demo 1 – Normal recommendation (start here)

| Input | Value |
|---|---|
| District / Season / Year | Salem / Rabi / 2024 |
| Land / Budget | 5 ha / empty (no limit) |
| Ranking profile | Balanced |

**Expected result**
- Top plan: **maize 37 %, ragi 45 %, red gram 8 %, green gram 10 %**, TOPSIS **0.6485**.
- Totals: 15.89 t yield, ₹6.95 lakh cost, 1.96 ha irrigated, 562 kg NPK.
- Next two plans: maize 90 % / green gram 10 % (0.6453), maize 40 / ragi 49 / green gram 10 (0.6451) – close scores, different trade-offs.
- 80 Pareto plans; hypervolume ratio 0.914, IGD+ 0.075, spread 0.435; 100 % constraint satisfaction.

**Explainability highlights**
- Data: rainfall 545 mm vs 342 mm normal (**+59.5 %**, surplus), Mettur storage 87.4 %, Soil Health Card fertility 30.6 (N Low, P Medium, K High).
- Fuzzy: yield confidence 0.532, irrigation risk 0.12.
- Confidence **64.8 % – "Recommended"**; reasons: high yield, low irrigation demand, low fertiliser load, soil supports the crops.
- Crop evidence for each crop: 3 supported, 3 worth checking (soil, yield, risks), 3 for information, 1 Official Data Not Available (market price).
- 8 crops excluded with reasons (e.g. cotton and rice: no official kapas/paddy conversion factor).

**Speaking notes:** "Everything here comes from official 2024-25 data. The optimiser found 80 trade-off plans; TOPSIS picked this mix. Open 'Why this plan?' – every crop has ten checks, each citing its government source, and market price says *Official Data Not Available* because we refuse to estimate it."

---

## Demo 2 – High rainfall

| Input | Value |
|---|---|
| District / Season / Year | **Tirunelveli** / Rabi / 2024 |
| Land / Budget | 5 ha / no limit |
| Ranking profile | Balanced |

**Expected result**
- Top plan: **maize 44 %, black gram 56 %**, TOPSIS **0.6036**; 9.49 t, ₹1.83 lakh, 1.84 ha irrigated, 479 kg NPK.
- Second: maize 86 / black gram 7 / jowar 7 (18.28 t, ₹3.29 lakh) – almost the same score with twice the yield and cost.

**Explainability highlights**
- Rainfall **1,108 mm vs 573 mm normal (+93.4 %)** – the wettest Rabi season among the districts where the fuzzy stage runs; storage 62.5 %.
- Fuzzy: yield confidence **0.816** (highest of all), irrigation risk 0.119 – rainfall surplus, water medium, soil good.
- Confidence **79.9 % – "Highly recommended"**; adds "Historically established crops".
- Crop evidence: 4 supported per crop; water flagged "worth checking".

**Speaking notes:** "With a strong monsoon the fuzzy model is most confident – 0.82 – and the system labels the plan 'Highly recommended'. Note the second plan: nearly the same score, double the yield and cost. That is why we return the whole Pareto set, not one answer."

---

## Demo 3 – Low rainfall

| Input | Value |
|---|---|
| District / Season / Year | **Nagapattinam** / **Kharif** / 2024 |
| Land / Budget | 5 ha / no limit |
| Ranking profile | Balanced |

**Expected result**
- Top plan: **ragi 53 %, black gram 33 %, gingelly 13 %, green gram 1 %**, TOPSIS **0.6042**; 11.6 t, ₹3.61 lakh, 1.48 ha irrigated, 304 kg NPK.
- Only 4 candidate crops (maize and rice excluded with reasons).

**Explainability highlights**
- Rainfall **123 mm vs 247 mm normal (−50.1 %)** – the driest district-season in the data.
- **Fuzzy stage not applied**: no official reservoir reading for this district and season, so yield is left unadjusted and the app says so (yield confidence 1.0).
- Confidence 74.5 % – "Recommended"; reasons include **"Mostly rain-resilient crops"**; risk "Irrigation pressure".
- Crop evidence: rainfall "worth checking", risks marked **"Concern"** (rainfall far below normal) for every crop.

**Speaking notes:** "Half the normal rainfall. The plan shifts to rain-resilient pulses and millets, and the evidence marks rainfall risk as a concern. Also notice honesty about data: there is no official reservoir reading here, so the fuzzy adjustment is skipped and the screen tells you so instead of guessing."

---

## Demo 4 – Low budget

| Input | Value |
|---|---|
| District / Season / Year | Salem / Rabi / 2024 |
| Land / Budget | 5 ha / **₹1,00,000** |
| Ranking profile | Balanced |

**Expected result**
- Top plan: **jowar 24 %, green gram 76 %**, TOPSIS **0.6064**; **₹84,287** (within budget), 1.16 t, 0.30 ha irrigated, 284 kg NPK.
- Compare with Demo 1 (same district, no budget): ₹6.95 lakh and 15.9 t.

**Explainability highlights**
- Reason **"Fits the budget"**; confidence **55.0 % – "Use with caution"** (lower: low yield and a concentrated mix).
- Risks: rain-dependent crops, concentrated crop mix, inputs at the model minimum.

**Optional edge case (live):** set the budget to **₹50,000** → "No feasible plan found: no crop plan for 5 ha fits within the budget of ₹50,000. Raise the budget or reduce the land area." (the cheapest possible 5 ha plan costs about ₹72,000). Requires the QA fixes to be deployed.

**Speaking notes:** "The budget is a hard constraint inside NSGA-II, not a filter afterwards. With ₹1 lakh it moves to cheap pulses and millets and the explanation says 'Use with caution' – it does not hide the lower yield."

---

## Demo 5 – Sustainability profile

| Input | Value |
|---|---|
| District / Season / Year | **Coimbatore** / Rabi / 2024 |
| Land / Budget | 5 ha / no limit |
| Ranking profile | **Sustainability** |

**Expected result**
- Top plan: **maize 28 %, black gram 39 %, gingelly 33 %**, TOPSIS **0.6678**; 5.77 t, ₹1.89 lakh, **0.81 ha irrigated**, 370 kg NPK.
- Next: maize 6 / gingelly 94 (0.6629), gingelly 100 % (0.6625) – progressively lower water and fertiliser.

**Explainability highlights**
- Rainfall 510 mm vs 355 mm (+43.5 %), storage 72.3 %; yield confidence 0.678, irrigation risk 0.131.
- Confidence 72.2 % – "Recommended"; reasons: low cost, low irrigation demand, low fertiliser load; risk "Weak on yield" (low).
- On the result page switch the profile to **Balanced** and press **Re-rank plans**: the same 80 plans are re-ranked instantly without re-running NSGA-II.

**Speaking notes:** "Same optimiser, different priorities. Sustainability weights low irrigation, low nutrient load and soil fit; the recommendation trades yield for a third of the irrigated area. Re-ranking takes milliseconds because TOPSIS runs after the Pareto front exists."

---

## Supporting pages to show (no input needed)

| Page | What to point at |
|---|---|
| Official Data | 10 datasets, 39,065 rows, checksums, 9 disabled features with the missing dataset |
| District Intelligence → Salem | summary, Soil Health Card (pH, organic carbon, N/P/K, salinity) |
| Scenario Simulation → Salem Rabi, rainfall −20 % | original vs simulated plan; changes judged with a paired test over 5 seeds (takes ≈70 s on the free server – start it before talking) |
| History | saved runs with "Official-Data Model" and "Official Data" badges |
