"""Read-only loader for the archived synthetic CSVs (comparison / debugging only)."""
from __future__ import annotations
from pathlib import Path
import pandas as pd

LEGACY_RAW = Path(__file__).resolve().parent / "data" / "raw"
LOCATIONS = ("Coimbatore", "Erode", "Pollachi", "Salem")
KINDS = ("crop", "land", "rainfall", "water_availability")


def load_kind(kind: str) -> pd.DataFrame:
    frames = [pd.read_csv(LEGACY_RAW / f"{loc.lower()}_{kind}.csv") for loc in LOCATIONS]
    return pd.concat(frames, ignore_index=True)


def load_all() -> dict:
    return {k: load_kind(k) for k in KINDS}
