"""Unit tests for the official-data pipelines (validator, cleaner, loader, importer, service, cache)."""
from __future__ import annotations
import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from app.datasets import cache, service
from app.datasets.base import DataValidationError, RAW_DIR
from app.datasets.normalize import crop_key, district_key
from app.datasets.pipeline import all_datasets, build_database
from app.datasets.units import to_std
from app.db import session

DATASETS = all_datasets()
IDS = [d.name for d in DATASETS]


@pytest.fixture(scope="module")
def built_db(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "official.db"
    url = f"sqlite:///{path}"
    mp = pytest.MonkeyPatch(); mp.setenv("AGROOPTIMIZE_DB_URL", url)
    session.reset_engine_cache(); cache.clear_all()
    report = build_database(engine=session.get_engine(), clean_dir=None)
    yield report
    mp.undo(); session.reset_engine_cache(); cache.clear_all()


@pytest.mark.parametrize("ds", DATASETS, ids=IDS)
def test_validator_rejects_missing_column(ds):
    df = ds.read_raw()
    with pytest.raises(DataValidationError):
        ds.validate_raw(df.drop(columns=[ds.required_columns[-2]]))


@pytest.mark.parametrize("ds", DATASETS, ids=IDS)
def test_validator_rejects_empty(ds):
    with pytest.raises(DataValidationError):
        ds.validate_raw(ds.read_raw().iloc[0:0])


@pytest.mark.parametrize("ds", DATASETS, ids=IDS)
def test_cleaner_drops_exact_duplicates(ds):
    df = ds.read_raw()
    doubled = pd.concat([df, df.head(5)], ignore_index=True)
    assert len(ds.clean(doubled).frame) == len(ds.clean(df).frame)


@pytest.mark.parametrize("ds", DATASETS, ids=IDS)
def test_loader_reads_real_file_and_keeps_rows(ds):
    res = ds.load()
    assert res.rows_raw > 100 and len(res.frame) > 0
    assert not any(i.level == "error" for i in res.issues), [i for i in res.issues if i.level == "error"]


@pytest.mark.parametrize("ds", DATASETS, ids=IDS)
def test_importer_row_counts_match_clean(built_db, ds):
    n = session.get_engine().connect().execute(text(f"select count(*) from {ds.table}")).scalar()
    assert n == next(r["rows_clean"] for r in built_db if r["dataset"] == ds.name)


def test_registry_has_hash_for_each_file(built_db):
    prov = service.provenance()
    assert {p["name"] for p in prov} == set(IDS)
    assert all(len(p["sha256"]) == 64 for p in prov)


def test_district_normalisation_and_catalogue(built_db):
    assert district_key("Kanchipuram") == district_key("Kancheepuram")
    assert district_key("Tamil Nadu (State)") == "tamil nadu"
    d = service.districts()
    assert len(d) == 38 and "Pollachi" not in set(d.name)
    assert service.resolve_district("coimbatore") == "Coimbatore"
    with pytest.raises(ValueError):
        service.resolve_district("Pollachi")          # a taluk, not an official district


def test_crop_aliases():
    assert crop_key("Paddy") == crop_key("Rice") and crop_key("Sorghum") == crop_key("Jowar")


def test_unit_conversion():
    assert to_std("production", "bales of 170 kg lint", 100) == ("tonne", 17.0)
    assert to_std("production", "lakh nuts", 2) == ("nuts", 200000.0)
    assert to_std("yield", "tonnes / ha", 101) == ("kg_per_ha", 101000.0)
    assert to_std("yield", "nuts / ha", 1000)[0] == "nuts_per_ha"
    assert to_std("area", "ha", None)[1] is None
    with pytest.raises(ValueError):
        to_std("yield", "furlongs", 1)


def test_nulls_never_zero_filled(built_db):
    raw = pd.read_csv(RAW_DIR / "crops_by_district.csv")
    n = session.get_engine().connect().execute(text("select count(*) from crop_stat where value_raw is null")).scalar()
    assert n == int(raw.value.isna().sum()) > 0


def test_rainfall_reconciles(built_db):
    r = service.rainfall("Salem")
    whole = r[r.period.str.startswith("Whole")].iloc[0]
    assert whole.actual_mm == pytest.approx(1245.4) and whole.normal_mm == pytest.approx(912.5)


def test_groundwater_values_and_yearly_average_separated(built_db):
    g = service.groundwater("Coimbatore")
    assert g.is_yearly_average.sum() == 1 and g[~g.is_yearly_average.astype(bool)].level_m_bgl.between(0, 100).all()


def test_land_use_partition(built_db):
    lu = service.land_use("Salem")
    assert lu["Total geographical area"] == 520530 and lu["Net area sown"] == 208492


def test_reservoir_storage_pct_bounded_and_flagged(built_db):
    s = service.reservoir_series("mettur")
    assert s.storage_pct.between(0, 100).all()
    over = session.get_engine().connect().execute(text("select count(*) from reservoir_reading where over_capacity")).scalar()
    assert over > 0


def test_district_storage_none_when_no_reservoir(built_db):
    assert service.district_storage_pct("Salem") is not None      # Mettur
    assert service.district_storage_pct("Chennai") is None         # nothing mapped -> no invented number


def test_cache_returns_same_object_until_cleared(built_db):
    a = service.districts(); b = service.districts()
    assert a is b
    cache.clear_all()
    assert service.districts() is not a


def test_service_raises_clear_error_without_database(tmp_path, monkeypatch):
    monkeypatch.setenv("AGROOPTIMIZE_DB_URL", f"sqlite:///{tmp_path/'none.db'}")
    session.reset_engine_cache(); cache.clear_all()
    with pytest.raises(service.OfficialDataUnavailable):
        service.districts()
    session.reset_engine_cache(); cache.clear_all()
