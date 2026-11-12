"""Features that are switched off because the official dataset they need has not been obtained.
Shown by GET /api/datasets and written into the migration report. Each entry names the missing dataset and the
official source to scrape; a feature is re-enabled by loading that dataset - never by estimating it."""
DISABLED_FEATURES = [
    {"feature": "Live weather widget (/api/weather)", "missing_dataset": "IMD district weather: observed temperature, humidity, forecast",
     "source": "mausam.imd.gov.in", "scope": "weather widget only"},
    {"feature": "Crop water requirement in mm / irrigation litres (NSGA-II f3)", "missing_dataset": "Crop-wise water requirement (mm) - TNAU guide gives schedules, not totals",
     "source": "TNAU crop guides (per-crop pages) / Agriculture Dept", "scope": "f3 uses irrigated area share instead"},
    {"feature": "Fertiliser-price scenarios", "missing_dataset": "Notified fertiliser prices (Dept. of Fertilizers) - not loaded",
     "source": "fert.nic.in", "scope": "scenario lever only; cost objective uses CACP cost of cultivation"},
    {"feature": "Labour / pesticide cost, crop duration, sowing & harvest months", "missing_dataset": "Per-crop cultivation calendar and input costs (TNAU / CACP state cost tables)",
     "source": "TNAU, CACP", "scope": "display fields only"},
    {"feature": "Crops without TNAU dose or CACP cost (e.g. horticulture, coconut, sugarcane, pulses beyond MSP list)", "missing_dataset": "TNAU horticulture guide doses; MSP/FRP and cost of cultivation for the report year",
     "source": "agritech.tnau.ac.in/pdf/HORTICULTURE.pdf, CACP", "scope": "crop excluded from candidate lists (reason shown)"},
    {"feature": "Cotton and rice as optimisation candidates", "missing_dataset": "Official conversion factors: kapas to lint (ginning outturn) and paddy to rice (milling outturn); official yield is lint / rice, MSP and CACP cost are per quintal kapas / paddy",
     "source": "CACP / Dept. of Agriculture TN / Season & Crop Report notes", "scope": "crop excluded from candidate lists (reason shown); nothing converted with an assumed factor"},
    {"feature": "Reservoir storage for Kharif 2024 and for districts without a mapped reservoir", "missing_dataset": "Reservoir daily levels before 2025-01-01; district command-area map",
     "source": "TN Water Resources Dept", "scope": "fuzzy stage skipped for the district/season (yield left unadjusted, flagged)"},
    {"feature": "District year-on-year trends and multi-year history", "missing_dataset": "Season & Crop Reports of earlier years (district level)",
     "source": "Dept. of Economics & Statistics TN", "scope": "trend widgets; state-level series is available"},
    {"feature": "Taluk-level analysis (Pollachi)", "missing_dataset": "Taluk-wise statistics", "source": "Dept. of Economics & Statistics TN", "scope": "Pollachi reported as 'taluk data not available'"},
]
