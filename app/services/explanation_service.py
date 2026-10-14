"""
Explainable Recommendation Engine.

Turns one ranked plan plus the context it was chosen from into a
structured explanation: why it was recommended, how the four objectives
were balanced, what was traded off against the alternatives, which
constraints hold, benefits, risks, historical context, a decomposed
confidence score, and a trace of the pipeline that produced it.

Design rules
------------
* Every statement is computed from data the pipeline already produced
  (region profile, fuzzy assessment, the ranked Pareto set, convergence
  history, request constraints) or from data/raw/*.csv. Nothing is
  hard-coded per crop, district or plan.
* Every item carries `evidence` (the numbers behind it) and `source`
  (which stage produced them), so any sentence can be traced back.
* Thresholds that turn numbers into wording are named constants below and
  documented in docs/handbook/EXPLAINABILITY.md.
* The frontend only renders the returned JSON; it composes no reasoning.

Two entry points build the same `ExplanationContext`:
    context_from_saved_run(record, rank)            -> saved runs (Run, History, Reports)
    context_from_comparison(location, plan, ...)    -> Comparison page plans A/B/C
and `explain(context)` produces the explanation dict.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from app import config
from app.data import preprocessing as pp
from app.data.loader import load_all
from app.decision import ranking
from app.fuzzy import engine as fz

# ---------------------------------------------------------------------------
# Wording thresholds (documented in EXPLAINABILITY.md). They only decide
# which computed facts are worth stating; they never change a number.
# ---------------------------------------------------------------------------
STRONG_GOODNESS = 0.60        # objective counted as a strength (0-1 TOPSIS goodness)
WEAK_GOODNESS = 0.30          # objective counted as a weakness
MIN_SHARE_PCT = 1.0           # crops below this land share are not discussed individually
DIVERSIFIED_SHARE_PCT = 5.0   # a crop "counts" toward diversification at >= 5 % of land
CONCENTRATION_HHI = 0.50      # Herfindahl index >= 0.5 ~ effectively fewer than 2 crops
PERENNIAL_DAYS = 300          # crop duration treated as perennial / multi-season
INPUT_FLOOR_TOLERANCE = 0.02  # multiplier within this of its lower bound = "at the floor"
HISTORICAL_TOP_N = 3          # "top crops" by district revenue
HISTORICAL_HIT_RATE = 0.75    # top-N in at least 75 % of observed years = historically established
PRICE_SHOCK = 0.10            # price-sensitivity scenario (10 %)
ROBUST_TOP_FRACTION = 0.10    # "stays near the top" = within the top 10 % of the set
CONSISTENCY_TOLERANCE = 0.01  # recomputed vs reported objective (relative)

OBJECTIVE_META = {
    "yield": {"label": "Yield", "unit": "t/ha", "better": "higher", "key": "yield_tonnes", "scale": 1.0, "strength": "High yield"},
    "cost": {"label": "Cost", "unit": "₹/ha", "better": "lower", "key": "cost_rs", "scale": 1.0, "strength": "Low cost"},
    "water": {"label": "Irrigation water", "unit": "ML/ha", "better": "lower", "key": "water_liters", "scale": 1e-6,
              "strength": "Low water use"},
    "env": {"label": "Environmental impact", "unit": "index/ha", "better": "lower", "key": "env_impact_score", "scale": 1.0,
            "strength": "Low environmental impact"},
}
PREFERENCES = ["balanced", "max_yield", "min_cost", "min_water", "min_env_impact"]


@dataclass
class ExplanationContext:
    region_profile: dict
    fuzzy: dict
    plans: List[dict]                    # ranked plans, rank order (RankedPlanOut-shaped dicts)
    plan_index: int
    preference: str
    total_land_ha: Optional[float]
    budget_rs: Optional[float]
    budget_recorded: bool                # False for runs saved before budgets were stored
    convergence_history: List[dict] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    subject: dict = field(default_factory=dict)   # what is being explained (run id / plan key)


# ---------------------------------------------------------------------------
# Context builders
# ---------------------------------------------------------------------------

def context_from_saved_run(record: dict, rank: int = 1) -> ExplanationContext:
    plans = record.get("plans") or []
    if not plans:
        raise ValueError("This run has no feasible plans to explain.")
    if not 1 <= rank <= len(plans):
        raise ValueError(f"rank must be between 1 and {len(plans)} for this run.")
    meta = record.get("meta") or {}
    land = meta.get("total_land_ha")
    budget_recorded = "budget_rs" in meta
    return ExplanationContext(
        region_profile=record["region_profile"],
        fuzzy=record["fuzzy_assessment"],
        plans=plans,
        plan_index=rank - 1,
        preference=meta.get("preference") or "balanced",
        total_land_ha=float(land) if land else float(sum(plans[0]["area_ha"])),
        budget_rs=meta.get("budget_rs"),
        budget_recorded=budget_recorded,
        convergence_history=record.get("convergence_history") or [],
        meta=meta,
        subject={"kind": "saved_run", "run_id": record.get("run_id"), "rank": rank},
    )


_COMPARISON_PLANS = {"A": ("balanced", "Plan A -- Balanced"),
                     "B": ("max_yield", "Plan B -- Max Yield"),
                     "C": ("min_cost", "Plan C -- Lowest Cost")}


def context_from_comparison(location: str, plan_key: str, total_land_ha: float = 5.0,
                            budget_rs: Optional[float] = None) -> ExplanationContext:
    """Rebuilds exactly the front GET /api/comparison uses (same memoised
    run; history tracking does not change the front) and ranks it under the
    preference that selects the requested plan."""
    from app.services import dashboard_service as ds
    from app.services.plan_service import region_profile_payload

    plan_key = plan_key.upper()
    if plan_key not in _COMPARISON_PLANS:
        raise ValueError("plan must be one of A, B, C.")
    preference, name = _COMPARISON_PLANS[plan_key]
    profile, assessment, raw_plans, conf_map, history = ds._run_dashboard_pareto_front(
        location, total_land_ha=total_land_ha, budget_rs=budget_rs, track_history=True
    )
    if not raw_plans:
        raise ValueError(f"No feasible plans found for {profile.location}.")
    ranked = ranking.to_dict_list(
        ranking.rank_plans(raw_plans, conf_map, preference=preference, max_plans=len(raw_plans))
    )
    return ExplanationContext(
        region_profile=region_profile_payload(profile),
        fuzzy=vars(assessment),
        plans=ranked,
        plan_index=0,
        preference=preference,
        total_land_ha=float(total_land_ha),
        budget_rs=budget_rs,
        budget_recorded=True,
        convergence_history=history,
        meta={"algorithm": "NSGA-II", "pop_size": ds._DEMO_POP_SIZE, "n_gen": config.NSGA2_N_GEN,
              "crossover_prob": config.NSGA2_CROSSOVER_PROB, "mutation_prob": config.NSGA2_MUTATION_PROB,
              "preference": preference, "n_pareto_solutions_found": len(raw_plans),
              "n_plans_returned": len(ranked)},
        subject={"kind": "comparison", "location": profile.location, "plan": plan_key, "name": name},
    )


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _per_ha(plan: dict, objective: str) -> float:
    meta = OBJECTIVE_META[objective]
    area = sum(plan["area_ha"]) or 1.0
    return plan[meta["key"]] / area * meta["scale"]


def _fmt(objective: str, value: float) -> str:
    if objective == "cost":
        return f"₹{value:,.0f}/ha"
    if objective == "yield":
        return f"{value:.2f} t/ha"
    if objective == "water":
        return f"{value:.2f} ML/ha"
    return f"{value:.2f}/ha"


def _signed_pct(value: Optional[float]) -> str:
    if value is None:
        return ""
    return f"{'+' if value >= 0 else '−'}{abs(value):.0f}%"


def _pct_diff(a: float, b: float) -> Optional[float]:
    """(a - b) / b in percent, None when b is 0."""
    return None if abs(b) < 1e-12 else (a - b) / abs(b) * 100


def _better_than_share(values: List[float], value: float, higher_is_better: bool) -> float:
    """Share (0-100) of OTHER plans this value is at least as good as."""
    others = len(values) - 1
    if others <= 0:
        return 100.0
    at_least = sum(1 for v in values if (value >= v if higher_is_better else value <= v)) - 1
    return round(100.0 * at_least / others, 1)


def make_item(id_: str, title: str, detail: str, source: str, evidence: dict, **extra) -> dict:
    """One traceable statement: generated `detail` text plus the `evidence`
    it was built from and the pipeline stage (`source`) that produced it.
    Shared by the explanation and district-intelligence services."""
    out = {"id": id_, "title": title, "detail": detail, "source": source, "evidence": evidence}
    out.update(extra)
    return out


def _season_months(season: str) -> List[str]:
    return list(config.SEASON_MONTH_MAP[season])




# ---------------------------------------------------------------------------
# Analysis blocks
# ---------------------------------------------------------------------------

def _crop_breakdown(ctx: ExplanationContext, plan: dict) -> dict:
    """Per-crop contribution, recomputed from the region profile and fuzzy
    assessment exactly as FarmPlanProblem._evaluate does, plus a
    consistency check against the plan's reported totals."""
    rp, fzd = ctx.region_profile, ctx.fuzzy
    crops = {c["name"]: c for c in rp["candidate_crops"]}
    eff_rain = rp["rainfall"]["effective_rainfall_mm"]
    crop_df = load_all()["crop"]
    rows = crop_df[(crop_df["Location"] == rp["location"]) & (crop_df["Year"] == rp["year"])
                   & (crop_df["Season"] == rp["season"])].set_index("Crop_Name")

    details, tonnes_total, water_total = [], 0.0, 0.0
    revenue_total, revenue_known = 0.0, True
    for name, share, area, irr, fert in zip(plan["crop_names"], plan["allocation_percent"], plan["area_ha"],
                                            plan["irrigation_multiplier"], plan["fertilizer_multiplier"]):
        c = crops.get(name)
        if c is None:
            continue
        conf = fz.crop_yield_confidence(fzd["yield_confidence"], fzd["irrigation_risk"], c["rainfall_dependency"])
        tonnes = area * c["yield_kg_ha"] / 1000 * conf
        net_mm = max(c["water_req_mm"] - eff_rain, 0.0)
        water = area * irr * net_mm * config.LITERS_PER_MM_PER_HA
        tonnes_total += tonnes
        water_total += water
        msp = float(rows.loc[name, "MSP_Rs_Qtl"]) if name in rows.index else None
        revenue = tonnes * 10 * msp if msp is not None else None   # 1 t = 10 quintals
        if revenue is None:
            revenue_known = False
        else:
            revenue_total += revenue
        details.append({
            "crop": name, "share_pct": round(share, 2), "area_ha": round(area, 3),
            "book_yield_t_ha": round(c["yield_kg_ha"] / 1000, 2), "crop_confidence": round(conf, 3),
            "expected_yield_t_ha": round(c["yield_kg_ha"] / 1000 * conf, 2), "expected_tonnes": round(tonnes, 2),
            "water_req_mm": c["water_req_mm"], "net_irrigation_mm": round(net_mm, 1),
            "irrigation_multiplier": round(irr, 3), "fertilizer_multiplier": round(fert, 3),
            "rainfall_dependency": c["rainfall_dependency"], "irrigation_type": c["irrigation_type"],
            "duration_days": c["crop_duration_days"], "msp_rs_qtl": msp,
            "indicative_revenue_rs": round(revenue, 0) if revenue is not None else None,
        })
    for d in details:
        d["tonnage_share_pct"] = round(100 * d["expected_tonnes"] / tonnes_total, 1) if tonnes_total else 0.0

    def check(reported, recomputed):
        rel = abs(recomputed - reported) / max(abs(reported), 1e-9)
        return {"reported": reported, "recomputed": round(recomputed, 3), "relative_difference": round(rel, 5),
                "consistent": rel <= CONSISTENCY_TOLERANCE}

    return {
        "crops": details,
        "shown": [d for d in details if d["share_pct"] >= MIN_SHARE_PCT],
        "consistency": {"yield_tonnes": check(plan["yield_tonnes"], tonnes_total),
                        "water_liters": check(plan["water_liters"], water_total)},
        "revenue_rs": round(revenue_total, 0) if revenue_known and details else None,
    }


