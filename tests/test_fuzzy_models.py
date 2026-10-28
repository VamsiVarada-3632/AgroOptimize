"""
Fuzzy model variants (docs/handbook/FUZZY_MODEL_IMPROVEMENTS.md).

The original model must stay the default and unchanged; every improvement
is a separate switch whose stated property is checked here.

Run with:  python3 -m pytest tests/test_fuzzy_models.py -q
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest
from skfuzzy import control as ctrl

from app import config
from app.fuzzy import audit
from app.fuzzy import engine as fz

RNG = np.random.default_rng(11)
POINTS = [(float(r), float(w), float(s)) for r, w, s in
          zip(RNG.uniform(-70, 70, 120), RNG.uniform(-10, 110, 120), RNG.uniform(-10, 110, 120))]
SALEM_KHARIF = (-21.1, 62.0, 67.8)


def reference(model, r, w, s):
    """Uncached scikit-fuzzy run on `model`'s compiled rule base (0-1, unrounded)."""
    system, *_ = fz.build_system(model)
    sim = ctrl.ControlSystemSimulation(system)
    x = fz._clipped_inputs(r, w, s)
    for k, v in x.items():
        sim.input[k] = v
    sim.compute()
    return sim.output["yield_conf"] / 100, sim.output["irrigation_risk"] / 100


# ---------------------------------------------------------------------------
# Model selection
# ---------------------------------------------------------------------------

def test_default_model_is_the_published_one():
    assert config.FUZZY_MODEL == "original"
    assert fz.resolve_model() is fz.ORIGINAL
    assert fz.resolve_model("original") is fz.ORIGINAL
    assert fz.membership_functions() == fz.MEMBERSHIP_FUNCTIONS
    assert fz.rule_numbers() == tuple(range(1, 27))


def test_unknown_model_is_rejected():
    with pytest.raises(ValueError, match="Unknown fuzzy model"):
        fz.resolve_model("nonsense")


def test_using_model_overrides_the_default_and_restores_it():
    with fz.using_model("strong_partition") as m:
        assert m is fz.STRONG_PARTITION
        assert fz.resolve_model() is fz.STRONG_PARTITION
        inside = fz.evaluate_uncertainty(*SALEM_KHARIF)
    assert fz.resolve_model() is fz.ORIGINAL
    assert inside == fz.evaluate_uncertainty(*SALEM_KHARIF, model="strong_partition")


def test_models_are_cached_separately():
    a = fz.evaluate_uncertainty(*SALEM_KHARIF)
    b = fz.evaluate_uncertainty(*SALEM_KHARIF, model="strong_partition")
    assert a != b
    assert fz.evaluate_uncertainty(*SALEM_KHARIF) == a


@pytest.mark.parametrize("name", sorted(fz.MODELS))
def test_every_model_matches_scikit_fuzzy_and_its_explanation(name):
    for p in POINTS[:40]:
        got = fz.evaluate_uncertainty(*p, model=name)
        y, r = reference(name, *p)
        assert got.yield_confidence == round(y, 3) and got.irrigation_risk == round(r, 3)
        e = fz.explain_inference(*p, model=name)
        assert e["model"] == name
        assert all(o["matches_engine"] for o in e["outputs"].values())


@pytest.mark.parametrize("name", sorted(fz.MODELS))
def test_every_model_stays_in_range_and_never_raises(name):
    for p in POINTS + [(-1000, -1000, 1000), (1000, 1000, -1000)]:
        a = fz.evaluate_uncertainty(*p, model=name)
        assert 0 <= a.yield_confidence <= 1 and 0 <= a.irrigation_risk <= 1


# ---------------------------------------------------------------------------
# Improvement 1: strong partition for storage and fertility
# ---------------------------------------------------------------------------

def test_strong_partition_keeps_the_modal_values():
    sets = fz.membership_functions("strong_partition")
    for var in ("water_storage", "soil_fert"):
        peaks = [p[1] for p in fz.MEMBERSHIP_FUNCTIONS[var].values()]
        assert [p[1] for p in sets[var].values()] == peaks == [0, 50, 100]
    assert sets["rainfall_dev"] == fz.MEMBERSHIP_FUNCTIONS["rainfall_dev"]


def test_strong_partition_is_epsilon_complete_and_sums_to_one():
    cov = audit.membership_coverage(model="strong_partition")
    for var in ("water_storage", "soil_fert"):
        assert cov[var]["epsilon_completeness"] == 0.5
        assert cov[var]["membership_sum_range"] == [1.0, 1.0]
        assert all(c["membership"] == 0.5 for c in cov[var]["crossings"])
    assert cov["rainfall_dev"] == audit.membership_coverage()["rainfall_dev"]


