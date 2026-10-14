"""
Tests for the District Intelligence service and endpoint
(app/services/district_service.py, GET /api/district-intelligence/{district}).

Values are checked against independent pandas calculations on the raw
CSVs, so the tests catch a wrong aggregation rather than re-asserting the
service's own arithmetic.
"""
from __future__ import annotations

import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import config
from app.data import loader
from app.data import preprocessing as pp
from app.fuzzy import engine as fz
from app.main import app
from app.services import district_service as dsv

client = TestClient(app)
DISTRICTS = list(config.LOCATIONS)


def _observed(kind, location):
    df = loader.load_all()[kind]
    df = df[df["Location"] == location]
    return df[~df["data_source"].str.startswith("Estimated")]


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

    def test_sections_present(self, intel):
        for key in ("overview", "coverage", "climate", "soil", "water", "crops", "suitability", "market", "insights", "summary"):
            assert key in intel

    def test_serialisable_without_nan(self, intel):
        json.dumps(intel)
        assert all(not (isinstance(v, float) and not math.isfinite(v)) for v in _walk(intel))

    def test_unavailable_fields_are_null_with_note(self, intel):
        assert intel["overview"]["agricultural_zone"] is None
        assert intel["overview"]["agricultural_zone_note"]

    def test_insights_are_traceable_items(self, intel):
        assert intel["insights"]
        for item in intel["insights"]:
            assert item["detail"] and item["source"] and isinstance(item["evidence"], dict)

    def test_summary_text_matches_sentences(self, intel):
        assert intel["summary"]["text"] == " ".join(intel["summary"]["sentences"])
        assert intel["district"] in intel["summary"]["text"]


class TestAgainstRawData:

    def test_estimated_years_are_excluded(self, intel):
        assert intel["coverage"]["estimated_years"] == [2024]
        assert 2024 not in [a["year"] for a in intel["climate"]["annual"]]
        assert 2024 not in intel["crops"]["filters"]["years"]

    def test_annual_rainfall_totals(self, intel):
        raw = _observed("rainfall", intel["district"]).groupby("Year")["Monthly_Rainfall_mm"].sum()
        for row in intel["climate"]["annual"]:
            assert row["total_mm"] == pytest.approx(raw[row["year"]], abs=0.05)
        assert intel["overview"]["average_annual_rainfall_mm"] == pytest.approx(raw.mean(), abs=0.05)

    def test_mean_temperature(self, intel):
        r = _observed("rainfall", intel["district"])
        assert intel["overview"]["average_temperature_c"] == pytest.approx(((r.Max_Temp_C + r.Min_Temp_C) / 2).mean(), abs=0.05)

    def test_met_season_shares_sum_to_100(self, intel):
        assert sum(m["share_pct"] for m in intel["climate"]["met_season_share"]) == pytest.approx(100, abs=0.5)

    def test_crop_records_match_csv(self, intel):
        raw = _observed("crop", intel["district"])
        assert len(intel["crops"]["records"]) == len(raw)
        rec = intel["crops"]["records"][0]
        row = raw[(raw.Year == rec["year"]) & (raw.Season == rec["season"]) & (raw.Crop_Name == rec["crop"])].iloc[0]
        assert rec["production_t"] == pytest.approx(row.Production_Tonnes, abs=1)
        assert rec["yield_t_ha"] == pytest.approx(row.Yield_Kg_Ha / 1000, abs=0.001)

    def test_season_area_shares_sum_to_100(self, intel):
        by = {}
        for r in intel["crops"]["records"]:
            by.setdefault((r["year"], r["season"]), 0.0)
            by[(r["year"], r["season"])] += r["area_share_pct"]
        assert all(v == pytest.approx(100, abs=0.5) for v in by.values())

    def test_soil_fertility_index_uses_existing_formula(self, intel):
        rec = intel["soil"]["records"][0]
        expected = pp.compute_soil_fertility_index(rec["ph"], rec["organic_carbon_pct"], rec["n_status"], rec["p_status"], rec["k_status"])
        assert rec["fertility_index"] == expected

    def test_water_demand_and_primary_sources(self, intel):
        w = _observed("water", intel["district"])
        demand = w.groupby("Year")["Total_Demand_MCM"].sum()
        for y in intel["water"]["yearly"]:
            assert y["total_demand_mcm"] == pytest.approx(demand[y["year"]], abs=0.05)
        assert sum(s["share_of_months_pct"] for s in intel["water"]["primary_sources"]) == pytest.approx(100, abs=0.5)

    def test_storage_static_flag_matches_data(self, intel):
        w = _observed("water", intel["district"])
        identical = bool((w.groupby("Month")["Storage_Percent"].nunique() == 1).all())
        assert intel["water"]["storage_identical_every_year"] is identical


