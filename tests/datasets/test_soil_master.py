import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import config
from app.datasets import soil_master as sm
from app.datasets.soil_master_validator import SoilMasterError, problems, validate
from app.main import app

RAW_SRC = pd.read_csv(sm.SOURCE_REF)
RAW = pd.read_csv(sm.PATH, dtype=str, keep_default_na=False, na_values=[""])
NUM = [*sm.COUNT_COLS, *[f"{p.lower()}_samples" for p in sm.PARAMS], "samples_tested", "district_code"]
for _c in NUM:
    RAW[_c] = pd.to_numeric(RAW[_c])
client = TestClient(app)


def test_loads_validates_and_covers_37_districts():
    df = sm.load_soil_master()
    assert list(df.columns) == sm.COLUMNS and len(df) == 37 and df.district.is_unique
    assert set(df.district) <= set(config.LOCATIONS)
    assert [d["district"] for d in sm.coverage()["unavailable"]] == ["Chennai"]


def test_counts_equal_the_official_file():
    row = RAW[RAW.district == "Coimbatore"].iloc[0]
    src = RAW_SRC[RAW_SRC.district.str.upper() == "COIMBATORE"].iloc[0]
    for p, (_, _, cs) in sm.PARAMS.items():
        for c in cs:
            assert row[f"{p}_{c}".lower()] == src[f"{p}_{c}"]


def test_record_structure_and_shares():
    r = sm.soil_record("Salem")
    assert r["available"] and r["cycle"] == "2024-25"
    for k in ("ph", "organic_carbon", "nitrogen", "phosphorus", "potassium", "electrical_conductivity"):
        assert abs(sum(r[k]["share_pct"].values()) - 100) < 0.05
    assert set(r["micronutrients"]) == {"Sulphur", "Iron", "Zinc", "Copper", "Boron", "Manganese"}
    assert r["soil_type"] == sm.UNAVAILABLE and all(v == sm.UNAVAILABLE for v in r["not_published_by_source"].values())


def test_alias_names_resolve():
    assert sm.soil_record("Tuticorin")["district"] == "Thoothukudi"
    assert sm.soil_record("kanchipuram")["available"]


def test_missing_district_returns_official_data_unavailable():
    r = sm.soil_record("Chennai")
    assert r["available"] is False and r["message"] == "Official data unavailable"
    assert "ph" not in r and "nitrogen" not in r            # no numbers invented
    assert sm.explanation_support("Chennai")["text"] == "Soil: Official data unavailable for Chennai."


def test_unknown_district_is_an_error():
    with pytest.raises(ValueError):
        sm.soil_record("Atlantis")


def test_explanation_support_cites_counts():
    e = sm.explanation_support("Salem")
    assert e["available"] and "Soil Health Card 2024-25" in e["text"] and "14,982" in e["text"]
    assert e["evidence"]["nitrogen"]["Low"] == 14922 and e["evidence"]["url"].startswith("https://soilhealth")


def test_api_endpoints():
    ok = client.get("/api/soil-master/Erode").json()
    assert ok["available"] and ok["ph"]["samples"] > 0 and ok["soil_type"] == "Official data unavailable"
    no = client.get("/api/soil-master/Chennai")
    assert no.status_code == 200 and no.json()["message"] == "Official data unavailable"
    assert client.get("/api/soil-master/Atlantis").status_code == 404
    cov = client.get("/api/soil-master").json()
    assert len(cov["available"]) == 37 and cov["unavailable"][0]["district"] == "Chennai"


def test_validator_rejects_bad_data():
    for mutate, expect in [
        (lambda d: d.loc.__setitem__((0, "soil_type"), "Red loam"), "soil_type"),
        (lambda d: d.loc.__setitem__((0, "n_low"), -1), "non-negative"),
        (lambda d: d.loc.__setitem__((0, "n_low"), d.loc[0, "n_low"] + 5), "sum of class counts"),
        (lambda d: d.loc.__setitem__((0, "ph_dominant_class"), "Acidic"), "dominant"),
        (lambda d: d.loc.__setitem__((0, "district"), "Atlantis"), "canonical"),
        (lambda d: d.loc.__setitem__((0, "source_url"), "https://blog.example.com"), "Soil Health Card portal"),
    ]:
        bad = RAW.copy(); mutate(bad)
        assert any(expect in p for p in problems(bad, RAW_SRC)), expect
    dup = pd.concat([RAW, RAW.iloc[[0]]], ignore_index=True)
    assert any("unique" in p for p in problems(dup, RAW_SRC))
    drift = RAW.copy(); drift.loc[0, "k_high"] += 1; drift.loc[0, "k_samples"] += 1
    assert any("differs from raw file" in p for p in problems(drift, RAW_SRC))
    with pytest.raises(SoilMasterError):
        validate(RAW.drop(columns=["zn_deficient"]), RAW_SRC)
    assert problems(RAW, RAW_SRC) == []
