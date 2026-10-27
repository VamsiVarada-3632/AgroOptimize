"""
Dynamic TOPSIS engine: explanation maths, profile comparison, the
pipeline and the API (app/decision/topsis_explain.py,
app/services/topsis_service.py, plan_service, main).

Regression core: Balanced reproduces the published ranking exactly, and
switching profile changes only the ranking -- never the Pareto front, the
fuzzy assessment or the objectives.
"""
from __future__ import annotations

import copy
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import config
from app.decision import ranking
from app.decision import topsis_explain as tx
from app.decision.criteria import CRITERIA, crop_attributes
from app.decision.profiles import resolve
from app.main import app
from app.schemas import FarmPlanRequest
from app.services import explanation_service as es
from app.services import results_store, topsis_service
from app.services.plan_service import generate_farm_plans, run_pipeline

client = TestClient(app)
FAST = {"pop_size": config.NSGA2_FAST_POP_SIZE, "n_gen": config.NSGA2_FAST_N_GEN}
BASE = {"location": "Salem", "season": "Kharif", "total_land_ha": 5, "budget_rs": 400_000, "save_results": False, **FAST}
PROFILES = ("balanced", "profit", "water", "sustainability", "low_cost")


@pytest.fixture(scope="module")
def runs():
    """One run per profile on the same problem, plus the default request."""
    out = {p: run_pipeline(FarmPlanRequest(**BASE, profile=p)) for p in PROFILES}
    out[None] = run_pipeline(FarmPlanRequest(**BASE))
    return out


@pytest.fixture(scope="module")
def front(runs):
    r = runs[None].response
    plans = topsis_service._as_farm_plans(r["ranked_front"])
    attrs = crop_attributes(r["region_profile"], r["fuzzy_assessment"])
    return plans, attrs


@pytest.fixture(scope="module")
def saved(tmp_path_factory):
    out = tmp_path_factory.mktemp("results")
    resp = generate_farm_plans(FarmPlanRequest(**{**BASE, "save_results": True}, profile="water"), results_dir=out)
    return results_store.load_run(resp["run_id"], out_dir=out)


def _strip(response):
    r = copy.deepcopy(response)
    r["meta"].pop("optimize_seconds")
    r["meta"]["quality_metrics"].pop("runtime_seconds")
    r["meta"]["optimizer"].pop("profile")          # wall-clock timings
    return r


class TestBalancedIsUnchanged:

    def test_profile_balanced_equals_default_request(self, runs):
        a, b = _strip(runs[None].response), _strip(runs["balanced"].response)
        assert a == b

    def test_default_meta_reports_balanced(self, runs):
        t = runs[None].response["meta"]["topsis"]
        assert t["profile"] == "balanced" and t["preference"] == "balanced"
        assert [t["weights"][k] for k in ranking.OBJECTIVES] == ranking.preference_weights("balanced").tolist()

    def test_rank_front_balanced_is_the_legacy_path(self, front):
        plans, attrs = front
        conf = dict(zip(attrs.names, attrs.confidence.tolist()))
        legacy = ranking.to_dict_list(ranking.rank_plans(plans, conf, preference="balanced"))
        assert ranking.to_dict_list(topsis_service.rank_front(plans, conf, resolve("balanced"), attrs, None)) == legacy

    @pytest.mark.parametrize("pref", ["max_yield", "min_cost", "min_water", "min_env_impact"])
    def test_preferences_still_work(self, pref):
        r = run_pipeline(FarmPlanRequest(**{**BASE, "preference": pref})).response
        assert r["meta"]["preference"] == pref and r["meta"]["topsis"]["profile"] is None
        assert r["meta"]["topsis"]["label"] == f"Preference '{pref}'"


