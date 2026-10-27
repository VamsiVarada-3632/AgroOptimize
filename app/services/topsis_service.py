"""
Dynamic TOPSIS ranking: ranking profiles applied to a run's Pareto front.

The ranking stage only. NSGA-II, the fuzzy assessment and the objectives
are inputs here and are never recomputed: a saved run is re-ranked from
the feasible front stored with it.

    rank_front()          rank a front under one WeightSpec
    topsis_meta()         the meta.topsis block of a run
    profile_comparison()  the front ranked under every standard profile
    rerank_saved_run()    POST /api/results/{run_id}/topsis

See docs/handbook/TOPSIS_DYNAMIC_ENGINE.md.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Dict, List, Mapping, Optional, Sequence

from app.decision import ranking
from app.decision import topsis_explain as tx
from app.decision.criteria import CRITERIA, CRITERIA_META, OPTIMISER_CRITERIA, CropAttributes, crop_attributes, plan_criteria
from app.decision.profiles import PROFILES, WeightSpec, profile_weights, resolve
from app.optimization.nsga2_runner import FarmPlan

BREAKDOWN_PLANS = 10     # plans whose weight -> contribution -> score chain is returned
COMPARISON_TOP_N = 5


def standard_specs() -> List[WeightSpec]:
    return [WeightSpec(name, p["label"], profile_weights(name)) for name, p in PROFILES.items()]


def criteria_for(plans: Sequence, attrs: Optional[CropAttributes], budget_rs: Optional[float],
                 keys: Sequence[str] = CRITERIA) -> Dict[str, List[float]]:
    needed = [k for k in CRITERIA if k in keys]
    return plan_criteria(plans, attrs if any(k not in OPTIMISER_CRITERIA for k in needed) else None, budget_rs, needed)


def rank_front(plans: Sequence[FarmPlan], crop_confidence_map: Dict[str, float], spec: WeightSpec,
               attrs: Optional[CropAttributes], budget_rs: Optional[float]):
    """rank_plans under a profile. Balanced goes through the original
    preference path, so its ranking is the published one bit for bit."""
    if spec.profile == "balanced":
        return ranking.rank_plans(list(plans), crop_confidence_map=crop_confidence_map, preference="balanced")
    values = criteria_for(plans, attrs, budget_rs, spec.active)
    return ranking.rank_plans(list(plans), crop_confidence_map=crop_confidence_map, criteria_values=values,
                              criteria_weights=spec.weights, criteria_directions=tx.directions(values))


def topsis_meta(spec: Optional[WeightSpec], preference: str, weights4=None, budget_rs: Optional[float] = None) -> dict:
    """meta.topsis: which weights ranked the run. For a run ranked by a
    preference (or by the simulation's priority weights) the weights are
    given over the four optimiser objectives."""
    if spec is not None:
        out = spec.as_dict()
    else:
        w = ranking.normalise_weights(weights4) if weights4 is not None else ranking.preference_weights(preference)
        weights = dict(zip(ranking.OBJECTIVES, map(float, w)))
        name = "balanced" if weights4 is None and preference == "balanced" else None
        out = {
            "profile": name, "label": PROFILES["balanced"]["label"] if name else
            ("Custom priorities" if weights4 is not None else f"Preference '{preference}'"),
            "weights": {c: weights.get(c, 0.0) for c in CRITERIA},
            "criteria": [{"key": c, **{k: CRITERIA_META[c][k] for k in ("label", "direction")}, "weight": weights[c]}
                         for c in ranking.OBJECTIVES if weights[c] > 0],
        }
    out["preference"] = preference
    out["method"] = "TOPSIS: min–max normalisation, weighted Euclidean distance to the ideal and anti-ideal plan"
    out["budget_active"] = bool(budget_rs)
    return out


def _plan_label(plan) -> dict:
    get = (lambda k: plan[k]) if isinstance(plan, dict) else (lambda k: getattr(plan, k))
    area = get("area_ha")
    total = sum(area) or 1.0
    mix = sorted(((n, a / total) for n, a in zip(get("crop_names"), area)), key=lambda x: -x[1])
    return {"crop_mix": [{"crop": n, "share_pct": round(100 * s, 1)} for n, s in mix if s >= 0.01][:4],
            "yield_tonnes": get("yield_tonnes"), "cost_rs": get("cost_rs"),
            "water_liters": get("water_liters"), "env_impact_score": get("env_impact_score")}


def profile_comparison(plans: Sequence, attrs: Optional[CropAttributes], budget_rs: Optional[float],
                       reference: WeightSpec, top_n: int = COMPARISON_TOP_N) -> dict:
    """The plan set ranked under the five standard profiles (plus the
    reference spec when it is custom)."""
    specs = standard_specs()
    if reference.profile not in PROFILES:
        specs.append(reference)
    values = criteria_for(plans, attrs, budget_rs)
    out = tx.compare_profiles(values, specs, reference.profile, top_n=top_n, plan_labels=[_plan_label(p) for p in plans])
    for p in out["profiles"]:
        p["weight_differences"] = {c: round(p["weights"][c] - reference.weights[c], 4) for c in CRITERIA}
    return out


def ranking_explanation(plans: Sequence, attrs: Optional[CropAttributes], budget_rs: Optional[float],
                        spec: WeightSpec, n: int = BREAKDOWN_PLANS) -> dict:
    """Weight -> contribution -> score for the top `n` plans, and why each of
    them ranks above the next one."""
    values = criteria_for(plans, attrs, budget_rs, spec.active)
    bd = tx.breakdown(values, spec)
    order = sorted(range(len(plans)), key=lambda i: bd["ranks"][i])
    top = order[:n]
    return {
        "profile": spec.profile, "label": spec.label, "plans_ranked": len(plans),
        "ideal_best": dict(zip(bd["criteria"], map(lambda x: round(float(x), 4), bd["ideal_best"]))),
        "ideal_worst": dict(zip(bd["criteria"], map(lambda x: round(float(x), 4), bd["ideal_worst"]))),
        "plans": [{**_plan_label(plans[i]), **tx.plan_terms(bd, i)} for i in top],
        "pairs": [tx.explain_pair(bd, a, b) for a, b in zip(top, top[1:])],
    }


def stored_front(record: dict) -> (List[dict], str):
    """The plan set a saved run is re-ranked over: the full feasible front
    when the run stored it, else the plans it returned (older runs)."""
    front = record.get("ranked_front")
    if front:
        return front, "ranked_front"
    return record.get("plans") or [], "returned_plans"


def _as_farm_plans(front: List[dict]) -> List[FarmPlan]:
    fields = FarmPlan.__dataclass_fields__
    plans = []
    for p in front:
        if "allocation_fraction" not in p:      # a returned plan of an older run
            total = sum(p["area_ha"]) or 1.0
            p = {**p, "allocation_fraction": [a / total for a in p["area_ha"]]}
        plans.append(FarmPlan(**{k: p[k] for k in fields}))
    return plans


def rerank_saved_run(record: dict, profile: str, custom_weights: Optional[Mapping[str, float]] = None,
                     compare: bool = True) -> dict:
    spec = resolve(profile, custom_weights)
    meta = record.get("meta") or {}
    front, source = stored_front(record)
    if not front:
        raise ValueError("This run has no feasible plans to rank.")
    plans = _as_farm_plans(front)
    budget = meta.get("budget_rs")
    attrs = crop_attributes(record["region_profile"], record["fuzzy_assessment"])
    confidence = dict(zip(attrs.names, attrs.confidence.tolist()))
    ranked = rank_front(plans, confidence, spec, attrs, budget)
    out = {
        "topsis": topsis_meta(spec, meta.get("preference") or "balanced", budget_rs=budget),
        "plans": ranking.to_dict_list(ranked),
        "ranked_over": source, "plans_ranked": len(plans),
        "explanation": ranking_explanation(plans, attrs, budget, spec),
    }
    if compare:
        out["comparison"] = profile_comparison(plans, attrs, budget, spec)
    return out


def front_record(plans: Sequence[FarmPlan]) -> List[dict]:
    """The feasible front as stored with a saved run (full precision)."""
    return [asdict(p) for p in plans]
