"""
TOPSIS explanation and profile comparison.

breakdown()        every plan's path from weight to score: raw value ->
                   0-1 goodness -> weighted value -> squared distance to the
                   ideal and anti-ideal per criterion -> closeness
explain_pair()     why one plan ranks above another, criterion by criterion
compare_profiles() the same plan set ranked under several weight profiles:
                   best plan, rank changes, rank correlation

All of it uses ranking.criteria_closeness' normalisation and distance maths,
so the numbers reproduce the ranking exactly. Method:
docs/handbook/TOPSIS_EXPLAINABILITY.md.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np
from scipy.stats import kendalltau

from app.decision import ranking
from app.decision.criteria import CRITERIA_META
from app.decision.profiles import WeightSpec

SCORE_DECIMALS = 4   # rank_plans sorts on the closeness rounded to 4 places


def directions(keys) -> Dict[str, str]:
    return {k: CRITERIA_META[k]["direction"] for k in keys}


def ranks_from_closeness(closeness: Sequence[float]) -> List[int]:
    """1-based rank of every plan, ordered exactly as rank_plans orders them
    (closeness rounded to 4 places, descending, ties in input order)."""
    order = sorted(range(len(closeness)), key=lambda i: round(float(closeness[i]), SCORE_DECIMALS), reverse=True)
    ranks = [0] * len(closeness)
    for r, i in enumerate(order, start=1):
        ranks[i] = r
    return ranks


def breakdown(values: Dict[str, List[float]], spec: WeightSpec) -> dict:
    """Per-plan, per-criterion TOPSIS terms for the criteria `spec` weights.

    For criterion j and plan i with goodness g_ij and weight w_j:
        v_ij  = w_j * g_ij                      weighted value
        d+_ij = (v_ij - max_i v_ij)^2           squared gap to the ideal
        d-_ij = (v_ij - min_i v_ij)^2           squared gap to the anti-ideal
        D+_i  = sqrt(sum_j d+_ij),  D-_i = sqrt(sum_j d-_ij),  C_i = D-_i / (D+_i + D-_i)
    """
    active = [k for k in values if spec.weights.get(k, 0.0) > 0]
    closeness, goodness = ranking.criteria_closeness({k: values[k] for k in active}, directions(active), spec.weights)
    w = np.array([spec.weights[k] for k in active])
    V = np.column_stack([goodness[k] for k in active]) * w
    best, worst = V.max(axis=0), V.min(axis=0)
    d_best, d_worst = (V - best) ** 2, (V - worst) ** 2
    return {
        "criteria": active, "weights": w, "values": {k: np.asarray(values[k], dtype=float) for k in active},
        "goodness": np.column_stack([goodness[k] for k in active]), "weighted": V,
        "ideal_best": best, "ideal_worst": worst, "d_best": d_best, "d_worst": d_worst,
        "dist_best": np.sqrt(d_best.sum(axis=1)), "dist_worst": np.sqrt(d_worst.sum(axis=1)),
        "closeness": np.asarray(closeness), "ranks": ranks_from_closeness(closeness),
    }


def plan_terms(bd: dict, i: int) -> dict:
    """One plan's weight -> contribution -> score chain."""
    db, dw = bd["d_best"][i], bd["d_worst"][i]
    tot_b, tot_w = db.sum() or 1.0, dw.sum() or 1.0
    rows = []
    for j, k in enumerate(bd["criteria"]):
        rows.append({
            "criterion": k, "label": CRITERIA_META[k]["label"], "direction": CRITERIA_META[k]["direction"],
            "unit": CRITERIA_META[k]["unit"], "weight": round(float(bd["weights"][j]), 4),
            "value": round(float(bd["values"][k][i]), 4), "goodness": round(float(bd["goodness"][i, j]), 4),
            "weighted": round(float(bd["weighted"][i, j]), 4),
            "gap_to_ideal": round(float(np.sqrt(db[j])), 4), "gap_to_anti_ideal": round(float(np.sqrt(dw[j])), 4),
            "share_of_distance_to_ideal_pct": round(100 * float(db[j]) / tot_b, 1),
            "share_of_distance_to_anti_ideal_pct": round(100 * float(dw[j]) / tot_w, 1),
        })
    return {
        "rank": bd["ranks"][i], "closeness": round(float(bd["closeness"][i]), 6),
        "distance_to_ideal": round(float(bd["dist_best"][i]), 6),
        "distance_to_anti_ideal": round(float(bd["dist_worst"][i]), 6),
        "criteria": rows,
    }


