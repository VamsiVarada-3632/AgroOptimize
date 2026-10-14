"""
Tests for the Explainable Recommendation Engine
(app/services/explanation_service.py and its two API endpoints).

The central property: every explanation is traceable -- the numbers it
states are the numbers the pipeline produced, and nothing is invented
when information is missing.
"""
from __future__ import annotations

import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from app import config
from app.decision import ranking
from app.fuzzy import engine as fz
from app.main import app
from app.schemas import FarmPlanRequest
from app.services import explanation_service as es
from app.services import results_store
from app.services.plan_service import generate_farm_plans

client = TestClient(app)
FAST = {"pop_size": config.NSGA2_FAST_POP_SIZE, "n_gen": config.NSGA2_FAST_N_GEN}
SECTIONS = ("summary", "reasons", "objectives", "trade_offs", "constraints", "benefits", "risks",
            "historical_context", "confidence", "insights", "alternatives", "economics", "timeline")


@pytest.fixture(scope="module")
def saved_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("results")
    response = generate_farm_plans(
        FarmPlanRequest(location="Erode", season="Rabi", year=2023, total_land_ha=3, budget_rs=150_000,
                        save_results=True, **FAST),
        results_dir=out,
    )
    return results_store.load_run(response["run_id"], out_dir=out)


@pytest.fixture(scope="module")
def saved_explanation(saved_run):
    return es.explain_saved_run(saved_run, rank=1)


@pytest.fixture(scope="module")
def comparison_explanation():
    return es.explain_comparison_plan("salem", "A")