class TestOnlyRankingChanges:

    @pytest.mark.parametrize("profile", PROFILES[1:])
    def test_front_fuzzy_and_objectives_identical(self, runs, profile):
        a, b = runs[None].response, runs[profile].response
        assert a["ranked_front"] == b["ranked_front"]
        assert a["fuzzy_assessment"] == b["fuzzy_assessment"]
        assert a["region_profile"] == b["region_profile"]
        assert a["meta"]["quality_metrics"]["hypervolume"] == b["meta"]["quality_metrics"]["hypervolume"]
        assert a["meta"]["n_pareto_solutions_found"] == b["meta"]["n_pareto_solutions_found"]

    @pytest.mark.parametrize("profile", PROFILES[1:])
    def test_ranked_plans_come_from_the_same_front(self, runs, profile):
        front = {(p["yield_tonnes"], p["cost_rs"], p["water_liters"], p["env_impact_score"])
                 for p in runs[None].response["ranked_front"]}
        for p in runs[profile].response["plans"]:
            assert (p["yield_tonnes"], p["cost_rs"], p["water_liters"], p["env_impact_score"]) in front

    def test_profiles_change_the_ranking(self, runs):
        tops = {p: tuple(runs[p].response["plans"][0]["area_ha"]) for p in PROFILES}
        assert len(set(tops.values())) >= 2

    def test_profile_meta(self, runs):
        t = runs["profit"].response["meta"]["topsis"]
        assert t["profile"] == "profit" and t["label"] == "Profit priority"
        assert sum(t["weights"].values()) == pytest.approx(1.0)

    def test_normalized_scores_stay_the_four_objectives(self, runs):
        assert set(runs["profit"].response["plans"][0]["normalized_scores"]) == set(ranking.OBJECTIVES)

    def test_scores_sorted(self, runs):
        for p in PROFILES:
            scores = [x["composite_score"] for x in runs[p].response["plans"]]
            assert scores == sorted(scores, reverse=True)
            assert [x["rank"] for x in runs[p].response["plans"]] == list(range(1, len(scores) + 1))


class TestExplainMaths:

    @pytest.mark.parametrize("profile", PROFILES)
    def test_breakdown_reproduces_rank_plans(self, front, profile):
        plans, attrs = front
        spec = resolve(profile)
        bd = tx.breakdown(topsis_service.criteria_for(plans, attrs, BASE["budget_rs"], spec.active), spec)
        conf = dict(zip(attrs.names, attrs.confidence.tolist()))
        ranked = topsis_service.rank_front(plans, conf, spec, attrs, BASE["budget_rs"])
        order = sorted(range(len(plans)), key=lambda i: bd["ranks"][i])
        for rp, i in zip(ranked, order):
            assert rp.composite_score == round(float(bd["closeness"][i]), 4)
            assert rp.yield_tonnes == plans[i].yield_tonnes and rp.cost_rs == plans[i].cost_rs

    def test_terms_rebuild_the_score(self, front):
        plans, attrs = front
        spec = resolve("sustainability")
        bd = tx.breakdown(topsis_service.criteria_for(plans, attrs, None, spec.active), spec)
        for i in range(len(plans)):
            t = tx.plan_terms(bd, i)
            d_best = math.sqrt(sum(r["gap_to_ideal"] ** 2 for r in t["criteria"]))
            d_worst = math.sqrt(sum(r["gap_to_anti_ideal"] ** 2 for r in t["criteria"]))
            assert d_best == pytest.approx(t["distance_to_ideal"], abs=1e-3)
            assert d_worst == pytest.approx(t["distance_to_anti_ideal"], abs=1e-3)
            assert t["closeness"] == pytest.approx(t["distance_to_anti_ideal"] / (t["distance_to_ideal"] + t["distance_to_anti_ideal"]), abs=1e-5)
            assert sum(r["share_of_distance_to_ideal_pct"] for r in t["criteria"]) == pytest.approx(100, abs=0.5)
            for r in t["criteria"]:
                assert r["weighted"] == pytest.approx(r["weight"] * r["goodness"], abs=1e-3)

    def test_pair_explains_adjacent_plans(self, front):
        plans, attrs = front
        spec = resolve("profit")
        bd = tx.breakdown(topsis_service.criteria_for(plans, attrs, None, spec.active), spec)
        order = sorted(range(len(plans)), key=lambda i: bd["ranks"][i])
        pair = tx.explain_pair(bd, order[0], order[1])
        assert pair["rank_a"] == 1 and pair["rank_b"] == 2 and "ranks above" in pair["summary"]
        assert pair["closeness_a"] >= pair["closeness_b"]
        advantages = [abs(r["weighted_advantage"]) for r in pair["criteria"]]
        assert advantages == sorted(advantages, reverse=True)
        assert tx.explain_pair(bd, order[1], order[0])["summary"].startswith("Plan #2 ranks below plan #1")

    def test_ranks_break_ties_in_input_order(self):
        assert tx.ranks_from_closeness([0.5, 0.7, 0.5, 0.70001]) == [3, 1, 4, 2]

    def test_comparison(self, front):
        plans, attrs = front
        cmp = topsis_service.profile_comparison(plans, attrs, BASE["budget_rs"], resolve("water"))
        names = [p["profile"] for p in cmp["profiles"]]
        assert names == list(PROFILES) and cmp["reference"] == "water"
        by = {p["profile"]: p for p in cmp["profiles"]}
        assert by["water"]["kendall_tau_vs_reference"] == 1.0 and by["water"]["top_n_overlap"] == cmp["top_n"]
        assert by["water"]["best_plan"]["rank_under_reference"] == 1
        assert all(v == 0 for v in by["water"]["weight_differences"].values())
        for p in cmp["profiles"]:
            assert p["top_plans"][0]["rank"] == 1 and -1 <= (p["kendall_tau_vs_reference"] or 0) <= 1
        for row in cmp["rank_changes"]:
            assert row["ranks"]["water"] == row["reference_rank"]
        assert 1 <= cmp["distinct_best_plans"] <= len(PROFILES)

    def test_custom_reference_is_added(self, front):
        plans, attrs = front
        cmp = topsis_service.profile_comparison(plans, attrs, None, resolve("custom", {"yield": 0.5, "soil": 0.5}))
        assert [p["profile"] for p in cmp["profiles"]][-1] == "custom"

    def test_pipeline_comparison(self):
        r = run_pipeline(FarmPlanRequest(**BASE, profile="low_cost", compare_profiles=True)).response
        cmp = r["meta"]["profile_comparison"]
        assert cmp["reference"] == "low_cost" and cmp["plans_compared"] == len(r["ranked_front"])
        best = next(p for p in cmp["profiles"] if p["profile"] == "low_cost")["best_plan"]
        assert best["yield_tonnes"] == r["plans"][0]["yield_tonnes"] and best["cost_rs"] == r["plans"][0]["cost_rs"]


