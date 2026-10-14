"""
Scenario Simulation & Decision Impact Analysis.

A simulation runs the normal pipeline for the baseline conditions and for
the modified scenario and analyses the difference. Nothing is approximated:
both sides go through plan_service.run_pipeline (preprocessing -> fuzzy ->
NSGA-II -> TOPSIS) and the explanation engine.

NSGA-II is stochastic: with identical inputs, different seeds recommend
noticeably different plans (e.g. Salem Kharif top-plan yield 50-70 t over
five seeds). Comparing one baseline run with one scenario run would
therefore attribute search variation to the scenario. Each side is run with
the same ENSEMBLE_SEEDS (common random numbers) and every change is judged
with a paired t-test over those runs; only changes with p < SIGNIFICANCE_P
are reported as improved/worsened. The displayed recommendation of each side
is the first seed's run -- the seed Run Optimization uses -- so the baseline
plan is exactly what Run Optimization shows for the same inputs.

Where each scenario control enters the pipeline:

  rainfall change     preprocessing: monthly rainfall is scaled before the
                      season is aggregated, so the fuzzy rainfall-deviation
                      input and the effective rainfall in the water objective
                      both change
  water availability  fuzzy water-storage input (seasonal storage %)
  fertiliser cost     NSGA-II cost objective (fertiliser prices)
  land size           NSGA-II problem (hectares allocated)
  budget              NSGA-II budget constraint
  preference /        TOPSIS weights (NSGA-II is Pareto-based and has no
  priority sliders    weights; they decide which Pareto plan is chosen)
  market price        indicative revenue and profit only -- price is not an
                      optimiser objective, so it cannot change the plan

Payload sections: inputs, conditions, baseline, scenario, comparison,
impact, crop_effects, fuzzy_changes, optimization, constraints, historical,
decision_impact, trade_offs, summary. Thresholds are module constants.
"""

from __future__ import annotations

import secrets
import threading
import time
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy import stats

from app import config

from app.data import preprocessing as pp
from app.data.loader import load_all
from app.decision import ranking
from app.fuzzy import engine as fz
from app.schemas import FarmPlanRequest
from app.services import district_service as dsv
from app.services import explanation_service as es
from app.services.explanation_service import make_item
from app.services.plan_service import PipelineAdjustments, PipelineRun, run_pipeline

OBJECTIVES = ("yield", "cost", "water", "env")
OBJECTIVE_LABEL = {"yield": "Expected yield", "cost": "Production cost", "water": "Irrigation water",
                   "env": "Environmental impact"}
OBJECTIVE_KEY = {"yield": "yield_tonnes", "cost": "cost_rs", "water": "water_liters", "env": "env_impact_score"}
HIGHER_IS_BETTER = {"yield": True, "cost": False, "water": False, "env": False, "profit": True, "confidence": True,
                    "yield_confidence": True, "irrigation_risk": False}

RAINFALL_STEPS = (-30, -20, -10, 0, 10, 20, 30)
FERTILIZER_STEPS = (-20, -10, 0, 10, 20, 30)
MARKET_OPTIONS = ("decrease", "stable", "increase")

# Water availability levels -> seasonal reservoir storage % fed to the fuzzy
# model. Each level sits in a distinct region of the model's own water-storage
# partition (low [0,0,35], medium [20,50,75], high [60,100,100]):
#   very_low  10  only "low" active (0.71)
#   low       25  low/medium overlap, "low" dominant (0.29 vs 0.17)
#   medium    50  peak of "medium"
#   high      70  medium/high overlap, "high" dominant (0.25 vs 0.20)
#   very_high 90  only "high" active (0.75)
WATER_LEVEL_STORAGE_PCT = {"very_low": 10.0, "low": 25.0, "medium": 50.0, "high": 70.0, "very_high": 90.0}
WATER_LEVEL_LABEL = {"current": "Current (dataset)", "very_low": "Very low", "low": "Low", "medium": "Medium",
                     "high": "High", "very_high": "Very high"}

UNCHANGED_PCT = 1.0          # |change| below this is reported as unchanged
SHARE_SHIFT_PP = 5.0         # crop share change (percentage points) worth explaining
RULE_STRENGTH_CHANGE = 0.05  # fuzzy rule firing change worth reporting
BUDGET_TIGHT_PCT = 95.0      # top plan using >= this % of the budget = binding
LOW_STORAGE_PCT = dsv.LOW_STORAGE_PCT

ENSEMBLE_SEEDS = (config.NSGA2_SEED, 1, 2, 3, 4)   # first = Run Optimization's seed
SIGNIFICANCE_P = 0.05        # paired t-test threshold for a reported change

PENDING_LIMIT = 32           # unsaved results kept so "Save" does not re-run


class SimulationError(ValueError):
    """Invalid simulation inputs (mapped to HTTP 422)."""


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def market_price_step_pct(location: str) -> float:
    """Largest one-year change in the dataset's price column for this
    district (observed years, any crop/season). "Increase"/"Decrease" move
    every price by this much: a change the district has actually seen."""
    crop = pp.observed_rows(load_all()["crop"])
    rows = crop[crop["Location"] == location].sort_values("Year")
    yoy = rows.groupby(["Season", "Crop_Name"])["MSP_Rs_Qtl"].pct_change().dropna().abs() * 100
    return round(float(yoy.max()), 1) if len(yoy) else 0.0


def _priority_weights(priorities: Optional[dict]) -> Optional[Tuple[float, float, float, float]]:
    if priorities is None:
        return None
    w = tuple(float(priorities[k]) for k in OBJECTIVES)
    if any(v < 0 for v in w) or sum(w) <= 0:
        raise SimulationError("At least one priority must be above zero.")
    return w


