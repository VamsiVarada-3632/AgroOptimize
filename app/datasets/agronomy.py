"""TNAU crop-guide agronomy reference (blanket NPK/S doses) -> `agronomy_reference`.

Raw file `data/official/raw/agronomy_tnau.csv` is written by scripts/extract_tnau.py from
app/scrapers/tnau_guide.py (values transcribed from the official guide, page-cited)."""
from __future__ import annotations
import pandas as pd

from app.datasets.base import OfficialDataset, CleanResult, Issue, DataValidationError
from app.datasets.normalize import crop_key
from app.scrapers.tnau_guide import COLUMNS

LIMITS = {"n_kg_ha": (0, 400), "p_kg_ha": (0, 200), "k_kg_ha": (0, 300), "s_kg_ha": (0, 100)}


class AgronomyTnau(OfficialDataset):
    name, filename, table = "agronomy_tnau", "agronomy_tnau.csv", "agronomy_reference"
    required_columns = tuple(COLUMNS)

    def _clean(self, df: pd.DataFrame, res: CleanResult) -> pd.DataFrame:
        df = df.copy()
        df["crop"] = df["crop"].map(crop_key)
        if df.duplicated(["crop", "condition"]).any():
            raise DataValidationError("duplicate (crop, condition) rows in TNAU agronomy data")
        for col, (lo, hi) in LIMITS.items():
            bad = df[(df[col].notna()) & ((df[col] < lo) | (df[col] > hi))]
            if len(bad):
                raise DataValidationError(f"{col} outside [{lo},{hi}]: {bad[['crop','condition',col]].values.tolist()}")
        if df[["n_kg_ha", "p_kg_ha", "k_kg_ha"]].isna().all(axis=1).any():
            raise DataValidationError("row without any nutrient value")
        if not df["source_url"].str.startswith("https://agritech.tnau.ac.in/").all():
            raise DataValidationError("source_url is not an official TNAU host")
        if (df["pdf_page"] - df["printed_page"] != 12).any():
            raise DataValidationError("pdf_page/printed_page offset inconsistent")
        for _, r in df[df["note"].notna() & (df["note"] != "")].iterrows():
            res.issues.append(Issue("warning", "source_anomaly", f"{r['crop']}/{r['condition']}: {r['note']}", 1))
        res.issues.append(Issue("info", "agronomy_coverage",
                                f"{df.crop.nunique()} crops, {len(df)} condition rows; water requirement (mm) and duration NOT provided "
                                f"as numbers by the guide -> left NULL", len(df)))
        out = df[["crop", "condition", "n_kg_ha", "p_kg_ha", "k_kg_ha", "s_kg_ha", "pdf_page", "printed_page",
                  "evidence", "note", "source_url", "retrieved_at"]].copy()
        for c in ("water_req_mm", "duration_days"):
            out[c] = None
        out["note"] = out["note"].where(out["note"].notna() & (out["note"] != ""), None)
        return out