class TestSavedRuns:

    def test_front_is_stored(self, saved):
        assert len(saved["ranked_front"]) == saved["meta"]["n_pareto_solutions_found"]

    def test_rerank_with_own_profile_reproduces_the_run(self, saved):
        out = topsis_service.rerank_saved_run(saved, "water", compare=False)
        assert out["ranked_over"] == "ranked_front" and out["plans"] == saved["plans"]

    def test_rerank_balanced_matches_a_balanced_run(self, saved):
        out = topsis_service.rerank_saved_run(saved, "balanced", compare=False)
        direct = run_pipeline(FarmPlanRequest(**BASE)).response
        assert out["plans"] == direct["plans"]

    def test_older_run_without_front(self, saved):
        old = {k: v for k, v in saved.items() if k != "ranked_front"}
        out = topsis_service.rerank_saved_run(old, "profit")
        assert out["ranked_over"] == "returned_plans" and out["plans_ranked"] == len(saved["plans"])

    def test_explanation_section(self, saved):
        exp = es.explain_saved_run(saved, rank=2)
        t = exp["topsis"]
        assert t["available"] and t["profile"] == "water" and t["ranked_over"] == "ranked_front"
        assert t["plan"]["rank"] == 2 and round(t["plan"]["closeness"], 4) == saved["plans"][1]["composite_score"]
        assert t["versus_previous"]["rank_b"] == 1 and t["versus_next"]["rank_b"] == 3
        assert t["rank_by_profile"]["water"] == 2
        assert "'Water saving' ranking profile" in exp["reasons"][0]["detail"]

    def test_explanation_weights_for_profile(self, saved):
        ctx = es.context_from_saved_run(saved, 1)
        assert ctx.topsis_weights().tolist() == [saved["meta"]["topsis"]["weights"][k] for k in ranking.OBJECTIVES]


