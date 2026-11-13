"""Methodology and module-interaction diagrams for the review slides.

Every box names the module/function that implements it (verified against the code on the
official-data migration branch). Writes SVG and draw.io from one layout; PNG/PDF are rendered
from the SVG by render_assets.py (headless Chrome).

Usage (from the repository root):  python final_ppt/assets/scripts/make_diagrams.py
"""
from __future__ import annotations

import html
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "final_ppt" / "diagrams"

INK, INK2, LINE, SURFACE = "#0b0b0b", "#52514e", "#8a8984", "#fcfcfb"
PHASE = {  # stroke, tint
    "input": ("#2a78d6", "#eaf2fc"),
    "data": ("#1baf7a", "#e6f6ef"),
    "engine": ("#eb6834", "#fdeee7"),
    "delivery": ("#6250d6", "#efedfb"),
}
FONT = "Helvetica, Arial, sans-serif"


class Canvas:
    def __init__(self, w, h, title, subtitle):
        self.w, self.h = w, h
        self.svg = []
        self.cells = []  # draw.io
        self.nid = 2
        self.text(w / 2, 46, title, 30, INK, "bold", "middle")
        self.text(w / 2, 80, subtitle, 17, INK2, "normal", "middle")

    def text(self, x, y, s, size, color, weight="normal", anchor="start"):
        self.svg.append(f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" '
                        f'font-weight="{weight}" fill="{color}" text-anchor="{anchor}">{html.escape(s)}</text>')

    def box(self, x, y, w, h, phase, title, lines, ref=None, num=None):
        stroke, tint = PHASE[phase]
        self.svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{tint}" stroke="{stroke}" stroke-width="2.5"/>')
        self.svg.append(f'<rect x="{x}" y="{y}" width="8" height="{h}" rx="3" fill="{stroke}"/>')
        tx = x + 22
        ty = y + 32
        if num is not None:
            self.svg.append(f'<circle cx="{x + w - 26}" cy="{y + 26}" r="15" fill="{stroke}"/>')
            self.text(x + w - 26, y + 31.5, str(num), 15, "#ffffff", "bold", "middle")
        self.text(tx, ty, title, 17, INK, "bold")
        ty += 28
        for ln in lines:
            self.text(tx, ty, ln, 14.5, INK, "normal")
            ty += 21
        if ref:
            self.text(tx, y + h - 14, ref, 12.5, INK2, "normal")
        value = f"<b>{html.escape(title)}</b><br>" + "<br>".join(html.escape(l) for l in lines)
        if ref:
            value += f"<br><i>{html.escape(ref)}</i>"
        cid = self.nid
        self.nid += 1
        self.cells.append(f'<mxCell id="{cid}" value="{html.escape(value)}" style="rounded=1;whiteSpace=wrap;html=1;align=left;'
                          f'verticalAlign=top;spacingLeft=10;fillColor={tint};strokeColor={stroke};strokeWidth=2;fontSize=12;" '
                          f'vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
        return cid

    def arrow(self, pts, label=None, src=None, dst=None, lx=None, ly=None):
        d = "M " + " L ".join(f"{px:.1f} {py:.1f}" for px, py in pts)
        self.svg.append(f'<path d="{d}" fill="none" stroke="{LINE}" stroke-width="2.5" marker-end="url(#ah)"/>')
        if label:
            mx = lx if lx is not None else (pts[0][0] + pts[-1][0]) / 2 + 10
            my = ly if ly is not None else (pts[0][1] + pts[-1][1]) / 2 + 5
            self.text(mx, my, label, 13, INK2, "normal")
        if src is not None and dst is not None:
            cid = self.nid
            self.nid += 1
            self.cells.append(f'<mxCell id="{cid}" value="{html.escape(label or "")}" style="edgeStyle=orthogonalEdgeStyle;'
                              f'html=1;strokeColor={LINE};strokeWidth=2;fontSize=11;" edge="1" parent="1" source="{src}" '
                              f'target="{dst}"><mxGeometry relative="1" as="geometry"/></mxCell>')

    def band(self, x, y, w, h, label):
        self.svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="none" stroke="#d6d5cf" '
                        f'stroke-width="1.5" stroke-dasharray="6 6"/>')
        self.text(x + 16, y + 24, label, 14, INK2, "bold")

    def legend(self, x, y, items):
        for i, (phase, lab) in enumerate(items):
            stroke, tint = PHASE[phase]
            xx = x + i * 260
            self.svg.append(f'<rect x="{xx}" y="{y - 14}" width="22" height="18" rx="4" fill="{tint}" stroke="{stroke}" stroke-width="2.5"/>')
            self.text(xx + 32, y, lab, 15, INK, "normal")

    def write_svg(self, path, footer):
        self.text(30, self.h - 22, footer, 13, INK2)
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}">'
                f'<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                f'<path d="M0 0 L10 5 L0 10 z" fill="{LINE}"/></marker></defs>'
                f'<rect width="100%" height="100%" fill="{SURFACE}"/>')
        path.write_text(head + "".join(self.svg) + "</svg>\n")

    def write_drawio(self, path, name):
        body = "".join(self.cells)
        path.write_text(f'<mxfile host="app.diagrams.net"><diagram name="{html.escape(name)}"><mxGraphModel dx="{self.w}" dy="{self.h}" '
                        f'grid="1" gridSize="10" pageWidth="{self.w}" pageHeight="{self.h}"><root><mxCell id="0"/>'
                        f'<mxCell id="1" parent="0"/>{body}</root></mxGraphModel></diagram></mxfile>\n')


