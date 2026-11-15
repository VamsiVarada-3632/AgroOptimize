"""The four NSGA-II objectives, checked against the formulas in the documentation.

For land shares a_i (normalised to the farm area A), irrigation multipliers m_i and
fertiliser multipliers r_i:

    f1 = -sum a_i * Y_i * kappa_i           expected yield (t), maximised (stored negated)
    f2 =  sum a_i * Y_i(q/ha) * CACP_i      cultivation cost (Rs)
    f3 =  sum a_i * m_i * sigma_i           irrigated hectare-equivalents
    f4 =  sum a_i * r_i * (N + P2O5 + K2O)_i  nutrient load (kg)

Each value is recomputed here by hand from the official crop records of one district.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.data import preprocessing as pp
from app.fuzzy import engine as fz
from app.optimization.problem import FarmPlanProblem

LAND_HA = 5.0


@pytest.fixture(scope="module")
def salem_rabi():
    profile = pp.get_region_season_profile("Salem", "Rabi", year=2024)
    assessment = fz.assess_profile(profile)
    return profile, assessment


def _problem(salem_rabi, budget=None):
    profile, assessment = salem_rabi
    return FarmPlanProblem(profile, assessment, total_land_ha=LAND_HA, budget_rs=budget)


def _chromosome(n, shares, irr, fert):
    return np.concatenate([np.asarray(shares, float), np.full(n, irr), np.full(n, fert)])


def test_objectives_match_the_documented_formulas(salem_rabi):
    problem = _problem(salem_rabi)
    profile, assessment = salem_rabi
    n = problem.n_crops
    raw = np.linspace(1.0, 2.0, n)                     # unequal, unnormalised shares
    x = _chromosome(n, raw, irr=1.2, fert=0.8)
    F = problem.evaluate(x[None, :], return_as_dictionary=True)["F"][0]

    area = raw / raw.sum() * LAND_HA
    crops = profile.candidate_crops
    kappa = np.array([fz.crop_yield_confidence(assessment.yield_confidence, assessment.irrigation_risk, c.rainfed_share)
                      for c in crops])
    yield_t = sum(a * c.yield_kg_ha / 1000.0 * k for a, c, k in zip(area, crops, kappa))
    cost = sum(a * c.cost_rs_ha for a, c in zip(area, crops))
    irrigated = sum(a * 1.2 * c.irrigated_share for a, c in zip(area, crops))
    npk = sum(a * 0.8 * (c.fert_n_kg_ha + c.fert_p_kg_ha + c.fert_k_kg_ha) for a, c in zip(area, crops))

    assert F[0] == pytest.approx(-yield_t, rel=1e-9)
    assert F[1] == pytest.approx(cost, rel=1e-9)
    assert F[2] == pytest.approx(irrigated, rel=1e-9)
    assert F[3] == pytest.approx(npk, rel=1e-9)


def test_cost_is_official_yield_in_quintals_times_cacp_cost(salem_rabi):
    profile, _ = salem_rabi
    for c in profile.candidate_crops:
        # 1 quintal = 100 kg; CACP cost of production is per quintal
        assert c.cost_rs_ha == pytest.approx(c.yield_kg_ha / 100.0 * c.cost_rs_qtl, rel=1e-6)


def test_shares_are_normalised_to_the_farm_area(salem_rabi):
    problem = _problem(salem_rabi)
    n = problem.n_crops
    a = _chromosome(n, np.ones(n), irr=1.0, fert=1.0)
    b = _chromosome(n, np.full(n, 7.0), irr=1.0, fert=1.0)   # same proportions, different scale
    Fa, Fb = (problem.evaluate(v[None, :], return_as_dictionary=True)["F"][0] for v in (a, b))
    assert np.allclose(Fa, Fb)


def test_budget_constraint_is_cost_minus_budget(salem_rabi):
    problem = _problem(salem_rabi, budget=300_000)
    n = problem.n_crops
    x = _chromosome(n, np.ones(n), irr=1.0, fert=1.0)
    out = problem.evaluate(x[None, :], return_as_dictionary=True)
    # pymoo treats G <= 0 as feasible: within budget exactly when cost <= budget
    assert out["G"][0, 0] == pytest.approx(out["F"][0, 1] - 300_000)


def test_no_budget_means_no_constraint(salem_rabi):
    problem = _problem(salem_rabi, budget=None)
    assert problem.n_ieq_constr == 0
    n = problem.n_crops
    out = problem.evaluate(_chromosome(n, np.ones(n), 1.0, 1.0)[None, :], return_as_dictionary=True)
    assert out.get("G") is None or np.size(out["G"]) == 0


def test_decode_gives_hectares_and_bounded_multipliers(salem_rabi):
    problem = _problem(salem_rabi)
    n = problem.n_crops
    x = _chromosome(n, np.arange(1, n + 1), irr=0.7, fert=1.3)
    plan = problem.decode(x)
    assert sum(plan["area_ha"]) == pytest.approx(LAND_HA)
    assert sum(plan["allocation_fraction"]) == pytest.approx(1.0)
    assert plan["crop_names"] == [c.name for c in salem_rabi[0].candidate_crops]
    assert all(0.7 <= m <= 1.3 for m in plan["irrigation_multiplier"] + plan["fertilizer_multiplier"])


def test_single_crop_metrics_are_one_hectare_of_each_crop(salem_rabi):
    problem = _problem(salem_rabi)
    metrics = {m["crop"]: m for m in problem.single_crop_metrics()}
    for c in salem_rabi[0].candidate_crops:
        m = metrics[c.name]
        assert m["cost_rs_ha"] == pytest.approx(c.cost_rs_ha, rel=1e-9)
        assert m["irrigated_ha_per_ha"] == pytest.approx(c.irrigated_share, rel=1e-9)
        assert m["env_per_ha"] == pytest.approx(c.fert_n_kg_ha + c.fert_p_kg_ha + c.fert_k_kg_ha, rel=1e-9)
        assert m["yield_t_ha"] == pytest.approx(c.yield_kg_ha / 1000.0 * m["crop_confidence"], rel=1e-9)
