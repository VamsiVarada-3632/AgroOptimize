"""MSP values transcribed by eye from the page images of the SCANNED official notifications
(OCR was unreliable on these scans). Every row records its file and page; all rows are re-checked by
app/datasets/msp.py (cross-notification equality, margin/increase arithmetic).

Columns: marketing_season, crop, variety, msp_rs_qtl, source_file, source_page"""
KMS = "KMS"; RMS = "RMS"
F_25K = "MSP-Notification-KMS-2025-26-English.pdf"
F_23K = "MSP price 2023- 2024.pdf"
F_22K = "Revised MSP notification_1_230322_223200.pdf"
F_22R = "English MSP 2021 new.pdf"

def _rows(season, file, page, items):
    return [(season, c, v, p, file, page) for c, v, p in items]

TRANSCRIBED = (
    _rows("KMS 2025-26", F_25K, 1, [("Paddy", "Common", 2369), ("Paddy", "Grade A", 2389), ("Jowar", "Hybrid", 3699),
          ("Jowar", "Maldandi", 3749), ("Bajra", None, 2775), ("Ragi", None, 4886), ("Maize", None, 2400),
          ("Tur (Arhar)", None, 8000), ("Moong", None, 8768), ("Urad", None, 7800), ("Groundnut", None, 7263),
          ("Sunflower seed", None, 7721)])
    + _rows("KMS 2025-26", F_25K, 2, [("Soybean (Yellow)", None, 5328), ("Sesamum", None, 9846), ("Nigerseed", None, 9537),
          ("Cotton", "Medium Staple", 7710), ("Cotton", "Long Staple", 8110)])
    + _rows("KMS 2023-24", F_23K, 1, [("Paddy", "Common", 2183), ("Paddy", "Grade A", 2203), ("Jowar", "Hybrid", 3180),
          ("Jowar", "Maldandi", 3225), ("Bajra", None, 2500), ("Ragi", None, 3846), ("Maize", None, 2090),
          ("Tur (Arhar)", None, 7000), ("Moong", None, 8558), ("Urad", None, 6950), ("Groundnut", None, 6377),
          ("Sunflower seed", None, 6760), ("Soybean (Yellow)", None, 4600), ("Sesamum", None, 8635),
          ("Nigerseed", None, 7734), ("Cotton", "Medium Staple", 6620), ("Cotton", "Long Staple", 7020)])
    + _rows("KMS 2022-23", F_22K, 1, [("Paddy", "Common", 2040), ("Paddy", "Grade A", 2060), ("Jowar", "Hybrid", 2970),
          ("Jowar", "Maldandi", 2990), ("Bajra", None, 2350), ("Ragi", None, 3578), ("Maize", None, 1962),
          ("Tur (Arhar)", None, 6600), ("Moong", None, 7755), ("Urad", None, 6600), ("Groundnut", None, 5850),
          ("Sunflower seed", None, 6400), ("Soybean (Yellow)", None, 4300), ("Sesamum", None, 7830),
          ("Nigerseed", None, 7287), ("Cotton", "Medium Staple", 6080), ("Cotton", "Long Staple", 6380)])
    + _rows("RMS 2022-23", F_22R, 1, [("Wheat", None, 2015), ("Barley", None, 1635), ("Gram", None, 5230),
          ("Lentil (Masur)", None, 5500), ("Rapeseed & Mustard", None, 5050), ("Safflower", None, 5441)])
)

# CACP Copra Report 2024 season, page "recommends that MSP of milling copra be fixed at Rs 11,160 and ball copra Rs 12,000"
# (a recommendation, stored as such; verify=True means checked against the PDF text by the tests)
COPRA_2024 = [("Copra 2024", "Coconut (copra)", "Milling", 11160.0, "Copra Report - 2024 Season.pdf", None),
              ("Copra 2024", "Coconut (copra)", "Ball", 12000.0, "Copra Report - 2024 Season.pdf", None)]
