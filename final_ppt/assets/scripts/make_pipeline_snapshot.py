"""Pipeline execution snapshot (PNG via HTML, and Markdown) from final_ppt/assets/data/pipeline_run.json.

Every value printed comes from that file, which run_pipeline_snapshot.py recorded from one real run.
Usage (from the repository root):  python final_ppt/assets/scripts/make_pipeline_snapshot.py
then render: render_assets.py final_ppt/diagrams/pipeline_execution.html
"""
from __future__ import annotations

import html
import re
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
run = json.loads((ROOT / "final_ppt" / "assets" / "data" / "pipeline_run.json").read_text())
S = {s["stage"]: s for s in run["stages"]}
req = run["request"]


def short(detail):
    """The validation message itself: pydantic's 'msg' for 422, the first sentence otherwise."""
    m = re.search(r"'msg': '([^']+)'", detail)
    return m.group(1) if m else detail.split(". ")[0] + "."


def inr(x):
    return f"₹{x:,.0f}"


val = S["Input validation"]
load = S["Official dataset loading"]
pre = S["Preprocessing and crop filtering"]
fz = S["Fuzzy inference"]
ns = S["NSGA-II optimisation"]
tp = S["TOPSIS ranking"]
rec = S["Recommendation"]
ex = S["Explanation"]
qm = ns["quality_metrics"]
plan = rec["plan"]

cards = [
    ("Input", "#2a78d6", None, [
        f"POST /api/farm-plans  {{location: {req['location']}, season: {req['season']}, year: {req['year']}, "
        f"total_land_ha: {req['total_land_ha']:g}, preference: {req['preference']}, save_results: true}}"]),
    ("Validation", "#2a78d6", val["ms"], [
        "Request accepted by the Pydantic FarmPlanRequest model and the district / season checks.",
        *[f"Rejected example → HTTP {r['status']}: {r['input']['location']}, {r['input']['season']}, "
          f"{r['input']['total_land_ha']:g} ha — {short(r['detail'])}" for r in val["rejected_examples"]]]),
    ("Official dataset loading", "#1baf7a", load["ms"], [
        f"{len(load['registry'])} registered official datasets, {sum(d['rows_clean'] for d in load['registry']):,} clean rows "
        f"(report year {load['registry'][0]['report_year']}), each with a sha256 in dataset_registry.",
        "Pipeline frames built from the database: " + ", ".join(f"{k} {v}" for k, v in load["frames_rows"].items()) + " rows.",
        f"{len(load['disabled_features'])} features disabled because their official dataset is missing (no estimates)."]),
    ("Preprocessing & crop filtering", "#1baf7a", pre["ms"], [
        f"{pre['district']} · {pre['season']} {pre['year']} · months {', '.join(m[:3] for m in pre['rainfall']['months'])}",
        f"Rainfall {pre['rainfall']['season_actual_mm']} mm vs IMD normal {pre['rainfall']['season_normal_mm']} mm "
        f"({pre['rainfall']['deviation_pct']:+.1f} %) · reservoir storage {pre['water']['storage_pct']} % "
        f"({', '.join(pre['water']['reservoirs'] or [])}) · Soil Health Card fertility index {pre['soil']['fertility_index']} "
        f"(N {pre['soil']['N']}, P {pre['soil']['P']}, K {pre['soil']['K']})",
        f"Candidates ({len(pre['candidate_crops'])}): {', '.join(pre['candidate_crops'])}",
        f"Excluded ({len(pre['excluded_crops'])}): " + ", ".join(e["crop"] for e in pre["excluded_crops"])
        + " — e.g. cotton: no official kapas-to-lint conversion factor loaded"]),
    ("Fuzzy inference", "#eb6834", fz["ms"], [
        f"Model '{fz['model']}': rainfall {fz['assessment']['rainfall_label']}, water {fz['assessment']['water_label']}, "
        f"soil {fz['assessment']['soil_label']} → yield confidence {fz['assessment']['yield_confidence']}, "
        f"irrigation risk {fz['assessment']['irrigation_risk']} (applied: {fz['assessment']['applied']})"]),
    ("NSGA-II optimisation", "#eb6834", ns["ms"], [
        f"Population {ns['pop_size']} × {ns['n_gen']} generations = {qm['evaluations']:,} evaluations · crossover {ns['crossover_prob']}, "
        f"mutation {ns['mutation_prob']} · seed {run['environment']['seed']}",
        f"{ns['pareto_solutions']} Pareto-optimal plans, constraint satisfaction {qm['constraint_satisfaction_rate']:.0%} · "
        f"hypervolume ratio {qm['hypervolume_ratio']:.3f}, IGD+ {qm['igd_plus']:.3f}, spread {qm['spread']:.3f}"]),
    ("TOPSIS ranking", "#eb6834", None, [
        f"{tp['plans_ranked']} plans ranked with the '{tp['topsis']['label']}' profile: weights "
        + ", ".join(f"{c['label'].lower()} {c['weight']:.3f}" for c in tp["topsis"]["criteria"]),
        "Top closeness: " + " · ".join(f"#{p['rank']} {p['composite_score']:.4f}" for p in tp["top5"])]),
    ("Recommendation", "#eb6834", rec["api_ms"], [
        "Rank 1: " + " + ".join(f"{c} {a:.1f} %" for c, a in plan["crops"]) +
        f" · yield {plan['yield_tonnes']} t · cost {inr(plan['cost_rs'])} · irrigated {plan['irrigated_ha']} ha-eq. · "
        f"nutrients {plan['env_impact_score']} kg",
        f"{plan['trade_off_summary']} · saved as run {rec['run_id']} (HTTP {rec['api_status']}; time = whole API call)"]),
    ("Explanation", "#6250d6", ex["ms"], [
        f"GET /api/results/{{run_id}}/explanation → {ex['summary']['recommendation']}, confidence {ex['summary']['confidence_pct']} %, "
        f"{ex['n_reasons']} reasons, {ex['n_risks']} risks, {len(ex['sections'])} sections",
        "Reasons: " + "; ".join(ex["reasons"]),
        "Confidence components: " + ", ".join(f"{c['id']} {c['score']:g}" for c in ex["confidence_components"]),
        "Per-crop official evidence: " + "; ".join(
            f"{c['crop']} — " + ", ".join(f"{k['id']} {k['status']}" for k in c["criteria"]) for c in ex["crop_evidence"])]),
]


