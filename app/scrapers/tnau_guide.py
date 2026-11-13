"""TNAU 'Crop Production Guide - Agriculture 2020' blanket fertiliser recommendations.

Source (official, Tamil Nadu Agricultural University): https://agritech.tnau.ac.in/pdf/AGRICULTURE.pdf
Fetched through the browser pane (government hosts are not reachable from the shell); text extracted with
pdf.js, then each crop's section searched for "blanket recommendation"/"If soil test is not done" passages.
`pdf_page` is the PDF page number; printed page = pdf_page - 12.  Values are exactly as printed.
Nothing is estimated: a quantity the guide does not give is None.
"""
from __future__ import annotations

SOURCE_URL = "https://agritech.tnau.ac.in/pdf/AGRICULTURE.pdf"
RETRIEVED_AT = "2026-11-12"
PRINTED_OFFSET = 12

# crop, condition, N, P2O5, K2O, S, pdf_page, evidence (verbatim numbers), note
ROWS = [
    ("Rice", "short_duration_dry_season_cauvery_delta_coimbatore", 150, 50, 50, None, 33, "150 50 50", ""),
    ("Rice", "short_duration_dry_season_other_tracts", 120, 40, 40, None, 33, "120 40 40", ""),
    ("Rice", "medium_long_duration_wet_season", 150, 50, 50, None, 33, "150 50 50", ""),
    ("Rice", "hybrid", 175, 60, 60, None, 33, "175 60 60", ""),
    ("Sorghum", "blanket", 90, 45, 45, None, 80, "90 N, 45 P2O5 45 K2O kg/ha", ""),
    ("Cumbu", "varieties", 70, 35, 35, None, 96, "70:35:35 kg N, P2O5, K2O/ha", ""),
    ("Cumbu", "hybrids", 80, 40, 40, None, 96, "80 kg N, 40 kg P2O5 and 40 kg K2O per ha", ""),
    ("Ragi", "blanket", 60, 30, 30, None, 107, "60 kg N, 30 kg P2O5 and 30 kg K2O per ha", ""),
    ("Maize", "varieties", 135, 62.5, 50, None, 117, "135:62.5:50 kg NPK/ha", ""),
    ("Maize", "hybrids", 250, 75, 75, None, 117, "250:75:75 kg NPK/ha", ""),
    ("Redgram", "rainfed", 12.5, 25, 12.5, 10, 139, "12.5 kg N + 25 kg P2O5 + 12.5 kg K2O + 10 kg S/ha", ""),
    ("Redgram", "irrigated", 25, 50, 25, 20, 139, "25 kg N + 50 kg P2O5 + 25 kg K2O + 20 kg S/ha", ""),
    ("Blackgram", "rainfed", 12.5, 25, 12.5, 20, 149, "12.5 kg N + 25 kg P2O5 + 12.5 kg K2O + 20 kg S/ha", ""),
    ("Blackgram", "irrigated", 25, 50, 25, 40, 149, "25 kg N + 50 kg P2O5 + 25 kg K2O + 40 kg S/ha", ""),
    ("Greengram", "rainfed", 12.5, 25, 12.5, 20, 158, "12.5 kg N + 25 kg P2O5 + 12.5 kg K2O + 20 kg S/ha", ""),
    ("Greengram", "irrigated", 25, 50, 25, 40, 158, "25 kg N + 50 kg P2O5 + 25 kg K2O + 40 kg S/ha", ""),
    ("Bengalgram", "rainfed", 12.5, 25, 12.5, 10, 174, "12.5 kg N + 25 kg P2O5 + 12.5 kg K2O + 10 kg S/ha", ""),
    ("Bengalgram", "irrigated", 25, None, 25, 20, 174, "25 kg N + 5 kg P2O5 + 25 kg K2O + 20 kg S/ha",
     "P2O5 printed as '5' (apparent typo vs 25 for the other pulses); stored NULL, not corrected"),
    ("Soybean", "blanket", 20, 40, 20, 20, 187, "20:40:20:20 NPKS kg/ha", ""),
    ("Groundnut", "blanket", 25, 50, 75, None, 199, "N P K 25 50 75 kg/ha", ""),
    ("Sesame", "rainfed", 23, 13, 13, None, 211, "23:13:13 kg NPK/ha", ""),
    ("Sesame", "irrigated", 35, 23, 23, None, 211, "35:23:23 kg NPK/ha", ""),
    ("Sunflower", "hybrid_irrigated", 60, 90, 60, None, 228, "Hybrids IRRI 60 90 60", ""),
    ("Sunflower", "hybrid_rainfed", 40, 50, 40, None, 228, "Hybrids RF 40 50 40", ""),
    ("Sunflower", "variety_irrigated", 60, 30, 30, None, 228, "Varieties IRRI 60 30 30", ""),
    ("Sunflower", "variety_rainfed", 40, 50, 40, None, 228, "Varieties RF 40 50 40", ""),
    ("Cotton", "irrigated_MCU7_SVPR3", 60, 30, 30, None, 269, "MCU 7, SVPR 3 60 30 30", ""),
    ("Cotton", "irrigated_MCU5_MCU12_MCU13_Suvin_SVPR2", 80, 40, 40, None, 269, "MCU 5, MCU 12, MCU 13, Suvin, SVPR 2 80 40 40", ""),
    ("Cotton", "rainfed_K11", 20, 0, 0, None, 279, "K 11 20 0 0", ""),
    ("Cotton", "rainfed_SVPR2_KC2", 40, 20, 40, None, 279, "SVPR 2 40 20 40; KC 2 40 20 40", ""),
    ("Sugarcane", "blanket", 300, 100, 200, None, 301, "NPK @ 300:100:200 kg/ha", ""),
]
COLUMNS = ["crop", "condition", "n_kg_ha", "p_kg_ha", "k_kg_ha", "s_kg_ha", "pdf_page", "printed_page", "evidence", "note", "source_url", "retrieved_at"]


def rows():
    return [(c, cond, n, p, k, s, pg, pg - PRINTED_OFFSET, ev, note, SOURCE_URL, RETRIEVED_AT)
            for c, cond, n, p, k, s, pg, ev, note in ROWS]
