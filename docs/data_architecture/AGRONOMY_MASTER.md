# agronomy_master.csv - TNAU Crop Production Guide, verbatim

Source: TNAU, *Crop Production Guide - Agriculture* (https://agritech.tnau.ac.in/pdf/AGRICULTURE.pdf, 460 PDF pages), read through the browser pane with pdf.js (the shell cannot reach the host). Files: `data/official/raw/agronomy_master.csv`, `app/scrapers/tnau_master.py` (page-cited transcription), `scripts/build_agronomy_master.py`, `app/datasets/agronomy_master.py` (loader), `app/datasets/agronomy_master_validator.py`, `tests/datasets/test_agronomy_master.py`.

## Rules
- Every text value is a quote from the PDF text layer (odd spacing such as `P 2 O 5` and the guide's own spelling/typos are kept). `evidence_pages` gives the PDF page per field; the validator refuses a populated field without a page, and a page for a NULL field.
- NULL = empty cell. Nothing estimated, no AI-generated values. NPK are numbers only when the guide gives one recommendation for the crop (checked against `agronomy_tnau.csv`); otherwise NULL and every condition is in `npk_by_condition`.
- Zone/season tables are flattened in reading order; where the PDF text layer leaves NW/Western-zone season cells blank (merged cells) this is stated in the value.

## Coverage (15 crops)
Rice, Sorghum, Cumbu, Ragi, Maize, Redgram, Blackgram, Greengram, Bengalgram, Soybean, Groundnut, Sesame, Sunflower, Cotton, Sugarcane.

| Field | Status |
|---|---|
| water_requirement (mm), recommended_soil, soil_ph | **NULL for every crop**: the guide gives no per-crop water requirement in mm, no recommended soil type or suitable pH range for these crops. (Only an unrelated statement "Lime application is recommended for pulses with soil pH less than 6.0" exists; it is not a suitable-pH range and is not stored. The only mm figure, 500 mm, is for jute.) |
| season, seed_rate, spacing, fertilizer_schedule, suitable_districts, suitable_rainfall | present for all crops (soybean: no seed rate / district list in its main section) |
| duration, expected_yield, harvest_time, irrigation_frequency | present where located; see `extraction_notes` for what is pending |

## Not yet extracted (in the guide, not in the CSV)
- Rice: per-variety duration/yield tables (printed p5-11), irrigation schedule, harvest. Sugarcane: later variety tables (printed p288-290). Bengalgram: main-crop harvest/irrigation.
- Crops not yet transcribed: Small millets, Wheat, Cowpea, Horsegram, Lablab (Avarai, Mochai), Sword bean, Castor, Safflower, Coconut, Oilpalm, Niger, Jute, Sweet sorghum, Tropical sugarbeet, forage and green-manure crops. Horticulture crops are in a different TNAU PDF (HORTICULTURE.pdf).
- Cotton, Redgram, Greengram, Blackgram, Groundnut, Sesame and Sunflower season tables are complete; per-variety yield rows beyond those printed in the first variety table are not duplicated.

## Findings worth knowing
- Soybean irrigated dose "20 kg N, 80 kg P2O5, 40 kg K2O, 40 kg S" (PDF p186) is **missing from agronomy_tnau.csv**, which holds only the rainfed 20:40:20:20 blanket (p187). Soybean is not an optimisation candidate, so nothing changes at runtime; fix when soybean is enabled.
- Cotton: the guide prints *Mean yield of seed (kg/ha)* (kapas) per variety (e.g. MCU 5 1850, MCU 13 2200) and variety-specific ginning outturn (e.g. MCU 5 "ginning 34%", MCU 12 "GOT 34.8%", SVPR 2 36.4%, KC 2 37.5%, p265-266). These are variety-specific figures, not a district-level kapas->lint conversion, so cotton stays disabled.
