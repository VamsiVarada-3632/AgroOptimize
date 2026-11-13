"""Loader for data/official/raw/agronomy_master.csv: TNAU Crop Production Guide agronomy, verbatim, NULL where absent."""
from __future__ import annotations

import pathlib
from functools import lru_cache
from typing import Optional

import pandas as pd

from app.datasets.agronomy_master_validator import validate

ROOT = pathlib.Path(__file__).resolve().parents[2]
PATH = ROOT / "data" / "official" / "raw" / "agronomy_master.csv"
REFERENCE = ROOT / "data" / "official" / "raw" / "agronomy_tnau.csv"


@lru_cache(maxsize=1)
def load_agronomy_master() -> pd.DataFrame:
    """Validated frame; empty cells are NaN/None (NULL), numerics are float."""
    df = pd.read_csv(PATH, dtype=str, keep_default_na=False, na_values=[""])
    for c in ("n_kg_ha", "p_kg_ha", "k_kg_ha"):
        df[c] = pd.to_numeric(df[c])
    ref = pd.read_csv(REFERENCE) if REFERENCE.exists() else None
    validate(df, ref)
    return df


def agronomy_for(crop: str) -> Optional[pd.Series]:
    df = load_agronomy_master()
    hit = df[df["crop"].str.lower() == crop.strip().lower()]
    return None if hit.empty else hit.iloc[0]


def crops() -> list:
    return load_agronomy_master()["crop"].tolist()
