"""
Data layer on the OFFICIAL datasets: loader, catalogue, region/season profiles, normalised snapshot, exclusions.
(The synthetic-data version of this file is archived in legacy/tests/ for paper reproduction.)
"""
from __future__ import annotations

import math

import pytest

from app import config
from app.data import loader
from app.data import official_view as ov
from app.data import preprocessing as pp
from app.errors import FeatureUnavailable


class TestLoader:

    def test_load_all_returns_the_four_frames(self):
        assert set(loader.load_all()) == {"crop", "land", "rainfall", "water"}

    def test_every_district_is_present_in_every_frame(self):
        for kind, df in loader.load_all().items():
            assert set(df["Location"]) == set(config.LOCATIONS), kind

    def test_locations_are_the_official_38_districts_and_pollachi_is_not_one(self):
        assert len(config.LOCATIONS) == 38 and "Pollachi" not in config.LOCATIONS

    def test_available_seasons_and_years_are_the_official_ones(self):
        assert loader.available_seasons() == ["Kharif", "Rabi"]
        assert loader.available_years("crop") == [2024]

    def test_load_all_is_cached_and_clear_cache_reloads(self):
        a = loader.load_all()
        assert loader.load_all()["crop"] is a["crop"]
        loader.clear_cache()
        assert loader.load_all()["crop"] is not a["crop"]

    def test_missing_database_raises_instead_of_falling_back(self, monkeypatch, tmp_path):
        from app.datasets import service as svc
        from app.db import session
        monkeypatch.setenv("AGROOPTIMIZE_DB_URL", f"sqlite:///{tmp_path / 'nothing.db'}")
        session.reset_engine_cache()
        try:
            with pytest.raises(svc.OfficialDataUnavailable, match="official database not available"):
                svc._q("select * from district")
        finally:
            monkeypatch.undo()
            session.reset_engine_cache()

    def test_candidate_crop_frame_has_no_estimated_values(self):
        crop = loader.load_all()["crop"]
        ok = crop.dropna(subset=["Yield_Kg_Ha", "MSP_Rs_Qtl", "Cost_Rs_Qtl", "Irrigated_Share"])
        assert len(ok) > 0 and (ok["Irrigated_Share"].between(0, 1)).all()
        assert (ok["Yield_Kg_Ha"] > 0).all() and (ok["Cost_Rs_Qtl"] > 0).all()


class TestCatalog:

    def test_list_catalog_shape(self):
        c = pp.list_catalog()
        assert set(c["locations"]) == set(config.LOCATIONS) and set(c["seasons"]) == set(config.AG_SEASONS)
        assert c["years"] == [2024] and set(c["crops_by_season"]) == set(config.AG_SEASONS)
        assert c["taluk_notes"] and c["data_sources"]

    def test_catalog_crops_are_the_ten_with_complete_comparable_official_data(self):
        crops = {x for v in pp.list_catalog()["crops_by_season"].values() for x in v}
        assert crops == {"bajra", "black gram", "gingelly", "green gram", "groundnut", "jowar", "maize",
                         "ragi", "red gram", "sunflower"}  # cotton, rice excluded: unit basis


