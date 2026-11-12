"""Read API over the official-data database (the only runtime data source).

Every method returns plain python / pandas; `provenance()` lists the registry rows behind the data so
API responses and explanations can cite file, report year and hash."""
from __future__ import annotations

from typing import Optional

import pandas as pd
from sqlalchemy import text

from app.datasets.cache import ttl_cache
from app.datasets.normalize import crop_key, district_key
from app.db.session import db_url, get_engine


class OfficialDataUnavailable(RuntimeError):
    """The official database has not been built (run scripts/preprocess_all.py)."""


def _q(sql: str, **params) -> pd.DataFrame:
    try:
        return pd.read_sql(text(sql), get_engine(), params=params)
    except Exception as exc:  # sqlite: no such table / missing file
        raise OfficialDataUnavailable(f"official database not available at {db_url()}: {exc}") from exc


@ttl_cache()
def districts(include_state: bool = False) -> pd.DataFrame:
    df = _q("select norm_name, name, code, is_state from district order by name")
    return df if include_state else df[~df.is_state.astype(bool)].reset_index(drop=True)


def resolve_district(name: str) -> str:
    """Official display name for any accepted spelling; raises ValueError for unknown names."""
    d = districts()
    k = district_key(name)
    hit = d[d.norm_name == k]
    if hit.empty:
        raise ValueError(f"Unknown district '{name}'. Official districts: {', '.join(d.name)}.")
    return str(hit.iloc[0]["name"])


@ttl_cache()
def provenance() -> list:
    return _q("select id, name, filename, sha256, report_year, rows_clean, imported_at from dataset_registry").to_dict("records")


@ttl_cache()
def crop_stats(district: str) -> pd.DataFrame:
    return _q("select crop, season, measure, unit_std, value_std from crop_stat where district = :d", d=district_key(district))


@ttl_cache()
def state_series(crop: str, measure: str) -> pd.DataFrame:
    return _q("select year_start, value_std, unit_std from state_crop_series where crop=:c and measure=:m order by year_start",
              c=crop_key(crop), m=measure)


@ttl_cache()
def land_use(district: str) -> dict:
    df = _q("select category, value from land_use where district=:d and measure='area_ha'", d=district_key(district))
    return {r.category: r.value for r in df.itertuples()}


@ttl_cache()
def irrigation(district: str) -> pd.DataFrame:
    return _q("select tbl, grp, item, measure, unit, value from irrigation where district=:d", d=district_key(district))


@ttl_cache()
def rainfall(district: str) -> pd.DataFrame:
    return _q("select imd_season, period, month_start, is_total, actual_mm, normal_mm, pct_deviation from rainfall where district=:d order by month_start",
              d=district_key(district))


@ttl_cache()
def groundwater(district: str) -> pd.DataFrame:
    return _q("select period, month_start, is_yearly_average, level_m_bgl from groundwater where district=:d order by month_start",
              d=district_key(district))


@ttl_cache()
def reservoirs_for(district: str) -> pd.DataFrame:
    return _q("select m.slug, r.name, m.basis from district_reservoir_map m join reservoir r on r.slug=m.slug where m.district=:d",
              d=district_key(district))


@ttl_cache()
def reservoir_series(slug: str) -> pd.DataFrame:
    return _q("select date, capacity_mcft, storage_mcft, storage_pct, inflow_cusecs, outflow_cusecs, last_year_storage_mcft "
              "from reservoir_reading where slug=:s order by date", s=slug)


def district_storage_pct(district: str, start: Optional[str] = None, end: Optional[str] = None) -> Optional[float]:
    """Capacity-weighted mean storage % of the reservoirs serving the district over [start, end]
    (ISO dates; default = whole record). None when no reservoir is mapped (never a made-up value)."""
    res = reservoirs_for(district)
    if res.empty:
        return None
    num = den = 0.0
    for slug in res.slug:
        s = reservoir_series(slug)
        if start:
            s = s[s.date >= start]
        if end:
            s = s[s.date <= end]
        s = s.dropna(subset=["storage_mcft", "capacity_mcft"])
        if s.empty:
            continue
        num += float(s.storage_mcft.sum()); den += float(s.capacity_mcft.sum())
    return None if den == 0 else round(min(100.0, num / den * 100.0), 2)
