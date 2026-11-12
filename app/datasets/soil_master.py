"""Soil master: Soil Health Card (soilhealth.dac.gov.in) district records, cycle 2024-25, as published.

What the official feed contains - and therefore what this module can return:
  * per-district counts of tested samples in the portal's classes (pH acidic/neutral/alkaline, organic carbon,
    N / P / K low-medium-high, EC saline/non-saline, S, Fe, Zn, Cu, B, Mn sufficient/deficient);
  * NOT published in the feed: soil type, numeric pH / OC / EC / N / P / K values. These are reported as
    "Official data unavailable" and are never estimated or back-calculated from the classes.
A district absent from the feed (Chennai) returns {"available": False, "message": "Official data unavailable"}.
Shares are plain arithmetic on the published counts (count / samples tested for that parameter)."""
from __future__ import annotations

import pathlib
from functools import lru_cache
from typing import Dict, Optional

import pandas as pd

from app import config
from app.datasets.normalize import district_key
from app.datasets.soil_master_validator import validate

ROOT = pathlib.Path(__file__).resolve().parents[2]
PATH = ROOT / "data" / "official" / "raw" / "soil_master.csv"
SOURCE_REF = ROOT / "data" / "official" / "raw" / "soil_health_tn.csv"
UNAVAILABLE = "Official data unavailable"

# parameter -> (api group, label, official classes)
PARAMS = {
    "pH": ("ph", "pH", ["Acidic", "Neutral", "Alkaline"]),
    "OC": ("organic_carbon", "Organic carbon", ["High", "Medium", "Low"]),
    "n": ("nitrogen", "Nitrogen (available N)", ["High", "Medium", "Low"]),
    "p": ("phosphorus", "Phosphorus (available P)", ["High", "Medium", "Low"]),
    "k": ("potassium", "Potassium (available K)", ["High", "Medium", "Low"]),
    "EC": ("electrical_conductivity", "Electrical conductivity", ["Saline", "NonSaline"]),
    "S": ("micronutrients", "Sulphur", ["Sufficient", "Deficient"]),
    "Fe": ("micronutrients", "Iron", ["Sufficient", "Deficient"]),
    "Zn": ("micronutrients", "Zinc", ["Sufficient", "Deficient"]),
    "Cu": ("micronutrients", "Copper", ["Sufficient", "Deficient"]),
    "B": ("micronutrients", "Boron", ["Sufficient", "Deficient"]),
    "Mn": ("micronutrients", "Manganese", ["Sufficient", "Deficient"]),
}
COUNT_COLS = [f"{p}_{c}".lower() for p, (_, _, cs) in PARAMS.items() for c in cs]
COLUMNS = ["district", "district_code", "cycle", "soil_type", *COUNT_COLS,
           *[f"{p.lower()}_samples" for p in PARAMS], *[f"{p.lower()}_dominant_class" for p in PARAMS],
           "samples_tested", "last_processed", "source_url", "retrieved_at"]
NOT_PUBLISHED = ["soil type", "numeric pH", "numeric organic carbon", "numeric nitrogen / phosphorus / potassium (kg/ha)",
                 "numeric electrical conductivity (dS/m)", "numeric micronutrient values (ppm)"]


@lru_cache(maxsize=1)
def load_soil_master() -> pd.DataFrame:
    df = pd.read_csv(PATH, dtype=str, keep_default_na=False, na_values=[""])
    for c in [*COUNT_COLS, *[f"{p.lower()}_samples" for p in PARAMS], "samples_tested", "district_code"]:
        df[c] = pd.to_numeric(df[c])
    ref = pd.read_csv(SOURCE_REF) if SOURCE_REF.exists() else None
    validate(df, ref)
    return df


def _canonical(location: str) -> str:
    key = district_key(location)
    for name in config.LOCATIONS:
        if district_key(name) == key:
            return name
    raise ValueError(f"unknown district '{location}'")


def _row(canon: str) -> Optional[pd.Series]:
    df = load_soil_master()
    hit = df[df["district"] == canon]
    return None if hit.empty else hit.iloc[0]


