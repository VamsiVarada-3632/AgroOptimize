"""
Regression tests for the 2026-09-29 audit hardening pass:

  * run_id validation / path safety in results_store
  * atomic JSON writes + mtime-keyed summary cache
  * case-insensitive location/season matching
  * query/body validation on the API
  * history ordering (newest saved run first)
  * dataset-provenance flag for estimated years
  * NSGA-II determinism, including under concurrent requests
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from app import config
from app.data import preprocessing as pp
from app.fuzzy import engine as fz
from app.main import app
from app.optimization.nsga2_runner import extract_pareto_plans, run_nsga2
from app.optimization.problem import FarmPlanProblem
from app.services import dashboard_service as ds
from app.services import results_store

client = TestClient(app)

FAST = {"pop_size": config.NSGA2_FAST_POP_SIZE, "n_gen": config.NSGA2_FAST_N_GEN}


# ---------------------------------------------------------------------------
# results_store: run_id validation, corrupt files, cache, atomic writes
# ---------------------------------------------------------------------------

class TestRunIdValidation:

    @pytest.mark.parametrize("run_id", [
        "coimbatore_kharif_2023_20260808T113724Z",
        "salem_summer_2024_20260101T000000Z",
    ])
    def test_real_run_ids_are_valid(self, run_id):
        assert results_store.is_valid_run_id(run_id)

    @pytest.mark.parametrize("run_id", ["../app/config", "..", "a/b", "", ".hidden", "x" * 200, "a b"])
    def test_unsafe_run_ids_are_rejected(self, run_id):
        assert not results_store.is_valid_run_id(run_id)

    def test_load_run_refuses_path_traversal(self, tmp_path):
        outside = tmp_path / "secret.json"
        outside.write_text(json.dumps({"x": 1}))
        inner = tmp_path / "results"
        inner.mkdir()
        assert results_store.load_run("../secret", out_dir=inner) is None

    def test_endpoint_returns_404_for_invalid_id(self):
        assert client.get("/api/results/..%2F..%2Fapp%2Fconfig").status_code == 404
        assert client.get("/api/results/.hidden").status_code == 404


class TestSavedRunListing:

    @staticmethod
    def _record(location="Erode", saved_at="2026-01-01T00:00:00+00:00", n_plans=2):
        return {
            "run_id": f"{location.lower()}_kharif_2023_x",
            "region_profile": {"location": location, "season": "Kharif", "year": 2023},
            "meta": {"preference": "balanced"},
            "saved_at": saved_at,
            "plans": [{}] * n_plans,
            "client_id": None,
        }

    def test_corrupt_or_incomplete_json_is_skipped(self, tmp_path):
        (tmp_path / "good.json").write_text(json.dumps(self._record()))
        (tmp_path / "broken.json").write_text("{not json")
        (tmp_path / "incomplete.json").write_text(json.dumps({"plans": []}))
        runs = results_store.list_saved_runs(out_dir=tmp_path)
        assert [r["location"] for r in runs] == ["Erode"]

    def test_load_run_returns_none_for_corrupt_file(self, tmp_path):
        (tmp_path / "broken.json").write_text("{not json")
        assert results_store.load_run("broken", out_dir=tmp_path) is None

    def test_summary_cache_notices_rewritten_files(self, tmp_path):
        path = tmp_path / "run.json"
        path.write_text(json.dumps(self._record(n_plans=2)))
        assert results_store.list_saved_runs(out_dir=tmp_path)[0]["n_plans"] == 2
        time.sleep(0.01)
        path.write_text(json.dumps(self._record(n_plans=5)))
        os.utime(path, None)
        assert results_store.list_saved_runs(out_dir=tmp_path)[0]["n_plans"] == 5

    def test_returned_summaries_are_copies(self, tmp_path):
        (tmp_path / "run.json").write_text(json.dumps(self._record()))
        first = results_store.list_saved_runs(out_dir=tmp_path)
        first[0]["location"] = "mutated"
        assert results_store.list_saved_runs(out_dir=tmp_path)[0]["location"] == "Erode"

    def test_save_leaves_no_temp_files(self, tmp_path):
        from app.schemas import FarmPlanRequest
        from app.services.plan_service import generate_farm_plans

        generate_farm_plans(
            FarmPlanRequest(location="Salem", season="Rabi", total_land_ha=2, save_results=True, **FAST),
            results_dir=tmp_path,
        )
        leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
        assert leftovers == []


# ---------------------------------------------------------------------------
# Input normalisation and validation
# ---------------------------------------------------------------------------

class TestInputHandling:

    def test_location_and_season_are_case_insensitive(self):
        profile = pp.get_region_season_profile(" coimbatore ", "KHARIF", year=2023)
        assert profile.location == "Coimbatore"
        assert profile.season == "Kharif"

    def test_farm_plans_accepts_lowercase_location(self):
        r = client.post("/api/farm-plans", json={
            "location": "pollachi", "season": "rabi", "total_land_ha": 3, "save_results": False, **FAST,
        })
        assert r.status_code == 200
        assert r.json()["region_profile"]["location"] == "Pollachi"

    def test_unknown_location_is_still_rejected(self):
        with pytest.raises(ValueError):
            pp.get_region_season_profile("Chennai", "Kharif")

    @pytest.mark.parametrize("path", ["/api/plans/salem", "/api/comparison/salem", "/api/compare-fuzzy/salem"])
    @pytest.mark.parametrize("params", [{"total_land_ha": 0}, {"total_land_ha": -5}, {"budget_rs": -1}])
    def test_dashboard_endpoints_reject_non_positive_inputs(self, path, params):
        assert client.get(path, params=params).status_code == 422

    def test_overlong_client_id_is_rejected(self):
        assert client.get("/api/history/salem", params={"client_id": "x" * 500}).status_code == 422

    def test_negative_preference_filter_is_rejected(self):
        r = client.post("/api/farm-plans", json={
            "location": "Salem", "season": "Kharif", "total_land_ha": 3,
            "max_cost_rs": -10, "save_results": False, **FAST,
        })
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# History ordering
# ---------------------------------------------------------------------------

def test_history_is_newest_saved_run_first(monkeypatch):
    summaries = [
        {"run_id": "old", "location": "Salem", "season": "Summer", "year": 2023,
         "preference": "balanced", "saved_at": "2026-01-01T00:00:00+00:00", "n_plans": 1, "client_id": "me"},
        {"run_id": "new", "location": "Salem", "season": "Kharif", "year": 2023,
         "preference": "balanced", "saved_at": "2026-06-01T00:00:00+00:00", "n_plans": 1, "client_id": "me"},
    ]
    record = {"plans": [{"area_ha": [1.0], "yield_tonnes": 2.0, "cost_rs": 100.0}],
              "fuzzy_assessment": {"yield_confidence": 0.5, "irrigation_risk": 0.5}}
    monkeypatch.setattr(results_store, "list_saved_runs", lambda **k: summaries)
    monkeypatch.setattr(results_store, "load_run", lambda *a, **k: record)
    history = ds.get_history("salem", client_id="me")["history"]
    # Alphabetical-by-season ordering would have put "Summer" first.
    assert [h["id"] for h in history] == ["new", "old"]
    assert "saved_at" not in history[0]


# ---------------------------------------------------------------------------
# Provenance of estimated years
# ---------------------------------------------------------------------------

class TestEstimatedYearFlag:

    def test_observed_year_is_not_flagged(self):
        assert pp.is_estimated_year("Coimbatore", 2023) is False
        assert pp.get_region_season_profile("Coimbatore", "Kharif", year=2023).data_year_estimated is False

    def test_estimated_year_is_flagged(self):
        assert pp.is_estimated_year("Coimbatore", 2024) is True
        assert pp.get_region_season_profile("Coimbatore", "Kharif", year=2024).data_year_estimated is True

    def test_flag_is_exposed_by_the_api(self):
        body = client.get("/api/region-profile", params={"location": "Salem", "season": "Kharif", "year": 2023}).json()
        assert body["data_year_estimated"] is False
        dash = client.get("/api/dashboard/salem").json()
        assert isinstance(dash["data_year"], int)
        assert isinstance(dash["data_year_estimated"], bool)


# ---------------------------------------------------------------------------
# Determinism (serial and concurrent) and the dashboard cache
# ---------------------------------------------------------------------------

def _front_signature(location="Erode", season="Kharif", seed=42):
    profile = pp.get_region_season_profile(location, season, year=2023)
    assessment = fz.evaluate_uncertainty(
        profile.rainfall.avg_deviation_percent,
        profile.water.avg_storage_percent,
        profile.soil.fertility_index,
    )
    problem = FarmPlanProblem(profile, assessment, total_land_ha=4.0)
    result = run_nsga2(problem, seed=seed, **FAST)
    return sorted((p.yield_tonnes, p.cost_rs, p.water_liters, p.env_impact_score)
                  for p in extract_pareto_plans(result, problem))


def test_same_seed_gives_identical_front():
    assert _front_signature() == _front_signature()


def test_different_seeds_give_different_fronts():
    assert _front_signature(seed=1) != _front_signature(seed=2)


def test_concurrent_runs_match_serial_runs():
    expected = {s: _front_signature(seed=s) for s in (3, 4, 5, 6)}
    results, errors = {}, []

    def worker(seed):
        try:
            results[seed] = _front_signature(seed=seed)
        except Exception as exc:  # pragma: no cover - surfaced via assert below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(s,)) for s in expected for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert results == expected


def test_dashboard_front_cache_returns_equal_independent_results():
    ds.clear_pareto_cache()
    first = client.get("/api/comparison/erode").json()
    second = client.get("/api/comparison/erode").json()
    assert first == second
    info = ds._cached_pareto_front.cache_info()
    assert info.hits >= 1


def test_results_listing_never_exposes_client_ids(monkeypatch):
    summary = {"run_id": "salem_kharif_2023_x", "location": "Salem", "season": "Kharif", "year": 2023,
               "preference": "balanced", "saved_at": None, "n_plans": 1, "client_id": "secret-browser-id"}
    monkeypatch.setattr(results_store, "list_saved_runs", lambda **k: [summary])
    body = client.get("/api/results").json()
    assert body[0]["run_id"] == "salem_kharif_2023_x"
    assert body[0]["client_id"] is None
    assert summary["client_id"] == "secret-browser-id"  # stored record untouched


def test_same_second_saves_get_distinct_run_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(results_store, "make_run_id", lambda *a: "salem_kharif_2023_20260101T000000Z")
    response = {
        "region_profile": {"location": "Salem", "season": "Kharif", "year": 2023},
        "plans": [{"rank": 1}],
    }
    first = results_store.save_run_results(dict(response), [], out_dir=tmp_path)
    second = results_store.save_run_results(dict(response), [], out_dir=tmp_path)
    assert first.run_id == "salem_kharif_2023_20260101T000000Z"
    assert second.run_id == "salem_kharif_2023_20260101T000000Z-2"
    assert results_store.load_run(first.run_id, out_dir=tmp_path)["run_id"] == first.run_id
    assert results_store.load_run(second.run_id, out_dir=tmp_path)["run_id"] == second.run_id