def explain_pair(bd: dict, a: int, b: int) -> dict:
    """Why plan `a` ranks above (or below) plan `b`.

    The per-criterion advantage is the weighted goodness gap w_j (g_aj - g_bj):
    both plans are measured against the same ideal and anti-ideal, so the plan
    with the larger weighted value is closer to the ideal and farther from the
    anti-ideal on that criterion. The exact squared-distance terms are given
    alongside."""
    rows = []
    for j, k in enumerate(bd["criteria"]):
        gap = float(bd["weighted"][a, j] - bd["weighted"][b, j])
        rows.append({
            "criterion": k, "label": CRITERIA_META[k]["label"], "weight": round(float(bd["weights"][j]), 4),
            "goodness_a": round(float(bd["goodness"][a, j]), 4), "goodness_b": round(float(bd["goodness"][b, j]), 4),
            "weighted_advantage": round(gap, 4),
            "d_best_a": round(float(bd["d_best"][a, j]), 6), "d_best_b": round(float(bd["d_best"][b, j]), 6),
            "d_worst_a": round(float(bd["d_worst"][a, j]), 6), "d_worst_b": round(float(bd["d_worst"][b, j]), 6),
        })
    rows.sort(key=lambda r: -abs(r["weighted_advantage"]))
    ca, cb = float(bd["closeness"][a]), float(bd["closeness"][b])
    # Criteria are named in the sentence only when the advantage shows at 3 decimals.
    ahead = [r for r in rows if r["weighted_advantage"] >= 5e-4]
    behind = [r for r in rows if r["weighted_advantage"] <= -5e-4]
    lead = "ranks above" if bd["ranks"][a] < bd["ranks"][b] else "ranks below"

    def phrase(items):
        return ", ".join(f"{r['label'].lower()} ({r['weighted_advantage']:+.3f})" for r in items[:3])

    text = f"Plan #{bd['ranks'][a]} {lead} plan #{bd['ranks'][b]} (closeness {ca:.4f} vs {cb:.4f})."
    if ahead:
        text += f" It is better on {phrase(ahead)}"
        text += f" and worse on {phrase(behind)}." if behind else "."
    elif behind:
        text += f" It is worse on {phrase(behind)}."
    return {"rank_a": bd["ranks"][a], "rank_b": bd["ranks"][b], "closeness_a": round(ca, 6), "closeness_b": round(cb, 6),
            "criteria": rows, "summary": text}


def compare_profiles(values: Dict[str, List[float]], specs: Sequence[WeightSpec], reference: str,
                     top_n: int = 5, plan_labels: Optional[List[dict]] = None) -> dict:
    """Rank one plan set under every spec. `reference` names the spec the
    rank changes are measured against (normally the run's own profile)."""
    by_name = {s.profile: s for s in specs}
    if reference not in by_name:
        raise ValueError(f"Reference profile '{reference}' is not in the comparison.")
    results = {}
    for s in specs:
        bd = breakdown(values, s)
        results[s.profile] = {"spec": s, "closeness": bd["closeness"], "ranks": bd["ranks"]}
    ref = results[reference]
    ref_order = sorted(range(len(ref["ranks"])), key=lambda i: ref["ranks"][i])
    ref_top = ref_order[:top_n]
    n = len(ref["ranks"])

    def describe(i):
        return {"plan_index": i, **(plan_labels[i] if plan_labels else {})}

    profiles = []
    for name, r in results.items():
        order = sorted(range(n), key=lambda i: r["ranks"][i])
        best = order[0]
        tau = None
        if n > 1 and name != reference:
            t = kendalltau(ref["ranks"], r["ranks"]).statistic
            tau = None if np.isnan(t) else round(float(t), 4)
        profiles.append({
            **r["spec"].as_dict(),
            "best_plan": {**describe(best), "closeness": round(float(r["closeness"][best]), 6),
                          "rank_under_reference": ref["ranks"][best]},
            "reference_top_plan_rank": r["ranks"][ref_order[0]],
            "kendall_tau_vs_reference": 1.0 if name == reference else tau,
            "top_n_overlap": len(set(order[:top_n]) & set(ref_top)),
            "top_plans": [{**describe(i), "rank": r["ranks"][i], "closeness": round(float(r["closeness"][i]), 6)}
                          for i in order[:top_n]],
        })
    rank_changes = [{**describe(i), "reference_rank": ref["ranks"][i],
                     "ranks": {name: r["ranks"][i] for name, r in results.items()},
                     "closeness": {name: round(float(r["closeness"][i]), 6) for name, r in results.items()}}
                    for i in ref_top]
    distinct_best = len({p["best_plan"]["plan_index"] for p in profiles})
    return {"reference": reference, "plans_compared": n, "top_n": top_n, "profiles": profiles,
            "rank_changes": rank_changes, "distinct_best_plans": distinct_best}