def resolve(request: dict) -> dict:
    """Validate and expand a simulation request into the two pipeline
    requests and the scenario adjustments."""
    base = dict(request["base"])
    sc = dict(request.get("scenario") or {})
    location = pp.canonical_choice(base["location"], pp.config.LOCATIONS, "location")
    season = pp.canonical_choice(base["season"], pp.config.AG_SEASONS, "season")
    base.update(location=location, season=season)

    rain = int(sc.get("rainfall_change_pct", 0))
    fert = int(sc.get("fertilizer_cost_change_pct", 0))
    water = sc.get("water_availability", "current")
    market = sc.get("market_price", "stable")
    if rain not in RAINFALL_STEPS:
        raise SimulationError(f"rainfall_change_pct must be one of {RAINFALL_STEPS}.")
    if fert not in FERTILIZER_STEPS:
        raise SimulationError(f"fertilizer_cost_change_pct must be one of {FERTILIZER_STEPS}.")
    if water != "current" and water not in WATER_LEVEL_STORAGE_PCT:
        raise SimulationError("water_availability must be current, very_low, low, medium, high or very_high.")
    if market not in MARKET_OPTIONS:
        raise SimulationError("market_price must be decrease, stable or increase.")

    step = market_price_step_pct(location)
    price_factor = {"decrease": 1 - step / 100, "stable": 1.0, "increase": 1 + step / 100}[market]

    common = {"location": location, "season": season, "year": base.get("year"), "save_results": False}
    base_req = FarmPlanRequest(**common, total_land_ha=base["total_land_ha"], budget_rs=base.get("budget_rs"),
                               preference=base.get("preference", "balanced"))
    scen_req = FarmPlanRequest(**common,
                               total_land_ha=sc.get("total_land_ha") or base["total_land_ha"],
                               budget_rs=sc["budget_rs"] if sc.get("budget_rs") is not None else base.get("budget_rs"),
                               preference=sc.get("preference") or base.get("preference", "balanced"))
    adjustments = PipelineAdjustments(
        rainfall_factor=1 + rain / 100,
        storage_override_pct=WATER_LEVEL_STORAGE_PCT.get(water),
        fertilizer_price_factor=1 + fert / 100,
        topsis_weights=_priority_weights(sc.get("priorities")),
    )
    return {"base_request": base_req, "scenario_request": scen_req, "adjustments": adjustments,
            "price_factor": price_factor, "market_step_pct": step,
            "controls": {"rainfall_change_pct": rain, "fertilizer_cost_change_pct": fert,
                         "water_availability": water, "market_price": market}}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _pct(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or abs(a) < 1e-12:
        return None
    return round(float((b - a) / abs(a) * 100), 1)


def _paired(metric: str, label: str, unit: str, base_vals: List[Optional[float]], scen_vals: List[Optional[float]],
            digits: int = 2) -> dict:
    """Compare one quantity across the paired seed runs (index k of both
    lists comes from the same seed). Reports the means, the change of the
    means, the seed-run ranges, a paired t-test p-value and a verdict:
    improved / worsened (p < SIGNIFICANCE_P and |change| >= UNCHANGED_PCT),
    unchanged, or not_significant (moved, but within search variation)."""
    pairs = [(b, s) for b, s in zip(base_vals, scen_vals) if b is not None and s is not None]
    out = {"id": metric, "label": label, "unit": unit, "higher_is_better": HIGHER_IS_BETTER[metric], "n_runs": len(pairs)}
    if not pairs:
        return {**out, "baseline": None, "scenario": None, "change": None, "change_pct": None, "p_value": None,
                "verdict": "not_available"}
    b = np.array([x for x, _ in pairs], dtype=float)
    sc = np.array([y for _, y in pairs], dtype=float)
    diff = sc - b
    if np.allclose(diff, 0):
        p_value = 1.0
    elif len(diff) < 2 or np.allclose(diff, diff[0]):
        p_value = 0.0                      # identical non-zero shift in every run
    else:
        p_value = float(stats.ttest_rel(sc, b).pvalue)
    pct = _pct(b.mean(), sc.mean())
    if np.allclose(diff, 0) or (pct is not None and abs(pct) < UNCHANGED_PCT):
        verdict = "unchanged"
    elif p_value >= SIGNIFICANCE_P:
        verdict = "not_significant"
    else:
        verdict = "improved" if (sc.mean() > b.mean()) == HIGHER_IS_BETTER[metric] else "worsened"
    return {**out, "baseline": round(float(b.mean()), digits), "scenario": round(float(sc.mean()), digits),
            "change": round(float(sc.mean() - b.mean()), digits), "change_pct": pct,
            "baseline_range": [round(float(b.min()), digits), round(float(b.max()), digits)],
            "scenario_range": [round(float(sc.min()), digits), round(float(sc.max()), digits)],
            "recommended": {"baseline": round(float(b[0]), digits), "scenario": round(float(sc[0]), digits)},
            "p_value": round(p_value, 4), "verdict": verdict}


def _compare(metric: str, label: str, unit: str, base: Optional[float], scen: Optional[float], digits: int = 2) -> dict:
    """Single deterministic comparison (no search involved, e.g. fuzzy outputs)."""
    pct = _pct(base, scen)
    if base is None or scen is None:
        verdict = "not_available"
    elif abs(scen - base) < 1e-9 or (pct is not None and abs(pct) < UNCHANGED_PCT):
        verdict = "unchanged"
    else:
        verdict = "improved" if (scen > base) == HIGHER_IS_BETTER[metric] else "worsened"
    return {"id": metric, "label": label, "unit": unit,
            "baseline": None if base is None else round(base, digits),
            "scenario": None if scen is None else round(scen, digits),
            "change": None if base is None or scen is None else round(scen - base, digits),
            "change_pct": pct, "verdict": verdict, "higher_is_better": HIGHER_IS_BETTER[metric]}


def _per_ha(plan: dict, objective: str) -> float:
    return plan[OBJECTIVE_KEY[objective]] / (sum(plan["area_ha"]) or 1.0)


def _fmt_money(v: float) -> str:
    return f"₹{v:,.0f}"


def _decision_vector(plan: dict, names: List[str]) -> np.ndarray:
    idx = {n: i for i, n in enumerate(plan["crop_names"])}
    alloc = [plan["allocation_percent"][idx[n]] / 100 if n in idx else 0.0 for n in names]
    irr = [plan["irrigation_multiplier"][idx[n]] if n in idx else 1.0 for n in names]
    fert = [plan["fertilizer_multiplier"][idx[n]] if n in idx else 1.0 for n in names]
    return np.array([alloc + irr + fert])


def _evaluate_plan(run: PipelineRun, plan: dict) -> dict:
    """A plan's decision variables evaluated under another run's problem
    (same objective function, that run's conditions)."""
    problem = run.problem
    out = problem.evaluate(_decision_vector(plan, list(problem.crop_vec.names)), return_as_dictionary=True)
    F = out["F"][0]
    feasible = True
    if problem.budget_rs:
        feasible = bool(out["G"][0][0] <= 0)
    return {"yield_tonnes": float(-F[0]), "cost_rs": float(F[1]), "water_liters": float(F[2]),
            "env_impact_score": float(F[3]), "feasible": feasible}


# ---------------------------------------------------------------------------
# One side (baseline or scenario)
# ---------------------------------------------------------------------------

def _run_metrics(run: PipelineRun, price_factor: float) -> Optional[dict]:
    """Top-plan outcomes of one seed run (None when it has no feasible plan)."""
    plans = run.response["plans"]
    if not plans:
        return None
    top = plans[0]
    land = sum(top["area_ha"]) or 1.0
    econ = es.indicative_economics(es.context_from_saved_run(run.response, 1, price_factor=price_factor), top)
    profit = econ.get("indicative_profit_rs") if econ["available"] else None
    return {**{o: top[OBJECTIVE_KEY[o]] for o in OBJECTIVES},
            **{f"{o}_per_ha": top[OBJECTIVE_KEY[o]] / land for o in OBJECTIVES},
            "profit": profit, "profit_per_ha": None if profit is None else profit / land,
            "shares": dict(zip(top["crop_names"], top["allocation_percent"]))}


def _cheapest_plan(run: PipelineRun) -> Tuple[str, float]:
    """Lowest cost any plan can have: all land in the cheapest crop at the
    lowest fertiliser level (cost is linear in the allocation)."""
    problem = run.problem
    n = problem.n_crops
    X = np.hstack([np.eye(n), np.ones((n, n)), np.full((n, n), config.FERTILIZER_MULT_MIN)])
    costs = problem.evaluate(X, return_as_dictionary=True)["F"][:, 1]
    i = int(np.argmin(costs))
    return problem.crop_vec.names[i], float(costs[i])


def _side(runs: List[PipelineRun], price_factor: float) -> dict:
    run = runs[0]
    resp = run.response
    plans = resp["plans"]
    rp = resp["region_profile"]
    dependency = {c["name"]: c["rainfall_dependency"] for c in rp["candidate_crops"]}
    side = {
        "available": bool(plans),
        "region_profile": {k: rp[k] for k in ("location", "season", "year", "data_year_estimated", "rainfall", "water", "soil")},
        "fuzzy_assessment": resp["fuzzy_assessment"],
        "meta": {k: resp["meta"].get(k) for k in ("preference", "pop_size", "n_gen", "n_pareto_solutions_found",
                                                  "n_plans_returned", "optimize_seconds", "total_land_ha", "budget_rs",
                                                  "topsis_weights", "adjustments")},
        "single_crop": [{**m, "rainfall_dependency": dependency.get(m["crop"])} for m in run.problem.single_crop_metrics()],
        "runs": [_run_metrics(r, price_factor) for r in runs],
        "front": [{o: _per_ha_raw(p, o) for o in OBJECTIVES} for p in run.feasible_plans],
    }
    side["feasible_runs"] = sum(m is not None for m in side["runs"])
    if not plans:
        crop, cost = _cheapest_plan(run)
        side["reason"] = (f"NSGA-II found no feasible plan for {resp['meta']['total_land_ha']:g} ha"
                          + (f" within the budget of {_fmt_money(resp['meta']['budget_rs'])}. The cheapest possible plan "
                             f"(all land in {crop} at the lowest fertiliser level) costs {_fmt_money(cost)}."
                             if resp["meta"].get("budget_rs") else "."))
        return side
    explanation = es.explain(es.context_from_saved_run(resp, 1, price_factor=price_factor))
    top = plans[0]
    side.update({
        "top_plan": top,
        "plans": plans[:5],
        "explanation": {k: explanation[k] for k in ("summary", "reasons", "risks", "constraints", "confidence", "economics",
                                                     "crop_breakdown", "fuzzy_reasoning", "objectives")},
        "crop_mix": [{"crop": c, "share_pct": s, "area_ha": a}
                     for c, s, a in zip(top["crop_names"], top["allocation_percent"], top["area_ha"]) if s >= es.MIN_SHARE_PCT],
        "per_ha": {o: _per_ha(top, o) for o in OBJECTIVES},
    })
    return side


def _per_ha_raw(plan, objective: str) -> float:
    value = getattr(plan, OBJECTIVE_KEY[objective])
    return float(value) / (float(sum(plan.area_ha)) or 1.0)


# ---------------------------------------------------------------------------
# Analysis sections
# ---------------------------------------------------------------------------

def _conditions(ctx: dict, base: dict, scen: dict) -> List[dict]:
    """Every condition, baseline vs scenario, and where it enters the pipeline."""
    br, sr = ctx["base_request"], ctx["scenario_request"]
    c = ctx["controls"]
    brp, srp = base["region_profile"], scen["region_profile"]
    bw, sw = base["meta"]["topsis_weights"], scen["meta"]["topsis_weights"]
    fmt_w = lambda w: " / ".join(f"{x:.2f}" for x in w)   # noqa: E731
    rows = [
        {"id": "rainfall", "label": "Rainfall", "baseline": "Dataset",
         "scenario": "Dataset" if c["rainfall_change_pct"] == 0 else f"{c['rainfall_change_pct']:+d}%",
         "detail": f"Season rainfall deviation {brp['rainfall']['avg_deviation_percent']:+.1f}% → "
                   f"{srp['rainfall']['avg_deviation_percent']:+.1f}%; effective rainfall "
                   f"{brp['rainfall']['effective_rainfall_mm']:.0f} → {srp['rainfall']['effective_rainfall_mm']:.0f} mm.",
         "enters": "Preprocessing → fuzzy rainfall input and the effective rainfall in the water objective",
         "changed": c["rainfall_change_pct"] != 0},
        {"id": "water", "label": "Water availability", "baseline": WATER_LEVEL_LABEL["current"],
         "scenario": WATER_LEVEL_LABEL[c["water_availability"]],
         "detail": f"Seasonal reservoir storage {brp['water']['avg_storage_percent']:.1f}% → {srp['water']['avg_storage_percent']:.1f}%.",
         "enters": "Fuzzy water-storage input", "changed": c["water_availability"] != "current"},
        {"id": "fertilizer", "label": "Fertiliser cost", "baseline": "Config prices",
         "scenario": "Config prices" if c["fertilizer_cost_change_pct"] == 0 else f"{c['fertilizer_cost_change_pct']:+d}%",
         "detail": "N, P and K prices per kg of nutrient scaled together.",
         "enters": "NSGA-II cost objective", "changed": c["fertilizer_cost_change_pct"] != 0},
        {"id": "market", "label": "Market price", "baseline": "Dataset prices",
         "scenario": {"stable": "Dataset prices", "increase": f"+{ctx['market_step_pct']}%",
                      "decrease": f"−{ctx['market_step_pct']}%"}[c["market_price"]],
         "detail": f"±{ctx['market_step_pct']}% is the largest one-year price change observed in {br.location}; the data has no "
                   "year-on-year price decline, so Decrease is a stress test.",
         "enters": "Indicative revenue and profit only (price is not an optimiser objective)",
         "changed": c["market_price"] != "stable"},
        {"id": "land", "label": "Land", "baseline": f"{br.total_land_ha:g} ha", "scenario": f"{sr.total_land_ha:g} ha",
         "detail": "Hectares the optimiser allocates.", "enters": "NSGA-II problem",
         "changed": sr.total_land_ha != br.total_land_ha},
        {"id": "budget", "label": "Budget",
         "baseline": _fmt_money(br.budget_rs) if br.budget_rs else "No limit",
         "scenario": _fmt_money(sr.budget_rs) if sr.budget_rs else "No limit",
         "detail": "Hard cap on total production cost.", "enters": "NSGA-II budget constraint",
         "changed": sr.budget_rs != br.budget_rs},
        {"id": "weights", "label": "Optimisation priorities",
         "baseline": f"{br.preference} ({fmt_w(bw)})",
         "scenario": ("custom" if ctx["adjustments"].topsis_weights is not None else sr.preference) + f" ({fmt_w(sw)})",
         "detail": "TOPSIS weights for yield / cost / water / environmental impact.",
         "enters": "TOPSIS ranking of the Pareto front", "changed": [round(x, 4) for x in bw] != [round(x, 4) for x in sw]},
    ]
    return rows


def _share_tests(base: dict, scen: dict) -> Dict[str, dict]:
    """Per-crop land share across the paired seed runs."""
    crops = [m["crop"] for m in base["single_crop"]]
    out = {}
    for c in crops:
        test = _paired("yield", c, "%", [None if r is None else r["shares"].get(c, 0.0) for r in base["runs"]],
                       [None if r is None else r["shares"].get(c, 0.0) for r in scen["runs"]], 2)
        change = test["change"] or 0.0
        out[c] = {"baseline_mean_pct": test["baseline"], "scenario_mean_pct": test["scenario"], "change_pp": test["change"],
                  "p_value": test["p_value"], "baseline_range": test.get("baseline_range"),
                  "scenario_range": test.get("scenario_range"),
                  "reliable": test["p_value"] is not None and test["p_value"] < SIGNIFICANCE_P and abs(change) >= SHARE_SHIFT_PP}
    return out


def _comparison(base: dict, scen: dict, shares: Dict[str, dict]) -> dict:
    bmix = {c["crop"]: c["share_pct"] for c in base["crop_mix"]}
    smix = {c["crop"]: c["share_pct"] for c in scen["crop_mix"]}
    crops = sorted(set(bmix) | set(smix), key=lambda c: -max(bmix.get(c, 0), smix.get(c, 0)))
    rows = [{"crop": c, "baseline_share_pct": bmix.get(c, 0.0), "scenario_share_pct": smix.get(c, 0.0),
             "change_pp": round(smix.get(c, 0.0) - bmix.get(c, 0.0), 2),
             "ensemble": shares.get(c)} for c in crops]
    bt, st = base["top_plan"], scen["top_plan"]
    bconf, sconf = base["explanation"]["confidence"], scen["explanation"]["confidence"]
    return {
        "crop_shares": rows,
        "reliable_shifts": [c for c, t in shares.items() if t["reliable"]],
        "ranking": {"baseline": {"closeness": bt["composite_score"], "plans_ranked": base["meta"]["n_plans_returned"],
                                 "pareto_plans": base["meta"]["n_pareto_solutions_found"],
                                 "recommendation": base["explanation"]["summary"]["recommendation"],
                                 "trade_off": bt["trade_off_summary"]},
                    "scenario": {"closeness": st["composite_score"], "plans_ranked": scen["meta"]["n_plans_returned"],
                                 "pareto_plans": scen["meta"]["n_pareto_solutions_found"],
                                 "recommendation": scen["explanation"]["summary"]["recommendation"],
                                 "trade_off": st["trade_off_summary"]}},
        "confidence": {"baseline_pct": bconf["overall_pct"], "scenario_pct": sconf["overall_pct"],
                       "baseline_label": bt["confidence_label"], "scenario_label": st["confidence_label"],
                       "components": [{"id": b["id"], "label": b["label"], "baseline": b["score"], "scenario": s["score"]}
                                      for b, s in zip(bconf["components"], sconf["components"])]},
    }


def _impact(base: dict, scen: dict, land_changed: bool) -> dict:
    units = {"yield": ("t", "t/ha"), "cost": ("₹", "₹/ha"), "water": ("L", "L/ha"), "env": ("index", "index/ha")}
    col = lambda runs, key: [None if r is None else r[key] for r in runs]   # noqa: E731
    totals = [_paired(o, OBJECTIVE_LABEL[o], units[o][0], col(base["runs"], o), col(scen["runs"], o)) for o in OBJECTIVES]
    per_ha = [_paired(o, OBJECTIVE_LABEL[o], units[o][1], col(base["runs"], f"{o}_per_ha"), col(scen["runs"], f"{o}_per_ha"), 4)
              for o in OBJECTIVES]
    profit_key = "profit_per_ha" if land_changed else "profit"
    profit = _paired("profit", "Indicative profit", "₹/ha" if land_changed else "₹",
                     col(base["runs"], profit_key), col(scen["runs"], profit_key), 0)
    profit["note"] = ("Revenue = expected tonnes × the dataset's unvalidated price column; profit is not an optimiser "
                      "objective.")
    conf = _compare("confidence", "Recommendation confidence", "%", base["explanation"]["confidence"]["overall_pct"],
                    scen["explanation"]["confidence"]["overall_pct"], 1)
    conf["note"] = "Explanation-engine confidence of each side's recommended plan."
    headline = {m["id"]: m for m in (per_ha if land_changed else totals)}
    headline["profit"], headline["confidence"] = profit, conf
    variation = [{"id": m["id"], "label": m["label"],
                  "baseline_spread_pct": None if not m.get("baseline_range") or not m["baseline"] else
                  round((m["baseline_range"][1] - m["baseline_range"][0]) / abs(m["baseline"]) * 100, 1)}
                 for m in (per_ha if land_changed else totals)]
    return {"basis": "per_ha" if land_changed else "total",
            "basis_note": ("Land differs between the two sides, so headline figures are per hectare." if land_changed
                           else "Same land on both sides, so headline figures are plan totals."),
            "method": (f"Each side was optimised {len(ENSEMBLE_SEEDS)} times with the same seeds. Figures are means over "
                       f"those runs; a change counts as improved or worsened only if a paired t-test gives p < "
                       f"{SIGNIFICANCE_P} and it is at least {UNCHANGED_PCT:g}%. 'Within search variation' means the "
                       "optimiser's own run-to-run spread could explain it."),
            "totals": totals, "per_ha": per_ha, "profit": profit, "confidence": conf, "search_variation": variation,
            "headline": {k: {"label": v["label"], "change_pct": v["change_pct"], "verdict": v["verdict"],
                             "p_value": v.get("p_value")} for k, v in headline.items()}}


def _crop_effects(base: dict, scen: dict, shares: Dict[str, dict]) -> List[dict]:
    """Per-crop, per-hectare objective values at baseline inputs under each
    side's conditions (FarmPlanProblem.single_crop_metrics -- deterministic,
    no search involved), plus the land share the optimiser gave each crop
    (mean over the seed runs, with its paired test)."""
    sc = {m["crop"]: m for m in scen["single_crop"]}
    out = []
    for b in base["single_crop"]:
        s = sc.get(b["crop"])
        if s is None:
            continue
        t = shares.get(b["crop"], {})
        row = {"crop": b["crop"], "rainfall_dependency": b["rainfall_dependency"],
               "baseline_share_pct": t.get("baseline_mean_pct") or 0.0, "scenario_share_pct": t.get("scenario_mean_pct") or 0.0,
               "share_change_pp": t.get("change_pp") or 0.0, "share_p_value": t.get("p_value"),
               "share_shift_reliable": bool(t.get("reliable"))}
        for key, label in (("crop_confidence", "confidence"), ("yield_t_ha", "yield"), ("cost_rs_ha", "cost"),
                           ("water_l_ha", "water"), ("env_per_ha", "env")):
            row[label] = {"baseline": round(b[key], 4), "scenario": round(s[key], 4), "change_pct": _pct(b[key], s[key])}
        out.append(row)
    return sorted(out, key=lambda r: -max(r["baseline_share_pct"], r["scenario_share_pct"]))


def _fuzzy_changes(base: dict, scen: dict) -> dict:
    def inputs(side):
        rp = side["region_profile"]
        return (rp["rainfall"]["avg_deviation_percent"], rp["water"]["avg_storage_percent"], rp["soil"]["fertility_index"])
    bi, si = inputs(base), inputs(scen)
    brules = {r["rule"]: r for r in fz.fired_rules(*bi)}
    srules = {r["rule"]: r for r in fz.fired_rules(*si)}
    changed = []
    for n in sorted(set(brules) | set(srules)):
        b, s = brules.get(n), srules.get(n)
        bs, ss = (b or {}).get("strength", 0.0), (s or {}).get("strength", 0.0)
        if abs(ss - bs) < RULE_STRENGTH_CHANGE:
            continue
        r = b or s
        changed.append({"rule": n, "if": r["if"], "then": r["then"], "baseline_strength": bs, "scenario_strength": ss,
                        "status": "started firing" if not b else "stopped firing" if not s else
                        "stronger" if ss > bs else "weaker"})
    bf, sf = base["fuzzy_assessment"], scen["fuzzy_assessment"]
    names = ("rainfall_dev", "water_storage", "soil_fert")
    return {
        "inputs": [{"id": n, "baseline": round(b, 2), "scenario": round(s, 2),
                    "baseline_set": bf[k], "scenario_set": sf[k]}
                   for n, b, s, k in zip(names, bi, si, ("rainfall_label", "water_label", "soil_label"))],
        "memberships": {"baseline": fz.input_memberships(*bi), "scenario": fz.input_memberships(*si)},
        "outputs": [_compare("yield_confidence", "Yield confidence", "0-1", bf["yield_confidence"], sf["yield_confidence"], 3),
                    _compare("irrigation_risk", "Irrigation risk", "0-1", bf["irrigation_risk"], sf["irrigation_risk"], 3)],
        "rules_changed": changed,
        "rules_fired": {"baseline": len(brules), "scenario": len(srules)},
    }


def _optimization(base_runs: List[PipelineRun], scen_runs: List[PipelineRun], base: dict, scen: dict) -> dict:
    """Pareto fronts, TOPSIS weights and a decomposition of the change into
    'same plan, new conditions' and 're-optimised plan'."""
    def front_stats(side):
        if not side["front"]:
            return None
        return {o: {"best": (max if o == "yield" else min)(p[o] for p in side["front"]),
                    "worst": (min if o == "yield" else max)(p[o] for p in side["front"])} for o in OBJECTIVES}
    bw, sw = base["meta"]["topsis_weights"], scen["meta"]["topsis_weights"]
    out = {
        "pareto": {"baseline": {"size": len(base["front"]), "ranges_per_ha": front_stats(base)},
                   "scenario": {"size": len(scen["front"]), "ranges_per_ha": front_stats(scen)}},
        "weights": {"baseline": dict(zip(OBJECTIVES, bw)), "scenario": dict(zip(OBJECTIVES, sw)),
                    "baseline_dominant": OBJECTIVES[int(np.argmax(bw))], "scenario_dominant": OBJECTIVES[int(np.argmax(sw))]},
        "seeds": list(ENSEMBLE_SEEDS),
        "front_identical": [round(v, 6) for p in base["front"] for v in p.values()]
                           == [round(v, 6) for p in scen["front"] for v in p.values()],
        "seed_note": f"Each side was optimised with seeds {', '.join(map(str, ENSEMBLE_SEEDS))} (same population and "
                     "generations); the recommended plans shown are from the first seed, the one Run Optimization uses.",
    }
    if not (base["available"] and scen["available"]):
        return out
    bt, st = base["top_plan"], scen["top_plan"]
    out["contributions"] = {
        side: [{"objective": o, "weight": round(w[i], 4), "goodness": plan["normalized_scores"][o],
                "weighted": round(w[i] * plan["normalized_scores"][o], 4)} for i, o in enumerate(OBJECTIVES)]
        for side, plan, w in (("baseline", bt, bw), ("scenario", st, sw))
    }
    # Goodness of both recommended plans on a common scale: min-max over the
    # union of both feasible fronts (per hectare), the same normalisation TOPSIS uses.
    union = base["front"] + scen["front"] + [base["per_ha"], scen["per_ha"]]
    _, goodness = ranking.topsis_scores(*[[p[o] for p in union] for o in OBJECTIVES], np.full(4, 0.25))
    out["common_scale"] = {
        "baseline": {o: round(float(goodness[i][-2]), 3) for i, o in enumerate(OBJECTIVES)},
        "scenario": {o: round(float(goodness[i][-1]), 3) for i, o in enumerate(OBJECTIVES)},
        "note": "1 = best and 0 = worst per hectare across both Pareto fronts combined.",
    }
    # Per seed: the baseline top plan, the same plan evaluated under the
    # scenario's objective function, and the scenario's own top plan.
    triples = []
    for br_, sr_ in zip(base_runs, scen_runs):
        if br_.response["plans"] and sr_.response["plans"]:
            bp, sp = br_.response["plans"][0], sr_.response["plans"][0]
            triples.append((bp, _evaluate_plan(sr_, bp), sp))
    rows = []
    for o in OBJECTIVES:
        key = OBJECTIVE_KEY[o]
        cond = _paired(o, OBJECTIVE_LABEL[o], "", [t[0][key] for t in triples], [t[1][key] for t in triples], 4)
        reopt = _paired(o, OBJECTIVE_LABEL[o], "", [t[1][key] for t in triples], [t[2][key] for t in triples], 4)
        rows.append({"objective": o, "label": OBJECTIVE_LABEL[o], "baseline_plan": cond["baseline"],
                     "baseline_plan_in_scenario": cond["scenario"], "scenario_plan": reopt["scenario"],
                     "condition_effect_pct": cond["change_pct"], "condition_effect_verdict": cond["verdict"],
                     "reoptimisation_effect_pct": reopt["change_pct"], "reoptimisation_effect_verdict": reopt["verdict"],
                     "reoptimisation_p_value": reopt["p_value"]})
    out["decomposition"] = {
        "rows": rows, "runs": len(triples),
        "baseline_plan_feasible_in_scenario": _evaluate_plan(scen_runs[0], bt)["feasible"],
        "note": "Each baseline plan's decision variables re-evaluated with the scenario's objective function separate the "
                "effect of the new conditions on an unchanged plan (deterministic) from the effect of re-optimising "
                "(tested across the seed runs). Means over the paired runs.",
    }
    return out


def _constraints(base: dict, scen: dict, optimization: dict) -> List[dict]:
    rows = []
    bitems = {c["id"]: c for c in base["explanation"]["constraints"]["items"]} if base["available"] else {}
    sitems = {c["id"]: c for c in scen["explanation"]["constraints"]["items"]} if scen["available"] else {}
    order = {"satisfied": 0, "not_applicable": 0, "moderate": 1, "risk": 2, "violated": 3}
    for cid in bitems.keys() | sitems.keys():
        b, s = bitems.get(cid), sitems.get(cid)
        bs, ss = (b or {}).get("status"), (s or {}).get("status")
        rows.append({"id": cid, "label": (s or b)["title"], "baseline_status": bs, "scenario_status": ss,
                     "scenario_detail": (s or {}).get("detail"),
                     "became_harder": order.get(ss, 0) > order.get(bs, 0)})
    budget_rows = []
    for side_name, side in (("baseline", base), ("scenario", scen)):
        budget = side["meta"]["budget_rs"]
        if budget and side["available"]:
            budget_rows.append(round(side["top_plan"]["cost_rs"] / budget * 100, 1))
        else:
            budget_rows.append(None)
    if any(v is not None for v in budget_rows):
        rows.append({"id": "budget_use", "label": "Budget used by the recommended plan",
                     "baseline_status": None if budget_rows[0] is None else f"{budget_rows[0]}%",
                     "scenario_status": None if budget_rows[1] is None else f"{budget_rows[1]}%",
                     "scenario_detail": f"Binding when ≥ {BUDGET_TIGHT_PCT:.0f}% of the budget is used.",
                     "became_harder": budget_rows[1] is not None and budget_rows[1] >= BUDGET_TIGHT_PCT
                     and (budget_rows[0] is None or budget_rows[0] < BUDGET_TIGHT_PCT)})
    dec = optimization.get("decomposition")
    if dec and not dec["baseline_plan_feasible_in_scenario"]:
        rows.append({"id": "baseline_plan_infeasible", "label": "Baseline plan under scenario conditions",
                     "baseline_status": "satisfied", "scenario_status": "violated",
                     "scenario_detail": "The baseline recommendation would exceed the scenario budget.", "became_harder": True})
    if not scen["available"]:
        rows.append({"id": "no_feasible_plan", "label": "Feasible plans", "baseline_status": "satisfied",
                     "scenario_status": "violated", "scenario_detail": scen["reason"], "became_harder": True})
    return sorted(rows, key=lambda r: (not r["became_harder"], r["id"]))


def _historical(location: str, season: str, base: dict, scen: dict) -> dict:
    """Recommended crops against the district's observed cropping pattern
    (District Intelligence trends for this season)."""
    district = dsv.get_district_intelligence(location)
    if not district["crops"].get("available"):
        return {"available": False, "note": dsv.NOT_AVAILABLE}
    trends = {t["crop"]: t for t in district["crops"]["trends"] if t["season"] == season}
    candidates = [m["crop"] for m in base["single_crop"]]
    hist_total = sum(trends[c]["mean_area_share_pct"] for c in candidates if c in trends) or 1.0
    hist_share = {c: (trends[c]["mean_area_share_pct"] / hist_total * 100 if c in trends else 0.0) for c in candidates}

    def side_rows(side):
        if not side["available"]:
            return None, None
        breakdown = {d["crop"]: d for d in side["explanation"]["crop_breakdown"]}
        rows = []
        for c in side["crop_mix"]:
            t = trends.get(c["crop"])
            d = breakdown.get(c["crop"], {})
            rows.append({"crop": c["crop"], "plan_share_pct": c["share_pct"],
                         "historical_share_pct": round(hist_share.get(c["crop"], 0.0), 1),
                         "expected_yield_t_ha": d.get("expected_yield_t_ha"),
                         "historical_yield_t_ha": t["mean_yield_t_ha"] if t else None,
                         "historical_yield_trend": t["yield"]["direction"] if t else None,
                         "grown_historically": t is not None})
        shares = {c["crop"]: c["share_pct"] for c in side["crop_mix"]}
        overlap = sum(min(shares.get(c, 0.0), hist_share[c]) for c in candidates)
        return rows, round(overlap, 1)

    brows, bover = side_rows(base)
    srows, sover = side_rows(scen)
    return {"available": True, "years": district["coverage"]["observed_years"],
            "historical_shares": [{"crop": c, "share_pct": round(v, 1)} for c, v in
                                  sorted(hist_share.items(), key=lambda kv: -kv[1])],
            "baseline": brows, "scenario": srows,
            "alignment_pct": {"baseline": bover, "scenario": sover},
            "method": "Historical share = each candidate crop's mean share of the season's sown area in observed years, "
                      "rescaled over the candidate crops. Alignment = Σ min(plan share, historical share): 100% means the "
                      "plan mirrors the district's observed cropping pattern."}


# ---------------------------------------------------------------------------
# Generated statements
# ---------------------------------------------------------------------------

def _decision_impact(ctx: dict, conditions: List[dict], base: dict, scen: dict, crop_effects: List[dict],
                     fuzzy: dict, optimization: dict) -> List[dict]:
    items = []
    changed = [c for c in conditions if c["changed"]]
    only = changed[0]["id"] if len(changed) == 1 else None
    cause = (lambda cid: f"With only {next(c['label'] for c in conditions if c['id'] == cid).lower()} changed, ")  # noqa: E731
    brp, srp = base["region_profile"], scen["region_profile"]

    if any(c["id"] == "rainfall" and c["changed"] for c in conditions):
        er_b, er_s = brp["rainfall"]["effective_rainfall_mm"], srp["rainfall"]["effective_rainfall_mm"]
        moved = sorted((e for e in crop_effects if e["water"]["change_pct"]), key=lambda e: -abs(e["water"]["change_pct"]))
        detail = (f"Rainfall {ctx['controls']['rainfall_change_pct']:+d}% moved effective rainfall from {er_b:.0f} to {er_s:.0f} mm "
                  f"and the seasonal deviation from {brp['rainfall']['avg_deviation_percent']:+.1f}% to "
                  f"{srp['rainfall']['avg_deviation_percent']:+.1f}% (fuzzy set {fuzzy['inputs'][0]['baseline_set']} → "
                  f"{fuzzy['inputs'][0]['scenario_set']}).")
        if moved:
            m = moved[0]
            detail += (f" {m['crop']}'s irrigation need per hectare changed {m['water']['change_pct']:+.1f}% "
                       f"({m['water']['baseline']:,.0f} → {m['water']['scenario']:,.0f} L/ha).")
        items.append(make_item("rainfall", "Rainfall changed crop water needs", detail, "preprocessing + fuzzy",
                               {"effective_rainfall_mm": [er_b, er_s]}))
    if any(c["id"] == "water" and c["changed"] for c in conditions):
        risk = fuzzy["outputs"][1]
        items.append(make_item("water", "Water availability changed the irrigation risk",
                               f"Storage {brp['water']['avg_storage_percent']:.1f}% → {srp['water']['avg_storage_percent']:.1f}% "
                               f"(fuzzy set {fuzzy['inputs'][1]['baseline_set']} → {fuzzy['inputs'][1]['scenario_set']}); "
                               f"irrigation risk {risk['baseline']} → {risk['scenario']}.", "fuzzy",
                               {"storage_pct": [brp['water']['avg_storage_percent'], srp['water']['avg_storage_percent']]}))
    conf_moves = sorted((e for e in crop_effects if e["confidence"]["change_pct"] and abs(e["confidence"]["change_pct"]) >= UNCHANGED_PCT),
                        key=lambda e: e["confidence"]["change_pct"])
    if conf_moves:
        by_size = sorted(conf_moves, key=lambda e: -abs(e["confidence"]["change_pct"]))
        most, least = by_size[0], by_size[-1]

        def fmt(e):
            return (f"{e['crop']} {e['confidence']['baseline']:.3f} → {e['confidence']['scenario']:.3f} "
                    f"({e['confidence']['change_pct']:+.1f}%; rainfall dependency {e['rainfall_dependency']})")
        text = f"most affected {fmt(most)}" + (f"; least affected {fmt(least)}" if least is not most else "")
        items.append(make_item("crop-confidence", "Crop suitability (fuzzy confidence) changed",
                               "Per-crop yield confidence scales expected yield in the optimiser: " + text + ".", "fuzzy",
                               {"changes": {e["crop"]: e["confidence"]["change_pct"] for e in conf_moves}}))
    if any(c["id"] == "fertilizer" and c["changed"] for c in conditions):
        moved = sorted((e for e in crop_effects if e["cost"]["change_pct"]), key=lambda e: -abs(e["cost"]["change_pct"]))
        if moved:
            m, l = moved[0], moved[-1]
            items.append(make_item("fertilizer", "Fertiliser prices changed crop costs unevenly",
                                   f"Fertiliser {ctx['controls']['fertilizer_cost_change_pct']:+d}% changed cost per hectare most for "
                                   f"{m['crop']} ({m['cost']['change_pct']:+.1f}%) and least for {l['crop']} "
                                   f"({l['cost']['change_pct']:+.1f}%), because fertiliser is a different share of each crop's cost.",
                                   "NSGA-II cost objective", {e["crop"]: e["cost"]["change_pct"] for e in moved}))
    if any(c["id"] == "weights" and c["changed"] for c in conditions):
        w = optimization["weights"]
        items.append(make_item("weights", "Priorities changed how TOPSIS picks from the Pareto front",
                               f"The dominant TOPSIS weight moved from {OBJECTIVE_LABEL[w['baseline_dominant']].lower()} "
                               f"({w['baseline'][w['baseline_dominant']]:.2f}) to {OBJECTIVE_LABEL[w['scenario_dominant']].lower()} "
                               f"({w['scenario'][w['scenario_dominant']]:.2f}). NSGA-II itself has no weights; they decide which "
                               "Pareto plan is recommended.", "TOPSIS", {"baseline": w["baseline"], "scenario": w["scenario"]}))
    if any(c["id"] == "market" and c["changed"] for c in conditions):
        items.append(make_item("market", "Market price changes profit, not the plan",
                               f"Prices {'+' if ctx['controls']['market_price'] == 'increase' else '−'}{ctx['market_step_pct']}% "
                               "change the indicative revenue and profit only; price is not an optimiser objective, so on its "
                               "own it leaves the recommended plan unchanged.", "economics", {"price_factor": round(ctx["price_factor"], 4)}))
    if not scen["available"]:
        items.append(make_item("infeasible", "No feasible plan under the scenario", scen["reason"], "NSGA-II constraint", {}))
        return items

    shifts = sorted((e for e in crop_effects if e["share_shift_reliable"]), key=lambda e: -abs(e["share_change_pp"]))
    noisy = [e for e in crop_effects if abs(e["share_change_pp"]) >= SHARE_SHIFT_PP and not e["share_shift_reliable"]]
    for e in shifts[:3]:
        verb = "gained" if e["share_change_pp"] > 0 else "lost"
        lead = cause(only) if only else ""
        facts = []
        for m, label in (("water", "irrigation need"), ("cost", "cost"), ("confidence", "confidence")):
            p = e[m]["change_pct"]
            if p is not None and abs(p) >= UNCHANGED_PCT:
                facts.append(f"{label} {p:+.1f}%/ha")
        if facts:
            tail = f" Under the scenario its {', '.join(facts)}."
        elif only == "weights":
            tail = (" Its per-hectare values are unchanged; the Pareto front is the same, and the new weights select a "
                    "different plan from it.")
        else:
            tail = " Its own per-hectare values did not change; the shift follows the other crops' changes."
        rival = next((r for r in shifts if r["share_change_pp"] < 0), None)
        if e["share_change_pp"] > 0 and rival is not None and facts:
            better = [label for m, label in (("water", "irrigation need"), ("cost", "cost"), ("confidence", "confidence"))
                      if e[m]["change_pct"] is not None and rival[m]["change_pct"] is not None
                      and abs(e[m]["change_pct"] - rival[m]["change_pct"]) >= UNCHANGED_PCT
                      and (e[m]["change_pct"] > rival[m]["change_pct"]) == (m == "confidence")]
            if better:
                tail += f" It fared better than {rival['crop']} on " + ", ".join(better) + "."
        items.append(make_item(f"shift-{e['crop'].lower()}", f"{e['crop']} {verb} land",
                               f"{lead}the optimiser moved {e['crop']} from {e['baseline_share_pct']:.1f}% to "
                               f"{e['scenario_share_pct']:.1f}% of the land on average over {len(ENSEMBLE_SEEDS)} runs "
                               f"({e['share_change_pp']:+.1f} pp, p = {e['share_p_value']:.3f}).{tail}",
                               "NSGA-II + TOPSIS", {"share_pct": [e["baseline_share_pct"], e["scenario_share_pct"]],
                                                    "p_value": e["share_p_value"]}))
    if not shifts:
        items.append(make_item("same-mix", "No reliable change in the crop mix",
                               f"No crop's average share moved by {SHARE_SHIFT_PP:.0f} percentage points or more with "
                               f"p < {SIGNIFICANCE_P} across {len(ENSEMBLE_SEEDS)} runs.", "NSGA-II + TOPSIS", {}))
    if noisy:
        items.append(make_item("search-variation", "Some shifts are within search variation",
                               ", ".join(f"{e['crop']} {e['share_change_pp']:+.1f} pp (p = {e['share_p_value']:.2f})" for e in noisy)
                               + ". These moves are not consistent across the seed runs, so the optimiser's own randomness "
                                 "could explain them; they are not attributed to the scenario.", "NSGA-II",
                               {e["crop"]: e["share_p_value"] for e in noisy}))
    dec = optimization.get("decomposition")
    if dec:
        water = next(r for r in dec["rows"] if r["objective"] == "water")
        if water["condition_effect_pct"] is not None and abs(water["condition_effect_pct"]) >= UNCHANGED_PCT:
            reopt = ("re-optimising changes it a further "
                     f"{(water['reoptimisation_effect_pct'] or 0):+.1f}%" if water["reoptimisation_effect_verdict"] in ("improved", "worsened")
                     else "re-optimising does not change it reliably")
            items.append(make_item("carry-over", "The baseline plan under the new conditions",
                                   f"Kept unchanged, the baseline plan's irrigation water would change "
                                   f"{water['condition_effect_pct']:+.1f}%; {reopt}.", "objective function",
                                   {r["objective"]: [r["condition_effect_pct"], r["reoptimisation_effect_pct"]] for r in dec["rows"]}))
    return items


def _trade_offs(impact: Optional[dict], constraints: List[dict], fuzzy: dict, optimization: dict) -> dict:
    out = {"improved": [], "worsened": [], "unchanged": [], "not_significant": [], "harder_constraints": [c["label"] for c in constraints if c["became_harder"]],
           "fuzzy_rules_changed": len(fuzzy["rules_changed"]),
           "dominant_objective": {"baseline": optimization["weights"]["baseline_dominant"],
                                  "scenario": optimization["weights"]["scenario_dominant"]}}
    if impact is None:
        return out
    metrics = (impact["per_ha"] if impact["basis"] == "per_ha" else impact["totals"]) + [impact["profit"], impact["confidence"]]
    for m in metrics:
        if m["verdict"] in ("improved", "worsened", "unchanged", "not_significant"):
            out[m["verdict"]].append({"id": m["id"], "label": m["label"], "change_pct": m["change_pct"]})
    return out


def _summary(ctx: dict, conditions: List[dict], base: dict, scen: dict, impact: Optional[dict], trade: dict,
             historical: dict, shares: Dict[str, dict]) -> dict:
    changed = [c for c in conditions if c["changed"]]
    s = []
    br = ctx["base_request"]
    if not changed:
        s.append(f"No condition was changed, so the scenario reproduces the baseline recommendation for {br.location} "
                 f"{br.season}.")
    else:
        s.append("Scenario for " + f"{br.location} {br.season}: " + "; ".join(f"{c['label'].lower()} {c['scenario']}" for c in changed) + ".")
    if not scen["available"]:
        s.append(scen["reason"] + " Relax the budget or land to obtain a plan.")
        return {"sentences": s, "text": " ".join(s)}
    bmix = ", ".join(f"{c['crop']} {c['share_pct']:.0f}%" for c in base["crop_mix"])
    smix = ", ".join(f"{c['crop']} {c['share_pct']:.0f}%" for c in scen["crop_mix"])
    reliable = [c for c, t in shares.items() if t["reliable"]]
    if bmix == smix:
        s.append(f"The recommended mix stays {smix}.")
    else:
        s.append(f"The recommended plan moved from {bmix} to {smix}; "
                 + (f"across {len(ENSEMBLE_SEEDS)} runs the shift is consistent for {', '.join(reliable)}." if reliable
                    else f"across {len(ENSEMBLE_SEEDS)} runs the crop-mix change is within search variation."))
    h = impact["headline"]
    parts = [f"{h[k]['label'].lower()} {h[k]['change_pct']:+.1f}%" for k in ("yield", "cost", "water", "env", "profit")
             if h.get(k) and h[k]["verdict"] in ("improved", "worsened")]
    if parts:
        text = ("Per hectare, " if impact["basis"] == "per_ha" else "") + ", ".join(parts) + f" (mean of {len(ENSEMBLE_SEEDS)} runs)."
        s.append(text[0].upper() + text[1:])
    if trade["not_significant"]:
        s.append("Within the optimiser's run-to-run variation (not attributed to the scenario): "
                 + ", ".join(m["label"].lower() for m in trade["not_significant"]) + ".")
    conf = impact["confidence"]
    s.append(f"Recommendation confidence {conf['baseline']}% → {conf['scenario']}%.")
    if trade["harder_constraints"]:
        s.append("Harder under the scenario: " + ", ".join(trade["harder_constraints"]).lower() + ".")
    if historical.get("available") and historical["alignment_pct"]["scenario"] is not None:
        s.append(f"Alignment with the district's observed cropping pattern: {historical['alignment_pct']['baseline']}% → "
                 f"{historical['alignment_pct']['scenario']}%.")
    return {"sentences": s, "text": " ".join(s)}


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def simulate(request: dict) -> dict:
    """Run baseline and scenario through the full pipeline and analyse them."""
    t0 = time.time()
    ctx = resolve(request)
    # The first seed's run is the displayed recommendation: it tracks the
    # convergence history like a saved Run Optimization run, so its
    # explanation (including the convergence confidence component) matches.
    base_runs = [run_pipeline(ctx["base_request"], PipelineAdjustments(), track_history=(i == 0), seed=seed)
                 for i, seed in enumerate(ENSEMBLE_SEEDS)]
    if not base_runs[0].response["plans"]:
        raise SimulationError("The baseline conditions have no feasible plan; increase the baseline budget or land.")
    scen_runs = [run_pipeline(ctx["scenario_request"], ctx["adjustments"], track_history=(i == 0), seed=seed)
                 for i, seed in enumerate(ENSEMBLE_SEEDS)]
    base = _side(base_runs, 1.0)
    scen = _side(scen_runs, ctx["price_factor"])
    shares = _share_tests(base, scen)

    conditions = _conditions(ctx, base, scen)
    br, sr = ctx["base_request"], ctx["scenario_request"]
    impact = _impact(base, scen, sr.total_land_ha != br.total_land_ha) if scen["available"] else None
    crop_effects = _crop_effects(base, scen, shares)
    fuzzy = _fuzzy_changes(base, scen)
    optimization = _optimization(base_runs, scen_runs, base, scen)
    constraints = _constraints(base, scen, optimization)
    historical = _historical(br.location, br.season, base, scen)
    decision = _decision_impact(ctx, conditions, base, scen, crop_effects, fuzzy, optimization)
    trade = _trade_offs(impact, constraints, fuzzy, optimization)
    for side in (base, scen):
        side.pop("front")   # per-plan front values were only needed for the analysis above
        for r in side["runs"]:
            if r is not None:
                r["shares"] = {c: v for c, v in r["shares"].items() if v >= es.MIN_SHARE_PCT}
    summary = _summary(ctx, conditions, base, scen, impact, trade, historical, shares)

    return {
        "inputs": {"base": request["base"], "scenario": request.get("scenario") or {}, "changes": [
            {"id": c["id"], "label": c["label"], "scenario": c["scenario"]} for c in conditions if c["changed"]]},
        "conditions": conditions,
        "baseline": base,
        "scenario": scen,
        "comparison": _comparison(base, scen, shares) if scen["available"] else None,
        "impact": impact,
        "crop_effects": crop_effects,
        "fuzzy_changes": fuzzy,
        "optimization": optimization,
        "constraints": constraints,
        "historical": historical,
        "decision_impact": decision,
        "trade_offs": trade,
        "summary": {**summary, "year": base["region_profile"]["year"],
                    "data_year_estimated": base["region_profile"]["data_year_estimated"]},
        "meta": {"pipeline": ["preprocessing", "fuzzy", "NSGA-II", "TOPSIS", "explanation", "scenario analysis"],
                 "runs_per_side": len(ENSEMBLE_SEEDS), "seeds": list(ENSEMBLE_SEEDS),
                 "significance_p": SIGNIFICANCE_P, "seconds": round(time.time() - t0, 2), "cached": False},
    }


# Unsaved results, so "Save" stores exactly what the user saw without re-running.
_PENDING: "OrderedDict[str, Tuple[Optional[str], dict]]" = OrderedDict()
_PENDING_LOCK = threading.Lock()


def remember(result: dict, client_id: Optional[str]) -> str:
    token = secrets.token_urlsafe(16)
    with _PENDING_LOCK:
        _PENDING[token] = (client_id, result)
        while len(_PENDING) > PENDING_LIMIT:
            _PENDING.popitem(last=False)
    return token


def pending(token: str, client_id: Optional[str]) -> Optional[dict]:
    with _PENDING_LOCK:
        entry = _PENDING.get(token)
    if entry is None or entry[0] != client_id:
        return None
    return entry[1]

