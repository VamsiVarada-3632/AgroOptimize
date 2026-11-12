"""The fuzzy stage on the official data: default model, calibration from official distributions, graceful unavailability."""
import numpy as np
import pytest

from app import config
from app.data import official_view
from app.fuzzy import audit, calibration
from app.fuzzy import engine as fz


def test_official_model_is_the_runtime_default():
    assert config.FUZZY_MODEL == "official"
    assert fz.resolve_model().name == "official"
    assert fz.resolve_model("original").name == "original"       # the published model stays selectable (paper reproduction)


def test_calibration_percentiles_are_recomputed_from_the_official_data():
    rep = calibration.report()
    frames = official_view.frames()
    storage = calibration._storage_values()          # every mapped reservoir x month, from the official daily levels
    assert rep["water_storage"]["n_values"] == len(storage) > 100 and storage.min() >= 0 and storage.max() <= 100
    for p in (10, 50, 90):
        assert rep["water_storage"]["percentiles"][p] == pytest.approx(float(np.percentile(storage, p)), abs=0.01)
    fert = frames["land"].drop_duplicates("Location")["Soil_Fertility_Index"].dropna()
    assert rep["soil_fert"]["n_values"] == len(fert)
    for p in (10, 50, 90):
        assert rep["soil_fert"]["percentiles"][p] == pytest.approx(float(np.percentile(fert, p)), abs=0.01)


@pytest.mark.parametrize("var", ["water_storage", "soil_fert"])
def test_calibrated_sets_form_a_strong_partition(var):
    xs = np.linspace(0, 100, 401)
    total = np.zeros_like(xs)
    for x_i, x in enumerate(xs):
        total[x_i] = sum(fz.input_memberships(0, x if var == "water_storage" else 50, x if var == "soil_fert" else 50)[var].values())
    assert np.allclose(total, 1.0, atol=0.01)       # memberships are rounded to 3 decimals


def test_every_official_profile_activates_each_set_it_is_labelled_with():
    for loc in config.LOCATIONS:
        try:
            p = pp_profile(loc, "Rabi")
        except ValueError:
            continue
        if p.fuzzy_available:
            a = fz.assess_profile(p)
            m = fz.input_memberships(p.rainfall.avg_deviation_percent, p.water.avg_storage_percent, p.soil.fertility_index)
            assert m["rainfall_dev"][a.rainfall_label] > 0 and m["water_storage"][a.water_label] > 0 and m["soil_fert"][a.soil_label] > 0


def pp_profile(loc, season):
    from app.data import preprocessing as pp
    return pp.get_region_season_profile(loc, season)


def test_inert_rules_are_pruned_from_the_official_model():
    assert audit.rule_dominance(fz.resolve_model("official"))["inert"] == []
    assert len(fz.rule_numbers(fz.resolve_model("official"))) == 20


def test_audit_endpoint_runs_on_official_districts():
    from fastapi.testclient import TestClient
    from app.main import app
    body = TestClient(app).get("/api/fuzzy/audit").json()
    assert body["model"] == "official"
    assert body["dataset_firing"]["profiles"] >= 9


def test_missing_official_input_means_fuzzy_not_applied_and_yield_unadjusted():
    p = pp_profile("Salem", "Kharif")
    assert fz.assess_profile(p) is None
    from app.optimization.problem import FarmPlanProblem
    problem = FarmPlanProblem(p, None, total_land_ha=1.0)
    for m in problem.single_crop_metrics():
        assert m["crop_confidence"] == 1.0
