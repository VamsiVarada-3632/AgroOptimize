"""Validator for data/official/raw/agronomy_master.csv (TNAU Crop Production Guide, verbatim).

Rules: exact column set; unique crop; official TNAU source URL; every populated text field has an evidence page
(1..460) and no evidence is claimed for a NULL field; NPK numeric and equal to agronomy_tnau.csv where filled;
no placeholder strings; NULL is the empty cell (never 'NA', 'nan', 'None', '0' for unknown)."""
from __future__ import annotations

import re
from typing import List

import pandas as pd

from app.scrapers.tnau_master import COLUMNS, TEXT_FIELDS

PDF_PAGES = 460
PLACEHOLDERS = {"na", "n/a", "nan", "none", "null", "tbd", "unknown", "estimated", "-", "--"}
SOURCE_HOST = "agritech.tnau.ac.in"
NUMERIC = ["n_kg_ha", "p_kg_ha", "k_kg_ha"]
MAX_TEXT = 12000


class AgronomyMasterError(ValueError):
    pass


def parse_evidence(s: str) -> dict:
    out = {}
    for part in filter(None, (s or "").split(";")):
        m = re.fullmatch(r"([a-z_]+):(\d+)(?:-(\d+))?", part.strip())
        if not m:
            raise AgronomyMasterError(f"bad evidence token '{part}'")
        a, b = int(m.group(2)), int(m.group(3) or m.group(2))
        if not (1 <= a <= b <= PDF_PAGES):
            raise AgronomyMasterError(f"evidence pages out of range in '{part}'")
        out[m.group(1)] = (a, b)
    return out


def problems(df: pd.DataFrame, npk_reference: pd.DataFrame | None = None) -> List[str]:
    bad: List[str] = []
    if list(df.columns) != COLUMNS:
        return [f"columns must be exactly {COLUMNS}"]
    if df["crop"].isna().any() or df["crop"].duplicated().any():
        bad.append("crop must be present and unique")
    for i, r in df.iterrows():
        tag = f"{r['crop']}"
        if SOURCE_HOST not in str(r["source_url"]):
            bad.append(f"{tag}: source_url is not agritech.tnau.ac.in")
        try:
            ev = parse_evidence(r["evidence_pages"] if isinstance(r["evidence_pages"], str) else "")
        except AgronomyMasterError as exc:
            bad.append(f"{tag}: {exc}"); ev = {}
        for f in TEXT_FIELDS:
            v = r[f]
            if isinstance(v, str):
                if v.strip().lower() in PLACEHOLDERS or not v.strip():
                    bad.append(f"{tag}.{f}: placeholder value '{v}' (use an empty cell for NULL)")
                if len(v) > MAX_TEXT:
                    bad.append(f"{tag}.{f}: text too long")
                if f not in ev:
                    bad.append(f"{tag}.{f}: populated without an evidence page")
            elif f in ev:
                bad.append(f"{tag}.{f}: evidence given for a NULL field")
        for f in NUMERIC:
            v = r[f]
            if pd.notna(v) and not (0 <= float(v) <= 500):
                bad.append(f"{tag}.{f}: {v} outside 0..500 kg/ha")
        if npk_reference is not None and pd.notna(r["n_kg_ha"]):
            sub = npk_reference[npk_reference.crop == r["crop"]]
            trips = {(a, b, c) for a, b, c in zip(sub.n_kg_ha, sub.p_kg_ha, sub.k_kg_ha)}
            if trips != {(r["n_kg_ha"], r["p_kg_ha"], r["k_kg_ha"])}:
                bad.append(f"{tag}: NPK differs from agronomy_tnau.csv")
        if pd.isna(r["n_kg_ha"]) and not isinstance(r["npk_by_condition"], str):
            bad.append(f"{tag}: NPK NULL but npk_by_condition empty")
    return bad


def validate(df: pd.DataFrame, npk_reference: pd.DataFrame | None = None) -> None:
    p = problems(df, npk_reference)
    if p:
        raise AgronomyMasterError("; ".join(p[:20]))