def test_strong_partition_reduces_monotonicity_violations():
    before = {(r["output"], r["input"]): r for r in audit.monotonicity(11)}
    after = {(r["output"], r["input"]): r for r in audit.monotonicity(11, model="strong_partition")}
    for key in before:
        assert after[key]["largest_violation"] <= before[key]["largest_violation"]
        assert after[key]["violating_steps_pct"] <= before[key]["violating_steps_pct"]
    assert after[("yield_conf", "soil_fert")]["violating_steps_pct"] == 0


# ---------------------------------------------------------------------------
# Improvement 2: rainfall sets aligned to the IMD categories
# ---------------------------------------------------------------------------

def test_imd_rainfall_sets_cross_at_the_imd_boundary():
    cov = audit.membership_coverage(model="imd_rainfall")["rainfall_dev"]
    assert cov["epsilon_completeness"] == 0.5
    assert cov["membership_sum_range"] == [1.0, 1.0]
    assert [c["at"] for c in cov["crossings"]] == [-19.75, 19.75]
    assert all(c["membership"] == 0.5 for c in cov["crossings"])
    sets = fz.membership_functions("imd_rainfall")
    assert sets["water_storage"] == fz.MEMBERSHIP_FUNCTIONS["water_storage"]
    assert sets["soil_fert"] == fz.MEMBERSHIP_FUNCTIONS["soil_fert"]


@pytest.mark.parametrize("dev,category", [(-60, "deficit"), (-39.5, "deficit"), (-20, "deficit"), (-19, "normal"),
                                          (0, "normal"), (19, "normal"), (20, "surplus"), (121.1, "surplus")])
def test_imd_rainfall_labels_follow_the_imd_category(dev, category):
    assert fz.imd_category(dev) == category
    assert fz.evaluate_uncertainty(dev, 60, 70, model="imd_rainfall").rainfall_label == category


def test_imd_rainfall_labels_every_dataset_profile_like_imd():
    profiles = audit.dataset_points()
    agree = {m: sum(fz.evaluate_uncertainty(*p["inputs"], model=m).rainfall_label == fz.imd_category(p["inputs"][0])
                    for p in profiles) for m in ("original", "imd_rainfall")}
    assert agree == {"original": 51, "imd_rainfall": len(profiles)}


# ---------------------------------------------------------------------------
# Improvement 3: provably inert rules left out
# ---------------------------------------------------------------------------

def test_subsumed_rules_are_the_audited_inert_rules():
    assert fz.subsumed_rules() == (13, 15, 19, 21, 25, 26)
    assert [r["rule"] for r in audit.rule_dominance()["inert"]] == list(fz.subsumed_rules())


def test_pruned_model_keeps_the_original_numbering():
    numbers = fz.rule_numbers("pruned_rules")
    assert len(numbers) == 20 and not set(numbers) & set(fz.subsumed_rules())
    assert [s.number for s in fz.rule_specs("pruned_rules")] == list(numbers)
    original = {s.number: s for s in fz.rule_specs()}
    assert all(original[s.number] == s for s in fz.rule_specs("pruned_rules"))
    dominance = audit.rule_dominance("pruned_rules")
    assert dominance["inert"] == [] and dominance["effective_rules"] == 20


def test_pruned_model_outputs_are_identical_to_the_original():
    points = POINTS + [tuple(p) for p in audit.grid(7)] + [p["inputs"] for p in audit.dataset_points()]
    for p in points:
        assert fz.evaluate_uncertainty(*p, model="pruned_rules") == fz.evaluate_uncertainty(*p)


def test_pruned_model_reports_fewer_fired_rules_and_unmasks_their_twins():
    """A subsumed rule tied with its general rule hides the general rule's
    leave-one-out importance (removing either leaves the other setting the
    cut). Without the subsumed rules that importance shows: on the data it
    rises in 29 of 60 profiles, from 0 in 18 rule readings, and never falls."""
    raised = from_zero = 0
    for p in [p["inputs"] for p in audit.dataset_points()]:
        full = fz.explain_inference(*p)
        pruned = fz.explain_inference(*p, model="pruned_rules")
        assert all(pruned["outputs"][v]["value"] == full["outputs"][v]["value"] for v in fz.OUTPUT_VARIABLES)
        assert pruned["summary"]["fired"] == full["summary"]["fired"] - sum(
            r["status"] != "not fired" for r in full["rules"] if r["rule"] in fz.subsumed_rules())
        assert all(r["importance"] == 0 for r in full["rules"] if r["rule"] in fz.subsumed_rules())
        before = {r["rule"]: r["importance"] for r in full["rules"]}
        changed = [(before[r["rule"]], r["importance"]) for r in pruned["rules"] if r["importance"] != before[r["rule"]]]
        assert all(new > old for old, new in changed)
        raised += bool(changed)
        from_zero += sum(old == 0 for old, _ in changed)
    assert (raised, from_zero) == (29, 18)


