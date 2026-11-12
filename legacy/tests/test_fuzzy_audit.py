"""
Fuzzy system optimisation: memoised engine, rule-level explanation and audit.

The engine's outputs must not change; explanations must reproduce the
engine exactly; audit figures are checked against analytic values and
independent scikit-fuzzy runs.

Run with:  python3 -m pytest tests/test_fuzzy_audit.py -q
"""

from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest
from fastapi.testclient import TestClient
from skfuzzy import control as ctrl

from app.data import preprocessing as pp
from app.fuzzy import audit
from app.fuzzy import engine as fz
from app.main import app

client = TestClient(app)
RNG = np.random.default_rng(7)
RANDOM_POINTS = [(float(r), float(w), float(s)) for r, w, s in
                 zip(RNG.uniform(-70, 70, 150), RNG.uniform(-10, 110, 150), RNG.uniform(-10, 110, 150))]
SALEM_KHARIF = (-21.1, 62.0, 67.8)


def reference(r, w, s):
    """Uncached scikit-fuzzy run on the compiled rule base (0-1 scale, unrounded)."""
    system, *_ = fz._build_system()
    sim = ctrl.ControlSystemSimulation(system)
    x = fz._clipped_inputs(r, w, s)
    for k, v in x.items():
        sim.input[k] = v
    sim.compute()
    return float(sim.output["yield_conf"]) / 100, float(sim.output["irrigation_risk"]) / 100


@pytest.fixture(scope="module")
def dataset():
    return audit.dataset_points()


@pytest.fixture(scope="module")
def loo():
    return {r["rule"]: r for r in audit.leave_one_out(audit.grid(11))}


# ---------------------------------------------------------------------------
# Engine unchanged and memoised safely
# ---------------------------------------------------------------------------

def test_membership_table_matches_the_published_triangles():
    assert fz.MEMBERSHIP_FUNCTIONS == {
        "rainfall_dev": {"deficit": (-60, -60, -5), "normal": (-15, 0, 15), "surplus": (5, 60, 60)},
        "water_storage": {"low": (0, 0, 35), "medium": (20, 50, 75), "high": (60, 100, 100)},
        "soil_fert": {"poor": (0, 0, 40), "medium": (25, 50, 75), "good": (60, 100, 100)},
        "yield_conf": {"low": (0, 0, 45), "medium": (30, 55, 75), "high": (65, 100, 100)},
        "irrigation_risk": {"low": (0, 0, 35), "medium": (25, 50, 75), "high": (60, 100, 100)},
    }
    system, *_ = fz._build_system()
    assert len(list(system.rules)) == 26 == len(fz.rule_specs())


@pytest.mark.parametrize("point", RANDOM_POINTS[:60] + [SALEM_KHARIF])
def test_memoised_engine_equals_an_uncached_run(point):
    a = fz.evaluate_uncertainty(*point)
    y, i = reference(*point)
    assert a.yield_confidence == round(min(max(y, 0), 1), 3)
    assert a.irrigation_risk == round(min(max(i, 0), 1), 3)


def test_memoised_results_are_independent_objects():
    a = fz.evaluate_uncertainty(*SALEM_KHARIF)
    a.yield_confidence = -1
    assert fz.evaluate_uncertainty(*SALEM_KHARIF).yield_confidence != -1
    m = fz.input_memberships(*SALEM_KHARIF)
    m["rainfall_dev"]["deficit"] = 9
    assert fz.input_memberships(*SALEM_KHARIF)["rainfall_dev"]["deficit"] != 9
    f = fz.fired_rules(*SALEM_KHARIF)
    f[0]["strength"] = 9
    assert fz.fired_rules(*SALEM_KHARIF)[0]["strength"] != 9


def test_fired_rules_follow_the_rounded_memberships():
    m = fz.input_memberships(*SALEM_KHARIF)
    fired = {r["rule"]: r["strength"] for r in fz.fired_rules(*SALEM_KHARIF)}
    for spec in fz.rule_specs():
        strength = min(m[v][t] for v, t in spec.antecedents)
        assert fired.get(spec.number, 0) == (round(strength, 3) if strength > 0 else 0)


def test_rule_specs_read_the_compiled_rules():
    system, *_ = fz._build_system()
    for spec, rule in zip(fz.rule_specs(), system.rules):
        assert {f"{v}[{t}]" for v, t in spec.antecedents} <= set(str(rule.antecedent).replace("(", " ").replace(")", " ").replace("AND", " ").split())
        assert [f"{v}[{t}]" for v, t in spec.consequents] == [str(c.term) for c in rule.consequent]
    assert fz.rule_specs()[14].scenario == "Severe/compound drought stress"
    assert all(s.scenario is None for s in fz.rule_specs()[:14])