def _objective_analysis(ctx: ExplanationContext, plan: dict) -> dict:
    plans = ctx.plans
    w = ranking.preference_weights(ctx.preference)
    goodness = plan["normalized_scores"]
    gaps = {k: (w[i] * (1 - goodness[k])) ** 2 for i, k in enumerate(ranking.OBJECTIVES)}
    gap_total = sum(gaps.values()) or 1.0
    rows = []
    for i, k in enumerate(ranking.OBJECTIVES):
        meta = OBJECTIVE_META[k]
        values = [_per_ha(p, k) for p in plans]
        v = _per_ha(plan, k)
        hib = meta["better"] == "higher"
        rows.append({
            "objective": k, "label": meta["label"], "unit": meta["unit"], "better": meta["better"],
            "value_per_ha": round(v, 4 if k == "water" else 2), "value_total": plan[meta["key"]],
            "goodness": goodness[k], "weight": round(float(w[i]), 3),
            "better_than_pct_of_plans": _better_than_share(values, v, hib),
            "set_best": round(max(values) if hib else min(values), 2),
            "set_median": round(float(np.median(values)), 2),
            "set_worst": round(min(values) if hib else max(values), 2),
            "share_of_gap_to_ideal_pct": round(100 * gaps[k] / gap_total, 1),
        })
    strongest = max(rows, key=lambda r: (r["goodness"], r["weight"]))
    compromise = max(rows, key=lambda r: r["share_of_gap_to_ideal_pct"])
    return {"objectives": rows, "strongest": strongest["objective"], "compromise": compromise["objective"],
            "weights_source": f"TOPSIS weights for the '{ctx.preference}' preference (app/decision/ranking.py)"}


