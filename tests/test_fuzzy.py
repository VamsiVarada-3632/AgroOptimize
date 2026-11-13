"""
Test suite for the Mamdani fuzzy inference engine (app/fuzzy/engine.py).

Validates output ranges, rule-base directional behaviour, the per-crop
rainfall-dependency adjustment, and integration with real region profiles.

Every assertion in this file was checked against the actual engine output
before being committed (see docs/fuzzy_rules.md for the full rule base and
membership-function reference this file is testing against).

Author: Vennela Harshini (CB.SC.U4CSE23455)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app import config

from app.data import preprocessing as pp
from app.fuzzy import engine as fz
from app.fuzzy.engine import UncertaintyAssessment


# ---------------------------------------------------------------------------
# Output range / shape
# ---------------------------------------------------------------------------

class TestFuzzyOutputRanges:
    """evaluate_uncertainty() must always return values inside [0, 1], even
    at or beyond the membership functions' universe boundaries (rainfall_dev
    is defined over [-60, 60], water_storage/soil_fert over [0, 100])."""

    @pytest.mark.parametrize(
        "rainfall_dev,water_storage,soil_fert",
        [
            (-60, 0, 0),        # worst corner of every universe
            (60, 100, 100),     # best corner of every universe
            (0, 50, 50),        # dead centre
            (-15, 20, 25),      # sits on a boundary between adjacent sets
            (-120, -20, 150),   # out-of-range inputs -- must clip, not raise
        ],
    )
    def test_outputs_always_in_unit_range(self, rainfall_dev, water_storage, soil_fert):
        result = fz.evaluate_uncertainty(rainfall_dev, water_storage, soil_fert)
        assert isinstance(result, UncertaintyAssessment)
        assert 0.0 <= result.yield_confidence <= 1.0
        assert 0.0 <= result.irrigation_risk <= 1.0

    def test_extreme_out_of_range_inputs_are_clipped_not_rejected(self):
        """Readings far outside any sensible physical range shouldn't raise
        -- evaluate_uncertainty clips to [-60,60]/[0,100]/[0,100] first."""
        result = fz.evaluate_uncertainty(-1000, -1000, 1000)
        assert 0.0 <= result.yield_confidence <= 1.0
        assert 0.0 <= result.irrigation_risk <= 1.0

    def test_dominant_labels_are_valid_categories(self):
        result = fz.evaluate_uncertainty(-55, 5, 20)
        assert result.rainfall_label in {"deficit", "normal", "surplus"}
        assert result.water_label in {"low", "medium", "high"}
        assert result.soil_label in {"poor", "medium", "good"}


# ---------------------------------------------------------------------------
# Rule-base behaviour (directional sanity checks against the 14 Mamdani rules)
# ---------------------------------------------------------------------------

class TestFuzzyRuleBaseBehaviour:

    def test_drought_and_low_storage_gives_high_risk_low_confidence(self):
        # rainfall_dev="deficit", water_storage="low" -> rule 1:
        # [irrigation_risk-high, yield_conf-low]
        result = fz.evaluate_uncertainty(
            rainfall_deviation_percent=-55,
            water_storage_percent=5,
            soil_fertility_index=15,
        )
        assert result.irrigation_risk > 0.5
        assert result.yield_confidence < 0.5

    def test_normal_rainfall_with_medium_storage_gives_high_confidence_low_risk(self):
        # rainfall_dev="normal", water_storage="medium" -> rule 5:
        # [irrigation_risk-low, yield_conf-high]
        result = fz.evaluate_uncertainty(
            rainfall_deviation_percent=0,
            water_storage_percent=55,
            soil_fertility_index=70,
        )
        assert result.yield_confidence > 0.5
        assert result.irrigation_risk < 0.5

    def test_drought_scores_worse_than_favourable_conditions(self):
        drought = fz.evaluate_uncertainty(-55, 5, 20)
        favourable = fz.evaluate_uncertainty(10, 80, 80)
        assert drought.yield_confidence < favourable.yield_confidence
        assert drought.irrigation_risk > favourable.irrigation_risk

    def test_good_soil_alone_lifts_yield_confidence(self):
        # rules: soil_fert-good -> yield_conf-high / soil_fert-poor -> yield_conf-low,
        # holding rainfall/water fixed at their "normal"/"medium" anchor points.
        poor_soil = fz.evaluate_uncertainty(0, 50, 10)
        good_soil = fz.evaluate_uncertainty(0, 50, 95)
        assert good_soil.yield_confidence > poor_soil.yield_confidence

    def test_high_water_storage_and_good_soil_gives_high_confidence(self):
        # rule: water_storage-high & soil_fert-good -> yield_conf-high
        result = fz.evaluate_uncertainty(
            rainfall_deviation_percent=0,
            water_storage_percent=95,
            soil_fertility_index=95,
        )
        assert result.yield_confidence > 0.6


# ---------------------------------------------------------------------------
# Per-crop confidence adjustment (crop_yield_confidence)
# ---------------------------------------------------------------------------

class TestPerCropConfidenceAdjustment:
    """The argument is the crop's official rainfed (unirrigated) area share, 0-1 - no hand-picked label factors."""

    def test_higher_rainfed_share_is_penalised_more(self):
        base_conf, irr_risk = 0.8, 0.8
        vals = [fz.crop_yield_confidence(base_conf, irr_risk, share) for share in (0.0, 0.25, 0.5, 0.75, 1.0)]
        assert vals == sorted(vals, reverse=True) and vals[0] > vals[-1]

    def test_zero_irrigation_risk_means_no_penalty(self):
        assert fz.crop_yield_confidence(0.8, 0.0, 1.0) == pytest.approx(0.8, abs=1e-9)

    def test_fully_irrigated_crop_is_not_penalised(self):
        assert fz.crop_yield_confidence(0.8, 1.0, 0.0) == pytest.approx(0.8, abs=1e-9)

    def test_penalty_capped_at_forty_percent_of_base(self):
        # penalty = irrigation_risk * rainfed_share * 0.4; worst case (1.0, 1.0) caps it at 0.4
        assert fz.crop_yield_confidence(1.0, 1.0, 1.0) == pytest.approx(0.6, abs=1e-6)

    def test_share_is_clipped_to_the_unit_interval(self):
        # source-reported irrigated percentages can exceed 100 (validation_report.json); shares are clamped
        assert fz.crop_yield_confidence(0.8, 0.5, 1.7) == fz.crop_yield_confidence(0.8, 0.5, 1.0)
        assert fz.crop_yield_confidence(0.8, 0.5, -0.2) == fz.crop_yield_confidence(0.8, 0.5, 0.0)

    def test_output_stays_in_unit_range_at_worst_case_inputs(self):
        for share in (0.0, 0.3, 1.0):
            assert 0.0 <= fz.crop_yield_confidence(1.0, 1.0, share) <= 1.0


