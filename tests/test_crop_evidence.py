"""Per-crop source-cited recommendation evidence (app/services/crop_evidence.py)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app import config
from app.schemas import FarmPlanRequest
from app.services import crop_evidence as ce
from app.services import explanation_service as es
from app.services import results_store
from app.services.plan_service import generate_farm_plans

FAST = {"pop_size": config.NSGA2_FAST_POP_SIZE, "n_gen": config.NSGA2_FAST_N_GEN}
IDS = ["rainfall", "soil", "water", "budget", "fertiliser", "market_price", "msp", "duration", "yield", "risks"]


@pytest.fixture(scope="module", params=[("Erode", "Rabi", 3_000_000), ("Coimbatore", "Kharif", None)])
def explanation(request, tmp_path_factory):
    loc, season, budget = request.param
    out = tmp_path_factory.mktemp("res")
    r = generate_farm_plans(FarmPlanRequest(location=loc, season=season, total_land_ha=3, budget_rs=budget, save_results=True, **FAST),
                            results_dir=out)
    return es.explain_saved_run(results_store.load_run(r["run_id"], out_dir=out), rank=1)


def test_every_shown_crop_has_all_ten_criteria(explanation):
    shown = {c["crop"] for c in explanation["summary"]["crop_mix"]}
    assert {e["crop"] for e in explanation["crop_evidence"]} == shown
    for e in explanation["crop_evidence"]:
        assert [c["id"] for c in e["criteria"]] == IDS


def test_every_statement_cites_an_official_dataset(explanation):
    for e in explanation["crop_evidence"]:
        for c in e["criteria"]:
            assert c["statement"].strip()
            assert c["sources"], (e["crop"], c["id"])
            assert all(s.get("dataset") for s in c["sources"])


def test_unavailable_criteria_say_so_and_carry_no_number(explanation):
    for e in explanation["crop_evidence"]:
        for c in e["criteria"]:
            if c["status"] == "unavailable":
                assert c["statement"].startswith(ce.UNAVAILABLE)


def test_market_price_never_stated_without_an_official_dataset(explanation):
    for e in explanation["crop_evidence"]:
        mp = next(c for c in e["criteria"] if c["id"] == "market_price")
        assert mp["status"] == "unavailable" and "Rs" not in mp["statement"].split(":", 1)[1].split("MSP")[0]


def test_msp_and_fertiliser_numbers_match_the_candidate_data(explanation):
    cands = {c["crop"]: c for c in explanation["crop_breakdown"]}
    for e in explanation["crop_evidence"]:
        d = cands[e["crop"]]
        msp = next(c for c in e["criteria"] if c["id"] == "msp")
        assert msp["evidence"]["msp_rs_qtl"] == d["msp_rs_qtl"]
        fert = next(c for c in e["criteria"] if c["id"] == "fertiliser")
        assert fert["evidence"]["recommended_npk_kg_ha"] == d["npk_kg_ha"]


def test_no_nan_or_none_text(explanation):
    for e in explanation["crop_evidence"]:
        for c in e["criteria"]:
            assert "nan" not in c["statement"].lower().split() and "None" not in c["statement"]


def test_missing_master_row_is_unavailable_not_invented():
    assert ce._duration(None)["status"] == "unavailable"
    assert ce._rainfall({"season": "Kharif", "location": "X", "rainfall": {}}, None)["status"] == "unavailable"


def test_yield_cut_flagged_as_caution():
    rp = {"location": "X"}
    d = {"book_yield_t_ha": 6.0, "expected_yield_t_ha": 3.0, "crop_confidence": 0.5}
    assert ce._yield(rp, {}, d, None, {"applied": True})["status"] == "caution"
    assert ce._yield(rp, {}, {**d, "expected_yield_t_ha": 5.9}, None, {"applied": True})["status"] == "supported"


def test_explanation_endpoint_returns_crop_evidence():
    """The API response model must keep crop_evidence, not only the service."""
    from fastapi.testclient import TestClient

    from app.main import app

    r = TestClient(app).get("/api/comparison/Salem/explanation", params={"plan": "A"})
    assert r.status_code == 200
    body = r.json()
    shown = {c["crop"] for c in body["summary"]["crop_mix"]}
    assert {e["crop"] for e in body["crop_evidence"]} == shown
    assert all([c["id"] for c in e["criteria"]] == IDS for e in body["crop_evidence"])
