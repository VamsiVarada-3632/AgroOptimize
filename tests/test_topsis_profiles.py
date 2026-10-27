"""
Ranking profiles and custom weights (app/decision/profiles.py).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app.decision import profiles as pf
from app.decision import ranking
from app.decision.criteria import CRITERIA

STANDARD = ("balanced", "profit", "water", "sustainability", "low_cost")


class TestDefinitions:

    def test_standard_profiles(self):
        assert tuple(pf.PROFILES) == STANDARD
        assert pf.PROFILE_NAMES == STANDARD + ("custom",)

    @pytest.mark.parametrize("name", STANDARD)
    def test_weights_cover_every_criterion_and_sum_to_one(self, name):
        w = pf.profile_weights(name)
        assert list(w) == list(CRITERIA)
        assert sum(w.values()) == pytest.approx(1.0)
        assert all(0 <= v <= 1 for v in w.values())

    def test_balanced_is_the_published_preference(self):
        w = pf.profile_weights("balanced")
        assert [w[k] for k in ranking.OBJECTIVES] == ranking.preference_weights("balanced").tolist()
        assert all(w[k] == 0 for k in CRITERIA if k not in ranking.OBJECTIVES)

    def test_rank_sum_tiers(self):
        w = pf.rank_sum_weights({"high": ("yield",), "medium": ("cost", "water"), "low": ("env",)})
        assert w["yield"] == pytest.approx(3 / 8) and w["cost"] == pytest.approx(2 / 8) and w["env"] == pytest.approx(1 / 8)
        assert w["income"] == 0

    @pytest.mark.parametrize("name", STANDARD[1:])
    def test_tiers_are_ordered(self, name):
        w, tiers = pf.profile_weights(name), pf.PROFILES[name]["tiers"]
        high = min(w[c] for c in tiers["high"])
        low = max(w[c] for c in tiers["low"])
        assert high > low
        if "medium" in tiers:
            assert high > max(w[c] for c in tiers["medium"]) and min(w[c] for c in tiers["medium"]) > low

    def test_profiles_follow_the_brief(self):
        p = pf.profile_weights
        assert min(p("profit")[c] for c in ("income", "market_price", "yield")) > max(p("profit")[c] for c in ("water", "env"))
        assert min(p("water")[c] for c in ("water", "env")) > max(p("water")[c] for c in ("yield", "income"))
        assert min(p("sustainability")[c] for c in ("env", "water", "soil")) > p("sustainability")["income"]
        assert min(p("low_cost")[c] for c in ("cost", "budget")) > p("low_cost")["yield"]

    def test_every_tier_criterion_is_known(self):
        for p in pf.PROFILES.values():
            for crits in p.get("tiers", {}).values():
                assert set(crits) <= set(CRITERIA)

    def test_unknown_profile(self):
        with pytest.raises(ValueError):
            pf.profile_weights("maximum_everything")


class TestCustomWeights:

    def test_valid(self):
        w = pf.validate_custom_weights({"yield": 0.4, "water": 0.35, "soil": 0.25})
        assert w["yield"] == 0.4 and w["income"] == 0.0 and list(w) == list(CRITERIA)

    def test_float_tolerance(self):
        pf.validate_custom_weights({"yield": 0.1, "cost": 0.2, "water": 0.7000000001})

    @pytest.mark.parametrize("weights", [
        {"yield": 0.5, "water": 0.4},                       # sums to 0.9
        {"yield": 0.6, "water": 0.6},                       # sums to 1.2
        {"yield": 1.2, "water": -0.2},                      # out of range
        {"yield": 0.5, "happiness": 0.5},                   # unknown criterion
        {"yield": 0.0},                                     # sums to 0
        {},
        None,
    ])
    def test_invalid(self, weights):
        with pytest.raises(ValueError):
            pf.validate_custom_weights(weights)

    def test_single_criterion(self):
        assert pf.validate_custom_weights({"rainfall": 1.0})["rainfall"] == 1.0


class TestResolve:

    def test_custom(self):
        spec = pf.resolve("custom", {"yield": 0.5, "income": 0.5})
        assert spec.profile == "custom" and spec.active == ("yield", "income") and spec.needs_crop_attributes

    def test_balanced_needs_no_crop_data(self):
        spec = pf.resolve("balanced")
        assert spec.active == ranking.OBJECTIVES and not spec.needs_crop_attributes

    def test_custom_weights_only_with_custom(self):
        with pytest.raises(ValueError):
            pf.resolve("profit", {"yield": 1.0})

    def test_as_dict(self):
        d = pf.resolve("water").as_dict()
        assert d["profile"] == "water" and d["label"] == "Water saving"
        assert [c["key"] for c in d["criteria"]] == [c for c in CRITERIA if d["weights"][c] > 0]
        assert {c["direction"] for c in d["criteria"]} <= {"benefit", "cost"}


def test_catalogue():
    cat = pf.catalogue()
    assert cat["default_profile"] == "balanced"
    assert [p["profile"] for p in cat["profiles"]] == list(STANDARD)
    assert [c["key"] for c in cat["criteria"]] == list(CRITERIA)
    assert cat["custom"]["default_weights"] == pf.balanced_weights()
    assert all("tiers" in p for p in cat["profiles"][1:])