# ---------------------------------------------------------------------------
# Rule-level explanation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("point", RANDOM_POINTS[60:110] + [SALEM_KHARIF])
def test_explanation_reproduces_the_engine_exactly(point):
    e = fz.explain_inference(*point)
    y, i = reference(*point)
    assert e["outputs"]["yield_conf"]["matches_engine"] and e["outputs"]["irrigation_risk"]["matches_engine"]
    assert e["outputs"]["yield_conf"]["value"] == round(y, 3)
    assert e["outputs"]["irrigation_risk"]["value"] == round(i, 3)


@pytest.mark.parametrize("point", RANDOM_POINTS[110:150] + [SALEM_KHARIF])
def test_explanation_attribution_is_complete_and_consistent(point):
    e = fz.explain_inference(*point)
    rules = {r["rule"]: r for r in e["rules"]}
    for var in fz.OUTPUT_VARIABLES:
        shares = [r["contribution_pct"].get(var, 0) for r in e["rules"]]
        if not e["outputs"][var]["fallback_used"]:
            assert sum(shares) == pytest.approx(100, abs=0.5)
            assert sum(e["outputs"][var]["term_area_share_pct"].values()) == pytest.approx(100, abs=0.5)
        for term, cut in e["outputs"][var]["term_cuts"].items():
            for n in cut["set_by"]:
                assert rules[n]["strength"] == pytest.approx(cut["cut"], abs=1e-4)
    for r in e["rules"]:
        if r["status"] == "not fired":
            assert r["strength"] == 0 and not r["contribution_pct"] and r["limiting_condition"] is None
        else:
            assert r["limiting_condition"]["membership"] == pytest.approx(r["strength"], abs=1e-4)
        if r["status"] == "masked":
            assert r["masked_by"] and all(rules[m]["strength"] > r["strength"] for m in r["masked_by"])
            assert r["importance"] == 0
    assert e["ranking"] == sorted(e["ranking"], key=lambda n: (-rules[n]["importance"],
                                                               -sum(rules[n]["contribution_pct"].values()),
                                                               -rules[n]["strength"], n))
    assert e["summary"]["fired"] == e["summary"]["decisive"] + e["summary"]["masked"]


def test_leave_one_out_matches_rebuilding_the_system_without_the_rule():
    e = fz.explain_inference(*SALEM_KHARIF)
    system, *_ = fz._build_system()
    for r in e["rules"]:
        if not r["leave_one_out_change"]:
            continue
        reduced = ctrl.ControlSystem([rule for n, rule in enumerate(system.rules, 1) if n != r["rule"]])
        sim = ctrl.ControlSystemSimulation(reduced)
        for k, v in fz._clipped_inputs(*SALEM_KHARIF).items():
            sim.input[k] = v
        sim.compute()
        full = reference(*SALEM_KHARIF)
        for k, var in enumerate(fz.OUTPUT_VARIABLES):
            if var in r["leave_one_out_change"]:
                assert r["leave_one_out_change"][var] == pytest.approx(full[k] - sim.output[var] / 100, abs=1e-4)


def test_salem_kharif_example():
    e = fz.explain_inference(*SALEM_KHARIF)
    status = {r["rule"]: r["status"] for r in e["rules"] if r["status"] != "not fired"}
    assert status == {2: "decisive", 3: "masked", 10: "decisive", 13: "masked", 19: "masked", 24: "decisive"}
    assert e["ranking"][0] == 2


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

def test_dominance_finds_the_inert_rules():
    d = audit.rule_dominance()
    assert [r["rule"] for r in d["inert"]] == [13, 15, 19, 21, 25, 26]
    assert [r["rule"] for r in d["partly_dominated"]] == [14, 20, 22, 24]
    assert d["effective_rules"] == 20


def test_inert_rules_never_change_any_output(loo):
    inert = {r["rule"] for r in audit.rule_dominance()["inert"]}
    for n, row in loo.items():
        if n in inert:
            assert row["max_change_yield_conf"] == 0 and row["max_change_irrigation_risk"] == 0
        else:
            assert row["max_change_yield_conf"] > 0 or row["max_change_irrigation_risk"] > 0


def test_inert_rules_have_zero_importance_everywhere():
    inert = {r["rule"] for r in audit.rule_dominance()["inert"]}
    for point in RANDOM_POINTS[:40]:
        for r in fz.explain_inference(*point)["rules"]:
            if r["rule"] in inert:
                assert r["importance"] == 0


def test_batch_evaluation_equals_the_engine():
    pts = RANDOM_POINTS[:40]
    values = audit.evaluate_grid(pts)
    for (y, i), p in zip(values, pts):
        a = fz.evaluate_uncertainty(*p)
        assert (round(y, 3), round(i, 3)) == (a.yield_confidence, a.irrigation_risk)


