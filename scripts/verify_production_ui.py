"""Browser verification of a deployed AgroOptimize app.

Drives the app in Google Chrome (Playwright, channel="chrome"), runs each
feature end to end (official datasets, optimisation, explanation with crop
evidence, history, reports, District Intelligence, Soil Health Card, scenario
simulation, analytics, comparison, settings), records console errors, failed
API responses and raw null/NaN/undefined text, and saves screenshots.

    pip install playwright        # uses the installed Google Chrome
    python scripts/verify_production_ui.py https://agrooptimize.onrender.com \
        docs/deployment/screenshots /tmp/ui_verification.json

Exits non-zero if any check fails. Complements scripts/smoke_test_deployment.py.
"""
import json, re, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE, OUT, RES = sys.argv[1].rstrip("/"), Path(sys.argv[2]), Path(sys.argv[3])
OUT.mkdir(parents=True, exist_ok=True)
USER = {"fullName": "", "location": "Salem", "landSize": "5", "primaryCrop": "maize", "season": "Rabi", "avatar": None}
BAD = re.compile(r"\bundefined\b|\bNaN\b|\bnull\b|ML/ha|\[object Object\]")
log = {"console": [], "pageerrors": [], "api_failures": [], "checks": [], "bad_text": []}


def check(name, ok, detail=""):
    log["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name, detail, flush=True)


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
    pg = ctx.new_page()
    pg.on("console", lambda m: m.type in ("error", "warning") and log["console"].append([pg.url, m.type, m.text[:300]]))
    pg.on("pageerror", lambda e: log["pageerrors"].append(str(e)[:300]))
    pg.on("response", lambda r: r.status >= 400 and "/api/" in r.url and log["api_failures"].append([r.status, r.url]))

    def view(v, wait=2500):
        pg.evaluate("([u, v]) => { localStorage.setItem('agro_user', JSON.stringify(u)); localStorage.setItem('agro_currentView', v); }", [USER, v])
        pg.reload(); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(wait)
        t = pg.inner_text("body")
        for m in set(BAD.findall(t)):
            log["bad_text"].append([v, m])
        return t

    def shot(name, full=True):
        pg.screenshot(path=str(OUT / f"{name}.png"), full_page=full)

    t0 = time.time()
    pg.goto(BASE + "/"); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(2500)
    shot("01_home_page", full=False)

    t = view("datasets")
    check("Official datasets load", "Loaded datasets" in t and "39,065" in t and pg.locator("table tbody tr").count() == 10,
          f"{pg.locator('table tbody tr').count()} dataset rows")
    shot("02_official_datasets")

    t = view("dashboard")
    check("Dashboard loads", "Estimated Yield" in t and "Official Data Not Available" in t)
    shot("03_dashboard")

    view("run-optimization")
    pg.locator("select").nth(0).select_option("Salem"); pg.locator("select").nth(1).select_option("Rabi")
    pg.get_by_role("button", name=re.compile(r"run optimization$", re.I)).last.click()
    pg.wait_for_selector("text=Optimization complete and saved", timeout=120000)
    pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(1500)
    t = pg.inner_text("body")
    check("Optimization works", "Top-ranked plan" in t and "Official" in t, re.search(r"Top-ranked plan · ([^\n]+)", t).group(1) if "Top-ranked plan" in t else "")
    shot("04_optimization_result")

    pg.get_by_role("button", name=re.compile("why this plan", re.I)).first.click()
    pg.wait_for_selector("text=Why this crop was selected", timeout=60000); pg.wait_for_timeout(1000)
    dlg = pg.locator("[role=dialog]").first
    t = dlg.inner_text()
    check("Explainability loads", "Why this plan was recommended" in t and "Why this crop was selected" in t and "Rainfall" in t)
    pg.set_viewport_size({"width": 1440, "height": 2300}); pg.wait_for_timeout(500)
    sec = dlg.locator("section", has_text="Why this crop was selected").first
    sec.locator("details details summary").first.click(); pg.wait_for_timeout(500)
    sec.screenshot(path=str(OUT / "05_explainability_crop_evidence.png"))
    pg.set_viewport_size({"width": 1440, "height": 900})
    pg.keyboard.press("Escape")

    t = view("history")
    check("History works", "Rabi 2024" in t and "Official Data" in t and "Completed" in t)
    shot("06_history")

    view("reports")
    pg.get_by_role("button", name=re.compile("generate report", re.I)).first.click()
    pg.wait_for_timeout(4000)
    t = pg.inner_text("body")
    with pg.expect_download(timeout=30000) as dl:
        pg.get_by_role("button", name=re.compile("download", re.I)).first.click()
    rep = Path(dl.value.path()).read_text()
    check("Reports work", "AGROOPTIMIZE DECISION REPORT" in rep and "WHY EACH CROP WAS SELECTED" in rep and "NaN" not in rep,
          f"report {len(rep.splitlines())} lines")
    shot("07_reports")

    t = view("district-intelligence", 4000)
    check("District Intelligence works", ("DISTRICT SUMMARY" in t.upper()) and ("Climate profile" in t))
    check("Soil Health Card loads", "Soil Health Card" in t and "Soil Salinity" in t and "samples tested" in t)
    shot("08_district_intelligence")
    pg.locator("section", has_text="Soil Health Card").filter(has_text="Soil Salinity").last.screenshot(path=str(OUT / "09_soil_health_card.png"))

    view("scenario-simulation")
    pg.locator("select").nth(0).select_option("Salem"); pg.locator("select").nth(1).select_option("Rabi")
    pg.get_by_role("button", name=re.compile(r"^-20%$")).first.click()
    pg.get_by_role("button", name=re.compile("run simulation", re.I)).first.click()
    pg.wait_for_selector("text=Recommendation comparison", timeout=420000); pg.wait_for_timeout(1500)
    t = pg.inner_text("body")
    check("Scenario Simulation works", "Simulated recommendation" in t and "Rainfall -20%" in t)
    shot("10_scenario_simulation")

    t = view("analytics", 4000)
    check("Analytics loads", "Cost vs. Yield" in t)
    t = view("comparison", 4000)
    check("Comparison loads", "Plan Metrics" in t)
    t = view("settings")
    check("Settings shows system information", "System Information" in t and "Official dataset mode" in t)
    shot("11_settings")

    pg.goto(BASE + "/docs"); pg.wait_for_timeout(4000)
    shot("12_api_docs", full=False)
    b.close()

check("No console errors", not log["console"], f"{len(log['console'])} entries")
check("No API failures", not log["api_failures"], f"{len(log['api_failures'])} failed responses")
check("No page errors", not log["pageerrors"])
check("No raw null/NaN/undefined text", not log["bad_text"], json.dumps(log["bad_text"]))
log["seconds"] = round(time.time() - t0, 1)
RES.write_text(json.dumps(log, indent=1))
sys.exit(0 if all(c["ok"] for c in log["checks"]) else 1)
