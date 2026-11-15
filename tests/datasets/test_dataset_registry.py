"""Dataset registry: publishing sources and raw/clean row counts of the official datasets."""
from __future__ import annotations

from app.datasets import service
from app.datasets.pipeline import all_datasets

DATASETS = all_datasets()


def test_every_official_dataset_names_its_source():
    for ds in DATASETS:
        assert ds.source and len(ds.source) > 10, ds.name