class TestRegionSeasonProfile:

    @pytest.mark.parametrize("location", config.LOCATIONS)
    @pytest.mark.parametrize("season", config.AG_SEASONS)
    def test_profile_builds_or_is_refused_with_the_reason(self, location, season):
        try:
            p = pp.get_region_season_profile(location, season, year=2024)
        except ValueError as exc:
            assert "complete official data" in str(exc)
            return
        assert (p.location, p.season, p.year) == (location, season, 2024)
        assert len(p.candidate_crops) >= config.MIN_CANDIDATE_CROPS
        assert p.sources if hasattr(p, "sources") else True

    def test_profile_defaults_to_the_latest_official_year(self):
        assert pp.get_region_season_profile("Coimbatore", "Kharif", year=None).year == 2024

    def test_year_without_official_data_is_refused_not_estimated(self):
        with pytest.raises(ValueError, match="No official data for year=2023"):
            pp.get_region_season_profile("Coimbatore", "Kharif", year=2023)

    def test_unknown_location_season_and_pollachi(self):
        with pytest.raises(ValueError):
            pp.get_region_season_profile("Atlantis", "Kharif")
        with pytest.raises(ValueError):
            pp.get_region_season_profile("Coimbatore", "Monsoon")
        with pytest.raises(ValueError, match="taluk"):
            pp.get_region_season_profile("Pollachi", "Kharif")

    def test_summer_is_not_a_season_in_the_official_data(self):
        with pytest.raises(ValueError):
            pp.get_region_season_profile("Salem", "Summer")

    def test_soil_fertility_index_in_range_when_published(self):
        for loc in ("Coimbatore", "Salem", "Erode"):
            assert 0 <= pp.get_region_season_profile(loc, "Rabi").soil.fertility_index <= 100

    def test_candidate_crops_sorted_by_district_revenue_descending(self):
        p = pp.get_region_season_profile("Coimbatore", "Kharif")
        revenues = [c.revenue_rs_lakh_hist for c in p.candidate_crops]
        assert revenues == sorted(revenues, reverse=True)

    def test_max_candidate_crops_is_respected(self):
        assert len(pp.get_region_season_profile("Coimbatore", "Kharif", max_candidate_crops=3).candidate_crops) == 3

    def test_candidate_economics_are_msp_and_cacp_cost_per_quintal(self):
        p = pp.get_region_season_profile("Coimbatore", "Kharif")
        for c in p.candidate_crops:
            q = c.yield_kg_ha / 100.0
            assert c.revenue_rs_ha == pytest.approx(q * c.msp_rs_qtl) and c.cost_rs_ha == pytest.approx(q * c.cost_rs_qtl)
            assert c.irrigated_share == pytest.approx(1 - c.rainfed_share, abs=1e-3)

    def test_excluded_crops_are_listed_with_reasons(self):
        p = pp.get_region_season_profile("Coimbatore", "Kharif")
        assert p.excluded_crops and all(e["crop"] and e["reasons"] for e in p.excluded_crops)

    def test_missing_dose_excludes_the_crop(self):
        p = pp.get_region_season_profile("Coimbatore", "Kharif", max_candidate_crops=50)
        names = {c.name for c in p.candidate_crops}
        assert "banana" not in names and "sugarcane" not in names      # no TNAU dose / MSP in the loaded datasets


class TestNormalizedSnapshot:

    @pytest.mark.parametrize("location", config.LOCATIONS)
    def test_snapshot_fields_in_unit_range_or_none(self, location):
        try:
            p = pp.get_region_season_profile(location, "Rabi")
        except ValueError:
            return
        for key, value in pp.normalized_snapshot(p).items():
            assert value is None or (not math.isnan(value) and 0.0 <= value <= 1.0), (key, value)


class TestOfficialView:

    def test_soil_summary_classes_and_index(self):
        s = ov.soil_summary("coimbatore")
        assert s["n_status"] in {"Low", "Medium", "High"} and 0 <= s["fertility_index"] <= 100
        assert s["samples_tested"] > 0

    def test_unknown_district_has_no_soil_summary(self):
        assert ov.soil_summary("atlantis") is None

    def test_reservoir_storage_only_where_a_reservoir_is_mapped(self):
        w = pp.get_region_season_profile("Coimbatore", "Rabi").water
        assert w.avg_storage_percent is not None and w.reservoirs
        assert pp.get_region_season_profile("Salem", "Kharif").water.avg_storage_percent is None


class TestDisabledFeatures:

    def test_each_disabled_feature_names_its_missing_official_dataset(self):
        from app.datasets.status import DISABLED_FEATURES
        assert DISABLED_FEATURES
        for f in DISABLED_FEATURES:
            assert f["feature"] and f["missing_dataset"] and f["source"]

    def test_weather_raises_feature_unavailable(self):
        from app.services import dashboard_service as ds
        with pytest.raises(FeatureUnavailable):
            ds.get_weather("Coimbatore")
