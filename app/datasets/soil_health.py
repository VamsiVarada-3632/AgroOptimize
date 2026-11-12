"""Soil Health Card (soilhealth.dac.gov.in) district nutrient-class sample counts, Tamil Nadu, cycle 2024-25.

Raw file: data/official/raw/soil_health_tn.csv (reproduced by scripts/browser/shc_nutrient_dashboard.js).
Values are counts of tested samples per class exactly as published; nothing is estimated.
Derived shares (e.g. % samples Low in N) are computed in the service from these counts."""
from __future__ import annotations
import pandas as pd

from app.datasets.base import OfficialDataset, CleanResult, Issue, DataValidationError
from app.datasets.normalize import district_key

PARAMS = {"n": ["High", "Medium", "Low"], "p": ["High", "Medium", "Low"], "k": ["High", "Medium", "Low"],
          "S": ["Sufficient", "Deficient"], "OC": ["High", "Medium", "Low"], "pH": ["Acidic", "Neutral", "Alkaline"],
          "EC": ["Saline", "NonSaline"], "Fe": ["Sufficient", "Deficient"], "Zn": ["Sufficient", "Deficient"],
          "Cu": ["Sufficient", "Deficient"], "B": ["Sufficient", "Deficient"], "Mn": ["Sufficient", "Deficient"]}
VALUE_COLS = [f"{p}_{c}" for p, cs in PARAMS.items() for c in cs]
SOURCE_URL = "https://soilhealth.dac.gov.in/"
MAX_SPREAD = 0.03    # tested-sample totals of different parameters may differ by at most 3 %


class SoilHealthTN(OfficialDataset):
    name, filename, table = "soil_health_tn", "soil_health_tn.csv", "soil_health"
    required_columns = ("district", "district_code", "cycle", *VALUE_COLS, "last_processed")

    def _clean(self, df: pd.DataFrame, res: CleanResult) -> pd.DataFrame:
        df = df.copy()
        if (df[VALUE_COLS] < 0).any().any() or df[VALUE_COLS].isna().any().any():
            raise DataValidationError("soil health counts must be non-negative integers and non-null")
        df["district"] = df["district"].map(district_key)
        if df.duplicated(["district", "cycle"]).any():
            raise DataValidationError("duplicate (district, cycle) in soil health data")
        totals = pd.DataFrame({p: df[[f"{p}_{c}" for c in cs]].sum(axis=1) for p, cs in PARAMS.items()})
        spread = (totals.max(axis=1) - totals.min(axis=1)) / totals.max(axis=1)
        if (spread > MAX_SPREAD).any():
            raise DataValidationError(f"tested-sample totals disagree across parameters by >{MAX_SPREAD:.0%}: "
                                      f"{df.loc[spread > MAX_SPREAD, 'district'].tolist()}")
        res.issues.append(Issue("info", "totals_consistent", f"max spread of per-parameter totals {spread.max():.2%}", len(df)))
        df["samples_tested"] = totals.max(axis=1).astype(int)
        res.issues.append(Issue("info", "coverage", f"{df.district.nunique()} districts; districts absent from the portal feed for this "
                                f"cycle have no soil data (not estimated)", len(df)))
        out = df.copy()
        out.columns = [c.lower() for c in out.columns]
        out["source_url"] = SOURCE_URL
        out["retrieved_at"] = "2026-11-12"
        keep = ["district", "cycle", "district_code", *[c.lower() for c in VALUE_COLS], "last_processed", "source_url", "retrieved_at"]
        return out[keep]