def card_html(i, title, color, ms, lines):
    t = (f'<span class="ms">{ms:,.1f} ms</span>' if ms is not None else
         '' if i == 1 else '<span class="ms muted">inside the API call</span>')
    body = "".join(f"<li>{html.escape(l)}</li>" for l in lines)
    return (f'<div class="card" style="border-color:{color}"><div class="num" style="background:{color}">{i}</div>'
            f'<div class="head"><h2>{html.escape(title)}</h2>{t}</div><ul>{body}</ul></div>')


page = f"""<!doctype html><html><head><meta charset="utf-8"><title>Pipeline execution</title><style>
body{{margin:0;background:#fcfcfb;font-family:Helvetica,Arial,sans-serif;color:#0b0b0b}}
.wrap{{width:1520px;margin:0 auto;padding:36px 40px 30px}}
h1{{font-size:32px;margin:0 0 6px;text-align:center}} .sub{{text-align:center;color:#52514e;font-size:17px;margin-bottom:26px}}
.card{{position:relative;border:2.5px solid;border-left-width:10px;border-radius:10px;background:#fff;padding:14px 22px 12px 70px;margin:0 0 6px}}
.num{{position:absolute;left:18px;top:14px;width:34px;height:34px;border-radius:17px;color:#fff;font-weight:bold;font-size:17px;
display:flex;align-items:center;justify-content:center}}
.head{{display:flex;justify-content:space-between;align-items:baseline}} h2{{font-size:21px;margin:0 0 6px}}
.ms{{font-size:16px;font-weight:bold;color:#0b0b0b}} .muted{{color:#52514e;font-weight:normal}}
ul{{margin:0;padding-left:18px;font-size:15.5px;line-height:1.5}} li{{margin:1px 0}}
.arrow{{text-align:center;color:#8a8984;font-size:22px;line-height:22px;margin:0 0 6px}}
.foot{{color:#52514e;font-size:13px;margin-top:16px}}
</style></head><body><div class="wrap">
<h1>Pipeline execution snapshot: one real optimisation run</h1>
<div class="sub">{html.escape(req['location'])} · {html.escape(req['season'])} {req['year']} · {req['total_land_ha']:g} ha · balanced preference ·
NSGA-II mode {html.escape(run['environment']['nsga2_mode'])} · fuzzy model {html.escape(run['environment']['fuzzy_model'])} · official data only</div>
{('<div class="arrow">▼</div>').join(card_html(i + 1, *c) for i, c in enumerate(cards))}
<div class="foot">Recorded by final_ppt/assets/scripts/run_pipeline_snapshot.py through the FastAPI app (TestClient) and the pipeline
modules; times measured with time.perf_counter (fuzzy time includes building the 'official' model on first use; NSGA-II time is the
run's own optimize_seconds). Raw record: final_ppt/assets/data/pipeline_run.json.</div>
</div></body></html>"""
(ROOT / "final_ppt" / "diagrams" / "pipeline_execution.html").write_text(page)

