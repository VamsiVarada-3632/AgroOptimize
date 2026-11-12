"""Official-data loader (replaces the synthetic CSV loader).

`load_all()` returns the four frames the pipeline consumes - "crop", "land", "rainfall", "water" -
built by app.data.official_view from the official database only. There is no CSV fallback: if the
database or a dataset is missing the loader raises OfficialDataUnavailable naming the dataset.
The archived synthetic CSVs live in legacy/ and are never read here."""
from __future__ import annotations
from typing import Dict, List

import pandas as pd

from app import config
from app.data import official_view


def load_all() -> Dict[str, pd.DataFrame]:
    return official_view.frames()


def clear_cache() -> None:
    official_view.clear_cache()


def available_locations() -> List[str]:
    return list(config.LOCATIONS)


def available_years(kind: str = "crop") -> List[int]:
    return sorted(int(y) for y in load_all()[kind]["Year"].unique())


def available_seasons() -> List[str]:
    return list(config.AG_SEASONS)
