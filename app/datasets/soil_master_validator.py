"""Validator for data/official/raw/soil_master.csv.

Rules: exact columns; unique canonical district (config.LOCATIONS); counts are non-negative integers; per-parameter
samples equal the sum of its class counts; the dominant class is the argmax of the counts (ties are labelled 'tie');
samples_tested = max per-parameter samples; per-parameter totals within 3 % of each other; soil_type is NULL (the
official feed has none); counts equal the raw Soil Health Card file; cycle/URL/provenance present."""
from __future__ import annotations

from typing import List

import pandas as pd

MAX_SPREAD = 0.03


class SoilMasterError(ValueError):
    pass


def problems(df: pd.DataFrame, raw: pd.DataFrame | None = None) -> List[str]:
    from app import config
    from app.datasets import soil_master as sm
    from app.datasets.normalize import district_key
    bad: List[str] = []
    if list(df.columns) != sm.COLUMNS:
        return [f"columns must be exactly {sm.COLUMNS}"]
    if df["district"].isna().any() or df["district"].duplicated().any():
        bad.append("district must be present and unique")
    known = set(config.LOCATIONS)
    for d in df["district"].dropna():
        if d not in known:
            bad.append(f"{d}: not a canonical district name")
    if df["soil_type"].notna().any():
        bad.append("soil_type must be NULL: the official feed does not publish it")
    for i, r in df.iterrows():
        tag = r["district"]
        sample_totals = []
        for p, (_, _, classes) in sm.PARAMS.items():
            vals = [r[f"{p}_{c}".lower()] for c in classes]
            if any(pd.isna(v) or v < 0 or float(v) != int(v) for v in vals):
                bad.append(f"{tag}.{p}: counts must be non-negative integers"); continue
            tot = int(sum(vals))
            sample_totals.append(tot)
            if int(r[f"{p.lower()}_samples"]) != tot:
                bad.append(f"{tag}.{p}: samples != sum of class counts")
            top = max(vals)
            expect = "tie" if vals.count(top) > 1 else classes[vals.index(top)]
            if r[f"{p.lower()}_dominant_class"] != expect:
                bad.append(f"{tag}.{p}: dominant class should be {expect}")
        if sample_totals:
            if int(r["samples_tested"]) != max(sample_totals):
                bad.append(f"{tag}: samples_tested != max parameter total")
            if (max(sample_totals) - min(sample_totals)) / max(sample_totals) > MAX_SPREAD:
                bad.append(f"{tag}: parameter totals differ by more than {MAX_SPREAD:.0%}")
        for f in ("cycle", "source_url", "retrieved_at", "last_processed"):
            if pd.isna(r[f]) or not str(r[f]).strip():
                bad.append(f"{tag}.{f}: missing")
        if "soilhealth.dac.gov.in" not in str(r["source_url"]):
            bad.append(f"{tag}: source_url is not the Soil Health Card portal")
    if raw is not None:
        raw = raw.copy(); raw["k"] = raw["district"].map(district_key)
        for _, r in df.iterrows():
            src = raw[raw.k == district_key(r["district"])]
            if src.empty:
                bad.append(f"{r['district']}: not in raw Soil Health Card file"); continue
            s = src.iloc[0]
            for p, (_, _, classes) in sm.PARAMS.items():
                for c in classes:
                    if int(r[f"{p}_{c}".lower()]) != int(s[f"{p}_{c}"]):
                        bad.append(f"{r['district']}.{p}_{c}: differs from raw file")
    return bad


def validate(df: pd.DataFrame, raw: pd.DataFrame | None = None) -> None:
    p = problems(df, raw)
    if p:
        raise SoilMasterError("; ".join(p[:20]))