# ---------------------------------------------------------------------------
# 1. Proposed methodology / research workflow (as implemented)
# ---------------------------------------------------------------------------
STAGES = [
    ("input", "User Inputs", ["District, season, farm size (ha)", "Optional budget, preference or", "TOPSIS profile / custom weights"], "RunOptimizationView → POST /api/farm-plans"),
    ("input", "Validation", ["Pydantic FarmPlanRequest: land > 0,", "pop 8–300, generations 5–500", "38 official districts; Kharif / Rabi", "(Pollachi → taluk note, 400)"], "app/schemas.py · preprocessing.resolve_location"),
    ("data", "Official Dataset Loading", ["10 official raw files: Season & Crop", "Report, IMD rainfall, WRD reservoirs,", "groundwater, CACP MSP/cost, TNAU,", "Soil Health Card → SQLite database"], "app/datasets/pipeline.py build_database"),
    ("data", "Dataset Registry", ["Per file: sha256, report year", "2024-25, raw and clean rows;", "ingestion_log of validation issues", "Served by GET /api/datasets"], "app/db/schema.py dataset_registry"),
    ("data", "Cleaning & Normalisation", ["Validators and cleaners per dataset;", "district / crop name keys, units;", "official_view → crop, land, rainfall,", "water frames (985 / 76 / 456 / 456)"], "app/datasets/* · normalize.py · official_view.py"),
    ("data", "District Selection", ["Season rainfall vs IMD normal,", "reservoir storage %, groundwater,", "Soil Health Card fertility index", "for the chosen district and season"], "preprocessing.get_region_season_profile"),
    ("data", "Crop Filtering", ["Keep crops with official yield,", "TNAU dose, MSP and CACP cost;", "every exclusion keeps its reason;", "6 candidates by default (2–12)"], "preprocessing._candidate_mask"),
    ("engine", "Fuzzy Logic", ["Mamdani model 'official': IMD", "rainfall bands, data-percentile", "storage and fertility sets →", "yield confidence, irrigation risk"], "app/fuzzy/engine.py · calibration.py"),
    ("engine", "NSGA-II", ["4 objectives: yield, CACP cost,", "irrigated area, nutrient load;", "optional budget constraint;", "pop 80 × 200 gen, pc 0.85, pm 0.12"], "app/optimization/problem.py · nsga2_runner.py"),
    ("engine", "TOPSIS", ["Closeness to the ideal plan", "over weighted criteria: balanced,", "profit, water, sustainability,", "low-cost or custom profile"], "app/decision/ranking.py · topsis_service.py"),
    ("engine", "Ranking & Recommendation", ["Up to 50 ranked Pareto plans;", "rank 1 = crop mix, areas, cost,", "trade-off summary, confidence;", "run saved as JSON + CSV"], "ranking.to_dict_list · results_store.py"),
    ("delivery", "Explainability Engine", ["Reasons, trade-offs, constraints,", "risks, confidence, fuzzy rules,", "TOPSIS contributions, per-crop", "official evidence (10 criteria)"], "explanation_service.py · crop_evidence.py"),
    ("delivery", "REST API", ["FastAPI: farm-plans, results,", "explanation, comparison, district", "intelligence, simulations,", "datasets, soil-master"], "app/main.py"),
    ("delivery", "React Dashboard", ["Dashboard, Run Optimization,", "Analytics, Comparison, History,", "Reports, District Intelligence,", "Scenario Simulation, Official Data"], "frontend/src/views (React 19 + Vite)"),
]


