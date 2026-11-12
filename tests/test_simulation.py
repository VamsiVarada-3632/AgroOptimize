"""
Scenario Simulation & Decision Impact Analysis.

Covers the default-neutral pipeline hooks, parameter validation, the
statistical comparison, end-to-end simulations checked against independent
calculations on the raw CSVs and config, historical comparison, generated
statements, persistence and the HTTP endpoints.

Run with:  python3 -m pytest tests/test_simulation.py -q
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest
from fastapi.testclient import TestClient
from scipy import stats

from app import config
from app.data import preprocessing as pp
from app.data.loader import load_all
from app.decision import ranking
from app.fuzzy import engine as fz
from app.main import app
from app.optimization.problem import FarmPlanProblem
from app.schemas import FarmPlanRequest
from app.services import explanation_service as es
from app.services import plan_service as ps
from app.services import results_store as rs
from app.services import simulation_service as sim

client = TestClient(app)
BASE = {"location": "Salem", "season": "Rabi", "total_land_ha": 5.0, "preference": "balanced"}


def simulate(scenario=None, base=None):
    return sim.simulate({"base": dict(base or BASE), "scenario": scenario or {}})


@pytest.fixture(scope="module")
def unchanged():
    return simulate({})


@pytest.fixture(scope="module")
def drought():
    return simulate({"rainfall_change_pct": -20, "water_availability": "low"})


@pytest.fixture(scope="module")
def market_up():
    return simulate({"market_price": "increase"})


@pytest.fixture(scope="module")
def water_priority():
    return simulate({"priorities": {"yield": 10, "cost": 10, "water": 80, "env": 10}})


@pytest.fixture(scope="module")
def tight_budget():
    return simulate({"budget_rs": 1_000})


def _season_rows(df, location="Salem", season="Rabi", year=None):
    year = year or int(df["Year"].max())
    months = config.SEASON_MONTH_MAP[season]
    return df[(df["Location"] == location) & (df["Year"] == year) & (df["Month"].isin(months))]


# ---------------------------------------------------------------------------
# Pipeline hooks are neutral by default and exact when used
# ---------------------------------------------------------------------------

def test_profile_defaults_are_unchanged():
    a = pp.get_region_season_profile("Salem", "Kharif")
    b = pp.get_region_season_profile("Salem", "Kharif", rainfall_factor=1.0, storage_override_pct=None)
    assert a == b


@pytest.mark.parametrize("factor", [0.7, 0.9, 1.2, 1.3])
def test_rainfall_factor_rescales_rainfall_and_recomputes_deviation(factor):
    base = pp.get_region_season_profile("Salem", "Rabi")
    profile = pp.get_region_season_profile("Salem", "Rabi", rainfall_factor=factor)
    actual, normal = base.rainfall.season_actual_mm, base.rainfall.season_normal_mm
    assert profile.rainfall.season_actual_mm == pytest.approx(actual * factor, abs=0.1)
    assert profile.rainfall.season_normal_mm == normal                      # the IMD normal is never scaled
    assert profile.rainfall.avg_deviation_percent == pytest.approx((actual * factor - normal) / normal * 100, abs=0.01)
    assert profile.rainfall.avg_monthly_rainfall_mm == pytest.approx(base.rainfall.avg_monthly_rainfall_mm * factor, abs=0.01)
    # soil, water and candidate crops are untouched
    assert profile.soil == base.soil and profile.water == base.water and profile.candidate_crops == base.candidate_crops


def test_dataset_deviation_matches_the_formula_used_for_scaled_rainfall():
    r = load_all()["rainfall"].dropna(subset=["Monthly_Rainfall_mm", "Normal_Rainfall_mm", "Deviation_Percent"])
    r = r[r.Normal_Rainfall_mm > 0]
    calc = (r.Monthly_Rainfall_mm - r.Normal_Rainfall_mm) / r.Normal_Rainfall_mm * 100
    assert (calc - r.Deviation_Percent).abs().max() < 0.1


def test_storage_override_only_changes_storage():
    base = pp.get_region_season_profile("Erode", "Rabi")
    low = pp.get_region_season_profile("Erode", "Rabi", storage_override_pct=10.0)
    assert low.water.avg_storage_percent == 10.0
    assert low.water.groundwater_status == base.water.groundwater_status
    assert low.rainfall == base.rainfall and low.candidate_crops == base.candidate_crops


def _problem(**kw):
    profile = pp.get_region_season_profile("Salem", "Rabi")
    return profile, FarmPlanProblem(profile, fz.assess_profile(profile), total_land_ha=1.0, **kw)


@pytest.mark.parametrize("factor", [0.8, 1.3])
def test_fertilizer_price_factor_is_disabled_without_official_prices(factor):
    """No official fertiliser retail-price dataset is loaded, so a price lever must refuse rather than use assumed prices."""
    with pytest.raises(ValueError, match="fertili[sz]er"):
        _problem(fertilizer_price_factor=factor)
    _problem(fertilizer_price_factor=1.0)       # neutral value is accepted


def test_single_crop_metrics_match_the_objective_formula():
    profile, problem = _problem()
    for i, m in enumerate(problem.single_crop_metrics()):
        c = profile.candidate_crops[i]
        assert m["crop"] == c.name
        assert m["yield_t_ha"] == pytest.approx(c.yield_kg_ha / 1000 * problem.crop_vec.crop_yield_confidence[i])
        assert m["cost_rs_ha"] == pytest.approx(c.yield_kg_ha / 100 * c.cost_rs_qtl)          # CACP A2+FL Rs/quintal x quintals/ha
        assert m["irrigated_ha_per_ha"] == pytest.approx(c.irrigated_share)
        assert m["env_per_ha"] == pytest.approx(c.fert_n_kg_ha + c.fert_p_kg_ha + c.fert_k_kg_ha)   # TNAU dose, kg/ha


def test_explicit_weights_equal_to_a_preference_rank_identically():
    run = ps.run_pipeline(FarmPlanRequest(**BASE, save_results=False), track_history=False)
    conf = dict(zip(run.problem.crop_vec.names, run.problem.crop_vec.crop_yield_confidence.tolist()))
    for pref in ("balanced", "min_water"):
        a = ranking.rank_plans(run.feasible_plans, conf, preference=pref)
        b = ranking.rank_plans(run.feasible_plans, conf, weights=list(ranking.preference_weights(pref) * 7))
        assert ranking.to_dict_list(a) == ranking.to_dict_list(b)


@pytest.mark.parametrize("bad", [[0, 0, 0, 0], [1, -1, 1, 1], [1, 1, 1]])
def test_normalise_weights_rejects_invalid(bad):
    with pytest.raises(ValueError):
        ranking.normalise_weights(bad)


def test_run_pipeline_matches_a_normal_run():
    req = FarmPlanRequest(**BASE, save_results=False)
    a = ps.generate_farm_plans(req)
    b = ps.run_pipeline(req, seed=config.NSGA2_SEED).response
    for r in (a, b):
        r["meta"].pop("optimize_seconds")
        for timing in ("total_seconds", "avg_generation_ms"):   # wall-clock, differs per run
            r["meta"]["optimizer"]["profile"].pop(timing)
        r["meta"]["quality_metrics"].pop("runtime_seconds")
    assert a["run_id"] is None and a["saved_files"] is None   # not saved
    assert {k: a[k] for k in b} == b


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------

def test_water_levels_sit_in_their_own_fuzzy_set():
    expected = {"very_low": "low", "low": "low", "medium": "medium", "high": "high", "very_high": "high"}
    for level, pct in sim.water_level_storage_pct().items():
        degrees = fz.input_memberships(0, pct, 50)["water_storage"]
        assert max(degrees, key=degrees.get) == expected[level], level
    values = list(sim.water_level_storage_pct().values())
    assert values == sorted(values)


@pytest.mark.parametrize("location", config.LOCATIONS)
def test_market_step_is_the_largest_notified_one_year_msp_change(location):
    """Independent recomputation from the official MSP notifications (KMS 2022-23 .. 2025-26) for the crops grown in the district."""
    from app.datasets import service as svc
    grown = set(load_all()["crop"].query("Location == @location")["Crop_Name"])
    msp = svc.msp_table()
    msp = msp[msp.marketing_season.str.startswith("KMS") & msp.crop.isin(grown)]
    best = 0.0
    for _, g in msp.groupby(["crop", "variety"]):
        prices = g.assign(y=g.marketing_season.str[4:8].astype(int)).sort_values("y")["msp_rs_qtl"].tolist()
        for a_, b_ in zip(prices, prices[1:]):
            best = max(best, abs(b_ - a_) / a_ * 100)
    assert sim.market_price_step_pct(location) == pytest.approx(round(best, 1))
    assert 0 <= sim.market_price_step_pct(location) <= 25


@pytest.mark.parametrize("scenario", [
    {"rainfall_change_pct": -25}, {"fertilizer_cost_change_pct": 50}, {"water_availability": "plenty"},
    {"market_price": "boom"}, {"priorities": {"yield": 0, "cost": 0, "water": 0, "env": 0}},
])
def test_resolve_rejects_invalid_controls(scenario):
    with pytest.raises(ValueError):
        sim.resolve({"base": BASE, "scenario": scenario})


def test_resolve_inherits_base_values_and_maps_controls():
    ctx = sim.resolve({"base": {**BASE, "budget_rs": 300_000, "location": "salem"},
                       "scenario": {"rainfall_change_pct": 10, "water_availability": "high", "market_price": "decrease"}})
    sr = ctx["scenario_request"]
    assert (sr.location, sr.total_land_ha, sr.budget_rs, sr.preference) == ("Salem", 5.0, 300_000, "balanced")
    adj = ctx["adjustments"]
    assert adj.rainfall_factor == pytest.approx(1.1) and adj.fertilizer_price_factor == pytest.approx(1.0)
    assert adj.storage_override_pct == sim.water_level_storage_pct()["high"] and adj.topsis_weights is None
    assert ctx["price_factor"] == pytest.approx(1 - sim.market_price_step_pct("Salem") / 100)


def test_fertilizer_price_lever_is_disabled_and_names_the_missing_dataset():
    from app.errors import FeatureUnavailable
    with pytest.raises(FeatureUnavailable, match="fertiliser retail prices"):
        sim.resolve({"base": BASE, "scenario": {"fertilizer_cost_change_pct": -20}})


def test_unknown_district_is_rejected():
    with pytest.raises(ValueError):
        sim.resolve({"base": {**BASE, "location": "Nowhere"}})


# ---------------------------------------------------------------------------
# Paired comparison
# ---------------------------------------------------------------------------

def test_paired_identical_runs_are_unchanged():
    r = sim._paired("yield", "Yield", "t", [1, 2, 3], [1, 2, 3])
    assert r["verdict"] == "unchanged" and r["p_value"] == 1.0


def test_paired_consistent_shift_is_significant_with_direction():
    up = sim._paired("cost", "Cost", "₹", [100, 110, 120], [110, 121, 132])
    assert up["verdict"] == "worsened" and up["p_value"] < 0.05
    shifted = sim._paired("water", "Water", "L", [5, 6, 7], [4, 5, 6])      # identical shift in every run
    assert shifted["p_value"] == 0.0 and shifted["verdict"] == "improved"
    base, scen = [10, 12, 14, 13, 11], [8, 10.5, 11, 10, 9.4]
    down = sim._paired("yield", "Yield", "t", base, scen)
    assert down["verdict"] == "worsened"
    assert down["p_value"] == pytest.approx(stats.ttest_rel(scen, base).pvalue, abs=1e-4)
    assert down["baseline"] == pytest.approx(np.mean(base))
    assert down["change_pct"] == pytest.approx((np.mean(scen) - np.mean(base)) / np.mean(base) * 100, abs=0.05)


def test_paired_noisy_change_is_not_significant():
    r = sim._paired("water", "Water", "L", [10, 20, 12, 18, 15], [16, 14, 22, 13, 20])
    assert r["change_pct"] == pytest.approx(13.3, abs=0.1)
    assert r["verdict"] == "not_significant"


def test_paired_ignores_runs_without_a_plan():
    r = sim._paired("yield", "Yield", "t", [1, None, 3], [1, 5, None])
    assert r["n_runs"] == 1


# ---------------------------------------------------------------------------
# End-to-end simulations
# ---------------------------------------------------------------------------

def _strict_json(payload):
    json.dumps(payload, allow_nan=False)


@pytest.mark.parametrize("name", ["unchanged", "drought", "market_up", "water_priority", "tight_budget"])
def test_result_is_complete_and_serialisable(name, request):
    r = request.getfixturevalue(name)
    for key in ("inputs", "conditions", "baseline", "scenario", "crop_effects", "fuzzy_changes", "optimization",
                "constraints", "historical", "decision_impact", "trade_offs", "summary", "meta"):
        assert key in r
    _strict_json(r)
    assert r["meta"]["cached"] is False and r["meta"]["runs_per_side"] == len(sim.ENSEMBLE_SEEDS)
    for item in r["decision_impact"]:
        assert set(item) >= {"id", "title", "detail", "source", "evidence"}
    assert r["summary"]["text"] == " ".join(r["summary"]["sentences"])


def test_baseline_is_exactly_the_run_optimization_result(unchanged):
    normal = ps.generate_farm_plans(FarmPlanRequest(**BASE, save_results=False))
    assert unchanged["baseline"]["top_plan"] == normal["plans"][0]
    assert unchanged["baseline"]["fuzzy_assessment"] == normal["fuzzy_assessment"]
    # Same explanation as the saved run (which tracks convergence history).
    saved_like = ps.run_pipeline(FarmPlanRequest(**BASE, save_results=False), track_history=True).response
    expected = es.explain(es.context_from_saved_run(saved_like, 1))["confidence"]
    assert unchanged["baseline"]["explanation"]["confidence"]["overall_pct"] == expected["overall_pct"]
    assert all(c["score"] is not None for c in unchanged["baseline"]["explanation"]["confidence"]["components"]
               if c["id"] == "convergence")


def test_unchanged_scenario_reports_no_change(unchanged):
    assert not any(c["changed"] for c in unchanged["conditions"])
    assert unchanged["scenario"]["top_plan"] == unchanged["baseline"]["top_plan"]
    assert all(h["verdict"] == "unchanged" for h in unchanged["impact"]["headline"].values())
    assert unchanged["comparison"]["reliable_shifts"] == []
    assert unchanged["fuzzy_changes"]["rules_changed"] == []
    assert any(i["id"] == "same-mix" for i in unchanged["decision_impact"])
    assert unchanged["summary"]["sentences"][0].startswith("No condition was changed")


def test_drought_conditions_reach_the_pipeline(drought):
    b, s = drought["baseline"]["region_profile"], drought["scenario"]["region_profile"]
    assert s["rainfall"]["season_actual_mm"] == pytest.approx(b["rainfall"]["season_actual_mm"] * 0.8, abs=0.1)
    assert s["water"]["avg_storage_percent"] == sim.water_level_storage_pct()["low"]
    expected = fz.evaluate_uncertainty(s["rainfall"]["avg_deviation_percent"], s["water"]["avg_storage_percent"],
                                       s["soil"]["fertility_index"])
    assert drought["scenario"]["fuzzy_assessment"] == {**vars(expected), "applied": True, "reason": None}
    assert drought["fuzzy_changes"]["inputs"][1]["scenario_set"] == "low"
    changed = {c["id"] for c in drought["conditions"] if c["changed"]}
    assert changed == {"rainfall", "water"}


def test_crop_effects_match_the_official_data(drought):
    """Per-hectare irrigated area is the crop's official irrigated share (not changed by rainfall); cost and rainfed share
    come straight from the Season & Crop Report / CACP rows."""
    crop = load_all()["crop"]
    year = drought["baseline"]["region_profile"]["year"]
    rows = crop[(crop.Location == "Salem") & (crop.Year == year) & (crop.Season == "Rabi")].set_index("Crop_Name")
    assert drought["crop_effects"]
    for e in drought["crop_effects"]:
        r = rows.loc[e["crop"]]
        for side in ("baseline", "scenario"):
            assert e["water"][side] == pytest.approx(r.Irrigated_Share, abs=1e-3)
            assert e["cost"][side] == pytest.approx(r.Yield_Kg_Ha / 100 * r.Cost_Rs_Qtl, rel=1e-3)
        assert e["rainfall_dependency"] == f"{1 - r.Irrigated_Share:.0%} rainfed"


def test_impact_is_the_paired_mean_over_seed_runs(drought):
    for side in ("baseline", "scenario"):
        assert len(drought[side]["runs"]) == len(sim.ENSEMBLE_SEEDS)
    b = [r["yield"] for r in drought["baseline"]["runs"]]
    s = [r["yield"] for r in drought["scenario"]["runs"]]
    y = next(m for m in drought["impact"]["totals"] if m["id"] == "yield")
    assert y["baseline"] == pytest.approx(np.mean(b), abs=0.01) and y["scenario"] == pytest.approx(np.mean(s), abs=0.01)
    assert y["p_value"] == pytest.approx(stats.ttest_rel(s, b).pvalue, abs=1e-4)
    assert y["recommended"]["baseline"] == pytest.approx(drought["baseline"]["top_plan"]["yield_tonnes"], abs=0.01)
    for m in drought["impact"]["totals"]:
        if m["verdict"] in ("improved", "worsened"):
            assert m["p_value"] < sim.SIGNIFICANCE_P


def test_seed_runs_reproduce_independently(drought):
    ctx = sim.resolve({"base": BASE, "scenario": {"rainfall_change_pct": -20, "water_availability": "low"}})
    for seed, recorded in zip(sim.ENSEMBLE_SEEDS[:2], drought["scenario"]["runs"]):
        top = ps.run_pipeline(ctx["scenario_request"], ctx["adjustments"], track_history=False, seed=seed).response["plans"][0]
        assert top["yield_tonnes"] == pytest.approx(recorded["yield"]) and top["cost_rs"] == pytest.approx(recorded["cost"])


def test_decomposition_reevaluates_the_baseline_plan(drought):
    ctx = sim.resolve({"base": BASE, "scenario": {"rainfall_change_pct": -20, "water_availability": "low"}})
    run = ps.run_pipeline(ctx["scenario_request"], ctx["adjustments"], track_history=False)
    plan = drought["baseline"]["top_plan"]
    # Independent: same allocation and irrigation multipliers on the scenario's crop data: irrigated area = area x multiplier x irrigated share.
    share = {c["name"]: c["irrigated_share"] if c.get("irrigated_share") is not None else 1 - c["rainfed_share"]
             for c in run.response["region_profile"]["candidate_crops"]}
    irrigated = sum(a * i * share[n] for n, a, i in zip(plan["crop_names"], plan["area_ha"], plan["irrigation_multiplier"]))
    assert sim._evaluate_plan(run, plan)["irrigated_ha"] == pytest.approx(irrigated, rel=5e-3)   # plan fields are rounded to 3 decimals
    rows = {r["objective"]: r for r in drought["optimization"]["decomposition"]["rows"]}
    # Rainfall/storage act on yield through the fuzzy confidence only; official irrigated area, CACP cost and TNAU fertiliser
    # per hectare do not depend on weather, so the same plan costs and irrigates the same under the scenario.
    for k in ("cost", "water", "env"):
        assert rows[k]["condition_effect_pct"] in (0.0, None) or abs(rows[k]["condition_effect_pct"]) < 0.1, k
    assert rows["yield"]["condition_effect_pct"] <= 0       # drought cannot raise the fuzzy yield confidence


def test_market_price_changes_profit_only(market_up):
    b, s = market_up["baseline"], market_up["scenario"]
    assert s["top_plan"] == b["top_plan"]
    factor = 1 + sim.market_price_step_pct("Salem") / 100
    rev_b = b["explanation"]["economics"]["indicative_revenue_rs"]
    assert s["explanation"]["economics"]["indicative_revenue_rs"] == pytest.approx(rev_b * factor, abs=1)
    h = market_up["impact"]["headline"]
    assert h["profit"]["verdict"] == "improved"
    assert all(h[k]["verdict"] == "unchanged" for k in ("yield", "cost", "water", "env"))
    assert any(i["id"] == "market" for i in market_up["decision_impact"])


def test_priorities_only_change_topsis(water_priority):
    opt = water_priority["optimization"]
    assert opt["front_identical"] is True
    assert opt["weights"]["scenario"] == pytest.approx(dict(zip(sim.OBJECTIVES, [0.1 / 1.1, 0.1 / 1.1, 0.8 / 1.1, 0.1 / 1.1])), abs=1e-4)
    assert opt["weights"]["scenario_dominant"] == "water"
    water = next(m for m in water_priority["impact"]["totals"] if m["id"] == "water")
    assert water["verdict"] == "improved"
    explanation_weights = water_priority["scenario"]["explanation"]["objectives"]
    assert explanation_weights   # explanation ran with the custom weights
    assert any(i["id"] == "weights" for i in water_priority["decision_impact"])


def test_infeasible_budget_reports_the_cheapest_plan(tight_budget):
    s = tight_budget["scenario"]
    assert s["available"] is False and tight_budget["impact"] is None and tight_budget["comparison"] is None
    profile = pp.get_region_season_profile("Salem", "Rabi")
    # official CACP cost per hectare does not depend on input multipliers: the cheapest plan is all land in the cheapest crop
    cheapest = min(c.cost_rs_ha for c in profile.candidate_crops) * BASE["total_land_ha"]
    assert f"₹{cheapest:,.0f}" in s["reason"]
    assert tight_budget["constraints"][0]["id"] == "no_feasible_plan"
    assert any(i["id"] == "infeasible" for i in tight_budget["decision_impact"])


def test_baseline_without_feasible_plan_is_an_error():
    with pytest.raises(sim.SimulationError):
        simulate({}, base={**BASE, "budget_rs": 1000})


def test_land_change_uses_per_hectare_headline():
    r = simulate({"total_land_ha": 10})
    assert r["impact"]["basis"] == "per_ha"
    assert r["impact"]["headline"]["profit"]["label"] == "Indicative profit"
    assert r["impact"]["profit"]["unit"] == "₹/ha"


def test_historical_alignment_matches_the_district_pattern(drought):
    h = drought["historical"]
    crop = load_all()["crop"]
    rows = crop[(crop.Location == "Salem") & (crop.Season == "Rabi")]
    share = rows.assign(s=rows.Area_Ha / rows.groupby("Year").Area_Ha.transform("sum") * 100).groupby("Crop_Name").s.mean()
    candidates = [c["crop"] for c in drought["baseline"]["single_crop"]]
    hist = {c: share.get(c, 0.0) for c in candidates}
    total = sum(hist.values())
    hist = {c: v / total * 100 for c, v in hist.items()}
    for row in h["historical_shares"]:
        assert row["share_pct"] == pytest.approx(hist[row["crop"]], abs=0.5)   # district shares are rounded to 0.1 before renormalising
    mix = {c["crop"]: c["share_pct"] for c in drought["scenario"]["crop_mix"]}
    alignment = sum(min(mix.get(c, 0.0), hist[c]) for c in candidates)
    assert h["alignment_pct"]["scenario"] == pytest.approx(alignment, abs=1.0)


def test_statements_only_attribute_reliable_shifts(drought):
    shifts = [i for i in drought["decision_impact"] if i["id"].startswith("shift-")]
    for item in shifts:
        assert item["evidence"]["p_value"] < sim.SIGNIFICANCE_P
    for e in drought["crop_effects"]:
        if abs(e["share_change_pp"]) >= sim.SHARE_SHIFT_PP and not e["share_shift_reliable"]:
            assert any(i["id"] == "search-variation" for i in drought["decision_impact"])


def test_trade_offs_follow_the_impact_verdicts(drought):
    t = drought["trade_offs"]
    verdicts = {m["id"]: m["verdict"] for m in drought["impact"]["totals"]}
    verdicts.update(profit=drought["impact"]["profit"]["verdict"], confidence=drought["impact"]["confidence"]["verdict"])
    for bucket in ("improved", "worsened", "unchanged", "not_significant"):
        for m in t[bucket]:
            assert verdicts[m["id"]] == bucket


def test_explanation_uses_scenario_weights_and_price():
    run = ps.run_pipeline(FarmPlanRequest(**BASE, save_results=False),
                          ps.PipelineAdjustments(topsis_weights=(1, 1, 8, 1)), track_history=False)
    ctx = es.context_from_saved_run(run.response, 1, price_factor=1.1)
    assert ctx.topsis_weights() == pytest.approx(np.array([1, 1, 8, 1]) / 11)
    plain = es.indicative_economics(es.context_from_saved_run(run.response, 1), run.response["plans"][0])
    priced = es.indicative_economics(ctx, run.response["plans"][0])
    assert priced["indicative_revenue_rs"] == pytest.approx(plain["indicative_revenue_rs"] * 1.1, abs=1)


# ---------------------------------------------------------------------------
# Persistence and endpoints
# ---------------------------------------------------------------------------

def test_saved_simulation_roundtrip(tmp_path, unchanged):
    stored = rs.save_simulation(unchanged, client_id="me", name="Baseline check", out_dir=tmp_path)
    assert stored["simulation_id"].startswith("sim_salem_")
    listed = rs.list_simulations("me", out_dir=tmp_path)
    assert [s["simulation_id"] for s in listed] == [stored["simulation_id"]]
    assert listed[0]["name"] == "Baseline check" and listed[0]["location"] == "Salem"
    assert rs.list_simulations("someone-else", out_dir=tmp_path) == []
    assert rs.load_simulation(stored["simulation_id"], "someone-else", out_dir=tmp_path) is None
    assert rs.load_simulation(stored["simulation_id"], "me", out_dir=tmp_path)["result"]["summary"] == unchanged["summary"]
    assert rs.load_simulation("../etc/passwd", "me", out_dir=tmp_path) is None
    assert rs.delete_simulation(stored["simulation_id"], "me", out_dir=tmp_path) is True
    assert rs.list_simulations("me", out_dir=tmp_path) == []


def test_pending_results_are_bounded_and_scoped():
    tokens = [sim.remember({"n": i}, "c1") for i in range(sim.PENDING_LIMIT + 3)]
    assert sim.pending(tokens[0], "c1") is None            # evicted
    assert sim.pending(tokens[-1], "c1") == {"n": sim.PENDING_LIMIT + 2}
    assert sim.pending(tokens[-1], "c2") is None


def test_endpoints_run_save_list_get_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RESULTS_DIR", tmp_path)
    # the fertiliser-price lever is disabled (no official prices): HTTP 501 naming the missing dataset
    blocked = client.post("/api/simulations/run", json={"base": BASE, "scenario": {"fertilizer_cost_change_pct": 20}})
    assert blocked.status_code == 501 and "fertiliser retail prices" in blocked.json()["missing_dataset"]
    body = {"base": BASE, "scenario": {"market_price": "increase"}, "client_id": "browser-1"}
    r = client.post("/api/simulations/run", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["token"] and data["inputs"]["scenario"]["market_price"] == "increase"

    assert client.post("/api/simulations", json={"token": data["token"], "client_id": "browser-2"}).status_code == 404
    saved = client.post("/api/simulations", json={"token": data["token"], "client_id": "browser-1", "name": "Price up"})
    assert saved.status_code == 201
    sim_id = saved.json()["simulation_id"]
    assert saved.json()["changes"] == ["market"]

    assert [s["simulation_id"] for s in client.get("/api/simulations", params={"client_id": "browser-1"}).json()] == [sim_id]
    assert client.get("/api/simulations", params={"client_id": "browser-2"}).json() == []
    got = client.get(f"/api/simulations/{sim_id}", params={"client_id": "browser-1"})
    assert got.status_code == 200 and got.json()["result"]["summary"] == data["summary"]
    assert "token" not in got.json()["result"] or got.json()["result"]["token"] is None
    assert client.get(f"/api/simulations/{sim_id}", params={"client_id": "browser-2"}).status_code == 404
    assert client.delete(f"/api/simulations/{sim_id}", params={"client_id": "browser-2"}).status_code == 404
    assert client.delete(f"/api/simulations/{sim_id}", params={"client_id": "browser-1"}).status_code == 200
    assert client.get(f"/api/simulations/{sim_id}", params={"client_id": "browser-1"}).status_code == 404


@pytest.mark.parametrize("body", [
    {"base": BASE, "scenario": {"rainfall_change_pct": 15}},
    {"base": BASE, "scenario": {"water_availability": "plenty"}},
    {"base": BASE, "scenario": {"priorities": {"yield": 0, "cost": 0, "water": 0, "env": 0}}},
    {"base": {**BASE, "total_land_ha": 0}},
    {"base": {**BASE, "location": "Nowhere"}},
])
def test_run_endpoint_validates(body):
    assert client.post("/api/simulations/run", json=body).status_code == 422


def test_list_requires_client_id():
    assert client.get("/api/simulations").status_code == 422
    assert client.post("/api/simulations", json={"token": "x" * 20, "client_id": "a"}).status_code == 404
