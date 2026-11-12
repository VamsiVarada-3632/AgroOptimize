"""
Tests for the District Intelligence service and endpoint (app/services/district_service.py,
GET /api/district-intelligence/{district}) on the OFFICIAL data.

Values are checked against independent calculations on the official frames / Soil Health Card counts, so the tests
catch a wrong aggregation rather than re-asserting the service's own arithmetic. The synthetic-data version of this
file (multi-year trends, estimated years) is archived in legacy/tests/ for paper reproduction.
"""
from __future__ import annotations

import json
import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import config
from app.data import loader
from app.datasets import service as svc
from app.main import app
from app.services import district_service as dsv

client = TestClient(app)
DISTRICTS = list(config.LOCATIONS)
SECTIONS = ("overview", "coverage", "climate", "soil", "water", "crops", "suitability", "market", "insights", "summary")


@pytest.fixture(scope="module", params=DISTRICTS)
def intel(request):
    return dsv.get_district_intelligence(request.param)


def _walk(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)
    else:
        yield obj


class TestTrendHelper:

    def test_insufficient_data(self):
        assert dsv.trend([2020], [1.0]) is None

    def test_unchanged(self):
        t = dsv.trend([2020, 2021, 2022], [5.0, 5.0, 5.0])
        assert t["direction"] == "unchanged" and t["change_pct"] == 0.0

    def test_stable_increasing_decreasing(self):
        assert dsv.trend([2020, 2023], [100, 104])["direction"] == "stable"
        up = dsv.trend([2020, 2021, 2022, 2023], [100, 110, 120, 130])
        assert up["direction"] == "increasing" and up["change_pct"] == 30.0 and up["slope_per_year"] == 10.0
        assert dsv.trend([2020, 2023], [100, 80])["direction"] == "decreasing"

    def test_ignores_nan_and_sorts_years(self):
        t = dsv.trend([2022, 2020, 2021], [130.0, 100.0, float("nan")])
        assert (t["first_year"], t["last_year"], t["n_years"]) == (2020, 2022, 2)

    @pytest.mark.parametrize("cv,label", [(0.05, "low"), (0.10, "moderate"), (0.249, "moderate"), (0.25, "high"), (None, None)])
    def test_variability_label(self, cv, label):
        assert dsv.variability_label(cv) == label


class TestStructure:

    def test_all_sections_present_and_serialisable(self, intel):
        assert set(SECTIONS) <= set(intel) and intel["district"] in DISTRICTS
        json.dumps(intel)

    def test_no_nan_anywhere(self, intel):
        assert not [v for v in _walk(intel) if isinstance(v, float) and math.isnan(v)]

    def test_every_statement_carries_evidence_and_a_source(self, intel):
        for item in intel["insights"]:
            assert item["detail"] and item["source"] and isinstance(item["evidence"], dict)

    def test_summary_is_built_from_the_sections(self, intel):
        assert intel["summary"]["text"] == " ".join(intel["summary"]["sentences"])


class TestOfficialProvenance:

    def test_one_official_report_year_and_nothing_estimated(self, intel):
        cov = intel["coverage"]
        assert cov["observed_years"] == [2024] and cov["estimated_years"] == []
        assert cov["report_year"] == "2024-25" and cov["provenance"]
        assert any("crops_by_district" in p for p in cov["provenance"])

    def test_unavailable_official_fields_are_none_with_a_note_not_filled(self, intel):
        o = intel["overview"]
        assert o["coordinates"] is None and o["agricultural_zone"] is None and o["average_temperature_c"] is None
        assert o["coordinates_note"] and o["agricultural_zone_note"]
        assert all(a["mean_temp_c"] is None and a["humidity_pct"] is None for a in intel["climate"].get("annual", []))

    def test_pollachi_taluk_note_is_on_coimbatore_only(self):
        assert dsv.get_district_intelligence("Coimbatore")["overview"]["taluk_note"]
        assert dsv.get_district_intelligence("Salem")["overview"]["taluk_note"] is None