md = [f"# Pipeline execution snapshot", "",
      f"One complete optimisation on the official data, recorded by `final_ppt/assets/scripts/run_pipeline_snapshot.py` "
      f"through the real FastAPI app and pipeline modules. Raw record: `final_ppt/assets/data/pipeline_run.json`.", "",
      f"**Request:** `{json.dumps(req)}`  ",
      f"**Engine:** NSGA-II mode `{run['environment']['nsga2_mode']}`, seed {run['environment']['seed']}, fuzzy model "
      f"`{run['environment']['fuzzy_model']}`. Re-running the same request reproduced the same top plan: "
      f"{run['same_top_plan_as_rerun']}.", "",
      "| # | Stage | Time | What happened |", "|---|---|---|---|"]
for i, (title, _c, ms, lines) in enumerate(cards, 1):
    md.append(f"| {i} | {title} | {f'{ms:,.1f} ms' if ms is not None else ('–' if i == 1 else 'inside the API call')} | "
              + "<br>".join(l.replace("|", "/") for l in lines) + " |")
md += ["", "## Excluded crops and reasons", ""]
for e in pre["excluded_crops"]:
    md.append(f"- **{e['crop']}**: " + "; ".join(e["reasons"]))
md += ["", "## Notes from the preprocessing stage", ""] + [f"- {n}" for n in pre["notes"]]
md += ["", "## Disabled features reported by GET /api/datasets", ""]
md += [f"- **{d['feature']}**: missing {d['missing_dataset']} (source: {d['source']}; scope: {d['scope']})" for d in load["disabled_features"]]
md += ["", "## Official datasets in the registry", "", "| Dataset | File | Report year | Clean rows | sha256 (first 12) |", "|---|---|---|---|---|"]
md += [f"| {d['name']} | {d['filename']} | {d['report_year']} | {d['rows_clean']:,} | {d['sha256'][:12]} |" for d in load["registry"]]
md += ["", "Timing notes: times are measured with `time.perf_counter` in one process. The fuzzy time includes building the "
       "`official` model on first use; the NSGA-II time is the run's own `optimize_seconds`; the recommendation time is the whole "
       "`POST /api/farm-plans` call (preprocessing, fuzzy, NSGA-II with convergence tracking, TOPSIS and saving the run)."]
(ROOT / "final_ppt" / "diagrams" / "pipeline_execution.md").write_text("\n".join(md) + "\n")
print("wrote pipeline_execution.html and pipeline_execution.md")
