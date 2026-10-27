"""
Benchmark of the dynamic TOPSIS ranking stage.

For every district x season (12 problems) and seeds 0..N-1, one NSGA-II run
with the published settings (population 80, 200 generations, original
engine) produces a feasible Pareto front, with and without a budget. Every
front is then ranked under every profile. NSGA-II is run once per front:
the profiles only re-rank it.

Reported:
  identity      Balanced profile vs the published ranking: identical plans,
                order and scores (bit for bit), and the general criteria path
  profiles      per profile: how often its #1 differs from Balanced's,
                Kendall's tau and top-5 overlap with Balanced, and the paired
                change of the #1 plan's criteria (Wilcoxon signed-rank)
  correlation   median Spearman correlation between the ten criteria
  sensitivity   rank-sum vs rank-order-centroid weights for the same tiers;
                Balanced's #1 under +-10 % yield weight; entropy and CRITIC
                weights of the four objectives for reference
  runtime       ranking time per front: published path, profile path,
                five-profile comparison

    python scripts/benchmark_topsis.py [--seeds 5] [--json out.json] [--charts DIR]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np
from scipy.stats import kendalltau, spearmanr, wilcoxon

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402
from app.data import preprocessing as pp  # noqa: E402
from app.decision import ranking  # noqa: E402
from app.decision import topsis_explain as tx  # noqa: E402
from app.decision.criteria import CRITERIA, CRITERIA_META, crop_attributes  # noqa: E402
from app.decision.profiles import PROFILES, WeightSpec, profile_weights, resolve  # noqa: E402
from app.fuzzy import engine as fz  # noqa: E402
from app.optimization.engine_settings import engine_settings  # noqa: E402
from app.optimization.nsga2_runner import extract_pareto_plans, run_nsga2  # noqa: E402
from app.optimization.problem import FarmPlanProblem  # noqa: E402
from app.services import topsis_service as ts  # noqa: E402
from app.services.plan_service import region_profile_payload  # noqa: E402

SEASONS = ("Kharif", "Rabi", "Summer")
PROFILE_ORDER = tuple(PROFILES)
TOP_N = 5


def roc_tier_weights(tiers) -> dict:
    """Rank-order-centroid weights (Barron & Barrett 1996) with tied ranks
    averaged over the positions each tier occupies."""
    ordered = [c for t in ("high", "medium", "low") for c in tiers.get(t, ())]
    n = len(ordered)
    roc = [sum(1 / j for j in range(k, n + 1)) / n for k in range(1, n + 1)]
    w, pos = {}, 0
    for t in ("high", "medium", "low"):
        crits = tiers.get(t, ())
        if crits:
            avg = sum(roc[pos:pos + len(crits)]) / len(crits)
            for c in crits:
                w[c] = avg
            pos += len(crits)
    return {c: w.get(c, 0.0) for c in CRITERIA}


def entropy_weights(M: np.ndarray) -> np.ndarray:
    """Shannon-entropy objective weights (Hwang & Yoon 1981) of goodness columns."""
    P = M / np.clip(M.sum(axis=0), 1e-12, None)
    logs = np.log(P, out=np.zeros_like(P), where=P > 0)
    e = -(P * logs).sum(axis=0) / np.log(len(M))
    d = 1 - e
    return d / d.sum()


def critic_weights(M: np.ndarray) -> np.ndarray:
    """CRITIC weights (Diakoulaki, Mavrotas & Papayannakis 1995)."""
    sd = M.std(axis=0, ddof=1)
    R = np.corrcoef(M, rowvar=False)
    c = sd * (1 - R).sum(axis=0)
    return c / c.sum()


def make_fronts(seeds: int):
    fronts = []
    for loc in config.LOCATIONS:
        for season in SEASONS:
            prof = pp.get_region_season_profile(loc, season)
            a = fz.evaluate_uncertainty(prof.rainfall.avg_deviation_percent, prof.water.avg_storage_percent,
                                        prof.soil.fertility_index)
            free = FarmPlanProblem(prof, a, 5.0)
            median_cost = float(np.median([m["cost_rs_ha"] for m in free.single_crop_metrics()])) * 5.0
            for budget in (None, median_cost):
                problem = free if budget is None else FarmPlanProblem(prof, a, 5.0, budget_rs=budget)
                for seed in range(seeds):
                    res = run_nsga2(problem, seed=seed, engine=engine_settings("original"))
                    plans = [p for p in extract_pareto_plans(res, problem) if p.feasible]
                    if len(plans) < 2:
                        continue
                    attrs = crop_attributes(region_profile_payload(prof), vars(a))
                    fronts.append({"problem": f"{loc} {season}" + (", budget" if budget else ""), "seed": seed,
                                   "plans": plans, "attrs": attrs, "budget": budget,
                                   "conf": dict(zip(problem.crop_vec.names, problem.crop_vec.crop_yield_confidence.tolist()))})
            print(f"  {loc} {season}: {sum(1 for f in fronts if f['problem'].startswith(f'{loc} {season}'))} fronts", flush=True)
    return fronts


def per_ha(values, land=5.0):
    return {k: v / land if k in ("yield", "cost", "water", "env", "income", "budget") else v for k, v in values.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--json", default=None)
    ap.add_argument("--charts", default=None)
    args = ap.parse_args()

    fronts = make_fronts(args.seeds)
    specs = [resolve(p) for p in PROFILE_ORDER]
    out = {"fronts": len(fronts), "seeds": args.seeds, "front_sizes": [len(f["plans"]) for f in fronts]}

    # ---- identity ----
    identical = generic_identical = 0
    for f in fronts:
        legacy = ranking.to_dict_list(ranking.rank_plans(f["plans"], f["conf"], preference="balanced"))
        prof = ranking.to_dict_list(ts.rank_front(f["plans"], f["conf"], resolve("balanced"), f["attrs"], f["budget"]))
        values = ts.criteria_for(f["plans"], f["attrs"], f["budget"], ranking.OBJECTIVES)
        generic = ranking.to_dict_list(ranking.rank_plans(f["plans"], f["conf"], criteria_values=values,
                                                          criteria_weights=profile_weights("balanced"),
                                                          criteria_directions=tx.directions(values)))
        identical += legacy == prof
        generic_identical += legacy == generic
    out["identity"] = {"balanced_profile_identical": identical, "generic_path_identical": generic_identical, "fronts": len(fronts)}
    print(f"\nBalanced identical to the published ranking: {identical}/{len(fronts)} (general path {generic_identical}/{len(fronts)})")

    # ---- profiles ----
    rows = []
    corr = {(a, b): [] for a in CRITERIA for b in CRITERIA}
    for f in fronts:
        values = ts.criteria_for(f["plans"], f["attrs"], f["budget"])
        bds = {s.profile: tx.breakdown(values, s) for s in specs}
        ref = bds["balanced"]["ranks"]
        ref_top = sorted(range(len(ref)), key=lambda i: ref[i])
        for s in specs:
            r = bds[s.profile]["ranks"]
            order = sorted(range(len(r)), key=lambda i: r[i])
            tau = kendalltau(ref, r).statistic
            rows.append({"problem": f["problem"], "seed": f["seed"], "profile": s.profile, "top": order[0],
                         "same_top": order[0] == ref_top[0], "tau": None if np.isnan(tau) else float(tau),
                         "overlap": len(set(order[:TOP_N]) & set(ref_top[:TOP_N])),
                         "top_values": per_ha({k: values[k][order[0]] for k in CRITERIA}),
                         "balanced_top_rank": r[ref_top[0]]})
        for a in CRITERIA:
            for b in CRITERIA:
                va, vb = np.asarray(values[a]), np.asarray(values[b])
                if va.std() > 0 and vb.std() > 0:
                    corr[(a, b)].append(spearmanr(va, vb).statistic)

    summary = {}
    print(f"\n{'profile':<15}{'#1 differs':>11}{'tau med':>9}{'top-5 overlap':>15}{'Balanced #1 rank (median)':>27}")
    for p in PROFILE_ORDER:
        pr = [r for r in rows if r["profile"] == p]
        taus = [r["tau"] for r in pr if r["tau"] is not None]
        summary[p] = {
            "top_differs_share": sum(not r["same_top"] for r in pr) / len(pr),
            "tau_median": statistics.median(taus) if taus else None,
            "overlap_median": statistics.median(r["overlap"] for r in pr),
            "balanced_top_rank_median": statistics.median(r["balanced_top_rank"] for r in pr),
            "top_values_median": {k: statistics.median(r["top_values"][k] for r in pr) for k in CRITERIA},
        }
        s = summary[p]
        print(f"{p:<15}{s['top_differs_share']:>10.0%}{s['tau_median'] if s['tau_median'] is not None else float('nan'):>9.2f}"
              f"{s['overlap_median']:>15}{s['balanced_top_rank_median']:>27}")

    # paired change of the #1 plan's criteria vs Balanced
    shifts = {}
    bal = {(r["problem"], r["seed"]): r for r in rows if r["profile"] == "balanced"}
    print("\nChange of the #1 plan vs Balanced (median of paired differences; better/worse counts; Wilcoxon p)")
    for p in PROFILE_ORDER[1:]:
        shifts[p] = {}
        pr = [r for r in rows if r["profile"] == p]
        for k in CRITERIA:
            d = np.array([r["top_values"][k] - bal[(r["problem"], r["seed"])]["top_values"][k] for r in pr])
            sign = 1 if CRITERIA_META[k]["direction"] == "benefit" else -1
            better, worse = int((sign * d > 1e-9).sum()), int((sign * d < -1e-9).sum())
            pval = float(wilcoxon(d).pvalue) if np.any(np.abs(d) > 1e-12) else None
            shifts[p][k] = {"median_change": float(np.median(d)), "better": better, "worse": worse, "p": pval}
        print(f"  {p}: " + ", ".join(f"{k} {shifts[p][k]['better']}/{shifts[p][k]['worse']}" for k in CRITERIA
                                       if profile_weights(p)[k] > 0))
    out["profiles"] = summary
    out["top_plan_shift_vs_balanced"] = shifts
    out["spearman_median"] = {f"{a}|{b}": (float(np.median(v)) if v else None) for (a, b), v in corr.items()}

    print("\nMedian Spearman correlation (selected pairs)")
    for a, b in (("yield", "cost"), ("yield", "water"), ("yield", "env"), ("cost", "budget"), ("yield", "income"),
                 ("income", "market_price"), ("water", "env"), ("soil", "env"), ("rainfall", "water"), ("land", "yield")):
        v = out["spearman_median"][f"{a}|{b}"]
        print(f"  {a:>12} ~ {b:<12} {v:+.2f}" if v is not None else f"  {a} ~ {b}: constant")

    # ---- sensitivity ----
    def top_shift(values, bd_ref, bd_alt):
        """Rank under the reference weights of the alternative weights' #1, its
        closeness gap to the reference #1, and the largest per-ha change of
        the four objectives between the two #1 plans (percent)."""
        a, b = bd_ref["ranks"].index(1), bd_alt["ranks"].index(1)
        change = max(abs(values[k][b] - values[k][a]) / abs(values[k][a]) * 100 if values[k][a] else 0.0
                     for k in ranking.OBJECTIVES)
        return a == b, bd_ref["ranks"][b], float(bd_ref["closeness"][a] - bd_ref["closeness"][b]), change

    agree = {}
    for p in PROFILE_ORDER[1:]:
        roc = WeightSpec(p, p, roc_tier_weights(PROFILES[p]["tiers"]))
        res = []
        for f in fronts:
            values = ts.criteria_for(f["plans"], f["attrs"], f["budget"])
            res.append(top_shift(values, tx.breakdown(values, resolve(p)), tx.breakdown(values, roc)))
        agree[p] = {"roc_weights": roc.weights, "top_agreement": sum(r[0] for r in res) / len(res),
                    "roc_top_rank_median": statistics.median(r[1] for r in res),
                    "closeness_gap_median": statistics.median(r[2] for r in res),
                    "max_objective_change_pct_median": statistics.median(r[3] for r in res)}
    perturb = []
    for f in fronts:
        values = ts.criteria_for(f["plans"], f["attrs"], f["budget"], ranking.OBJECTIVES)
        ref = tx.breakdown(values, resolve("balanced"))
        for yw in (0.27, 0.33):
            w = {"yield": yw, **{k: (1 - yw) / 3 for k in ("cost", "water", "env")}}
            perturb.append(top_shift(values, ref, tx.breakdown(values, WeightSpec("x", "x", {c: w.get(c, 0.0) for c in CRITERIA}))))
    stab = sum(1 for i in range(0, len(perturb), 2) if perturb[i][0] and perturb[i + 1][0])
    out["sensitivity_detail"] = {
        "yield_weight_pm10pct": {"top_unchanged_share": stab / len(fronts),
                                 "alternative_top_rank_median": statistics.median(r[1] for r in perturb),
                                 "alternative_top_rank_max": max(r[1] for r in perturb),
                                 "closeness_gap_median": statistics.median(r[2] for r in perturb),
                                 "max_objective_change_pct_median": statistics.median(r[3] for r in perturb)}}
    ent, cri = [], []
    for f in fronts:
        values = ts.criteria_for(f["plans"], f["attrs"], f["budget"], ranking.OBJECTIVES)
        G = np.column_stack([ranking.criteria_goodness({k: values[k]}, tx.directions([k]))[k] for k in ranking.OBJECTIVES])
        if (G.std(axis=0) > 0).all():
            ent.append(entropy_weights(G))
            cri.append(critic_weights(G))
    out["sensitivity"] = {
        "rank_sum_vs_roc": agree,
        "balanced_top_stable_under_yield_weight_pm10pct": stab / len(fronts),
        "entropy_weights_median": dict(zip(ranking.OBJECTIVES, np.median(ent, axis=0).round(4).tolist())),
        "critic_weights_median": dict(zip(ranking.OBJECTIVES, np.median(cri, axis=0).round(4).tolist())),
    }
    print("\nRank-sum vs ROC weights, same #1: " + ", ".join(f"{p} {v['top_agreement']:.0%}" for p, v in agree.items()))
    for p, v in agree.items():
        print(f"  {p}: ROC #1 ranks {v['roc_top_rank_median']} (median) under rank-sum, closeness gap {v['closeness_gap_median']:.4f}, "
              f"largest objective change {v['max_objective_change_pct_median']:.1f}%")
    d = out["sensitivity_detail"]["yield_weight_pm10pct"]
    print(f"Balanced #1 unchanged for yield weight 0.27 and 0.33: {stab / len(fronts):.0%}; the new #1 ranks "
          f"{d['alternative_top_rank_median']} (median, max {d['alternative_top_rank_max']}) under 0.30, closeness gap "
          f"{d['closeness_gap_median']:.4f}, largest objective change {d['max_objective_change_pct_median']:.1f}%")
    print(f"Entropy weights (median): {out['sensitivity']['entropy_weights_median']}")
    print(f"CRITIC weights (median):  {out['sensitivity']['critic_weights_median']}")

    # ---- runtime ----
    def timed(fn, reps=20):
        t0 = time.perf_counter()
        for _ in range(reps):
            fn()
        return (time.perf_counter() - t0) / reps * 1000

    t_legacy, t_profile, t_compare, t_explain = [], [], [], []
    for f in fronts[:: max(1, len(fronts) // 24)]:
        t_legacy.append(timed(lambda: ranking.rank_plans(f["plans"], f["conf"], preference="balanced")))
        t_profile.append(timed(lambda: ts.rank_front(f["plans"], f["conf"], resolve("sustainability"), f["attrs"], f["budget"])))
        t_compare.append(timed(lambda: ts.profile_comparison(f["plans"], f["attrs"], f["budget"], resolve("balanced"))))
        t_explain.append(timed(lambda: ts.ranking_explanation(f["plans"], f["attrs"], f["budget"], resolve("profit"))))
    out["runtime_ms"] = {"published_ranking": statistics.median(t_legacy), "profile_ranking": statistics.median(t_profile),
                         "five_profile_comparison": statistics.median(t_compare), "ranking_explanation": statistics.median(t_explain)}
    print("\nRanking time per front (median ms): " + ", ".join(f"{k} {v:.2f}" for k, v in out["runtime_ms"].items()))
    print(f"Front size: median {statistics.median(out['front_sizes'])}, range {min(out['front_sizes'])}-{max(out['front_sizes'])}")

    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=1))
    if args.charts:
        charts(out, Path(args.charts))