def methodology():
    c = Canvas(2400, 1000, "AgroOptimize: proposed methodology (as implemented)",
               "From user input to an explainable crop-allocation recommendation on official Tamil Nadu data")
    bw, bh, gap, x0 = 300, 210, 40, 30
    rows = [(140, STAGES[:7], False), (520, STAGES[7:], True)]
    ids, pos = [], []
    n = 0
    for y, stages, rtl in rows:
        k = len(stages)
        for i, (ph, title, lines, ref) in enumerate(stages):
            n += 1
            col = (k - 1 - i) if rtl else i
            x = x0 + col * (bw + gap)
            ids.append(c.box(x, y, bw, bh, ph, title, lines, ref, num=n))
            pos.append((x, y))
    for i in range(len(pos) - 1):
        (xa, ya), (xb, yb) = pos[i], pos[i + 1]
        if ya == yb:
            if xb > xa:
                c.arrow([(xa + bw, ya + bh / 2), (xb - 3, yb + bh / 2)], src=ids[i], dst=ids[i + 1])
            else:
                c.arrow([(xa, ya + bh / 2), (xb + bw + 3, yb + bh / 2)], src=ids[i], dst=ids[i + 1])
        else:  # row change: down from the last box of row 1 to the first of row 2
            c.arrow([(xa + bw / 2, ya + bh), (xa + bw / 2, (ya + bh + yb) / 2), (xb + bw / 2, (ya + bh + yb) / 2), (xb + bw / 2, yb - 3)],
                    src=ids[i], dst=ids[i + 1])
    c.legend(30, 830, [("input", "Input and validation"), ("data", "Official data layer"),
                       ("engine", "Decision engine"), ("delivery", "Explanation and delivery")])
    c.text(30, 880, "Datasets are validated, cleaned and imported once (scripts/preprocess_all.py, also at Docker build); each request "
                    "reads them through app/data/loader.py (cached per process).", 15, INK2)
    c.text(30, 906, "The fuzzy stage runs only where an official reservoir reading exists for the district and season; otherwise "
                    "it is skipped and flagged (yield left unadjusted).", 15, INK2)
    c.text(30, 932, "Features without an official dataset (e.g. live weather) return HTTP 501 instead of estimated values.", 15, INK2)
    c.write_svg(OUT / "methodology.svg", "Source: AgroOptimize backend (app/), frontend (frontend/src) and docs/data_architecture, "
                                          "branch feature/official-data-migration")
    c.write_drawio(OUT / "methodology.drawio", "Methodology")


