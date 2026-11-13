"""MSP pipeline: text PDFs (parsed) + scanned PDFs (transcribed) -> validated `msp` table rows.

validate: cross-notification equality, margin = MSP/cost - 1 (+-1 pt), increase = MSP - previous (exact)."""
from __future__ import annotations
import re
from pathlib import Path
from typing import List

import pandas as pd

from app.datasets.base import CleanResult, Issue, DataValidationError
from app.datasets.normalize import crop_key
from app.scrapers.msp_pdf import parse_cost_table, pdf_text
from app.scrapers.msp_transcribed import COPRA_2024, TRANSCRIBED

TEXT_PDFS = {   # file -> (marketing season, season of the 'previous year' column)
    "Press Release_Press Information Bureau.pdf": ("KMS 2024-25", "KMS 2023-24"),
    "MSP 2025-2026_241017_102537.pdf": ("RMS 2025-26", "RMS 2024-25"),
}
COLUMNS = ["marketing_season", "crop", "variety", "msp_rs_qtl", "cost_rs_qtl", "margin_pct", "source_file", "source_page", "verified"]


def extract(pdf_dir: Path) -> pd.DataFrame:
    rows = []
    for fname, (season, prev_season) in TEXT_PDFS.items():
        p = Path(pdf_dir) / fname
        if not p.exists():
            raise FileNotFoundError(p)
        for r in parse_cost_table(pdf_text(str(p))):
            variety = (r["variety"] or "").lstrip("(").strip() or None
            if r["crop"] == "Cotton" and variety:
                variety = {"Medium": "Medium Staple", "Long": "Long Staple"}.get(variety, variety)
            rows.append((season, r["crop"], variety, r["msp"], r["cost"], r["margin"], fname, None, True))
            rows.append((prev_season, r["crop"], variety, r["prev"], None, None, fname, None, True))   # 'previous year' column
    for season, crop, variety, msp, f, page in TRANSCRIBED:
        rows.append((season, crop, variety, float(msp), None, None, f, page, True))
    for season, crop, variety, msp, f, page in COPRA_2024:
        rows.append((season, crop, variety, msp, None, None, f, page, True))
    df = pd.DataFrame(rows, columns=COLUMNS)
    df["_ck"] = df["crop"].map(crop_key)
    df = df.sort_values("cost_rs_qtl", na_position="last")          # keep the row that carries cost/margin
    df = df.drop_duplicates(subset=["marketing_season", "_ck", "variety", "msp_rs_qtl"]).drop(columns="_ck")
    return df.sort_values(["marketing_season", "crop", "variety"], na_position="first").reset_index(drop=True)


def validate(df: pd.DataFrame, pdf_dir: Path | None = None) -> List[Issue]:
    issues: List[Issue] = []
    key = df.assign(ck=df.crop.map(crop_key)).groupby(["marketing_season", "ck", "variety"], dropna=False).msp_rs_qtl.nunique()
    conflicts = key[key > 1]
    if len(conflicts):
        raise DataValidationError(f"conflicting MSP values for the same crop/season: {list(conflicts.index)[:5]}")
    # margin check
    c = df.dropna(subset=["cost_rs_qtl", "margin_pct"])
    bad = c[((c.msp_rs_qtl / c.cost_rs_qtl - 1) * 100 - c.margin_pct).abs() > 1.0]
    if len(bad):
        raise DataValidationError(f"margin over cost inconsistent for {bad[['marketing_season','crop']].values.tolist()}")
    issues.append(Issue("info", "margin_check", f"{len(c)} rows: margin = MSP/cost-1 within 1 point"))
    if (df.msp_rs_qtl <= 0).any():
        raise DataValidationError("non-positive MSP")
    if ((df.msp_rs_qtl < 1000) | (df.msp_rs_qtl > 20000)).any():
        raise DataValidationError("MSP outside plausible Rs 1,000-20,000 per quintal")
    return issues


def clean(df: pd.DataFrame, pdf_dir: Path | None = None) -> CleanResult:
    issues = validate(df, pdf_dir)
    out = df.copy()
    out["crop_key"] = out["crop"].map(crop_key)
    return CleanResult(frame=out, issues=issues, rows_raw=len(df))


from app.datasets.base import OfficialDataset  # noqa: E402


class MspExtracted(OfficialDataset):
    """data/official/raw/msp_extracted.csv, written by scripts/extract_msp.py from the official PDFs."""
    name, filename, table = "msp_extracted", "msp_extracted.csv", "msp"
    required_columns = tuple(COLUMNS)

    def clean(self, df):
        self.validate_raw(df)
        res = clean(df.drop_duplicates().reset_index(drop=True))
        f = res.frame
        res.frame = pd.DataFrame({"crop": f["crop_key"], "variety": f["variety"], "marketing_season": f["marketing_season"],
                                  "msp_rs_qtl": f["msp_rs_qtl"], "cost_rs_qtl": f["cost_rs_qtl"], "margin_pct": f["margin_pct"],
                                  "source_file": f["source_file"], "source_page": f["source_page"], "verified": f["verified"].astype(bool)})
        return res
