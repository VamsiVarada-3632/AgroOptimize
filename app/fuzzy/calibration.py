"""Fuzzy membership functions calibrated from the OFFICIAL data distributions (replaces hand-chosen breakpoints).

* water_storage: peaks at the 10th / 50th / 90th percentile of the official monthly reservoir storage % of
  every mapped reservoir (TN Water Resources Dept daily levels).
* soil_fert: peaks at the 10th / 50th / 90th percentile of the district fertility index derived from the
  Soil Health Card class counts.
* rainfall_dev: the official IMD category bands (normal within +/-19 %, deficient/excess beyond) are retained -
  they are an official classification, not something to re-estimate.
Sets form strong (Ruspini) partitions, so memberships sum to 1 and neighbours cross at 0.5.
`report()` returns every number used, for the explanation layer and the project report."""
from __future__ import annotations
from functools import lru_cache

import numpy as np

from app.data import official_view as ov
from app.datasets import service as svc
from app.fuzzy import engine

PCTS = (10, 50, 90)


def _storage_values() -> np.ndarray:
    vals = []
    for slug in svc._q("select slug from reservoir").slug:
        s = svc.reservoir_series(slug).dropna(subset=["storage_mcft", "capacity_mcft"])
        if s.empty:
            continue
        s = s.assign(m=s.date.astype(str).str[:7]).groupby("m")[["storage_mcft", "capacity_mcft"]].sum()
        vals.extend((s.storage_mcft / s.capacity_mcft * 100.0).clip(upper=100.0).tolist())
    return np.array(vals, dtype=float)


def _fertility_values() -> np.ndarray:
    d = svc._q("select norm_name from district where is_state = 0").norm_name
    return np.array([x["fertility_index"] for x in (ov.soil_summary(k) for k in d) if x], dtype=float)


def _sets(p10: float, p50: float, p90: float, labels) -> dict:
    lo, mid, hi = labels
    return {lo: (0.0, 0.0, p10, p50), mid: (p10, p50, p90), hi: (p50, p90, 100.0, 100.0)}


@lru_cache(maxsize=1)
def report() -> dict:
    out = {"method": "strong partition with peaks at the 10th/50th/90th percentile of the official distribution; IMD rainfall bands retained"}
    for var, vals, labels, src in (
        ("water_storage", _storage_values(), ("low", "medium", "high"), "TN Water Resources Dept daily reservoir levels (monthly storage %)"),
        ("soil_fert", _fertility_values(), ("poor", "medium", "good"), "Soil Health Card district class counts -> fertility index"),
    ):
        p = [round(float(np.percentile(vals, q)), 2) for q in PCTS]
        out[var] = {"source": src, "n_values": int(len(vals)), "min": round(float(vals.min()), 2), "max": round(float(vals.max()), 2),
                    "percentiles": dict(zip(PCTS, p)), "sets": {k: list(v) for k, v in _sets(*p, labels).items()}}
    out["rainfall_dev"] = {"source": "IMD category bands (normal within +/-19.5 %)", "sets": {k: list(v) for k, v in engine.IMD_RAINFALL_SETS["rainfall_dev"].items()}}
    return out


def official_model() -> engine.FuzzyModel:
    r = report()
    custom = tuple((var, tuple((lab, tuple(par)) for lab, par in r[var]["sets"].items())) for var in ("water_storage", "soil_fert"))
    return engine.FuzzyModel(
        "official", "Official-data calibration: IMD rainfall bands + percentile-based storage/fertility partitions, inert rules pruned.",
        strong_partition=False, imd_rainfall=True, prune_inert=True, custom_sets=custom)