def charts(out: dict, folder: Path):
    """Single-axis charts in the Okabe-Ito palette (fixed profile order)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    folder.mkdir(parents=True, exist_ok=True)
    colours = {"balanced": "#7f7f7f", "profit": "#E69F00", "water": "#0072B2", "sustainability": "#009E73", "low_cost": "#CC79A7"}
    labels = {p: PROFILES[p]["label"] for p in PROFILE_ORDER}

    # profile weights
    fig, ax = plt.subplots(figsize=(8, 4.2))
    width = 0.16
    xs = np.arange(len(CRITERIA))
    for i, p in enumerate(PROFILE_ORDER):
        w = profile_weights(p)
        ax.bar(xs + (i - 2) * width, [w[c] * 100 for c in CRITERIA], width - 0.02, color=colours[p], label=labels[p])
    ax.set_xticks(xs, [CRITERIA_META[c]["label"] for c in CRITERIA], rotation=30, ha="right")
    ax.set_ylabel("Weight (%)")
    ax.set_title("TOPSIS weights by profile")
    ax.legend(frameon=False, ncol=3, fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(folder / "topsis_profile_weights.png", dpi=150)
    plt.close(fig)

    # where Balanced's #1 lands, and share of fronts whose #1 changes
    fig, ax = plt.subplots(figsize=(6.5, 3.2))
    ps = PROFILE_ORDER[1:]
    vals = [out["profiles"][p]["top_differs_share"] * 100 for p in ps]
    ax.barh([labels[p] for p in ps], vals, color=[colours[p] for p in ps])
    for y, v in enumerate(vals):
        ax.text(v + 1, y, f"{v:.0f}%", va="center", fontsize=9)
    ax.set_xlim(0, 110)
    ax.set_xlabel("Fronts whose #1 plan differs from Balanced's (%)")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(folder / "topsis_top_plan_changes.png", dpi=150)
    plt.close(fig)

    # median per-hectare objectives of the #1 plan, relative to Balanced
    fig, ax = plt.subplots(figsize=(8, 4))
    keys = ("yield", "cost", "water", "env", "income")
    base = out["profiles"]["balanced"]["top_values_median"]
    for i, p in enumerate(ps):
        rel = [100 * (out["profiles"][p]["top_values_median"][k] - base[k]) / abs(base[k]) if base[k] else 0 for k in keys]
        ax.bar(np.arange(len(keys)) + (i - 1.5) * 0.2, rel, 0.18, color=colours[p], label=labels[p])
    ax.axhline(0, color="#404940", linewidth=0.8)
    ax.set_xticks(np.arange(len(keys)), [CRITERIA_META[k]["label"] for k in keys])
    ax.set_ylabel("Median #1 plan vs Balanced's (%)")
    ax.set_title("What each profile's top plan trades")
    ax.legend(frameon=False, ncol=2, fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(folder / "topsis_top_plan_objectives.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