def coverage() -> dict:
    df = load_soil_master()
    have = set(df["district"])
    return {"cycle": df["cycle"].iloc[0], "available": sorted(have),
            "unavailable": [{"district": d, "message": UNAVAILABLE} for d in config.LOCATIONS if d not in have]}


def parameter(row: pd.Series, p: str) -> dict:
    group, label, classes = PARAMS[p]
    counts = {c: int(row[f"{p}_{c}".lower()]) for c in classes}
    n = int(row[f"{p.lower()}_samples"])
    return {"label": label, "unit": "number of tested samples per class", "samples": n, "counts": counts,
            "share_pct": {c: (round(100.0 * v / n, 2) if n else None) for c, v in counts.items()},
            "dominant_class": row[f"{p.lower()}_dominant_class"]}


def soil_record(location: str) -> dict:
    """Full structured record for the API; raises ValueError only for an unknown district name."""
    canon = _canonical(location)
    row = _row(canon)
    if row is None:
        return {"district": canon, "available": False, "message": UNAVAILABLE,
                "reason": "the Soil Health Card portal feed for this cycle has no record for this district",
                "soil_type": UNAVAILABLE}
    out: Dict[str, object] = {
        "district": canon, "available": True, "cycle": row["cycle"], "samples_tested": int(row["samples_tested"]),
        "soil_type": UNAVAILABLE,
        "ph": parameter(row, "pH"), "organic_carbon": parameter(row, "OC"), "nitrogen": parameter(row, "n"),
        "phosphorus": parameter(row, "p"), "potassium": parameter(row, "k"),
        "electrical_conductivity": parameter(row, "EC"),
        "micronutrients": {PARAMS[p][1]: parameter(row, p) for p in ("S", "Fe", "Zn", "Cu", "B", "Mn")},
        "not_published_by_source": {k: UNAVAILABLE for k in NOT_PUBLISHED},
        "source": {"dataset": "Soil Health Card portal, district nutrient dashboard", "url": row["source_url"],
                   "cycle": row["cycle"], "last_processed": row["last_processed"], "retrieved_at": row["retrieved_at"],
                   "file": "data/official/raw/soil_master.csv"},
    }
    return out


def explanation_support(location: str) -> dict:
    """Citations for the explainability layer: sentence + the official counts it rests on, or 'Official data unavailable'."""
    rec = soil_record(location)
    if not rec["available"]:
        return {"available": False, "text": f"Soil: {UNAVAILABLE} for {rec['district']}.", "evidence": None}
    parts = []
    for key in ("ph", "organic_carbon", "nitrogen", "phosphorus", "potassium", "electrical_conductivity"):
        p = rec[key]
        d = p["dominant_class"]
        parts.append(f"{p['label']}: {p['share_pct'][d]}% of {p['samples']:,} tested samples are '{d}' ({p['counts'][d]:,})")
    deficient = {k: v["share_pct"]["Deficient"] for k, v in rec["micronutrients"].items()}
    worst = max(deficient, key=lambda k: deficient[k])
    parts.append(f"most frequently deficient micronutrient: {worst} ({deficient[worst]}% of samples)")
    return {"available": True,
            "text": f"Soil Health Card {rec['cycle']}, {rec['district']}: " + "; ".join(parts) + ". Soil type and numeric values are "
                    f"{UNAVAILABLE.lower()}.",
            "evidence": {"dataset": rec["source"]["dataset"], "cycle": rec["cycle"], "samples_tested": rec["samples_tested"],
                         "ph": rec["ph"]["counts"], "organic_carbon": rec["organic_carbon"]["counts"],
                         "nitrogen": rec["nitrogen"]["counts"], "phosphorus": rec["phosphorus"]["counts"],
                         "potassium": rec["potassium"]["counts"], "electrical_conductivity": rec["electrical_conductivity"]["counts"],
                         "micronutrient_deficient_pct": deficient, "url": rec["source"]["url"]}}