# ---------------------------------------------------------------------------
# Integration: real region profiles -> real fuzzy assessments
# ---------------------------------------------------------------------------

class TestFuzzyAgainstRealRegionProfiles:
    """Runs the actual official data -> fuzzy pipeline the way app/services/plan_service.py does."""

    @pytest.fixture(scope="class")
    def available(self):
        out = []
        for loc in config.LOCATIONS:
            for season in config.AG_SEASONS:
                try:
                    p = pp.get_region_season_profile(loc, season)
                except ValueError:
                    continue
                out.append(p)
        return out

    def test_every_profile_with_all_inputs_has_a_valid_assessment(self, available):
        done = 0
        for p in available:
            result = fz.assess_profile(p)
            if not p.fuzzy_available:
                assert result is None and p.fuzzy_unavailable_reason
                continue
            assert 0.0 <= result.yield_confidence <= 1.0 and 0.0 <= result.irrigation_risk <= 1.0
            done += 1
        assert done >= 9          # the nine districts with a mapped reservoir in the Rabi window

    def test_unavailable_input_is_reported_never_estimated(self):
        p = pp.get_region_season_profile("Salem", "Kharif")
        assert p.fuzzy_available is False and "reservoir" in p.fuzzy_unavailable_reason.lower()
        assert fz.assess_profile(p) is None
        block = fz.assessment_payload(None, p)
        assert block["applied"] is False and block["yield_confidence"] == 1.0 and block["irrigation_risk"] == 0.0

    def test_assessment_is_deterministic_for_the_same_inputs(self):
        profile = pp.get_region_season_profile("Coimbatore", "Rabi")
        args = (profile.rainfall.avg_deviation_percent, profile.water.avg_storage_percent, profile.soil.fertility_index)
        assert fz.evaluate_uncertainty(*args) == fz.evaluate_uncertainty(*args)

    def test_pollachi_is_a_taluk_not_a_district(self):
        with pytest.raises(ValueError, match="taluk"):
            pp.get_region_season_profile("Pollachi", "Rabi")