class TestAgainstOfficialData:

    def test_crop_records_equal_the_official_frame(self, intel):
        d = intel["district"]
        frame = loader.load_all()["crop"]
        frame = frame[frame.Location == d]
        assert len(intel["crops"]["records"]) == len(frame)
        by = {(r["season"], r["crop"]): r for r in intel["crops"]["records"]}
        for r in frame.itertuples():
            rec = by[(r.Season, r.Crop_Name)]
            assert rec["area_ha"] == (None if math.isnan(r.Area_Ha) else round(r.Area_Ha))
            assert rec["yield_t_ha"] == pytest.approx(r.Yield_Kg_Ha / 1000, abs=1e-3)
            assert rec["price_rs_qtl"] == (None if math.isnan(r.MSP_Rs_Qtl) else pytest.approx(r.MSP_Rs_Qtl, abs=0.01))

    def test_area_shares_sum_to_100_per_season(self, intel):
        for season in config.AG_SEASONS:
            shares = [r["area_share_pct"] for r in intel["crops"]["records"] if r["season"] == season and r["area_share_pct"] is not None]
            if shares:
                assert sum(shares) == pytest.approx(100.0, abs=0.05 * len(shares))

    def test_rainfall_equals_the_imd_rows(self, intel):
        d = intel["district"]
        r = loader.load_all()["rainfall"]
        r = r[r.Location == d].dropna(subset=["Monthly_Rainfall_mm"])
        clim = intel["climate"]
        if r.empty:
            assert clim["available"] is False
            return
        assert clim["annual"][0]["total_mm"] == pytest.approx(r.Monthly_Rainfall_mm.sum(), abs=0.1)
        assert clim["annual"][0]["normal_mm"] == pytest.approx(r.Normal_Rainfall_mm.sum(), abs=0.1)
        assert len(clim["monthly"]) == len(r)
        assert sum(m["share_pct"] for m in clim["met_season_share"]) == pytest.approx(100.0, abs=0.2)

    def test_soil_fertility_index_is_recomputed_from_soil_health_card_counts(self, intel):
        shc = svc.soil_health(intel["district"])
        if not shc or not intel["soil"].get("available"):
            assert intel["soil"]["available"] is False
            return
        score = []
        for k in ("n", "p", "k", "oc"):
            lo, me, hi = (shc[f"{k}_low"], shc[f"{k}_medium"], shc[f"{k}_high"])
            score.append((0.0 * lo + 0.5 * me + 1.0 * hi) / (lo + me + hi))
        assert intel["soil"]["latest"]["fertility_index_mean"] == pytest.approx(100 * np.mean(score), abs=0.06)
        assert intel["soil"]["latest"]["fuzzy_set"] in {"poor", "medium", "good"}

    def test_water_storage_matches_the_reservoir_frame(self, intel):
        d = intel["district"]
        w = loader.load_all()["water"]
        w = w[(w.Location == d)]
        sto = w.dropna(subset=["Storage_Percent"])
        water = intel["water"]
        if not water.get("available"):
            return
        assert {m["month"]: m["storage_pct"] for m in water["storage_by_month"]} == {r.Month: round(r.Storage_Percent, 1) for r in sto.itertuples()}
        for s in water["storage_by_season"]:
            months = config.SEASON_MONTH_MAP[s["season"]]
            g = sto[sto.Month.isin(months)]
            assert s["storage_pct"] == (round(g.Storage_Percent.mean(), 1) if len(g) else None)

    def test_market_prices_are_the_official_msp_and_cost(self, intel):
        for item in intel["market"]["crops"]:
            assert item["mean_rs_qtl"] > 0 and item["trend"] is None
        assert intel["market"]["is_live"] is False and "Agmarknet" in intel["market"]["note"]


class TestSuitability:

    def test_scores_are_bounded_and_ranked(self, intel):
        rows = intel["suitability"]["rankings"]
        if not rows:
            assert intel["suitability"]["available"] is False
            return
        scores = [r["score"] for r in rows]
        assert scores == sorted(scores, reverse=True) and all(0 <= s <= 100 for s in scores)
        assert [r["rank"] for r in rows] == list(range(1, len(rows) + 1))
        for r in rows:
            assert r["components"]["rainfall_fit"] is None          # crop water requirement (mm) is not published
            assert r["components"]["resource_efficiency"] is not None and r["cost_rs_ha"] > 0

    def test_only_crops_with_complete_official_data_are_ranked(self, intel):
        d = intel["district"]
        for season in config.AG_SEASONS:
            ranked = {r["crop"] for r in intel["suitability"]["rankings"] if r["season"] == season}
            try:
                from app.data import preprocessing as pp
                cands = {c.name for c in pp.get_region_season_profile(d, season, max_candidate_crops=12).candidate_crops}
            except ValueError:
                cands = set()
            assert ranked <= cands


class TestMissingData:

    def test_missing_water_and_soil_are_reported_not_estimated(self, monkeypatch):
        data = {k: v.copy() for k, v in loader.load_all().items()}
        data["water"] = data["water"][data["water"]["Location"] != "Erode"]
        data["land"] = data["land"][data["land"]["Location"] != "Erode"]
        monkeypatch.setattr(dsv, "load_all", lambda: data)
        dsv.clear_cache()
        try:
            out = dsv._build("Erode")
            assert out["water"]["available"] is False and "not available" in out["water"]["note"]
            assert out["soil"]["available"] is False
            assert out["overview"]["irrigated_pct"] is None
            json.dumps(out)
        finally:
            dsv.clear_cache()


class TestCachingAndEndpoint:

    def test_cached_per_district(self):
        assert dsv.get_district_intelligence("salem") is dsv.get_district_intelligence("SALEM")

    @pytest.mark.parametrize("district", [d.lower() for d in DISTRICTS])
    def test_endpoint(self, district):
        r = client.get(f"/api/district-intelligence/{district}")
        assert r.status_code == 200
        assert r.json()["district"].lower() == district

    def test_unknown_district(self):
        assert client.get("/api/district-intelligence/atlantis").status_code == 404

    def test_pollachi_taluk_is_not_a_district(self):
        assert client.get("/api/district-intelligence/pollachi").status_code in (400, 404)
