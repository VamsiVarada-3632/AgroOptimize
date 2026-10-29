"""
Charts and Markdown tables from a benchmark_fuzzy_models.py --json result.

    python3 scripts/report_fuzzy_benchmark.py results.json [--out docs/handbook/benchmarks/fuzzy_models]

One PNG per measure, single axis each. Models are coloured by role --
original, one improvement on its own, the cumulative chain, screened
candidates (also hatched) -- in the Okabe & Ito (2008) colour-blind-safe
palette, with a legend. Prints the tables used in
docs/handbook/FUZZY_BENCHMARK_RESULTS.md.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

ROLE = {"original": ("Original (published)", "#7f7f7f", None),
        "single": ("One improvement on its own", "#0072B2", None),
        "chain": ("Cumulative (1, 1+2, final)", "#D55E00", None),
        "screened": ("Screened candidate (rejected)", "#CC79A7", "//")}
SHORT = {"original": "Original", "I1 strong partition": "I1", "I2 IMD rainfall": "I2", "I3 pruned rules": "I3",
         "I1+I2": "I1+I2", "I1+I2+I3 (final)": "Final", "S1 product AND": "S1\nproduct AND",
         "S2 implicative caps (16, 19, 23)": "S2\ncaps"}


def role(name):
    if name == "original":
        return "original"
    if name.startswith("S"):
        return "screened"
    return "chain" if "+" in name else "single"


def bar_chart(models, values, title, ylabel, path, note=None, fmt="{:.3g}"):
    names = [m for m in models if values.get(m) is not None]
    fig, ax = plt.subplots(figsize=(8.4, 4.2), dpi=150)
    for i, m in enumerate(names):
        _, colour, hatch = ROLE[role(m)]
        ax.bar(i, values[m], width=0.62, color=colour, hatch=hatch, edgecolor="white", linewidth=2)
        ax.text(i, values[m], fmt.format(values[m]), ha="center", va="bottom", fontsize=8, color="#222")
    ax.set_xticks(range(len(names)), [SHORT.get(m, m) for m in names], fontsize=8.5)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_title(title, fontsize=11, loc="left")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#e5e5e5", linewidth=0.8)
    ax.set_axisbelow(True)
    used = []
    for m in names:
        if role(m) not in used:
            used.append(role(m))
    ax.legend(handles=[Patch(facecolor=ROLE[r][1], hatch=ROLE[r][2], edgecolor="white", label=ROLE[r][0]) for r in used],
              fontsize=7.5, frameon=False, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    if note:
        fig.text(0.01, 0.01, note, fontsize=7, color="#555")
    fig.tight_layout(rect=(0, 0.04 if note else 0, 1, 1))
    fig.savefig(path)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("--out", default="docs/handbook/benchmarks/fuzzy_models")
    args = ap.parse_args()
    data = json.loads(Path(args.results).read_text())
    M = data["models"]
    order = ["original", "I1 strong partition", "I2 IMD rainfall", "I3 pruned rules", "I1+I2", "I1+I2+I3 (final)",
             "S1 product AND", "S2 implicative caps (16, 19, 23)"]
    order = [m for m in order if m in M]
    engine = [m for m in order if not M[m].get("screened_only")]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    def col(fn, models=order):
        res = {}
        for m in models:
            try:
                res[m] = fn(M[m])
            except (KeyError, TypeError):
                res[m] = None
        return res

    charts = [
        ("monotonicity_largest_violation.png", col(lambda r: r["monotonicity"]["yield_vs_storage"]["largest"]),
         "Largest drop in yield confidence when storage rises", "Largest violation (0-1 scale)", None, "{:.3f}"),
        ("monotonicity_steps_over_001.png", col(lambda r: r["monotonicity"]["yield_vs_storage"]["steps_over_0.01_pct"]),
         "Grid steps where yield confidence falls by > 0.01 as storage rises", "Share of steps (%)", None, "{:.1f}"),
        ("robustness_yield_noise.png", col(lambda r: r["noise_change_mean"][0]),
         "Mean change in yield confidence under input noise", "Mean |change| (0-1 scale)",
         "Noise: rainfall ±5 pp, storage ±2 pp, fertility ±2, all 8 corners around each of 60 profiles.", "{:.4f}"),
        ("robustness_risk_noise.png", col(lambda r: r["noise_change_mean"][1]),
         "Mean change in irrigation risk under input noise", "Mean |change| (0-1 scale)",
         "Noise: rainfall ±5 pp, storage ±2 pp, fertility ±2, all 8 corners around each of 60 profiles.", "{:.4f}"),
        ("signal_to_noise_risk.png", col(lambda r: r["signal_to_noise"][1]),
         "Irrigation risk: spread across profiles ÷ change under noise", "Signal-to-noise ratio", None, "{:.2f}"),
        ("signal_to_noise_yield.png", col(lambda r: r["signal_to_noise"][0]),
         "Yield confidence: spread across profiles ÷ change under noise", "Signal-to-noise ratio", None, "{:.2f}"),
        ("coverage_min_epsilon.png", col(lambda r: min(r["epsilon_completeness"].values())),
         "Weakest input coverage (minimum ε-completeness)", "ε-completeness (target ≥ 0.5)", None, "{:.3f}"),
        ("imd_label_agreement.png", col(lambda r: r["imd_label_agreement"]),
         "Dataset profiles whose rainfall label matches IMD (of 60)", "Profiles", None, "{:.0f}"),
        ("rules_fired_per_profile.png", col(lambda r: r["fired_per_profile"]),
         "Rules fired per dataset profile", "Mean rules fired", None, "{:.2f}"),
        ("rules_zero_importance.png", col(lambda r: r["zero_importance_fired_per_profile"], engine),
         "Fired rules with no influence on the output, per profile", "Mean rules", None, "{:.2f}"),
        ("rule_support.png", col(lambda r: r["rule_support_mean"]),
         "Strongest rule firing per profile (rule support)", "Mean max firing strength", None, "{:.3f}"),
        ("runtime_inference.png", col(lambda r: r["inference_ms_per_call"], engine),
         "Fuzzy inference time per call (uncached)", "ms per call", None, "{:.2f}"),
        ("runtime_explanation.png", col(lambda r: r["explanation_ms_per_call"], engine),
         "Rule-level explanation time per call", "ms per call", None, "{:.2f}"),
        ("memory_peak.png", col(lambda r: r["peak_memory_kb_build_and_60_inferences"], engine),
         "Peak memory: build the system + 60 inferences", "KB", None, "{:.0f}"),
        ("pipeline_hypervolume.png", col(lambda r: r["pipeline"]["hypervolume"], engine),
         "NSGA-II hypervolume (each model vs. its own reference front)", "Hypervolume (higher is better)", None, "{:.4f}"),
        ("pipeline_igd_plus.png", col(lambda r: r["pipeline"]["igd_plus"], engine),
         "NSGA-II IGD+ (each model vs. its own reference front)", "IGD+ (lower is better)", None, "{:.4f}"),
        ("pipeline_runtime.png", col(lambda r: r["pipeline"]["runtime_s_mean"], engine),
         "NSGA-II run time per optimisation", "Seconds", None, "{:.3f}"),
        ("stability_topsis_tau.png", col(lambda r: r["pipeline"]["topsis_kendall_tau_mean"], engine),
         "TOPSIS ranking stability under input noise", "Mean Kendall τ (1 = identical order)", None, "{:.3f}"),
        ("stability_land_moved.png", col(lambda r: r["pipeline"]["top_plan_land_moved_pct_mean"], engine),
         "Land reallocated in the top plan under input noise", "Mean share of land moved (%)", None, "{:.1f}"),
    ]
    for fname, vals, title, ylabel, note, fmt in charts:
        if any(v is not None for v in vals.values()):
            bar_chart(order, vals, title, ylabel, out / fname, note, fmt)

    # ---- Markdown tables ----
    def row(cells):
        print("| " + " | ".join(str(c) for c in cells) + " |")

    print("\n### Fuzzy layer\n")
    row(["Model", "Rules", "Effective", "ε (rain / storage / fert.)", "Largest monotonicity drop", "Steps > 0.01 (%)",
         "IMD labels", "Fired / profile", "Zero-influence fired", "Rule support"])
    row(["---"] * 10)
    for m in order:
        r = M[m]
        e = r["epsilon_completeness"]
        mono = r["monotonicity"]
        row([m, r["rules"], r["effective_rules"], f"{e['rainfall_dev']} / {e['water_storage']} / {e['soil_fert']}",
             f"{max(v['largest'] for v in mono.values()):.4f}",
             " / ".join(f"{v['steps_over_0.01_pct']}" for v in mono.values()), f"{r['imd_label_agreement']}/60",
             r["fired_per_profile"], r.get("zero_importance_fired_per_profile", "–"), r["rule_support_mean"]])
    print("\n### Outputs, confidence and robustness\n")
    row(["Model", "Mean yield conf.", "Mean risk", "Std yield / risk", "Noise mean yield / risk", "Noise max yield / risk",
         "SNR yield / risk", "Output-term membership yield / risk"])
    row(["---"] * 8)
    for m in order:
        r = M[m]
        t = r.get("output_term_membership_mean") or {}
        row([m, r["output_mean"][0], r["output_mean"][1], f"{r['output_std'][0]} / {r['output_std'][1]}",
             f"{r['noise_change_mean'][0]} / {r['noise_change_mean'][1]}",
             f"{r['noise_change_max'][0]} / {r['noise_change_max'][1]}",
             f"{r['signal_to_noise'][0]} / {r['signal_to_noise'][1]}",
             f"{t.get('yield_conf', '–')} / {t.get('irrigation_risk', '–')}"])
    print("\n### Runtime and memory\n")
    row(["Model", "Inference (ms/call)", "Explanation (ms/call)", "Peak memory (KB)"])
    row(["---"] * 4)
    for m in engine:
        r = M[m]
        row([m, r["inference_ms_per_call"], r["explanation_ms_per_call"], r["peak_memory_kb_build_and_60_inferences"]])
    if all("pipeline" in M[m] for m in engine):
        print("\n### Pipeline (NSGA-II original engine, TOPSIS balanced)\n")
        row(["Model", "Runtime (s)", "HV", "GD", "IGD", "IGD+", "Spread", "Spacing", "Feasible pop. (%)",
             "Front size", "TOPSIS τ mean / min", "Land moved (%)", "Top crop kept (%)"])
        row(["---"] * 13)
        for m in engine:
            p = M[m]["pipeline"]
            row([m, p["runtime_s_mean"], p["hypervolume"], p["gd"], p["igd"], p["igd_plus"], p["spread"], p["spacing"],
                 p["population_feasible_pct"], p["feasible_front_mean"],
                 f"{p['topsis_kendall_tau_mean']} / {p['topsis_kendall_tau_min']}",
                 p["top_plan_land_moved_pct_mean"], p["top_crop_unchanged_pct"]])
        paired_tests(M, engine, row)


def paired_tests(M, engine, row):
    """Each model against the original on the same (problem, seed) runs and
    the same noise cases: Wilcoxon signed-rank (two-sided; zero differences
    dropped), and an exact binomial test on the discordant pairs for the
    top-crop indicator (McNemar)."""
    from scipy.stats import binomtest, wilcoxon

    base = M["original"]["pipeline"]
    keyed = {(r["problem"], r["seed"]): r for r in base["per_run"]}
    print("\n### Paired tests against the original\n")
    row(["Model", "Metric", "Original", "Model", "Change", "p"])
    row(["---"] * 6)
    for m in engine:
        if m == "original":
            continue
        p = M[m]["pipeline"]
        runs = [(keyed[(r["problem"], r["seed"])], r) for r in p["per_run"]]
        series = [(k, [a[k] for a, _ in runs], [b[k] for _, b in runs]) for k in
                  ("seconds", "hypervolume", "gd", "igd", "igd_plus", "spread", "spacing")]
        series += [(k, base["stability_cases"][k], p["stability_cases"][k])
                   for k in ("topsis_kendall_tau", "top_plan_land_moved_pct")]
        for k, a, b in series:
            a, b = np.array(a, float), np.array(b, float)
            diff = b - a
            pval = wilcoxon(a, b).pvalue if np.any(np.abs(diff) > 1e-12) else 1.0
            change = (b.mean() - a.mean()) / abs(a.mean()) * 100 if a.mean() else float("nan")
            row([m, k, f"{a.mean():.4g}", f"{b.mean():.4g}", f"{change:+.1f} %", f"{pval:.3g}"])
        a = np.array(base["stability_cases"]["top_crop_unchanged"], bool)
        b = np.array(p["stability_cases"]["top_crop_unchanged"], bool)
        n01, n10 = int(np.sum(~a & b)), int(np.sum(a & ~b))
        pval = binomtest(n01, n01 + n10).pvalue if n01 + n10 else 1.0
        row([m, "top_crop_unchanged", f"{a.mean() * 100:.1f} %", f"{b.mean() * 100:.1f} %",
             f"{n01} gained / {n10} lost", f"{pval:.3g}"])


if __name__ == "__main__":
    main()