class TestRequestValidation:

    @pytest.mark.parametrize("extra", [
        {"profile": "custom"},
        {"custom_weights": {"yield": 1.0}},
        {"profile": "profit", "custom_weights": {"yield": 1.0}},
        {"profile": "custom", "custom_weights": {"yield": 0.5}},
        {"profile": "custom", "custom_weights": {"yield": 0.5, "mood": 0.5}},
        {"profile": "custom", "custom_weights": {"yield": 1.5, "cost": -0.5}},
        {"profile": "water", "preference": "max_yield"},
        {"profile": "speed"},
    ])
    def test_rejected(self, extra):
        with pytest.raises(ValidationError):
            FarmPlanRequest(**BASE, **extra)

    def test_custom_accepted(self):
        r = FarmPlanRequest(**BASE, profile="custom", custom_weights={"yield": 0.3, "income": 0.3, "rainfall": 0.4})
        assert r.custom_weights.as_dict() == {"yield": 0.3, "income": 0.3, "rainfall": 0.4}


class TestApi:

    def test_profiles_endpoint(self):
        r = client.get("/api/topsis/profiles")
        assert r.status_code == 200
        body = r.json()
        assert [p["profile"] for p in body["profiles"]] == list(PROFILES)
        assert [c["key"] for c in body["criteria"]] == list(CRITERIA)

    def test_farm_plans_custom(self):
        weights = {"yield": 0.25, "income": 0.25, "water": 0.25, "soil": 0.25}
        r = client.post("/api/farm-plans", json={**BASE, "profile": "custom", "custom_weights": weights, "compare_profiles": True})
        assert r.status_code == 200
        meta = r.json()["meta"]
        assert meta["topsis"]["profile"] == "custom" and meta["topsis"]["weights"]["soil"] == 0.25
        assert meta["profile_comparison"]["reference"] == "custom"
        assert "ranked_front" not in r.json()

    def test_farm_plans_rejects_bad_weights(self):
        r = client.post("/api/farm-plans", json={**BASE, "profile": "custom", "custom_weights": {"yield": 0.2}})
        assert r.status_code == 422 and "sum to 1" in r.text

    def test_default_request_is_backward_compatible(self):
        r = client.post("/api/farm-plans", json={k: v for k, v in BASE.items()})
        assert r.status_code == 200
        body = r.json()
        assert body["meta"]["topsis"]["profile"] == "balanced" and body["meta"]["profile_comparison"] is None

    def test_rerank_endpoints(self, saved, monkeypatch):
        monkeypatch.setattr(results_store, "load_run", lambda run_id, **k: saved)
        g = client.get("/api/results/x/topsis", params={"profile": "profit"})
        assert g.status_code == 200 and g.json()["topsis"]["profile"] == "profit" and g.json()["comparison"]
        assert client.get("/api/results/x/topsis", params={"profile": "water", "compare": False}).json()["plans"] == saved["plans"]
        p = client.post("/api/results/x/topsis", json={"profile": "custom", "custom_weights": {"land": 0.5, "rainfall": 0.5}})
        assert p.status_code == 200 and p.json()["topsis"]["label"] == "Custom"
        assert client.post("/api/results/x/topsis", json={"profile": "custom", "custom_weights": {"land": 0.5}}).status_code == 422
        assert client.get("/api/results/x/topsis", params={"profile": "custom"}).status_code == 422

    def test_rerank_missing_run(self, monkeypatch):
        monkeypatch.setattr(results_store, "load_run", lambda run_id, **k: None)
        assert client.get("/api/results/nope/topsis").status_code == 404

    def test_explanation_endpoint_has_topsis(self, saved, monkeypatch):
        monkeypatch.setattr(results_store, "load_run", lambda run_id, **k: saved)
        body = client.get("/api/results/x/explanation", params={"rank": 1}).json()
        assert body["topsis"]["plan"]["rank"] == 1


def test_no_infeasible_plans_ranked(runs):
    for p in PROFILES:
        assert all(x["feasible"] for x in runs[p].response["plans"])


def test_profile_ranking_is_fast(front):
    import time
    plans, attrs = front
    t0 = time.perf_counter()
    for _ in range(20):
        topsis_service.profile_comparison(plans, attrs, None, resolve("profit"))
    assert (time.perf_counter() - t0) / 20 < 0.25
    assert np.isfinite([p.yield_tonnes for p in plans]).all()
