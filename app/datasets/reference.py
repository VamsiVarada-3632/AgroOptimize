"""Reference (metadata) tables - not measurements.

district_reservoir_map: which reservoir serves which district. This is hydrological metadata
(the reservoir's location district), recorded with its basis. Entries marked 'location' state the district
in which the dam is situated; they must be verified against the TN Water Resources Department command-area
lists (scraper S5 / S12). Reservoirs outside Tamil Nadu are not mapped to any district."""
DISTRICT_RESERVOIR_MAP = [
    ("coimbatore", "aliyar", "location"), ("coimbatore", "parambikulam", "location"), ("coimbatore", "sholayar", "location"),
    ("tiruppur", "thirumurthy", "location"), ("tiruppur", "amaravathi", "location"),
    ("erode", "bhavanisagar", "location"), ("salem", "mettur", "location"),
    ("krishnagiri", "krishnagiri", "location"), ("tiruvannamalai", "sathanur", "location"),
    ("theni", "vaigai", "location"), ("theni", "periyar", "location"),
    ("tirunelveli", "manimuthar", "location"), ("tirunelveli", "papanasam", "location"),
    ("kanniyakumari", "pechiparai", "location"), ("kanniyakumari", "perunchani", "location"),
]


# ------------------------------------------------------------------ modelling crosswalks (documented assumptions)
REPORT_YEAR_START = 2024                       # official reports cover 2024-25
SEASON_MONTHS = {                              # IMD season windows used for the crop seasons
    "Kharif": ["June", "July", "August", "September"],                          # IMD South-West Monsoon
    "Rabi": ["October", "November", "December", "January", "February"],         # IMD North-East Monsoon + Winter
}
# Official rice reporting splits the crop into sub-seasons; the guide pairs them with the two crop seasons as below.
RICE_SEASON_CROSSWALK = {"Kharif": "Kar/Kuruvai/Sornavari", "Rabi": "Samba/Thaladi/Pishanam"}   # Navarai/Kodai not mapped
# TNAU names "Cauvery delta & Coimbatore tract" for the higher short-duration rice dose.
RICE_DELTA_TRACT = {"thanjavur", "tiruvarur", "nagapattinam", "mayiladuthurai", "coimbatore"}
# MSP/CACP cost used for the report year 2024-25: the Kharif Marketing Season 2024-25 notification.
MARKETING_SEASON = "KMS 2024-25"
COST_VARIETY_PREFERENCE = ("Common", "Hybrid", "Medium Staple", None)   # the variety CACP prices the cost for


def pick_dose(agro, crop: str, district: str, season: str, irrigated_share: float):
    """Row of the TNAU table that applies, plus the rule used (documented, shown in explanations).
    Returns (row or None, rule text)."""
    rows = agro[agro.crop == crop]
    if rows.empty:
        return None, "no TNAU dose for this crop"
    conds = set(rows.condition)
    irr = irrigated_share >= 0.5
    if crop == "rice":
        name = ("short_duration_dry_season_cauvery_delta_coimbatore" if district in RICE_DELTA_TRACT
                else "short_duration_dry_season_other_tracts") if season == "Kharif" else "medium_long_duration_wet_season"
    elif {"irrigated", "rainfed"} <= conds:
        name = "irrigated" if irr else "rainfed"
    elif crop == "sunflower":
        name = "variety_irrigated" if irr else "variety_rainfed"
    elif crop == "cotton":
        name = "irrigated_MCU7_SVPR3" if irr else "rainfed_SVPR2_KC2"
    elif "varieties" in conds:
        name = "varieties"
    else:
        name = "blanket"
    hit = rows[rows.condition == name]
    return (None, f"condition '{name}' missing") if hit.empty else (hit.iloc[0], f"TNAU '{name}' (irrigated share {irrigated_share:.0%})")