class TestSuitability:

    def test_ranks_are_contiguous(self, intel):
        rows = intel["suitability"]["rankings"]
        assert [r["rank"] for r in rows] == list(range(1, len(rows) + 1))
        assert [r["score"] for r in rows] == sorted((r["score"] for r in rows), reverse=True)
        for season in config.AG_SEASONS:
            ranks = [r["season_rank"] for r in rows if r["season"] == season]
            assert ranks == list(range(1, len(ranks) + 1))

    def test_score_is_mean_of_components(self, intel):
        for r in intel["suitability"]["rankings"]:
            comps = [v for v in r["components"].values() if v is not None]
            assert all(0 <= v <= 1 for v in comps)
            assert r["score"] == pytest.approx(100 * np.mean(comps), abs=0.2)

    def test_per_hectare_values_match_objective_formula(self, intel):
        """Recompute cost/water/yield for one crop directly from the CSV row and
        config prices, independently of FarmPlanProblem."""
        r = intel["suitability"]["rankings"][0]
        year = intel["suitability"]["year_basis"]
        raw = loader.load_all()["crop"]
        row = raw[(raw.Location == intel["district"]) & (raw.Year == year) & (raw.Season == r["season"])
                  & (raw.Crop_Name == r["crop"])].iloc[0]
        prices = config.FERTILIZER_PRICE_RS_PER_KG_NUTRIENT
        cost = (row.Fertilizer_N_Kg_Ha * prices["N"] + row.Fertilizer_P_Kg_Ha * prices["P"]
                + row.Fertilizer_K_Kg_Ha * prices["K"] + row.Pesticide_Cost_Rs_Ha + row.Labor_Days_Ha * config.LABOR_WAGE_RS_PER_DAY)
        assert r["cost_rs_ha"] == pytest.approx(cost, abs=1)
        profile = pp.get_region_season_profile(intel["district"], r["season"], year=year)
        net = max(row.Water_Req_mm - profile.rainfall.effective_rainfall_mm, 0)
        assert r["irrigation_need_l_ha"] == pytest.approx(net * config.LITERS_PER_MM_PER_HA, abs=1)
        a = fz.evaluate_uncertainty(profile.rainfall.avg_deviation_percent, profile.water.avg_storage_percent,
                                    profile.soil.fertility_index)
        conf = fz.crop_yield_confidence(a.yield_confidence, a.irrigation_risk, row.Rainfall_Dependency)
        assert r["expected_yield_t_ha"] == pytest.approx(row.Yield_Kg_Ha / 1000 * conf, abs=0.01)
        assert r["components"]["climate_soil"] == pytest.approx(conf, abs=0.001)

    def test_uses_latest_observed_year(self, intel):
        assert intel["suitability"]["year_basis"] == max(intel["coverage"]["observed_years"])


class TestMarket:

    def test_marked_historical_not_live(self, intel):
        assert intel["market"]["is_live"] is False
        assert "not live" in intel["market"]["note"]

    def test_price_trend_matches_csv(self, intel):
        item = intel["market"]["crops"][0]
        raw = _observed("crop", intel["district"])
        series = raw[raw.Crop_Name == item["crop"]].groupby("Year")["MSP_Rs_Qtl"].mean()
        first, last = series.iloc[0], series.iloc[-1]
        assert item["trend"]["change_pct"] == pytest.approx((last - first) / first * 100, abs=0.1)


class TestMissingData:

    def test_missing_water_and_soil_are_reported_not_estimated(self, monkeypatch):
        data = {k: v.copy() for k, v in loader.load_all().items()}
        data["water"] = data["water"][data["water"]["Location"] != "Erode"]
        data["land"] = data["land"][data["land"]["Location"] != "Erode"]
        monkeypatch.setattr(dsv, "load_all", lambda: data)
        dsv.clear_cache()
        try:
            out = dsv._build("Erode")
            assert out["water"] == {"available": False, "note": dsv.NOT_AVAILABLE}
            assert out["soil"]["available"] is False
            assert out["overview"]["agricultural_area_ha"] is None
            assert out["overview"]["primary_irrigation_sources"] == []
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
        body = r.json()
        assert body["district"].lower() == district
        assert body["suitability"]["rankings"]

    def test_unknown_district(self):
        assert client.get("/api/district-intelligence/chennai").status_code == 404