def test_coverage_matches_analytic_values():
    c = audit.membership_coverage()
    # deficit/normal cross where (-5-x)/55 = (x+15)/15 -> x = -12.857, membership 1/7
    assert c["rainfall_dev"]["epsilon_completeness"] == pytest.approx(1 / 7, abs=1e-3)
    assert c["rainfall_dev"]["crossings"][0]["at"] == pytest.approx(-12.857, abs=0.01)
    # deficit = 0.5 at -32.5, normal = 0.5 at -7.5
    lo, hi = c["rainfall_dev"]["weak_intervals"][0]
    assert lo == pytest.approx(-32.5, abs=0.02) and hi == pytest.approx(-7.5, abs=0.02)
    # low/medium storage cross where (35-x)/35 = (x-20)/30 -> x = 26.92, membership 3/13
    assert c["water_storage"]["epsilon_completeness"] == pytest.approx(3 / 13, abs=1e-3)
    for var in c.values():
        assert var["uncovered_points"] == 0


def test_output_bounds_are_the_extreme_term_centroids():
    b = audit.output_bounds()
    assert b["yield_conf"]["min"] == pytest.approx(15 / 100, abs=1e-4)            # centroid of (0, 0, 45)
    assert b["yield_conf"]["max"] == pytest.approx((65 + 200) / 3 / 100, abs=1e-4)  # centroid of (65, 100, 100)
    assert b["irrigation_risk"]["min"] == pytest.approx(35 / 3 / 100, abs=1e-4)
    assert b["irrigation_risk"]["max"] == pytest.approx((60 + 200) / 3 / 100, abs=1e-4)


def test_firing_statistics_on_the_dataset(dataset):
    stats = audit.firing_statistics(dataset)
    assert stats["profiles"] == len(dataset) > 0
    storage = [p["inputs"][1] for p in dataset]
    fertility = [p["inputs"][2] for p in dataset]
    assert ("low" in stats["input_sets_never_activated"]["water_storage"]) == (min(storage) >= 35)
    assert ("poor" in stats["input_sets_never_activated"]["soil_fert"]) == (min(fertility) >= 40)
    rows = {r["rule"]: r for r in stats["rules"]}
    for p in dataset[:10]:
        for r in fz.fired_rules(*p["inputs"]):
            assert rows[r["rule"]]["fired"] > 0
    for n in stats["never_fired"]:
        assert rows[n]["fired"] == 0
    inert = {r["rule"] for r in audit.rule_dominance()["inert"]}
    for n in inert:
        assert rows[n]["decisive"] == rows[n]["decisive_only_by_tie"]


def test_monotonicity_report():
    rows = audit.monotonicity(11)
    assert {(r["output"], r["input"]) for r in rows} == {("yield_conf", "soil_fert"), ("yield_conf", "water_storage"),
                                                         ("irrigation_risk", "water_storage")}
    for r in rows:
        assert 0 <= r["violating_steps_pct"] <= 100 and r["largest_violation"] >= 0


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------

def test_explanation_service_includes_rule_attribution():
    from app.schemas import FarmPlanRequest
    from app.services import explanation_service as es
    from app.services import plan_service as ps

    run = ps.run_pipeline(FarmPlanRequest(location="Salem", season="Kharif", total_land_ha=5, save_results=False),
                          track_history=True).response
    e = es.explain(es.context_from_saved_run(run, 1))
    rp = run["region_profile"]
    expected = fz.explain_inference(rp["rainfall"]["avg_deviation_percent"], rp["water"]["avg_storage_percent"],
                                    rp["soil"]["fertility_index"])
    assert e["fuzzy_reasoning"]["inference"] == expected
    assert {r["rule"] for r in e["fuzzy_reasoning"]["fired_rules"]} == {
        r["rule"] for r in expected["rules"] if r["status"] != "not fired" and r["strength"] >= 0.0005}


def test_fuzzy_endpoints():
    r = client.get("/api/fuzzy/explain", params=dict(zip(("rainfall_dev", "water_storage", "soil_fert"), SALEM_KHARIF)))
    assert r.status_code == 200 and r.json()["ranking"][0] == 2
    assert client.get("/api/fuzzy/explain", params={"rainfall_dev": "nan", "water_storage": 1, "soil_fert": 1}).status_code == 422
    assert client.get("/api/fuzzy/explain", params={"rainfall_dev": 1}).status_code == 422
    a = client.get("/api/fuzzy/audit").json()
    assert set(a) == {"model", "dominance", "coverage", "output_bounds", "dataset_firing"}
    assert a["model"] == "original"
    assert not math.isnan(a["coverage"]["soil_fert"]["epsilon_completeness"])


def test_profiles_still_produce_valid_assessments(dataset):
    for p in dataset:
        a = fz.evaluate_uncertainty(*p["inputs"])
        assert 0 <= a.yield_confidence <= 1 and 0 <= a.irrigation_risk <= 1
    assert pp.get_region_season_profile("Salem", "Kharif").soil.fertility_index == pytest.approx(SALEM_KHARIF[2], abs=0.05)