def _rank_under_all_preferences(ctx: ExplanationContext) -> Dict[str, int]:
    plans = ctx.plans
    cols = [[p[OBJECTIVE_META[k]["key"]] for p in plans] for k in ranking.OBJECTIVES]
    out = {}
    for pref in PREFERENCES:
        closeness, _ = ranking.topsis_scores(*cols, ranking.preference_weights(pref))
        order = np.argsort(-closeness, kind="stable")
        out[pref] = int(np.where(order == ctx.plan_index)[0][0]) + 1
    return out


def _trade_offs(ctx: ExplanationContext, plan: dict) -> dict:
    plans, idx = ctx.plans, ctx.plan_index
    items = []
    for k in ranking.OBJECTIVES:
        hib = OBJECTIVE_META[k]["better"] == "higher"
        values = [_per_ha(p, k) for p in plans]
        champ = int(np.argmax(values) if hib else np.argmin(values))
        if champ == idx or abs(values[champ] - values[idx]) < 1e-9:
            continue
        other = plans[champ]
        deltas = {}
        for j in ranking.OBJECTIVES:
            a, b = _per_ha(other, j), _per_ha(plan, j)
            deltas[j] = {"this_plan": round(b, 4), "alternative": round(a, 4), "difference": round(a - b, 4),
                         "difference_pct": None if _pct_diff(a, b) is None else round(_pct_diff(a, b), 1)}
        gain = deltas[k]
        costs = []
        for j in ranking.OBJECTIVES:
            if j == k:
                continue
            d = deltas[j]["difference"]
            worse = (d < 0) if OBJECTIVE_META[j]["better"] == "higher" else (d > 0)
            if worse and abs(d) > 1e-9:
                pct = deltas[j]["difference_pct"]
                costs.append(f"{OBJECTIVE_META[j]['label'].lower()} {'+' if d > 0 else '−'}{_fmt(j, abs(d))}"
                             + (f" ({_signed_pct(pct)})" if pct is not None else ""))
        pct = gain["difference_pct"]
        verb = "higher" if hib else "lower"
        detail = (f"The plan with the best {OBJECTIVE_META[k]['label'].lower()} in this set (rank #{other['rank']}) "
                  f"is {_fmt(k, abs(gain['difference']))} {verb}"
                  + (f" ({abs(pct):.0f}%)" if pct is not None else "")
                  + (", but it would change " + ", ".join(costs) + "." if costs
                     else ", and is no worse on the other objectives -- it ranked lower only because of the preference weights."))
        items.append(make_item(f"tradeoff-{k}", f"Giving up some {OBJECTIVE_META[k]['label'].lower()}", detail, "nsga2+topsis",
                           {"alternative_rank": other["rank"], "deltas_per_ha": deltas}))

    rates = []
    ys = np.array([_per_ha(p, "yield") for p in plans])
    for k in ("cost", "water"):
        xs = np.array([_per_ha(p, k) for p in plans])
        if len(plans) >= 3 and ys.std() > 1e-9 and xs.std() > 1e-9:
            slope = float(np.polyfit(ys, xs, 1)[0])
            r = float(np.corrcoef(ys, xs)[0, 1])
            rates.append({"objective": k, "per_extra_t_ha": round(slope, 4 if k == "water" else 0),
                          "unit": OBJECTIVE_META[k]["unit"], "correlation_with_yield": round(r, 2),
                          "detail": (f"Across the {len(plans)} plans, each extra 1 t/ha of yield is associated with "
                                     f"{'+' if slope >= 0 else '−'}{_fmt(k, abs(slope))} (correlation r = {r:.2f}).")})
    return {"items": items, "marginal_rates": rates}


