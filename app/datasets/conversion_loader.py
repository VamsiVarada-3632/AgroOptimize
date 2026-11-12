"""Loads data/official/raw/conversion_table.csv - official unit-basis conversions with citations.

Nothing is hardcoded here. A conversion is available only if the CSV has a row for (crop, input_unit, output_unit)
AND that row is marked verified_applicable_to_dataset_units == 'yes', i.e. the official source says the factor
relates the same quantities as the Season & Crop Report yield and the MSP / CACP cost. Otherwise ConversionUnavailable
is raised and the crop stays disabled. Cotton (kapas <-> lint) has no row: no general official factor was found.
"""
from __future__ import annotations

import pathlib
from functools import lru_cache
from typing import List

import pandas as pd

PATH = pathlib.Path(__file__).resolve().parents[2] / "data" / "official" / "raw" / "conversion_table.csv"
COLUMNS = ["crop", "input_unit", "output_unit", "conversion_factor", "basis", "official_source", "source_url",
           "page_number", "year", "verified_applicable_to_dataset_units"]
OFFICIAL_HOSTS = ("pib.gov.in", "cag.gov.in", "cacp.da.gov.in", "agriwelfare.gov.in", "dfpd.gov.in", "fci.gov.in",
                  "des.tn.gov.in", "tnau.ac.in", "icar.gov.in", "cicr.org.in", "cotcorp.org.in", "texmin.nic.in")


class ConversionUnavailable(LookupError):
    """No official, applicable conversion is loaded for the requested units."""


@lru_cache(maxsize=1)
def load_table() -> pd.DataFrame:
    df = pd.read_csv(PATH, dtype=str).fillna("")
    validate(df)
    df["conversion_factor"] = df["conversion_factor"].astype(float)
    return df


def validate(df: pd.DataFrame) -> None:
    if list(df.columns) != COLUMNS:
        raise ValueError(f"conversion_table.csv columns must be {COLUMNS}")
    for i, r in df.iterrows():
        f = float(r.conversion_factor)
        if not 0 < f < 10:
            raise ValueError(f"row {i}: factor {f} out of range")
        if not r.official_source or not r.page_number or not r.year:
            raise ValueError(f"row {i}: source, page_number and year are required")
        if not any(h in r.source_url for h in OFFICIAL_HOSTS):
            raise ValueError(f"row {i}: source host is not on the official allow-list")
        if r.verified_applicable_to_dataset_units not in ("yes", "no"):
            raise ValueError(f"row {i}: verified_applicable_to_dataset_units must be yes/no")


def rows_for(crop: str) -> pd.DataFrame:
    t = load_table()
    return t[t["crop"] == crop.strip().lower()]


def conversion_factor(crop: str, input_unit: str, output_unit: str, *, require_applicable: bool = True) -> float:
    """Factor such that quantity_in_output_unit = quantity_in_input_unit * factor (or its inverse for the reverse direction)."""
    c, a, b = crop.strip().lower(), input_unit.strip().lower(), output_unit.strip().lower()
    t = rows_for(c)
    fwd = t[(t.input_unit == a) & (t.output_unit == b)]
    rev = t[(t.input_unit == b) & (t.output_unit == a)]
    hit, inverse = (fwd, False) if len(fwd) else (rev, True)
    if require_applicable:
        hit = hit[hit.verified_applicable_to_dataset_units == "yes"]
    if hit.empty:
        raise ConversionUnavailable(
            f"No official{' applicable' if require_applicable else ''} conversion loaded for {c}: {a} -> {b}")
    factors = set(hit.conversion_factor)
    if len(factors) != 1:
        raise ConversionUnavailable(f"Official sources disagree for {c}: {sorted(factors)}")
    f = factors.pop()
    return 1.0 / f if inverse else f


def citations(crop: str) -> List[dict]:
    return rows_for(crop).to_dict("records")
