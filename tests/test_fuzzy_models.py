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
