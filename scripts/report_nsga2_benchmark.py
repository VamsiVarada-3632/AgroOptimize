"""
Charts and Markdown tables from a benchmark_nsga2.py --json result.

    python scripts/report_nsga2_benchmark.py results.json [--out docs/handbook/benchmarks]

Writes one PNG per measure (paired difference to the baseline, runtime,
memory, convergence) and prints the Markdown tables used in
docs/handbook/NSGAII_BENCHMARK_RESULTS.md. Every chart has a single axis;
variants are coloured by role (baseline / original + switch / enhanced +
switch) with a legend, in a colour-blind-safe palette (Okabe & Ito 2008).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.optimization.metrics import summarise_runs  # noqa: E402

ROLE_COLOURS = {"baseline": "#7f7f7f", "original": "#0072B2", "enhanced": "#D55E00"}
LABELS = {
    "original": "original (published)",
    "enhanced": "enhanced",
    "lhs_initialization": "LHS initialisation",
    "constraint_aware_initialization": "constraint-aware init.",
    "adaptive_crossover@adaptive_crossover_params.schedule=diversity": "diversity crossover",
    "duplicate_avoidance": "duplicate avoidance",
    "early_stopping@early_stopping_params.criterion=objective_space": "early stop (pymoo default)",
    "early_stopping@early_stopping_params.criterion=objective_space+early_stopping_params.ftol=0.05"
    "+early_stopping_params.xtol=0.005": "early stop (pymoo, loose)",
    "parallel_evaluation": "parallel evaluation",
}


OVERRIDES: dict = {}


def label(variant: str) -> str:
    if variant in OVERRIDES:
        return OVERRIDES[variant]
    if variant in ("original", "enhanced"):
        return LABELS[variant]
    base, _, rest = variant.partition("+")
    return f"{base} + {LABELS.get(rest, rest)}"


def role(variant: str) -> str:
    if variant in ("original", "enhanced"):
        return "baseline"
    return variant.split("+")[0]


def paired(runs, variant, base, key):
    by = {(r["problem"], r["seed"]): r[key] for r in runs if r["variant"] == base}
    out = []
    for r in runs:
        if r["variant"] == variant and (r["problem"], r["seed"]) in by:
            a, b = r[key], by[(r["problem"], r["seed"])]
            if a is not None and b is not None and np.isfinite(a) and np.isfinite(b):
                out.append(a - b)
    return out


def _style(ax, title, xlabel):
    ax.set_title(title, loc="left", fontsize=11)
    ax.set_xlabel(xlabel)
    ax.grid(axis="x", color="#e6e6e6", linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def _legend(ax):
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=c, label=n) for n, c in
                       (("baseline mode", ROLE_COLOURS["baseline"]), ("original + switch", ROLE_COLOURS["original"]),
                        ("enhanced + switch", ROLE_COLOURS["enhanced"]))],
              loc="lower right", frameon=False, fontsize=8)


def difference_chart(runs, variants, key, title, xlabel, out, higher_is_better):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rows = []
    for v in variants:
        if v == "original":
            continue
        base = "enhanced" if v.startswith("enhanced+") else "original"
        d = paired(runs, v, base, key)
        if d:
            q1, med, q3 = np.percentile(d, [25, 50, 75])
            rows.append((label(v) + ("" if base == "original" else "  (vs enhanced)"), med, q1, q3, role(v)))
    fig, ax = plt.subplots(figsize=(8, 0.42 * len(rows) + 1.4))
    for i, (name, med, q1, q3, r) in enumerate(reversed(rows)):
        ax.plot([q1, q3], [i, i], color=ROLE_COLOURS[r], linewidth=2, solid_capstyle="round")
        ax.plot([med], [i], "o", color=ROLE_COLOURS[r], markersize=7, markeredgecolor="white", markeredgewidth=2)
    ax.axvline(0, color="#4d4d4d", linewidth=1)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in reversed(rows)], fontsize=9)
    better = "right" if higher_is_better else "left"
    _style(ax, title, f"{xlabel}\nmedian and inter-quartile range of paired differences (same problem and seed); better to the {better}")
    _legend(ax)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def bar_chart(values, title, xlabel, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    items = list(values.items())
    fig, ax = plt.subplots(figsize=(8, 0.42 * len(items) + 1.4))
    for i, (v, x) in enumerate(reversed(items)):
        ax.barh(i, x, height=0.6, color=ROLE_COLOURS[role(v)])
        ax.text(x, i, f"  {x:.3g}", va="center", fontsize=8, color="#333333")
    ax.set_yticks(range(len(items)))
    ax.set_yticklabels([label(v) for v, _ in reversed(items)], fontsize=9)
    _style(ax, title, xlabel)
    _legend(ax)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def convergence_chart(runs, variants, out, step=5):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    # Per problem, hypervolume relative to the best final value of any run.
    best = defaultdict(float)
    for r in runs:
        best[r["problem"]] = max(best[r["problem"]], r["hypervolume"])
    fig, ax = plt.subplots(figsize=(8, 4.2))
    palette = ["#7f7f7f", "#0072B2", "#D55E00", "#009E73", "#CC79A7"]
    for colour, v in zip(palette, variants):
        curves = [np.array(r["hv_history"]) / best[r["problem"]] for r in runs
                  if r["variant"] == v and r["hv_history"] and best[r["problem"]] > 0]
        if not curves:
            continue
        n = min(len(c) for c in curves)
        med = np.median([c[:n] for c in curves], axis=0)
        gens = (np.arange(n) + 1) * step
        ax.plot(gens, med, color=colour, linewidth=2, label=label(v))
    ax.set_ylabel("hypervolume / best final")
    _style(ax, "Convergence: median hypervolume over all problems and seeds", "generation")
    ax.grid(axis="y", color="#e6e6e6", linewidth=0.8)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def markdown_tables(data):
    runs, variants = data["runs"], data["variants"]
    table = data["table"]
    lines = ["| Variant | HV | GD | IGD | IGD+ | Spread | Spacing | Front | Constr. sat. | Dup. rejected | Gen. to 99 % | Evals | Time (s) | Peak MB |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    mem = data.get("peak_memory_mb", {})
    for v in variants:
        t = table[v]
        g = t["median_generations_to_99pct_original_hv"]
        lines.append(f"| {label(v)} | {t['hypervolume']:.4f} | {t['gd']:.4f} | {t['igd']:.4f} | {t['igd_plus']:.4f} | "
                     f"{t['spread']:.3f} | {t['spacing']:.3f} | {t['front_size']:.0f} | {t['constraint_satisfaction']:.2f} | "
                     f"{t['duplicates_rejected']:.0f} | {g if g is not None else '–'} | {t['evaluations']:.0f} | "
                     f"{t['seconds']:.3f} | {mem.get(v, float('nan')):.2f} |")
    print("\n".join(lines))
    for title, paired_ in (("original", data["paired"]), ("enhanced", data.get("paired_vs_enhanced", {}))):
        if not paired_:
            continue
        print(f"\nPaired vs {title}: better/worse (Wilcoxon p)\n")
        print("| Variant | HV | GD | IGD+ | Spread | Time |")
        print("|---|---|---|---|---|---|")
        for v, s in paired_.items():
            cells = []
            for m in ("hypervolume", "gd", "igd_plus", "spread", "seconds"):
                c = s[m]
                p = c["p_value"]
                cells.append(f"{c['better']}/{c['worse']} ({'–' if p != p else f'{p:.2g}'})")
            print(f"| {label(v)} | " + " | ".join(cells) + " |")
    print("\nMedian and IQR of hypervolume per variant\n")
    for v in variants:
        s = summarise_runs([r["hypervolume"] for r in runs if r["variant"] == v])
        print(f"- {label(v)}: {s['median']:.4f} [{s['q1']:.4f}, {s['q3']:.4f}] (n={s['n']})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json_file")
    ap.add_argument("--out", default="docs/handbook/benchmarks")
    ap.add_argument("--prefix", default="", help="prefix for the chart file names")
    ap.add_argument("--label", action="append", default=[], help='variant=text, e.g. "enhanced=enhanced (PR #12)"')
    args = ap.parse_args()
    for item in args.label:
        variant, _, text = item.partition("=")
        OVERRIDES[variant] = text
    data = json.loads(Path(args.json_file).read_text())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    runs, variants = data["runs"], data["variants"]

    difference_chart(runs, variants, "hypervolume", "Hypervolume: paired difference to the baseline mode",
                     "Δ hypervolume", out / f"{args.prefix}hypervolume_difference.png", True)
    difference_chart(runs, variants, "igd_plus", "IGD+: paired difference to the baseline mode",
                     "Δ IGD+", out / f"{args.prefix}igd_plus_difference.png", False)
    difference_chart(runs, variants, "gd", "Generational distance: paired difference to the baseline mode",
                     "Δ GD", out / f"{args.prefix}gd_difference.png", False)
    difference_chart(runs, variants, "spread", "Spread: paired difference to the baseline mode",
                     "Δ generalised spread", out / f"{args.prefix}spread_difference.png", False)
    bar_chart({v: statistics.median(r["seconds"] for r in runs if r["variant"] == v) for v in variants},
              "Runtime per run (median, convergence history tracked)", "seconds", out / f"{args.prefix}runtime.png")
    if data.get("peak_memory_mb"):
        bar_chart(data["peak_memory_mb"], "Peak traced memory per run (median of 4 problems)", "MB", out / f"{args.prefix}memory.png")
    focus = [v for v in ("original", "original+duplicate_avoidance", "enhanced", "enhanced+duplicate_avoidance",
                         "enhanced+duplicate_avoidance+constraint_aware_initialization") if v in variants]
    convergence_chart(runs, focus, out / f"{args.prefix}convergence.png")
    markdown_tables(data)


if __name__ == "__main__":
    main()
