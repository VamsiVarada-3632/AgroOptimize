"""
TOPSIS over any set of criteria (app/decision/ranking.py criteria_closeness).

The four optimiser objectives with the balanced weights must give exactly
the published ranking: criteria_closeness is the generalisation the
ranking profiles use, so any difference here would change Balanced.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest

from app.data import preprocessing as pp
from app.decision import ranking
from app.fuzzy import engine as fz
from app.optimization.nsga2_runner import extract_pareto_plans, run_nsga2
from app.optimization.problem import FarmPlanProblem

DIRECTIONS = {"yield": "benefit", "cost": "cost", "water": "cost", "env": "cost"}


@pytest.fixture(scope="module")
def front():
    prof = pp.get_region_season_profile("Salem", "Kharif")
    a = fz.evaluate_uncertainty(prof.rainfall.avg_deviation_percent, prof.water.avg_storage_percent, prof.soil.fertility_index)
    problem = FarmPlanProblem(prof, a, 5.0)
    plans = [p for p in extract_pareto_plans(run_nsga2(problem, pop_size=60, n_gen=40), problem) if p.feasible]
    conf = dict(zip(problem.crop_vec.names, problem.crop_vec.crop_yield_confidence.tolist()))
    return plans, conf


def _columns(plans):
    return {"yield": [p.yield_tonnes for p in plans], "cost": [p.cost_rs for p in plans],
            "water": [p.water_liters for p in plans], "env": [p.env_impact_score for p in plans]}


def _weights(pref):
    return dict(zip(ranking.OBJECTIVES, ranking.preference_weights(pref)))


class TestEquivalence:

    @pytest.mark.parametrize("pref", ["balanced", "max_yield", "min_cost", "min_water", "min_env_impact"])
    def test_four_objectives_reproduce_topsis_scores_exactly(self, front, pref):
        plans, _ = front
        cols = _columns(plans)
        legacy, _ = ranking.topsis_scores(*cols.values(), ranking.preference_weights(pref))
        general, _ = ranking.criteria_closeness(cols, DIRECTIONS, _weights(pref))
        assert np.array_equal(legacy, general)        # bit for bit

    def test_random_sets_reproduce_topsis_scores_exactly(self):
        rng = np.random.default_rng(7)
        for _ in range(50):
            n = int(rng.integers(2, 120))
            cols = {k: rng.uniform(0, 1e6, n).round(2).tolist() for k in ranking.OBJECTIVES}
            w = rng.dirichlet(np.ones(4))
            legacy, _ = ranking.topsis_scores(*cols.values(), w)
            general, _ = ranking.criteria_closeness(cols, DIRECTIONS, dict(zip(ranking.OBJECTIVES, w)))
            assert np.array_equal(legacy, general)

    def test_rank_plans_with_balanced_criteria_weights_is_identical(self, front):
        plans, conf = front
        legacy = ranking.to_dict_list(ranking.rank_plans(plans, conf, preference="balanced"))
        general = ranking.to_dict_list(ranking.rank_plans(plans, conf, criteria_values=_columns(plans),
                                                          criteria_weights=_weights("balanced"), criteria_directions=DIRECTIONS))
        assert legacy == general


class TestMaths:

    def test_hand_computed_example(self):
        # goodness a = [0, .5, 1], b = [1, .5, 0]; w = [.75, .25]
        # weighted rows (0, .25), (.375, .125), (.75, 0); ideal (.75, .25), anti-ideal (0, 0)
        c, _ = ranking.criteria_closeness({"a": [1, 2, 3], "b": [3, 2, 1]}, {"a": "benefit", "b": "benefit"},
                                          {"a": 0.75, "b": 0.25})
        assert c == pytest.approx([0.25, 0.5, 0.75])

    def test_cost_criterion_is_flipped(self):
        c, g = ranking.criteria_closeness({"x": [10, 20, 30]}, {"x": "cost"}, {"x": 1.0})
        assert g["x"] == pytest.approx([1.0, 0.5, 0.0])
        assert c.argmax() == 0

    def test_zero_weight_criteria_do_not_enter(self):
        cols = {"a": [1, 2, 3], "b": [3, 1, 2]}
        dirs = {"a": "benefit", "b": "benefit"}
        alone, _ = ranking.criteria_closeness({"a": cols["a"]}, dirs, {"a": 1.0})
        both, g = ranking.criteria_closeness(cols, dirs, {"a": 1.0, "b": 0.0})
        assert np.array_equal(alone, both) and "b" not in g

    def test_constant_criterion_is_neutral(self):
        dirs = {"a": "benefit", "b": "cost", "k": "benefit"}
        base, _ = ranking.criteria_closeness({"a": [1, 5, 3], "b": [2, 9, 4]}, dirs, {"a": 0.6, "b": 0.4})
        with_k, _ = ranking.criteria_closeness({"a": [1, 5, 3], "b": [2, 9, 4], "k": [7, 7, 7]}, dirs,
                                               {"a": 0.3, "b": 0.2, "k": 0.5})
        assert with_k == pytest.approx(base, abs=1e-12)

    def test_scaling_all_weights_leaves_closeness_unchanged(self):
        cols = {"a": [1, 5, 3, 2], "b": [2, 9, 4, 1]}
        dirs = {"a": "benefit", "b": "cost"}
        c1, _ = ranking.criteria_closeness(cols, dirs, {"a": 0.6, "b": 0.4})
        c2, _ = ranking.criteria_closeness(cols, dirs, {"a": 6.0, "b": 4.0})
        assert c1 == pytest.approx(c2, abs=1e-12)

    def test_closeness_is_between_zero_and_one(self):
        rng = np.random.default_rng(3)
        cols = {f"c{i}": rng.normal(size=40).tolist() for i in range(6)}
        dirs = {k: ("benefit" if i % 2 else "cost") for i, k in enumerate(cols)}
        c, _ = ranking.criteria_closeness(cols, dirs, dict(zip(cols, rng.dirichlet(np.ones(6)))))
        assert ((c >= 0) & (c <= 1)).all()

    def test_identical_plans_score_one_half(self):
        c, _ = ranking.criteria_closeness({"a": [2, 2], "b": [5, 5]}, {"a": "benefit", "b": "cost"}, {"a": 0.5, "b": 0.5})
        assert c.tolist() == [0.5, 0.5]

    def test_all_zero_weights_rejected(self):
        with pytest.raises(ValueError):
            ranking.criteria_closeness({"a": [1, 2]}, {"a": "benefit"}, {"a": 0.0})

    def test_criteria_weights_need_values(self, front):
        plans, conf = front
        with pytest.raises(ValueError):
            ranking.rank_plans(plans, conf, criteria_weights=_weights("balanced"))