def _constraints(ctx: ExplanationContext, plan: dict, crops: dict) -> dict:
    rp, fzd = ctx.region_profile, ctx.fuzzy
    items = []
    area = sum(plan["area_ha"])
    land = ctx.total_land_ha or area
    alloc = sum(plan["allocation_percent"])
    ok = abs(area - land) <= max(0.01, 0.002 * land)
    items.append(make_item("land", "Land", f"{area:.2f} ha allocated of {land:.2f} ha available (shares sum to {alloc:.2f}%).",
                       "nsga2 repair", {"allocated_ha": round(area, 3), "available_ha": land, "share_sum_pct": round(alloc, 2)},
                       status="satisfied" if ok else "violated"))

    cost = plan["cost_rs"]
    if not ctx.budget_recorded:
        items.append(make_item("budget", "Budget", "This run was saved before budgets were recorded, so the budget check cannot be shown.",
                           "run metadata", {"cost_rs": cost}, status="unknown"))
    elif ctx.budget_rs:
        head = (ctx.budget_rs - cost) / ctx.budget_rs * 100
        items.append(make_item("budget", "Budget",
                           f"Cost ₹{cost:,.0f} is {'within' if cost <= ctx.budget_rs else 'over'} the ₹{ctx.budget_rs:,.0f} budget "
                           f"({abs(head):.1f}% {'headroom' if head >= 0 else 'over'}).", "nsga2 constraint",
                           {"cost_rs": cost, "budget_rs": ctx.budget_rs, "headroom_pct": round(head, 1)},
                           status="satisfied" if cost <= ctx.budget_rs + 1e-6 else "violated"))
    else:
        items.append(make_item("budget", "Budget", f"No budget limit was set; the plan costs ₹{cost:,.0f}.", "request",
                           {"cost_rs": cost, "budget_rs": None}, status="not_applicable"))

    dev = rp["rainfall"]["avg_deviation_percent"]
    rain_label = fzd["rainfall_label"]
    weighted_req = sum(d["share_pct"] / 100 * d["water_req_mm"] for d in crops["crops"])
    eff = rp["rainfall"]["effective_rainfall_mm"]
    coverage = min(100.0, eff / weighted_req * 100) if weighted_req else None
    items.append(make_item("rainfall", "Rainfall",
                       f"Season rainfall is {dev:+.1f}% vs normal (fuzzy set: {rain_label}); effective rainfall of {eff:.0f} mm"
                       + (f" covers {coverage:.0f}% of this plan's land-weighted crop water need ({weighted_req:.0f} mm)."
                          if coverage is not None else "."),
                       "dataset + fuzzy", {"deviation_pct": dev, "fuzzy_label": rain_label, "effective_rainfall_mm": eff,
                                           "weighted_water_req_mm": round(weighted_req, 1),
                                           "rainfall_coverage_pct": None if coverage is None else round(coverage, 1)},
                       status={"normal": "satisfied", "surplus": "moderate", "deficit": "risk"}.get(rain_label, "unknown")))

    fert = rp["soil"]["fertility_index"]
    soil_label = fzd["soil_label"]
    items.append(make_item("soil", "Soil", f"{rp['soil']['soil_type']}, pH {rp['soil']['avg_ph']}, fertility index {fert}/100 (fuzzy set: {soil_label}).",
                       "dataset + fuzzy", {"fertility_index": fert, "fuzzy_label": soil_label, "ph": rp["soil"]["avg_ph"],
                                           "npk": [rp["soil"]["n_status"], rp["soil"]["p_status"], rp["soil"]["k_status"]]},
                       status={"good": "satisfied", "medium": "moderate", "poor": "risk"}.get(soil_label, "unknown")))

    risk = fzd["irrigation_risk"]
    term, degrees = fz.output_term("irrigation_risk", risk)
    items.append(make_item("water", "Water / irrigation", f"Irrigation risk {risk:.3f} falls in the '{term}' output set; reservoir storage "
                       f"{rp['water']['avg_storage_percent']}% (fuzzy set: {fzd['water_label']}).", "fuzzy",
                       {"irrigation_risk": risk, "risk_set": term, "membership": degrees,
                        "storage_pct": rp["water"]["avg_storage_percent"]},
                       status={"low": "satisfied", "medium": "moderate", "high": "risk"}[term]))
    items.append(make_item("feasible", "Optimiser feasibility", "The plan satisfies every constraint given to NSGA-II." if plan["feasible"]
                       else "The plan violates at least one optimiser constraint.", "nsga2", {"feasible": plan["feasible"]},
                       status="satisfied" if plan["feasible"] else "violated"))
    return {"items": items}


def _historical(ctx: ExplanationContext, crops: dict) -> dict:
    rp = ctx.region_profile
    data = load_all()
    crop_df = pp.observed_rows(data["crop"])
    sl = crop_df[(crop_df["Location"] == rp["location"]) & (crop_df["Season"] == rp["season"])]
    years = sorted(int(y) for y in sl["Year"].unique())
    ranks = {}
    for y in years:
        yr = sl[sl["Year"] == y].sort_values("Revenue_Rs_Lakh", ascending=False)
        for pos, name in enumerate(yr["Crop_Name"], start=1):
            ranks.setdefault(name, {})[y] = pos
    per_crop = []
    for d in crops["shown"]:
        hist = sl[sl["Crop_Name"] == d["crop"]]
        if hist.empty:
            per_crop.append({"crop": d["crop"], "observed_years": 0,
                             "detail": f"{d['crop']} has no observed {rp['season']} records for {rp['location']}."})
            continue
        mean_y = float(hist["Yield_Kg_Ha"].mean()) / 1000
        top = sum(1 for y in years if ranks.get(d["crop"], {}).get(y, 99) <= HISTORICAL_TOP_N)
        n = len(set(hist["Year"]))
        diff = _pct_diff(d["expected_yield_t_ha"], mean_y)
        per_crop.append({
            "crop": d["crop"], "observed_years": n, "years_in_top_n": top, "top_n": HISTORICAL_TOP_N,
            "historical_mean_yield_t_ha": round(mean_y, 2),
            "historical_yield_range_t_ha": [round(hist["Yield_Kg_Ha"].min() / 1000, 2), round(hist["Yield_Kg_Ha"].max() / 1000, 2)],
            "expected_yield_t_ha": d["expected_yield_t_ha"], "difference_pct": None if diff is None else round(diff, 1),
            "detail": (f"{d['crop']} was among the top {HISTORICAL_TOP_N} {rp['season']} crops in {rp['location']} by revenue in "
                       f"{top} of {n} observed years; historical mean yield {mean_y:.2f} t/ha vs {d['expected_yield_t_ha']:.2f} t/ha "
                       f"expected here" + (f" ({_signed_pct(diff)}, the fuzzy confidence adjustment)." if diff is not None else ".")),
        })

    rain = pp.observed_rows(data["rainfall"])
    months = _season_months(rp["season"])
    rs = rain[(rain["Location"] == rp["location"]) & (rain["Month"].isin(months))]
    totals = rs.groupby("Year")["Monthly_Rainfall_mm"].sum()
    devs = rs.groupby("Year")["Deviation_Percent"].mean()
    cv = float(totals.std() / totals.mean()) if len(totals) > 1 and totals.mean() else None
    this_total = rp["rainfall"]["avg_monthly_rainfall_mm"] * len(months)
    rainfall = {
        "observed_years": [int(y) for y in totals.index],
        "seasonal_total_mm_mean": round(float(totals.mean()), 1) if len(totals) else None,
        "seasonal_total_mm_cv": None if cv is None else round(cv, 3),
        "deviation_pct_mean": round(float(devs.mean()), 1) if len(devs) else None,
        "this_year_total_mm": round(this_total, 1), "this_year_deviation_pct": rp["rainfall"]["avg_deviation_percent"],
    }
    established = sum(d["share_pct"] for d, h in zip(crops["shown"], per_crop)
                      if h.get("observed_years") and h["years_in_top_n"] / h["observed_years"] >= HISTORICAL_HIT_RATE)
    hit = [(d["share_pct"], h["years_in_top_n"] / h["observed_years"] if h.get("observed_years") else 0.0)
           for d, h in zip(crops["shown"], per_crop)]
    share_sum = sum(s for s, _ in hit) or 1.0
    return {"crops": per_crop, "rainfall": rainfall, "observed_years": years,
            "established_land_pct": round(established, 1),
            "land_weighted_top_n_rate": round(sum(s * r for s, r in hit) / share_sum, 3)}


