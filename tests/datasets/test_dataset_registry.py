"""Dataset registry: publishing sources and raw/clean row counts of the official datasets."""
from __future__ import annotations

from app.datasets import service
from app.datasets.pipeline import all_datasets
from tests.datasets.test_official_datasets import built_db  # noqa: F401  (module-scoped fixture)

DATASETS = all_datasets()


def test_every_official_dataset_names_its_source():
    for ds in DATASETS:
        assert ds.source and len(ds.source) > 10, ds.name


def test_registry_reports_raw_and_clean_rows(built_db):
    for p in service.provenance():
        assert p["rows_raw"] >= p["rows_clean"] > 0, p["name"]
        report = next(r for r in built_db if r["dataset"] == p["name"])
        assert p["rows_raw"] == report["rows_raw"]