# ---------------------------------------------------------------------------
# 2. Module interaction (software architecture)
# ---------------------------------------------------------------------------
def module_interaction():
    c = Canvas(2400, 1720, "AgroOptimize: module interaction",
               "Modules, the calls between them and the data flow from official sources to the browser")
    W = 2340
    x0 = 30
    # Row 1: frontend
    fe = c.box(x0 + 470, 120, 1400, 120, "delivery", "React Frontend (frontend/src)",
               ["Views: Dashboard · Run Optimization · Analytics · Comparison · History · Reports · District Intelligence · Scenario Simulation · Official Data",
                "services/api.js: the single place that calls the backend (fetch, same origin in production)"])
    # Row 2: FastAPI
    api = c.box(x0, 330, W, 140, "delivery", "FastAPI REST API (app/main.py)",
                ["POST /api/farm-plans · GET /api/results/{id} · /api/results/{id}/explanation · /api/results/{id}/topsis · /api/region-profile",
                 "GET /api/dashboard · /api/plans · /api/comparison · /api/compare-fuzzy · /api/district-intelligence · /api/history  (per district)",
                 "POST /api/simulations/run · GET /api/datasets · /api/soil-master · /api/fuzzy/explain · /api/fuzzy/audit · /health  (+ 501 if no official data)"])
    c.arrow([(x0 + 1170, 240), (x0 + 1170, 327)], "HTTP / JSON", fe, api, lx=x0 + 1185, ly=290)
    # Row 3: services
    sv_y, sv_w, sv_h = 560, 440, 150
    services = [
        ("Plan service", ["Runs the pipeline per request:", "preprocess → fuzzy → NSGA-II → TOPSIS"], "app/services/plan_service.py"),
        ("Explainability engine", ["Reasons, risks, confidence, fuzzy", "rules, TOPSIS, per-crop evidence"], "explanation_service.py · crop_evidence.py"),
        ("TOPSIS service", ["Re-rank saved fronts, profiles,", "custom weights, comparisons"], "app/services/topsis_service.py"),
        ("Dashboard / District / Simulation", ["KPI cards, Pareto plans, A/B/C,", "district profile, what-if scenarios"], "dashboard_ · district_ · simulation_service.py"),
        ("Results store", ["Saved runs and simulations", "(JSON + CSV + convergence)"], "app/services/results_store.py → results/"),
    ]
    sx = []
    sids = []
    for i, (t, l, r) in enumerate(services):
        x = x0 + i * (sv_w + 35)
        sids.append(c.box(x, sv_y, sv_w, sv_h, "delivery", t, l, r))
        sx.append(x)
    c.band(x0 - 10, sv_y - 40, W + 20, sv_h + 55, "Services")
    for i in range(5):
        c.arrow([(sx[i] + sv_w / 2, 470), (sx[i] + sv_w / 2, sv_y - 3)], src=api, dst=sids[i])
    # Row 4: algorithm modules
    al_y, al_w, al_h = 800, 540, 165
    algos = [
        ("data", "Preprocessing", ["District + season profile: rainfall vs", "IMD normal, reservoir %, soil index;", "crop filtering with reasons"], "app/data/preprocessing.py"),
        ("engine", "Fuzzy engine", ["Mamdani FIS (scikit-fuzzy), model", "'official' calibrated on the data →", "yield confidence, irrigation risk"], "app/fuzzy/engine.py · calibration.py"),
        ("engine", "NSGA-II engine", ["pymoo NSGA-II, 4 objectives,", "single-point crossover, Gaussian", "mutation, quality metrics (HV, IGD+)"], "app/optimization/"),
        ("engine", "TOPSIS ranking", ["Criteria, profiles, closeness,", "per-criterion contributions,", "plan-vs-plan explanation"], "app/decision/"),
    ]
    ax = []
    aids = []
    for i, (ph, t, l, r) in enumerate(algos):
        x = x0 + i * (al_w + 60)
        aids.append(c.box(x, al_y, al_w, al_h, ph, t, l, r))
        ax.append(x)
    c.band(x0 - 10, al_y - 40, W + 20, al_h + 55, "Algorithm modules")
    # plan service fans out to the four algorithm modules
    for i in range(4):
        c.arrow([(sx[0] + sv_w / 2, sv_y + sv_h), (sx[0] + sv_w / 2, 760), (ax[i] + al_w / 2, 760), (ax[i] + al_w / 2, al_y - 3)],
                src=sids[0], dst=aids[i])
    c.text(sx[0] + sv_w / 2 + 12, 752, "stage 1 → 2 → 3 → 4", 13, INK2)
    # Row 5: dataset service
    ds_y, ds_h = 1050, 140
    ds = c.box(x0 + 270, ds_y, 1800, ds_h, "data", "Dataset service (official data access)",
               ["app/data/loader.py + official_view.py: crop, land, rainfall and water frames for the pipeline (cached per process)",
                "app/datasets/service.py: SQL queries with TTL cache, provenance; soil_master · agronomy_master · conversion_loader",
                "No CSV fallback: a missing dataset raises OfficialDataUnavailable → HTTP 501 for that feature"])
    c.arrow([(ax[0] + al_w / 2, al_y + al_h), (ax[0] + al_w / 2, ds_y - 3)], "reads", aids[0], ds, lx=ax[0] + al_w / 2 + 10, ly=1015)
    c.arrow([(ax[1] + al_w / 2, al_y + al_h), (ax[1] + al_w / 2, ds_y - 3)], "calibration", aids[1], ds, lx=ax[1] + al_w / 2 + 10, ly=1015)
    # Row 6: database and build
    db_y, db_h = 1270, 140
    db = c.box(x0 + 270, db_y, 860, db_h, "data", "SQLite database official_v1.db",
               ["16 tables via SQLAlchemy (AGROOPTIMIZE_DB_URL)", "dataset_registry (sha256, rows, report year),", "ingestion_log, district, crop_stat, msp, reservoir …"])
    bd = c.box(x0 + 1210, db_y, 860, db_h, "data", "Build pipeline (once, and at Docker build)",
               ["scripts/preprocess_all.py → build_database():", "per dataset validate → clean → import;", "validation_report.json"])
    c.arrow([(x0 + 700, ds_y + ds_h), (x0 + 700, db_y - 3)], "SQL", ds, db, lx=x0 + 712, ly=1235)
    c.arrow([(x0 + 1210, db_y + db_h / 2), (x0 + 1133, db_y + db_h / 2)], "writes", bd, db, lx=x0 + 1145, ly=db_y + db_h / 2 - 10)
    # Row 7: official datasets
    od_y, od_h = 1470, 120
    od = c.box(x0 + 270, od_y, 1800, od_h, "data", "Official government datasets (data/official/raw, report year 2024-25)",
               ["TN Season & Crop Report (crops, state series, land use, irrigation, IMD rainfall) · groundwater levels · WRD daily reservoir levels",
                "CACP MSP and cost of cultivation · TNAU Crop Production Guide doses · Soil Health Card 2024-25 · agronomy / soil masters, conversion table"])
    c.arrow([(x0 + 1640, od_y), (x0 + 1640, db_y + db_h + 3)], "read raw files", od, bd, lx=x0 + 1652, ly=od_y - 22)
    c.legend(x0, 1640, [("delivery", "Interface and services"), ("engine", "Decision algorithms"), ("data", "Official data layer")])
    c.text(x0 + 820, 1640, "The explanation, dashboard, district and simulation services also call preprocessing, the fuzzy engine, "
                           "NSGA-II and ranking directly (imports in app/services).", 14, INK2)
    c.write_svg(OUT / "module_interaction.svg", "Source: imports and routes in app/ and frontend/src/services/api.js "
                                                 "(branch feature/official-data-migration)")
    c.write_drawio(OUT / "module_interaction.drawio", "Module interaction")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    methodology()
    module_interaction()
    print("wrote", *sorted(p.name for p in OUT.iterdir()))
