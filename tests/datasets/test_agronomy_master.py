import pandas as pd
import pytest

from app.datasets import agronomy_master as am
from app.datasets.agronomy_master_validator import AgronomyMasterError, parse_evidence, problems, validate
from app.scrapers.tnau_master import COLUMNS, TEXT_FIELDS

RAW = pd.read_csv(am.PATH, dtype=str, keep_default_na=False, na_values=[""])
for c in ("n_kg_ha", "p_kg_ha", "k_kg_ha"):
    RAW[c] = pd.to_numeric(RAW[c])
REF = pd.read_csv(am.REFERENCE)


def test_loads_and_validates():
    df = am.load_agronomy_master()
    assert list(df.columns) == COLUMNS and len(df) >= 12 and df.crop.is_unique


def test_exact_values_from_the_guide():
    s = am.agronomy_for("sorghum")
    assert "10kg/ha" in s.seed_rate and "45 x 15 cm" in s.spacing and "400 - 600" in s.suitable_rainfall
    assert (s.n_kg_ha, s.p_kg_ha, s.k_kg_ha) == (90, 45, 45)
    assert "5 kg/ha" in am.agronomy_for("Sesame").seed_rate
    assert "120 kg/ha of kernels" in am.agronomy_for("Groundnut").seed_rate
    assert "20 kg/ha for CO 1" in am.agronomy_for("Maize").seed_rate
    assert "1000 - 4500" in am.agronomy_for("Rice").suitable_rainfall


def test_unreported_fields_are_null_not_estimated():
    df = am.load_agronomy_master()
    for f in ("water_requirement", "recommended_soil", "soil_ph"):
        assert df[f].isna().all(), f          # the guide gives no water mm / soil / pH range for these crops


def test_multi_condition_npk_stays_null_with_detail():
    c = am.agronomy_for("Cumbu")
    assert pd.isna(c.n_kg_ha) and "varieties: N 70 P2O5 35 K2O 35" in c.npk_by_condition
    assert "P2O5 NULL" in am.agronomy_for("Bengalgram").npk_by_condition if am.agronomy_for("Bengalgram") is not None else True


def test_every_populated_field_has_evidence_page():
    for _, r in am.load_agronomy_master().iterrows():
        ev = parse_evidence(r.evidence_pages)
        for f in TEXT_FIELDS:
            assert (f in ev) == isinstance(r[f], str), (r.crop, f)


def test_unknown_crop_returns_none():
    assert am.agronomy_for("dragonfruit") is None


def test_validator_rejects_bad_data():
    for mutate, expect in [
        (lambda d: d.__setitem__("source_url", "https://blog.example.com/x"), "source_url"),
        (lambda d: d.loc.__setitem__((0, "seed_rate"), "NA"), "placeholder"),
        (lambda d: d.loc.__setitem__((0, "n_kg_ha"), 900.0), "outside"),
        (lambda d: d.loc.__setitem__((0, "n_kg_ha"), 91.0), "differs"),
        (lambda d: d.loc.__setitem__((0, "soil_ph"), "6.5 to 7.5"), "evidence"),
        (lambda d: d.loc.__setitem__((0, "evidence_pages"), "seed_rate:999"), "out of range"),
    ]:
        bad = RAW.copy(); mutate(bad)
        assert any(expect in p for p in problems(bad, REF)), expect
    dup = pd.concat([RAW, RAW.iloc[[0]]], ignore_index=True)
    assert any("unique" in p for p in problems(dup, REF))
    with pytest.raises(AgronomyMasterError):
        validate(RAW.drop(columns=["spacing"]), REF)


def test_npk_agrees_with_tnau_fertiliser_csv():
    assert problems(RAW, REF) == []