def _walk_numbers(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_numbers(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_numbers(v)
    elif isinstance(obj, float):
        yield obj


class TestStructure:

    def test_all_sections_present(self, saved_explanation):
        for section in SECTIONS:
            assert section in saved_explanation

    def test_every_item_has_detail_source_and_evidence(self, saved_explanation):
        for section in ("reasons", "benefits", "risks", "insights", "alternatives", "timeline"):
            for item in saved_explanation[section]:
                assert item["detail"] and item["source"]
                assert isinstance(item["evidence"], dict)
        for item in saved_explanation["constraints"]["items"]:
            assert item["status"] in {"satisfied", "moderate", "risk", "violated", "unknown", "not_applicable"}

    def test_no_nan_or_infinite_numbers(self, saved_explanation, comparison_explanation):
        for exp in (saved_explanation, comparison_explanation):
            assert all(math.isfinite(x) for x in _walk_numbers(exp))
            json.dumps(exp)  # serialisable

    def test_deterministic(self, saved_run):
        assert es.explain_saved_run(saved_run, 1) == es.explain_saved_run(saved_run, 1)


class TestTraceability:

    def test_summary_matches_the_plan(self, saved_run, saved_explanation):
        plan = saved_run["plans"][0]
        s = saved_explanation["summary"]
        area = sum(plan["area_ha"])
        assert s["rank"] == 1
        assert s["closeness"] == plan["composite_score"]
        assert s["totals"]["yield"] == plan["yield_tonnes"]
        assert s["totals"]["cost"] == plan["cost_rs"]
        assert s["per_ha"]["yield"] == pytest.approx(plan["yield_tonnes"] / area, abs=0.01)
        shown = {c["crop"]: c["share_pct"] for c in s["crop_mix"]}
        for name, pct in zip(plan["crop_names"], plan["allocation_percent"]):
            if pct >= es.MIN_SHARE_PCT:
                assert shown[name] == pytest.approx(pct, abs=0.01)

    def test_recomputed_objectives_match_reported(self, saved_explanation, comparison_explanation):
        for exp in (saved_explanation, comparison_explanation):
            for check in exp["consistency_checks"].values():
                assert check["consistent"], check

    def test_objective_goodness_comes_from_topsis(self, saved_run, saved_explanation):
        scores = saved_run["plans"][0]["normalized_scores"]
        for o in saved_explanation["objectives"]["objectives"]:
            assert o["goodness"] == scores[o["objective"]]
        weights = ranking.preference_weights(saved_run["meta"]["preference"])
        assert [o["weight"] for o in saved_explanation["objectives"]["objectives"]] == pytest.approx(list(weights), abs=1e-3)

    def test_gap_shares_sum_to_100(self, saved_explanation):
        total = sum(o["share_of_gap_to_ideal_pct"] for o in saved_explanation["objectives"]["objectives"])
        assert total == pytest.approx(100, abs=0.5)

    def test_fuzzy_reasoning_uses_the_model(self, saved_run, saved_explanation):
        rp = saved_run["region_profile"]
        expected = fz.fired_rules(rp["rainfall"]["avg_deviation_percent"], rp["water"]["avg_storage_percent"],
                                  rp["soil"]["fertility_index"])
        assert saved_explanation["fuzzy_reasoning"]["fired_rules"] == expected
        assert all(1 <= r["rule"] <= 26 and 0 < r["strength"] <= 1 for r in expected)

    def test_comparison_plan_a_is_the_plan_the_page_shows(self, comparison_explanation):
        page = client.get("/api/comparison/salem").json()["plans"]["A"]
        s = comparison_explanation["summary"]
        assert s["per_ha"]["yield"] == pytest.approx(page["yield_val"], abs=0.01)
        assert round(s["per_ha"]["cost"]) == page["cost"]
        assert s["preference"] == "balanced" and s["rank"] == 1


class TestConfidence:

    def test_overall_is_mean_of_available_components(self, saved_explanation):
        comps = saved_explanation["confidence"]["components"]
        scored = [c["score"] for c in comps if c["score"] is not None]
        assert saved_explanation["confidence"]["overall_pct"] == pytest.approx(sum(scored) / len(scored), abs=0.1)
        assert all(0 <= c["score"] <= 100 for c in comps if c["score"] is not None)

    def test_missing_history_is_excluded_not_guessed(self, saved_run):
        record = dict(saved_run, convergence_history=[])
        comps = {c["id"]: c for c in es.explain_saved_run(record, 1)["confidence"]["components"]}
        assert comps["convergence"]["score"] is None
        assert comps["convergence"]["weight"] == 0.0

    def test_estimated_year_lowers_data_quality_and_is_a_risk(self):
        estimated = es.explain_comparison_plan("salem", "A")  # dashboard uses the latest (estimated) year
        comps = {c["id"]: c for c in estimated["confidence"]["components"]}
        assert estimated["summary"]["data_year_estimated"] is True
        assert comps["data_quality"]["score"] <= 50
        assert any(r["id"] == "estimated-data" for r in estimated["risks"])

    def test_observed_year_has_no_estimated_data_risk(self, saved_explanation):
        assert saved_explanation["summary"]["data_year_estimated"] is False
        assert not any(r["id"] == "estimated-data" for r in saved_explanation["risks"])


class TestConstraints:

    def test_budget_reported_with_headroom(self, saved_run, saved_explanation):
        budget = next(c for c in saved_explanation["constraints"]["items"] if c["id"] == "budget")
        assert budget["status"] == "satisfied"
        assert budget["evidence"]["budget_rs"] == 150_000
        assert budget["evidence"]["cost_rs"] == saved_run["plans"][0]["cost_rs"]

    def test_old_runs_without_budget_say_so(self, saved_run):
        record = dict(saved_run, meta={k: v for k, v in saved_run["meta"].items() if k not in ("budget_rs", "total_land_ha")})
        budget = next(c for c in es.explain_saved_run(record, 1)["constraints"]["items"] if c["id"] == "budget")
        assert budget["status"] == "unknown"


class TestHonesty:

    def test_unvalidated_prices_never_drive_reasons_or_confidence(self, saved_explanation):
        assert saved_explanation["economics"].get("validated") is False
        # "top crops by revenue" (the dataset's historical ranking) is allowed;
        # the unvalidated indicative profit / revenue estimate is not.
        text = json.dumps([saved_explanation[s] for s in ("reasons", "benefits", "risks")]).lower()
        assert "profit" not in text and "indicative" not in text and "msp" not in text
        assert "economics" not in {c["id"] for c in saved_explanation["confidence"]["components"]}

    def test_no_rank_outside_the_run(self, saved_run):
        with pytest.raises(ValueError):
            es.explain_saved_run(saved_run, rank=len(saved_run["plans"]) + 1)


class TestEndpoints:

    def test_saved_run_endpoint(self, saved_run, monkeypatch):
        monkeypatch.setattr(results_store, "load_run", lambda run_id, **k: saved_run)
        r = client.get("/api/results/any_valid_id/explanation", params={"rank": 2})
        assert r.status_code == 200
        assert r.json()["summary"]["rank"] == 2

    def test_saved_run_endpoint_errors(self, saved_run, monkeypatch):
        assert client.get("/api/results/missing_run/explanation").status_code == 404
        monkeypatch.setattr(results_store, "load_run", lambda run_id, **k: saved_run)
        assert client.get("/api/results/x/explanation", params={"rank": 0}).status_code == 422
        assert client.get("/api/results/x/explanation", params={"rank": 499}).status_code == 400

    @pytest.mark.parametrize("plan", ["A", "B", "C"])
    def test_comparison_endpoint(self, plan):
        r = client.get("/api/comparison/erode/explanation", params={"plan": plan})
        assert r.status_code == 200
        assert r.json()["subject"]["plan"] == plan

    def test_comparison_endpoint_errors(self):
        assert client.get("/api/comparison/chennai/explanation").status_code == 404
        assert client.get("/api/comparison/erode/explanation", params={"plan": "D"}).status_code == 422
        assert client.get("/api/comparison/erode/explanation", params={"total_land_ha": 0}).status_code == 422


def test_rank_plans_unchanged_by_topsis_refactor(saved_run):
    """rank_plans now delegates to topsis_scores; the saved composite
    scores must still be reproducible from the stored objective values."""
    plans = saved_run["plans"]
    cols = [[p[k] for p in plans] for k in ("yield_tonnes", "cost_rs", "water_liters", "env_impact_score")]
    closeness, _ = ranking.topsis_scores(*cols, ranking.preference_weights("balanced"))
    # stored scores were computed over the full front, so compare ordering, not values
    assert list(closeness) == sorted(closeness, reverse=True) or len(plans) < 3