# ---------------------------------------------------------------------------
# API: model catalogue, model parameters, per-request model
# ---------------------------------------------------------------------------

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)
FAST = {"pop_size": config.NSGA2_FAST_POP_SIZE, "n_gen": config.NSGA2_FAST_N_GEN}


def salem_kharif_inputs():
    """Fuzzy inputs of the default-year Salem Kharif profile the API uses."""
    from app.data import preprocessing as pp
    p = pp.get_region_season_profile("Salem", "Kharif")
    return p.rainfall.avg_deviation_percent, p.water.avg_storage_percent, p.soil.fertility_index


def test_models_endpoint_lists_every_model_and_the_default():
    body = client.get("/api/fuzzy/models").json()
    assert body["default"] == "original"
    by_name = {m["name"]: m for m in body["models"]}
    assert set(by_name) == set(fz.MODELS)
    assert by_name["original"]["rules"] == list(range(1, 27))
    assert by_name["pruned_rules"]["rules"] == list(fz.rule_numbers("pruned_rules"))
    assert by_name["imd_rainfall"]["switches"] == {"strong_partition": False, "imd_rainfall": True, "prune_inert": False}
    assert by_name["imd_rainfall"]["membership_functions"]["rainfall_dev"]["normal"] == [-39.5, 0, 39.5]


def test_explain_and_audit_take_a_model():
    params = dict(zip(("rainfall_dev", "water_storage", "soil_fert"), SALEM_KHARIF))
    assert client.get("/api/fuzzy/explain", params=params).json()["model"] == "original"
    e = client.get("/api/fuzzy/explain", params={**params, "model": "strong_partition"}).json()
    assert e["model"] == "strong_partition"
    assert e["outputs"]["yield_conf"]["value"] == fz.evaluate_uncertainty(*SALEM_KHARIF, model="strong_partition").yield_confidence
    a = client.get("/api/fuzzy/audit", params={"model": "pruned_rules"}).json()
    assert a["model"] == "pruned_rules" and a["dominance"]["inert"] == []
    assert client.get("/api/fuzzy/explain", params={**params, "model": "nope"}).status_code == 400
    assert client.get("/api/fuzzy/audit", params={"model": "nope"}).status_code == 400


def test_farm_plan_runs_with_the_requested_model_and_records_it():
    base = {"location": "Salem", "season": "Kharif", "total_land_ha": 5, "save_results": False, **FAST}
    default = client.post("/api/farm-plans", json=base).json()
    chosen = client.post("/api/farm-plans", json={**base, "fuzzy_model": "imd_rainfall"}).json()
    assert default["meta"]["fuzzy_model"] == "original"
    assert chosen["meta"]["fuzzy_model"] == "imd_rainfall"
    assert chosen["fuzzy_assessment"] == vars(fz.evaluate_uncertainty(*salem_kharif_inputs(), model="imd_rainfall"))
    assert client.post("/api/farm-plans", json={**base, "fuzzy_model": "nope"}).status_code == 422


def test_saved_run_is_explained_with_its_own_model():
    from app.services import explanation_service as es
    from app.services import plan_service as ps
    from app.schemas import FarmPlanRequest

    run = ps.run_pipeline(FarmPlanRequest(location="Salem", season="Kharif", total_land_ha=5, save_results=False,
                                          fuzzy_model="strong_partition", **FAST)).response
    inference = es.explain(es.context_from_saved_run(run, 1))["fuzzy_reasoning"]["inference"]
    assert inference["model"] == "strong_partition"
    assert inference["outputs"]["yield_conf"]["value"] == run["fuzzy_assessment"]["yield_confidence"]
    # A run saved before models existed has no meta.fuzzy_model: explained with the original model,
    # whatever the server default is.
    old = {**run, "meta": {k: v for k, v in run["meta"].items() if k != "fuzzy_model"}}
    with fz.using_model("imd_rainfall"):
        assert es.explain(es.context_from_saved_run(old, 1))["fuzzy_reasoning"]["inference"]["model"] == "original"


def test_simulation_runs_both_sides_with_the_requested_model():
    from app.services import simulation_service as sim

    out = sim.simulate({"base": {"location": "Salem", "season": "Kharif", "total_land_ha": 5,
                                 "fuzzy_model": "imd_rainfall"},
                        "scenario": {"rainfall_change_pct": -20}})
    assert out["meta"]["fuzzy_model"] == "imd_rainfall"
    assert out["baseline"]["fuzzy_assessment"] == vars(fz.evaluate_uncertainty(*salem_kharif_inputs(), model="imd_rainfall"))
