import pandas as pd, pytest
from app.datasets.base import DataValidationError
from app.datasets.msp import MspExtracted, validate
from app.datasets.agronomy import AgronomyTnau


def test_msp_known_values():
    f = MspExtracted().load().frame.set_index(["marketing_season", "crop"])
    assert f.loc[("KMS 2025-26", "jowar")].msp_rs_qtl.max() >= 3699
    paddy = MspExtracted().load().frame
    assert paddy[(paddy.crop == "rice") & (paddy.marketing_season == "KMS 2025-26")].msp_rs_qtl.isin([2369, 2389]).any()


def test_msp_conflict_rejected():
    df = pd.read_csv("data/official/raw/msp_extracted.csv")
    dup = df.iloc[[0]].copy(); dup["msp_rs_qtl"] += 50
    with pytest.raises(DataValidationError):
        validate(pd.concat([df, dup]))


def test_msp_implausible_rejected():
    df = pd.read_csv("data/official/raw/msp_extracted.csv").iloc[:3].copy()
    df["cost_rs_qtl"] = None; df["margin_pct"] = None; df["msp_rs_qtl"] = 50
    with pytest.raises(DataValidationError):
        validate(df)


def test_agronomy_values_and_nulls():
    r = AgronomyTnau().load(); f = r.frame
    m = f[(f.crop == "maize") & (f.condition == "hybrids")].iloc[0]
    assert (m.n_kg_ha, m.p_kg_ha, m.k_kg_ha) == (250, 75, 75)
    bg = f[(f.crop == "bengal gram") & (f.condition == "irrigated")].iloc[0]
    assert pd.isna(bg.p_kg_ha)                      # printed typo is not "fixed"
    assert f.water_req_mm.isna().all() and f.duration_days.isna().all()
    assert any(i.code == "source_anomaly" for i in r.issues)


def test_agronomy_rejects_unofficial_source_and_range():
    df = pd.read_csv("data/official/raw/agronomy_tnau.csv")
    bad = df.copy(); bad.loc[0, "source_url"] = "https://blog.example.com/x"
    with pytest.raises(DataValidationError):
        AgronomyTnau().clean(bad)
    bad = df.copy(); bad.loc[0, "n_kg_ha"] = 9999
    with pytest.raises(DataValidationError):
        AgronomyTnau().clean(bad)


def test_soil_health_loads_and_matches_districts():
    from app.datasets.soil_health import SoilHealthTN
    from app.datasets import service
    r = SoilHealthTN().load(); f = r.frame
    assert len(f) == 37 and f.district.is_unique
    d = service.districts(); known = set(d[d.is_state == 0].norm_name)
    assert set(f.district) <= known                 # every soil district resolves to an official district
    assert known - set(f.district) == {"chennai"}   # Chennai is absent from the portal feed (no data, not estimated)
    assert f.loc[f.district == "tiruvarur", "n_low"].iloc[0] == 15672


def test_soil_health_rejects_inconsistent_totals():
    import pandas as pd
    from app.datasets.soil_health import SoilHealthTN
    df = pd.read_csv("data/official/raw/soil_health_tn.csv"); df.loc[0, "p_High"] = 999999
    with pytest.raises(DataValidationError):
        SoilHealthTN().clean(df)
