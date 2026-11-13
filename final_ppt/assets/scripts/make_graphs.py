"""Experimental result plots for the review slides, from real project outputs only.

Inputs
  final_ppt/assets/data/pipeline_run.json            one real run (run_pipeline_snapshot.py)
  docs/handbook/benchmarks/runtime/*.json            measured runtime, published-v1 vs official
  the official database (via app.data / app.datasets) dataset rows and district coverage

Every graph is written as PNG (300 dpi), SVG and PDF to final_ppt/graphs/, and the numbers
behind each one to final_ppt/assets/data/graph_data.json.

Usage (from the repository root):  python final_ppt/assets/scripts/make_graphs.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "final_ppt" / "graphs"
DATA = ROOT / "final_ppt" / "assets" / "data"

# Reference palette (validated: blue/orange/aqua pass CVD separation on the light surface)
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "axes.titleweight": "bold", "axes.titlesize": 13,
    "axes.titlecolor": INK, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "legend.frameon": False, "svg.fonttype": "none",
})
written = []
graph_data = {}


def save(fig, name, data):
    fig.tight_layout(rect=(0, 0.045, 1, 1))
    for ext in ("png", "svg", "pdf"):
        path = OUT / f"{name}.{ext}"
        fig.savefig(path, dpi=300 if ext == "png" else None)
        written.append(path.relative_to(ROOT).as_posix())
    plt.close(fig)
    graph_data[name] = data


def source(fig, text):
    fig.text(0.01, 0.005, text, fontsize=8, color=INK2, ha="left", va="bottom")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    run = json.loads((DATA / "pipeline_run.json").read_text())
    req = run["request"]
    case = f"{req['location']} {req['season']} {req['year']}, {req['total_land_ha']:g} ha, seed {run['environment']['seed']}"

    # 1. Convergence: hypervolume per generation
    hist = run["convergence_history"]
    g = [h["generation"] for h in hist]
    hv = [h["hypervolume"] for h in hist]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(g, hv, color=BLUE, lw=2)
    ax.annotate(f"{hv[-1]:.3f} at generation {g[-1]}", (g[-1], hv[-1]), xytext=(-10, -70),
                textcoords="offset points", ha="right", color=INK,
                arrowprops={"arrowstyle": "-", "color": INK2, "lw": 0.8})
    ax.set(title="NSGA-II convergence (hypervolume per generation)", xlabel="Generation",
           ylabel="Hypervolume (objectives normalised per run)")
    source(fig, f"Source: one real run, {case}; app/optimization/nsga2_runner.py extract_convergence_history")
    save(fig, "convergence_hypervolume", {"generation": g, "hypervolume": hv})

    # 2. Convergence of the best and mean yield
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(g, [h["best_yield_tonnes"] for h in hist], color=BLUE, lw=2, label="Best in population")
    ax.plot(g, [h["mean_yield_tonnes"] for h in hist], color=ORANGE, lw=2, label="Population mean")
    ax.set(title="NSGA-II convergence (expected yield)", xlabel="Generation", ylabel="Expected yield (t, 5 ha)")
    ax.legend(loc="lower right")
    for key, col, lab in (("best_yield_tonnes", BLUE, "best"), ("mean_yield_tonnes", ORANGE, "mean")):
        ax.annotate(f"{lab} {hist[-1][key]:.2f} t", (g[-1], hist[-1][key]), xytext=(-6, 6),
                    textcoords="offset points", ha="right", color=INK, fontsize=9)
    source(fig, f"Source: one real run, {case}")
    save(fig, "convergence_yield", {"generation": g, "best": [h["best_yield_tonnes"] for h in hist],
                                    "mean": [h["mean_yield_tonnes"] for h in hist]})

    # 3/4. Pareto front projections with the recommended plan
    front = run["front"]
    top = run["ranked_plans"][0]
    for name, xk, xl, xs in (("pareto_front_yield_cost", "cost_rs", "Cultivation cost (₹ lakh, 5 ha)", 1e5),
                             ("pareto_front_yield_irrigated", "irrigated_ha", "Irrigated area (ha-equivalents)", 1)):
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.scatter([p[xk] / xs for p in front], [p["yield_tonnes"] for p in front], s=36, color=BLUE,
                   edgecolor=SURFACE, linewidth=1, label=f"Pareto-optimal plans ({len(front)})")
        ax.scatter([top[xk] / xs], [top["yield_tonnes"]], s=110, color=ORANGE, edgecolor=SURFACE, linewidth=2,
                   marker="D", label="TOPSIS rank 1 (recommended)", zorder=3)
        ax.annotate("recommended", (top[xk] / xs, top["yield_tonnes"]), xytext=(10, -16), textcoords="offset points", color=INK)
        ax.set(title="Pareto front (4 objectives, 2-D projection)", xlabel=xl, ylabel="Expected yield (t, 5 ha)")
        ax.legend(loc="lower right")
        source(fig, f"Source: feasible first front of one real run, {case}")
        save(fig, name, {"x": [p[xk] for p in front], "yield": [p["yield_tonnes"] for p in front],
                         "recommended": {"x": top[xk], "yield": top["yield_tonnes"]}})

    # 5. TOPSIS closeness of the top 15 plans
    plans = run["ranked_plans"][:15]
    fig, ax = plt.subplots(figsize=(8, 5.5))
    labels = [f"#{p['rank']}" for p in plans]
    vals = [p["composite_score"] for p in plans]
    cols = [ORANGE if p["rank"] == 1 else BLUE for p in plans]
    ax.barh(labels[::-1], vals[::-1], color=cols[::-1], height=0.7, edgecolor=SURFACE, linewidth=2)
    for i, v in enumerate(vals[::-1]):
        ax.text(v + 0.004, i, f"{v:.3f}", va="center", fontsize=9, color=INK)
    ax.set(title="TOPSIS closeness of the top 15 ranked plans (balanced profile)", xlabel="Closeness coefficient",
           ylabel="Plan rank")
    ax.set_xlim(0, max(vals) * 1.12)
    ax.grid(axis="y", visible=False)
    source(fig, f"Source: {run['stages'][6]['plans_ranked']} plans ranked by TOPSIS, {case}")
    save(fig, "topsis_scores_top15", {"rank": [p["rank"] for p in plans], "closeness": vals})

    # 6. Crop ranking: mean land share of each crop over the 50 ranked plans
    share = defaultdict(float)
    for p in run["ranked_plans"]:
        for c, a in zip(p["crop_names"], p["allocation_percent"]):
            share[c] += a / len(run["ranked_plans"])
    crops = sorted(share, key=share.get)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.barh(crops, [share[c] for c in crops], color=BLUE, height=0.65, edgecolor=SURFACE, linewidth=2)
    for i, c in enumerate(crops):
        ax.text(share[c] + 0.6, i, f"{share[c]:.1f} %", va="center", fontsize=9, color=INK)
    ax.set(title="Crop ranking: mean land share across the 50 ranked plans", xlabel="Mean share of farm area (%)")
    ax.set_xlim(0, max(share.values()) * 1.15)
    ax.grid(axis="y", visible=False)
    source(fig, f"Source: candidate crops from the official data, {case}")
    save(fig, "crop_ranking_land_share", {c: share[c] for c in crops})

    # 7. Objective comparison of the top 5 plans (small multiples, one unit each)
    top5 = run["ranked_plans"][:5]
    objs = [("yield_tonnes", "Expected yield (t)", "higher is better"), ("cost_rs", "Cultivation cost (₹ lakh)", "lower is better"),
            ("irrigated_ha", "Irrigated area (ha-eq.)", "lower is better"), ("env_impact_score", "Nutrient load (kg NPK)", "lower is better")]
    fig, axes = plt.subplots(1, 4, figsize=(13, 4))
    for ax, (k, lab, note) in zip(axes, objs):
        sc = 1e5 if k == "cost_rs" else 1
        v = [p[k] / sc for p in top5]
        ax.bar([f"#{p['rank']}" for p in top5], v, color=[ORANGE] + [BLUE] * 4, width=0.65, edgecolor=SURFACE, linewidth=2)
        ax.set_title(f"{lab}\n({note})", fontsize=11)
        ax.grid(axis="x", visible=False)
    fig.suptitle("Objective values of the five best-ranked plans (rank 1 = recommended)", fontweight="bold", color=INK)
    source(fig, f"Source: TOPSIS-ranked Pareto plans, {case}")
    save(fig, "objective_comparison_top5", {p["rank"]: {k: p[k] for k, *_ in objs} for p in top5})

    # 8. Runtime official vs legacy (published-v1), measured with scripts/benchmark_runtime.py
    bdir = ROOT / "docs" / "handbook" / "benchmarks" / "runtime"
    v1 = json.loads((bdir / "published_v1.json").read_text())
    off = json.loads((bdir / "official.json").read_text())
    stages = [("Import app", lambda b: b["startup"]["import_s"]["median"] * 1000),
              ("Dataset load (cold)", lambda b: b["load"]["cold_s"]["median"] * 1000),
              ("Preprocess (warm)", lambda b: b["preprocess"]["Salem:Rabi"]["warm_s"]["median"] * 1000),
              ("Optimisation run", lambda b: b["optimize"]["all_runs_s"]["median"] * 1000),
              ("POST /api/farm-plans", lambda b: b["api"]["POST /api/farm-plans"]["median_ms"])]
    fig, axes = plt.subplots(1, 5, figsize=(14, 4))
    rt = {}
    for ax, (lab, f) in zip(axes, stages):
        a, b = f(v1), f(off)
        rt[lab] = {"published_v1_ms": a, "official_ms": b}
        ax.bar(["Legacy\n(v1)", "Official"], [a, b], color=[BLUE, ORANGE], width=0.6, edgecolor=SURFACE, linewidth=2)
        for i, v in enumerate((a, b)):
            ax.text(i, v, f"{v:,.1f}", ha="center", va="bottom", fontsize=9, color=INK)
        ax.set_title(lab, fontsize=11)
        ax.set_ylabel("ms (median)" if ax is axes[0] else "")
        ax.set_ylim(0, max(a, b) * 1.18)
        ax.grid(axis="x", visible=False)
    fig.suptitle("Runtime: synthetic v1 data vs official datasets (same script, same machine)", fontweight="bold", color=INK)
    source(fig, "Source: scripts/benchmark_runtime.py on tag published-v1 and the migrated backend; medians over fresh processes / 18 runs")
    save(fig, "runtime_official_vs_legacy", rt)

    # 9. Optimisation runtime per case
    cases = list(off["optimize"]["per_case"])
    fig, ax = plt.subplots(figsize=(10, 4.5))
    xs = range(len(cases))
    va = [v1["optimize"]["per_case"][c]["runtime_s"]["median"] * 1000 for c in cases]
    vb = [off["optimize"]["per_case"][c]["runtime_s"]["median"] * 1000 for c in cases]
    ax.bar([x - 0.19 for x in xs], va, width=0.36, color=BLUE, label="Legacy (v1)", edgecolor=SURFACE, linewidth=2)
    ax.bar([x + 0.19 for x in xs], vb, width=0.36, color=ORANGE, label="Official", edgecolor=SURFACE, linewidth=2)
    ax.set_xticks(list(xs), [c.replace(":", "\n") for c in cases])
    ax.set_title("Optimisation runtime per district-season (median of 3 seeds)", pad=44)
    ax.set_ylabel("ms")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=2)
    ax.set_ylim(0, max(va + vb) * 1.1)
    ax.grid(axis="x", visible=False)
    source(fig, "Source: run_pipeline (preprocessing, fuzzy, NSGA-II 80 x 200, TOPSIS), scripts/benchmark_runtime.py")
    save(fig, "optimisation_runtime_per_case", {c: {"published_v1_ms": a, "official_ms": b} for c, a, b in zip(cases, va, vb)})

    # 10. Official dataset coverage: clean rows per dataset (dataset registry)
    reg = run["stages"][2]["registry"]
    reg = sorted(reg, key=lambda d: d["rows_clean"])
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh([d["name"] for d in reg], [d["rows_clean"] for d in reg], color=BLUE, height=0.65, edgecolor=SURFACE, linewidth=2)
    for i, d in enumerate(reg):
        ax.text(d["rows_clean"] * 1.02 + 50, i, f"{d['rows_clean']:,}", va="center", fontsize=9, color=INK)
    ax.set(title="Official datasets loaded (report year 2024-25)", xlabel="Clean rows in the database")
    ax.set_xlim(0, max(d["rows_clean"] for d in reg) * 1.15)
    ax.grid(axis="y", visible=False)
    source(fig, f"Source: dataset_registry table (GET /api/datasets); {sum(d['rows_clean'] for d in reg):,} rows in total")
    save(fig, "official_dataset_rows", {d["name"]: d["rows_clean"] for d in reg})

    # 11. District coverage / feature availability: every district x season through the real preprocessing
    from app import config
    from app.data import preprocessing as pp
    status = {}
    for loc in config.LOCATIONS:
        for season in config.AG_SEASONS:
            try:
                p = pp.get_region_season_profile(loc, season)
                status[f"{loc}:{season}"] = "Plans + fuzzy stage" if p.fuzzy_available else "Plans, fuzzy not applied (no reservoir reading)"
            except ValueError:
                status[f"{loc}:{season}"] = "No plans (< 2 crops with complete official data)"
    cats = ["Plans + fuzzy stage", "Plans, fuzzy not applied (no reservoir reading)", "No plans (< 2 crops with complete official data)"]
    colors = [BLUE, ORANGE, AQUA]
    counts = {s: Counter(v for k, v in status.items() if k.endswith(":" + s)) for s in config.AG_SEASONS}
    fig, ax = plt.subplots(figsize=(10, 3.8))
    for si, s in enumerate(config.AG_SEASONS):
        left = 0
        for c, col in zip(cats, colors):
            n = counts[s][c]
            if n:
                ax.barh(si, n, left=left, color=col, height=0.55, edgecolor=SURFACE, linewidth=2)
                ax.text(left + n / 2, si, str(n), ha="center", va="center", color=INK, fontsize=10, fontweight="bold")
            left += n
    ax.set_yticks(range(len(config.AG_SEASONS)), config.AG_SEASONS)
    ax.set(title=f"Coverage of the {len(config.LOCATIONS)} official districts by season", xlabel="Districts")
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=col, label=c) for c, col in zip(cats, colors)],
              loc="upper center", bbox_to_anchor=(0.5, -0.28), ncol=1, fontsize=9)
    ax.grid(axis="y", visible=False)
    source(fig, "Source: get_region_season_profile() for every district and season on the official database")
    save(fig, "district_feature_coverage", {"by_case": status, "counts": {s: dict(counts[s]) for s in counts}})

    (DATA / "graph_data.json").write_text(json.dumps(graph_data, indent=2, default=str))
    print("\n".join(written))


if __name__ == "__main__":
    main()