def _confidence(ctx: ExplanationContext, plan: dict, crops: dict, constraints: dict, history: dict,
                ranks: Dict[str, int]) -> dict:
    comps = []
    shares = [(d["share_pct"] / 100, d["crop_confidence"]) for d in crops["crops"]]
    climate = 100 * sum(s * c for s, c in shares) / (sum(s for s, _ in shares) or 1.0)
    comps.append({"id": "climate_soil", "label": "Climate & soil suitability (fuzzy)", "score": round(climate, 1),
                  "detail": f"Land-weighted fuzzy crop confidence {climate / 100:.3f} from yield confidence "
                            f"{ctx.fuzzy['yield_confidence']} and irrigation risk {ctx.fuzzy['irrigation_risk']}.",
                  "source": "fuzzy"})

    rp = ctx.region_profile
    data = load_all()
    months = _season_months(rp["season"])
    present = 0
    for kind in ("rainfall", "water"):
        df = data[kind]
        present += int(df[(df["Location"] == rp["location"]) & (df["Year"] == rp["year"]) & (df["Month"].isin(months))]["Month"].nunique())
    completeness = present / (2 * len(months))
    estimated = pp.is_estimated_year(rp["location"], rp["year"])
    quality = 100 * completeness * (0.5 if estimated else 1.0)
    comps.append({"id": "data_quality", "label": "Data quality", "score": round(quality, 1),
                  "detail": f"{completeness:.0%} of the season's monthly rainfall/water records present; "
                            + (f"{rp['year']} values are estimates carried forward from the previous year (×0.5)."
                               if estimated else f"{rp['year']} values are observed records."),
                  "source": "dataset"})

    hv = [g["hypervolume"] for g in ctx.convergence_history]
    if len(hv) >= 10 and hv[-1] - hv[0] > 1e-9:
        tail_start = hv[int(len(hv) * 0.8)]
        stability = 100 * (1 - max(0.0, hv[-1] - tail_start) / (hv[-1] - hv[0]))
        comps.append({"id": "convergence", "label": "Optimisation convergence", "score": round(max(0.0, stability), 1),
                      "detail": f"Hypervolume rose {hv[0]:.3f} → {hv[-1]:.3f}; the last 20% of generations added "
                                f"{100 * max(0.0, hv[-1] - tail_start) / (hv[-1] - hv[0]):.1f}% of the total gain.",
                      "source": "nsga2"})
    else:
        comps.append({"id": "convergence", "label": "Optimisation convergence", "score": None,
                      "detail": "No per-generation history was recorded for this run, so convergence cannot be scored; "
                                "it is excluded from the average.", "source": "nsga2"})

    violated = [c["title"] for c in constraints["items"] if c["status"] == "violated"]
    comps.append({"id": "constraints", "label": "Constraint satisfaction", "score": 0.0 if violated else 100.0,
                  "detail": "Violated: " + ", ".join(violated) if violated else "All hard constraints (land, budget, feasibility) hold.",
                  "source": "constraints"})

    rate = history["land_weighted_top_n_rate"]
    comps.append({"id": "historical", "label": "Historical consistency", "score": round(100 * rate, 1),
                  "detail": f"Land-weighted share of observed years in which the plan's crops were top-{HISTORICAL_TOP_N} "
                            f"by district revenue: {rate:.0%}.", "source": "dataset"})

    cv = history["rainfall"]["seasonal_total_mm_cv"]
    if cv is not None:
        comps.append({"id": "weather", "label": "Weather consistency", "score": round(100 * (1 - min(1.0, cv)), 1),
                      "detail": f"Coefficient of variation of {rp['season']} rainfall across observed years: {cv:.3f}.",
                      "source": "dataset"})

    top_k = max(1, math.ceil(ROBUST_TOP_FRACTION * len(ctx.plans)))
    near_top = [p for p, r in ranks.items() if r <= top_k]
    comps.append({"id": "robustness", "label": "Ranking robustness", "score": round(100 * len(near_top) / len(ranks), 1),
                  "detail": f"Within the top {top_k} of {len(ctx.plans)} plans under {len(near_top)} of {len(ranks)} "
                            f"preference weightings ({', '.join(near_top) or 'none'}).", "source": "topsis"})

    scored = [c["score"] for c in comps if c["score"] is not None]
    overall = round(sum(scored) / len(scored), 1)
    for c in comps:
        c["weight"] = round(1 / len(scored), 3) if c["score"] is not None else 0.0
    ordered = sorted([c for c in comps if c["score"] is not None], key=lambda c: c["score"])
    return {"overall_pct": overall, "components": comps,
            "method": "Unweighted mean of the available components (each 0–100); components that cannot be computed "
                      "are excluded rather than guessed.",
            "strongest_component": ordered[-1]["id"], "weakest_component": ordered[0]["id"]}


