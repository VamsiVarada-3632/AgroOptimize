"""GET /api/datasets reports exactly what the official database holds."""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.datasets import service
from app.datasets.pipeline import all_datasets
from app.db import session
from app.main import app

client = TestClient(app)


def test_datasets_endpoint_matches_the_registry():
    body = client.get("/api/datasets").json()
    api = {d["name"]: d for d in body["datasets"]}
    registry = {p["name"]: p for p in service.provenance()}
    assert set(api) == set(registry) == {d.name for d in all_datasets()}
    for name, row in registry.items():
        assert api[name]["sha256"] == row["sha256"]
        assert api[name]["rows_clean"] == row["rows_clean"]


def test_registered_row_counts_are_the_rows_in_the_tables():
    with session.get_engine().connect() as con:
        for ds in all_datasets():
            n = con.execute(text(f"select count(*) from {ds.table}")).scalar()
            assert n == next(p["rows_clean"] for p in service.provenance() if p["name"] == ds.name), ds.name


def test_every_disabled_feature_names_its_missing_dataset_and_source():
    features = client.get("/api/datasets").json()["disabled_features"]
    assert features, "the registry lists the features switched off for lack of official data"
    for f in features:
        assert f["feature"] and f["missing_dataset"] and f["source"] and f["scope"]
    assert any("/api/weather" in f["feature"] for f in features)
