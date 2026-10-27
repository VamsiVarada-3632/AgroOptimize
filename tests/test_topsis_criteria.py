"""
Decision criteria of the ranking stage (app/decision/criteria.py).

Each criterion is checked against its definition on hand-built plans, and
against the pipeline's own numbers on a real run (expected tonnes add up
to the plan's yield; revenue matches the explanation service).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest

from app import config
from app.decision import criteria as cr
from app.schemas import FarmPlanRequest
from app.services import explanation_service as es
from app.services.plan_service import run_pipeline

FAST = {"pop_size": config.NSGA2_FAST_POP_SIZE, "n_gen": config.NSGA2_FAST_N_GEN}


@pytest.fixture(scope="module")
def run():
    return run_pipeline(FarmPlanRequest(location="Erode", season="Rabi", total_land_ha=4, save_results=False, **FAST))


@pytest.fixture(scope="module")
def attrs(run):
    return cr.crop_attributes(run.response["region_profile"], run.response["fuzzy_assessment"])


def _plan(attrs, shares, land=4.0, cost=100_000.0):
    area = [s * land for s in shares]
    tonnes = sum(a * y * c for a, y, c in zip(area, attrs.yield_t_ha, attrs.confidence))
    return {"crop_names": attrs.names, "area_ha": area, "yield_tonnes": tonnes, "cost_rs": cost,
            "water_liters": 1.0, "env_impact_score": 1.0}


def _single(attrs, i, **kw):
    shares = [0.0] * len(attrs.names)
    shares[i] = 1.0
    return _plan(attrs, shares, **kw)


class TestAttributes:

    def test_confidence_matches_the_optimiser(self, run, attrs):
        assert attrs.names == run.problem.crop_vec.names
        assert np.array_equal(attrs.confidence, run.problem.crop_vec.crop_yield_confidence)

    def test_expected_tonnes_add_up_to_plan_yield(self, run, attrs):
        for p in run.feasible_plans[:20]:
            tonnes = float((np.array(p.area_ha) * attrs.yield_t_ha * attrs.confidence).sum())
            assert tonnes == pytest.approx(p.yield_tonnes, abs=1e-3)

    def test_unknown_crop_rejected(self, run):
        rp = dict(run.response["region_profile"])
        rp["candidate_crops"] = rp["candidate_crops"] + [{**rp["candidate_crops"][0], "name": "Saffron"}]
        with pytest.raises(ValueError, match="Saffron"):
            cr.crop_attributes(rp, run.response["fuzzy_assessment"])


class TestDefinitions:

    def test_optimiser_criteria_are_the_plan_objectives(self, run, attrs):
        plans = run.feasible_plans
        v = cr.plan_criteria(plans, attrs)
        assert v["yield"] == [p.yield_tonnes for p in plans]
        assert v["cost"] == [p.cost_rs for p in plans]
        assert v["water"] == [p.water_liters for p in plans]
        assert v["env"] == [p.env_impact_score for p in plans]

    def test_order_follows_criteria(self, run, attrs):
        assert list(cr.plan_criteria(run.feasible_plans, attrs)) == list(cr.CRITERIA)

    def test_single_crop_market_price_is_its_price(self, attrs):
        for i in range(len(attrs.names)):
            v = cr.plan_criteria([_single(attrs, i)], attrs, keys=["market_price"])
            assert v["market_price"][0] == pytest.approx(attrs.price_rs_qtl[i])

    def test_income_is_revenue_minus_cost(self, attrs):
        p = _plan(attrs, np.full(len(attrs.names), 1 / len(attrs.names)), cost=50_000)
        revenue = sum(a * y * c * 10 * pr for a, y, c, pr in
                      zip(p["area_ha"], attrs.yield_t_ha, attrs.confidence, attrs.price_rs_qtl))
        assert cr.plan_criteria([p], attrs, keys=["income"])["income"][0] == pytest.approx(revenue - 50_000)

    def test_income_matches_the_explanation_economics(self, run, attrs):
        plan = run.response["plans"][0]
        ctx = es.context_from_saved_run(run.response, 1)
        econ = es.indicative_economics(ctx, plan)
        income = cr.plan_criteria([plan], attrs, keys=["income"])["income"][0]
        assert income == pytest.approx(econ["indicative_profit_rs"], abs=1.0)    # economics rounds to rupees

    def test_budget_is_headroom_and_neutral_without_budget(self, attrs):
        plans = [_single(attrs, 0, cost=c) for c in (90_000, 120_000, 100_000)]
        assert cr.plan_criteria(plans, attrs, budget_rs=150_000, keys=["budget"])["budget"] == [60_000, 30_000, 50_000]
        assert cr.plan_criteria(plans, attrs, budget_rs=None, keys=["budget"])["budget"] == [0, 0, 0]

    def test_land_diversification(self, attrs):
        n = len(attrs.names)
        v = cr.plan_criteria([_single(attrs, 0), _plan(attrs, [1 / n] * n)], attrs, keys=["land"])["land"]
        assert v[0] == pytest.approx(0.0) and v[1] == pytest.approx(1.0)

    def test_rainfall_exposure(self, attrs):
        for i in range(len(attrs.names)):
            v = cr.plan_criteria([_single(attrs, i)], attrs, keys=["rainfall"])["rainfall"][0]
            assert v == pytest.approx(attrs.rainfall_factor[i])
        assert set(attrs.rainfall_factor) <= set(config.RAINFALL_DEPENDENCY_FACTOR.values())

    def test_soil_is_area_weighted_fit(self, attrs):
        shares = np.linspace(1, 2, len(attrs.names))
        shares /= shares.sum()
        v = cr.plan_criteria([_plan(attrs, shares)], attrs, keys=["soil"])["soil"][0]
        assert v == pytest.approx(float((shares * attrs.soil_fit).sum()))

    def test_criteria_beyond_objectives_need_attributes(self, run):
        with pytest.raises(ValueError):
            cr.plan_criteria(run.feasible_plans, None, keys=["income"])
        assert list(cr.plan_criteria(run.feasible_plans, None, keys=cr.OPTIMISER_CRITERIA)) == list(cr.OPTIMISER_CRITERIA)

    def test_crop_mismatch_rejected(self, attrs):
        p = _single(attrs, 0)
        p["crop_names"] = list(reversed(p["crop_names"]))
        with pytest.raises(ValueError):
            cr.plan_criteria([p], attrs, keys=["soil"])


class TestSoilFit:

    def test_rich_soil_suits_every_crop(self):
        assert cr.soil_fit(np.array([[120, 60, 40], [20, 10, 5]]), ["High", "High", "High"]).tolist() == [1.0, 1.0]

    def test_hand_computed(self):
        # demand relative to the largest dose: crop 0 (1, 1, 1), crop 1 (.5, 0, .25)
        # deficits Low 1, Medium .5, High 0 -> crop 0: 1 - (1 + .5 + 0)/3, crop 1: 1 - (.5 + 0 + 0)/3
        fit = cr.soil_fit(np.array([[100, 40, 80], [50, 0, 20]]), ["Low", "Medium", "High"])
        assert fit == pytest.approx([0.5, 1 - 0.5 / 3])

    def test_unknown_status_counts_as_medium(self):
        assert cr.soil_fit(np.array([[10, 0, 0]]), ["?", "Low", "Low"])[0] == pytest.approx(1 - 0.5 / 3)

    def test_in_unit_range(self, attrs):
        assert ((attrs.soil_fit >= 0) & (attrs.soil_fit <= 1)).all()


def test_metadata_covers_every_criterion():
    assert set(cr.CRITERIA_META) == set(cr.CRITERIA)
    assert all(m["direction"] in ("benefit", "cost") for m in cr.CRITERIA_META.values())