def _risks(ctx, plan, crops, constraints, objectives, history, economics) -> List[dict]:
    rp, fzd = ctx.region_profile, ctx.fuzzy
    out = []
    by_id = {c["id"]: c for c in constraints["items"]}
    water = by_id["water"]
    if water["status"] != "satisfied":
        out.append(make_item("irrigation-risk", "Irrigation pressure", water["detail"], "fuzzy", water["evidence"],
                         severity="high" if water["status"] == "risk" else "medium"))
    rain = by_id["rainfall"]
    if rain["status"] == "risk":
        out.append(make_item("rainfall-deficit", "Rainfall below normal", rain["detail"], "dataset + fuzzy", rain["evidence"], severity="high"))
    cov = rain["evidence"]["rainfall_coverage_pct"]
    if cov is not None and cov < 50:
        out.append(make_item("irrigation-dependence", "Depends on irrigation",
                         f"Rainfall covers only {cov:.0f}% of crop water need; the plan needs "
                         f"{_per_ha(plan, 'water'):.2f} ML/ha of irrigation.", "dataset + nsga2",
                         {"rainfall_coverage_pct": cov, "irrigation_ml_per_ha": round(_per_ha(plan, "water"), 3)},
                         severity="medium"))
    exposed = sum(d["share_pct"] for d in crops["shown"] if d["rainfall_dependency"] in ("High", "Medium"))
    if exposed > 0 and fzd["irrigation_risk"] > 0:
        out.append(make_item("rain-dependent-crops", "Rain-dependent crops",
                         f"{exposed:.0f}% of the land is in crops with Medium/High rainfall dependency "
                         f"({', '.join(d['crop'] for d in crops['shown'] if d['rainfall_dependency'] in ('High', 'Medium'))}), "
                         f"the crops the fuzzy model penalises most at irrigation risk {fzd['irrigation_risk']}.",
                         "dataset + fuzzy", {"exposed_land_pct": round(exposed, 1), "irrigation_risk": fzd["irrigation_risk"]},
                         severity="medium" if exposed >= 50 else "low"))
    hhi = sum((d["share_pct"] / 100) ** 2 for d in crops["crops"])
    if hhi >= CONCENTRATION_HHI:
        top = max(crops["shown"], key=lambda d: d["share_pct"])
        out.append(make_item("concentration", "Concentrated crop mix",
                         f"{top['share_pct']:.0f}% of the land is in {top['crop']} (Herfindahl index {hhi:.2f}); a crop-specific "
                         f"pest, price or water shock would affect most of the farm.", "nsga2", {"hhi": round(hhi, 3)},
                         severity="medium"))
    perennial = [d for d in crops["shown"] if d["duration_days"] >= PERENNIAL_DAYS]
    if perennial:
        out.append(make_item("perennial", "Long-duration crops in a single-season plan",
                         f"{', '.join(d['crop'] for d in perennial)} ({', '.join(str(d['duration_days']) + ' days' for d in perennial)}) "
                         f"take up {sum(d['share_pct'] for d in perennial):.0f}% of the land and run beyond this season.", "dataset",
                         {"crops": [d["crop"] for d in perennial]}, severity="medium"))
    for o in objectives["objectives"]:
        if o["goodness"] < WEAK_GOODNESS:
            out.append(make_item(f"weak-{o['objective']}", f"Weak on {o['label'].lower()}",
                             f"{o['label']} {_fmt(o['objective'], o['value_per_ha'])} is better than only "
                             f"{o['better_than_pct_of_plans']:.0f}% of the plans (best in set {_fmt(o['objective'], o['set_best'])}).",
                             "nsga2+topsis", {"goodness": o["goodness"]}, severity="low"))
    if rp.get("data_year_estimated"):
        out.append(make_item("estimated-data", "Estimated input data",
                         f"{rp['year']} inputs are estimates carried forward from the previous year, not observed records.",
                         "dataset", {"year": rp["year"]}, severity="high"))
    cv = history["rainfall"]["seasonal_total_mm_cv"]
    if cv is not None and cv > 0.10:
        out.append(make_item("rainfall-variability", "Year-to-year rainfall variability",
                         f"{rp['season']} rainfall varied with a coefficient of variation of {cv:.2f} across observed years.",
                         "dataset", {"cv": cv}, severity="low"))
    floor_i = config.IRRIGATION_MULT_MIN + INPUT_FLOOR_TOLERANCE
    floor_f = config.FERTILIZER_MULT_MIN + INPUT_FLOOR_TOLERANCE
    at_floor = [d["crop"] for d in crops["shown"] if d["irrigation_multiplier"] <= floor_i and d["fertilizer_multiplier"] <= floor_f]
    if at_floor:
        out.append(make_item("input-floor", "Input levels at the model minimum",
                         f"Irrigation and fertiliser for {', '.join(at_floor)} are at 70% of the baseline dose. The current yield "
                         f"model does not reward higher inputs, so treat these as the cheapest modelled levels, not agronomic advice.",
                         "model limitation", {"crops": at_floor}, severity="medium"))
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(out, key=lambda r: order[r["severity"]])


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def explain(ctx: ExplanationContext) -> dict:
    plan = ctx.plans[ctx.plan_index]
    rp, fzd = ctx.region_profile, ctx.fuzzy
    crops = _crop_breakdown(ctx, plan)
    objectives = _objective_analysis(ctx, plan)
    ranks = _rank_under_all_preferences(ctx)
    trade = _trade_offs(ctx, plan)
    constraints = _constraints(ctx, plan, crops)
    history = _historical(ctx, crops)
    obj = {o["objective"]: o for o in objectives["objectives"]}

    revenue = crops["revenue_rs"]
    economics = {"available": revenue is not None}
    if revenue is not None:
        profit = revenue - plan["cost_rs"]
        economics.update({
            "indicative_revenue_rs": revenue, "cost_rs": plan["cost_rs"], "indicative_profit_rs": round(profit, 0),
            "indicative_profit_rs_per_ha": round(profit / (sum(plan["area_ha"]) or 1), 0),
            "price_sensitivity_pct": round(PRICE_SHOCK * revenue / profit * 100, 1) if profit > 0 else None,
            "validated": False,
            "caveat": "Revenue = expected tonnes × the dataset's MSP_Rs_Qtl column. Those prices have not been validated "
                      "(several crops have no government-notified MSP, and some values look implausibly high), and cost covers "
                      "only fertiliser, pesticide and labour. Profit is not an optimiser objective, so it is shown for reference "
                      "only and is not used in any reason, benefit, risk or the confidence score.",
        })
    else:
        economics["reason"] = "No price is recorded in the dataset for at least one crop in this plan."

    confidence = _confidence(ctx, plan, crops, constraints, history, ranks)
    rank = plan["rank"]
    overall = confidence["overall_pct"]
    if rank == 1 and overall >= 75:
        strength = "Highly recommended"
    elif rank <= 5 and overall >= 60:
        strength = "Recommended"
    else:
        strength = "Use with caution"

    n = len(ctx.plans)
    nxt = ctx.plans[ctx.plan_index + 1] if ctx.plan_index + 1 < n else None
    margin = plan["composite_score"] - nxt["composite_score"] if nxt else None
    reasons = [make_item("topsis", "Best balance for the chosen preference",
                     f"Ranked #{rank} of {n} plans under the '{ctx.preference}' preference with TOPSIS closeness "
                     f"{plan['composite_score']:.4f}" + (f" ({margin:+.4f} ahead of the next plan)." if margin is not None else "."),
                     "topsis", {"rank": rank, "closeness": plan["composite_score"], "margin_to_next": None if margin is None else round(margin, 4),
                                "plans_compared": n})]
    for o in objectives["objectives"]:
        if o["goodness"] >= STRONG_GOODNESS:
            reasons.append(make_item(f"strong-{o['objective']}", OBJECTIVE_META[o["objective"]]["strength"],
                                 f"{o['label']} {_fmt(o['objective'], o['value_per_ha'])} is better than {o['better_than_pct_of_plans']:.0f}% "
                                 f"of the {n} plans (set median {_fmt(o['objective'], o['set_median'])}).", "nsga2",
                                 {k: o[k] for k in ("value_per_ha", "goodness", "better_than_pct_of_plans", "set_median", "set_best")}))
    by_id = {c["id"]: c for c in constraints["items"]}
    if by_id["soil"]["status"] in ("satisfied", "moderate"):
        reasons.append(make_item("soil", "Soil supports the crops", by_id["soil"]["detail"], "dataset + fuzzy", by_id["soil"]["evidence"]))
    resilient = sum(d["share_pct"] for d in crops["shown"] if d["rainfall_dependency"] in ("Low", "Very Low"))
    if resilient >= 50:
        reasons.append(make_item("resilience", "Mostly rain-resilient crops",
                             f"{resilient:.0f}% of the land is in crops with Low/Very Low rainfall dependency, which the fuzzy model "
                             f"penalises least at irrigation risk {fzd['irrigation_risk']}.", "dataset + fuzzy",
                             {"resilient_land_pct": round(resilient, 1)}))
    if by_id["budget"]["status"] == "satisfied":
        reasons.append(make_item("budget", "Fits the budget", by_id["budget"]["detail"], "constraint", by_id["budget"]["evidence"]))
    if history["established_land_pct"] >= 50:
        reasons.append(make_item("historical", "Historically established crops",
                             f"{history['established_land_pct']:.0f}% of the land goes to crops that were among the district's top "
                             f"{HISTORICAL_TOP_N} {rp['season']} crops by revenue in at least {HISTORICAL_HIT_RATE:.0%} of observed years.",
                             "dataset", {"established_land_pct": history["established_land_pct"]}))
    first_place = [p for p, r in ranks.items() if r == 1]
    if len(first_place) > 1:
        reasons.append(make_item("robust", "Robust to the preference choice",
                             f"This plan is also ranked #1 under: {', '.join(p for p in first_place if p != ctx.preference)}.",
                             "topsis", {"rank_by_preference": ranks}))

    benefits = []
    for o in objectives["objectives"]:
        hib = o["better"] == "higher"
        d = _pct_diff(o["value_per_ha"], o["set_median"])
        if d is not None and ((d > 0) if hib else (d < 0)):
            benefits.append(make_item(f"benefit-{o['objective']}", f"{'Higher' if hib else 'Lower'} {o['label'].lower()} than typical",
                                  f"{o['label']} {_fmt(o['objective'], o['value_per_ha'])} is {abs(d):.0f}% "
                                  f"{'above' if hib else 'below'} the median of the {n} plans.", "nsga2",
                                  {"value_per_ha": o["value_per_ha"], "set_median": o["set_median"], "difference_pct": round(d, 1)}))

    diversified = [d for d in crops["shown"] if d["share_pct"] >= DIVERSIFIED_SHARE_PCT]
    hhi = sum((d["share_pct"] / 100) ** 2 for d in crops["crops"])
    footprint = np.mean([obj[k]["goodness"] for k in ("cost", "water", "env")])
    lean = obj["yield"]["goodness"] - footprint
    insights = [make_item("position", "Where the plan sits on the trade-off",
                      ("It favours output over input savings" if lean > 0.2 else
                       "It favours lower cost, water and impact over maximum yield" if lean < -0.2 else
                       "It sits near the middle of the trade-off between output and resource use")
                      + f": yield goodness {obj['yield']['goodness']:.2f} vs average resource goodness {footprint:.2f}.",
                      "topsis", {"yield_goodness": obj["yield"]["goodness"], "resource_goodness_mean": round(float(footprint), 3)})]
    insights.append(make_item("diversification", "Crop diversification",
                          f"{len(diversified)} crop(s) hold at least {DIVERSIFIED_SHARE_PCT:.0f}% of the land each "
                          f"(Herfindahl index {hhi:.2f}; 1.0 = single crop).", "nsga2",
                          {"crops_over_threshold": [d["crop"] for d in diversified], "hhi": round(hhi, 3)}))
    if crops["shown"]:
        lead = max(crops["shown"], key=lambda d: d["tonnage_share_pct"])
        insights.append(make_item("yield-driver", "Main source of yield",
                              f"{lead['crop']} provides {lead['tonnage_share_pct']:.0f}% of the expected tonnage on "
                              f"{lead['share_pct']:.0f}% of the land.", "nsga2", {"crop": lead["crop"],
                              "tonnage_share_pct": lead["tonnage_share_pct"], "land_share_pct": lead["share_pct"]}))
    cov = by_id["rainfall"]["evidence"]["rainfall_coverage_pct"]
    if cov is not None:
        insights.append(make_item("rain-reliance", "Reliance on rainfall",
                              f"Effective rainfall meets {cov:.0f}% of the plan's crop water need; the rest is irrigation.",
                              "dataset", {"rainfall_coverage_pct": cov}))
    insights.append(make_item("preference-ranks", "Rank under each preference",
                          ", ".join(f"{p}: #{r}" for p, r in ranks.items()) + f" (of {n}).", "topsis", {"rank_by_preference": ranks}))

    alternatives = []
    if nxt is not None:
        deltas = {k: round(_per_ha(nxt, k) - _per_ha(plan, k), 4) for k in ranking.OBJECTIVES}
        alternatives.append(make_item("runner-up", f"Versus the runner-up (rank #{nxt['rank']})",
                                  "Runner-up per hectare: " + ", ".join(
                                      f"{OBJECTIVE_META[k]['label'].lower()} {'+' if v >= 0 else '−'}{_fmt(k, abs(v))}" for k, v in deltas.items())
                                  + f"; TOPSIS closeness {nxt['composite_score']:.4f} vs {plan['composite_score']:.4f}.",
                                  "topsis", {"rank": nxt["rank"], "deltas_per_ha": deltas}))

    hv = ctx.convergence_history
    meta = ctx.meta
    fired = fz.fired_rules(rp["rainfall"]["avg_deviation_percent"], rp["water"]["avg_storage_percent"], rp["soil"]["fertility_index"])
    timeline = [
        make_item("data", "1 · District data", f"{rp['location']} {rp['season']} {rp['year']}: months {', '.join(rp['rainfall']['months_used'])}; "
              f"{len(rp['candidate_crops'])} candidate crops ranked by historical revenue.", "dataset",
              {"year_estimated": bool(rp.get("data_year_estimated")), "candidate_crops": [c["name"] for c in rp["candidate_crops"]]}),
        make_item("fuzzy", "2 · Fuzzy uncertainty", f"Inputs: rainfall deviation {rp['rainfall']['avg_deviation_percent']}%, storage "
              f"{rp['water']['avg_storage_percent']}%, soil fertility {rp['soil']['fertility_index']} → yield confidence "
              f"{fzd['yield_confidence']}, irrigation risk {fzd['irrigation_risk']} ({len(fired)} rules fired).", "fuzzy",
              {"memberships": fz.input_memberships(rp["rainfall"]["avg_deviation_percent"], rp["water"]["avg_storage_percent"],
                                                   rp["soil"]["fertility_index"]), "fired_rules": fired[:5]}),
        make_item("nsga2", "3 · NSGA-II search", f"Population {meta.get('pop_size')}, {meta.get('n_gen')} generations → "
              f"{meta.get('n_pareto_solutions_found')} non-dominated plans"
              + (f"; hypervolume {hv[0]['hypervolume']:.3f} → {hv[-1]['hypervolume']:.3f}." if hv else "."), "nsga2",
              {k: meta.get(k) for k in ("pop_size", "n_gen", "crossover_prob", "mutation_prob", "n_pareto_solutions_found")}),
        make_item("topsis", "4 · TOPSIS ranking", f"'{ctx.preference}' weights (yield/cost/water/impact = "
              + "/".join(f"{x:.2f}" for x in ranking.preference_weights(ctx.preference))
              + f") → rank #{rank}, closeness {plan['composite_score']:.3f}.", "topsis", {"plans_ranked": n}),
        make_item("checks", "5 · Constraint checks", f"{sum(1 for c in constraints['items'] if c['status'] == 'satisfied')} of "
              f"{len(constraints['items'])} checks fully satisfied.", "constraints",
              {c["id"]: c["status"] for c in constraints["items"]}),
    ]

    return {
        "subject": ctx.subject,
        "summary": {
            "location": rp["location"], "season": rp["season"], "year": rp["year"],
            "data_year_estimated": bool(rp.get("data_year_estimated")), "preference": ctx.preference,
            "rank": rank, "plans_compared": n, "plans_found": meta.get("n_pareto_solutions_found"),
            "closeness": plan["composite_score"], "recommendation": strength, "confidence_pct": overall,
            "total_land_ha": round(sum(plan["area_ha"]), 3),
            "crop_mix": [{"crop": d["crop"], "share_pct": d["share_pct"], "area_ha": d["area_ha"]} for d in crops["shown"]],
            "per_ha": {k: round(_per_ha(plan, k), 4 if k == "water" else 2) for k in ranking.OBJECTIVES},
            "totals": {k: plan[OBJECTIVE_META[k]["key"]] for k in ranking.OBJECTIVES},
            "recommendation_rule": "Highly recommended: rank 1 and confidence ≥ 75%; Recommended: rank ≤ 5 and confidence ≥ 60%; "
                                   "otherwise Use with caution.",
        },
        "reasons": reasons,
        "objectives": objectives,
        "trade_offs": trade,
        "constraints": constraints,
        "benefits": benefits,
        "risks": _risks(ctx, plan, crops, constraints, objectives, history, economics),
        "historical_context": history,
        "confidence": confidence,
        "insights": insights,
        "alternatives": alternatives,
        "economics": economics,
        "crop_breakdown": crops["crops"],
        "consistency_checks": crops["consistency"],
        "timeline": timeline,
        "fuzzy_reasoning": {"input_memberships": timeline[1]["evidence"]["memberships"], "fired_rules": fired},
    }


def explain_saved_run(record: dict, rank: int = 1) -> dict:
    return explain(context_from_saved_run(record, rank))


def explain_comparison_plan(location: str, plan_key: str, total_land_ha: float = 5.0,
                            budget_rs: Optional[float] = None) -> dict:
    return explain(context_from_comparison(location, plan_key, total_land_ha, budget_rs))
