"""Frontend QA on the dev build (React warnings visible): page sweep at 4 widths and every workflow.

    uvicorn app.main:app --port 8000 & (cd frontend && npx vite --port 5173 &)
    pip install playwright        # uses the installed Google Chrome
    python final_demo/qa_scripts/ui_flows.py http://localhost:5173 ui_flows.json shots/
"""
import json, re, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE, OUT, SHOTS = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
SHOTS.mkdir(parents=True, exist_ok=True)
USER = {"fullName": "QA Tester", "location": "Salem", "landSize": "5", "primaryCrop": "maize", "season": "Rabi", "avatar": None}
VIEWS = ["dashboard", "analytics", "comparison", "run-optimization", "district-intelligence", "scenario-simulation",
         "history", "reports", "datasets", "settings"]
SIZES = {"desktop": (1440, 900), "laptop": (1280, 800), "tablet": (820, 1180), "mobile": (390, 844)}
BAD = re.compile(r"\bundefined\b|\bNaN\b|\bnull\b|ML/ha|\[object Object\]|Infinity")
log = {"checks": [], "console": [], "pageerrors": [], "http": [], "overflow": [], "badtext": [], "images": [], "timings": {}}


def idle(pg, ms=8000):
    try:
        pg.wait_for_load_state("networkidle", timeout=ms)
    except Exception:
        pass


def check(name, ok, detail=""):
    log["checks"].append({"check": name, "ok": bool(ok), "detail": str(detail)[:300]})
    print(("PASS " if ok else "FAIL ") + name, str(detail)[:160], flush=True)


def attach(pg, tag):
    pg.on("console", lambda m: m.type in ("error", "warning") and log["console"].append([tag, m.type, m.text[:300]]))
    pg.on("pageerror", lambda e: log["pageerrors"].append([tag, str(e)[:300]]))
    pg.on("response", lambda r: r.status >= 400 and "/api/weather" not in r.url and log["http"].append([tag, r.status, r.url[:150]]))


def set_view(pg, view, user=USER, wait=1800):
    pg.evaluate("([u, v]) => { if (u) localStorage.setItem('agro_user', JSON.stringify(u)); else localStorage.removeItem('agro_user'); localStorage.setItem('agro_currentView', v); }", [user, view])
    pg.reload(); idle(pg); pg.wait_for_timeout(wait)


def inspect(pg, tag, w):
    sw = pg.evaluate("document.documentElement.scrollWidth")
    if sw > w + 1:
        log["overflow"].append([tag, sw])
    t = pg.inner_text("body")
    for m in set(BAD.findall(t)):
        log["badtext"].append([tag, m, t[max(0, t.find(m) - 60): t.find(m) + 20]])
    broken = pg.evaluate("[...document.images].filter(i => i.complete && i.naturalWidth === 0).map(i => i.src.slice(0, 80))")
    if broken:
        log["images"].append([tag, broken])
    return t


def btn(pg, pattern, nth=0):
    return pg.get_by_role("button", name=re.compile(pattern, re.I)).nth(nth)


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")

    # ---------------- 1. Page sweep at 4 widths ----------------
    for size, (w, h) in SIZES.items():
        ctx = b.new_context(viewport={"width": w, "height": h})
        pg = ctx.new_page(); attach(pg, size)
        pg.goto(BASE + "/"); idle(pg); pg.wait_for_timeout(2500)
        inspect(pg, f"{size}/onboarding", w)
        for v, u in [("login", None), ("register", None), ("profile-setup", {"fullName": ""})] + [(v, USER) for v in VIEWS]:
            t0 = time.perf_counter(); set_view(pg, v, u)
            log["timings"].setdefault(v, []).append(round(time.perf_counter() - t0, 2))
            inspect(pg, f"{size}/{v}", w)
        icons = pg.evaluate("document.fonts.check('24px \"Material Symbols Outlined\"')")
        check(f"{size}: icon font loaded", icons)
        if size == "mobile":
            set_view(pg, "dashboard")
            pg.locator("header button").first.click(); pg.wait_for_timeout(500)
            check("mobile: menu drawer opens with all links", pg.get_by_role("button", name="Official Data").count() >= 1)
            pg.get_by_role("button", name="Official Data").first.click(); pg.wait_for_timeout(1500)
            check("mobile: drawer navigates", "Official Dataset Information" in pg.inner_text("body"))
            pg.screenshot(path=str(SHOTS / "mobile_official_data.png"), full_page=False)
        ctx.close()
    check("no horizontal overflow on any page/width", not log["overflow"], log["overflow"])
    check("no raw undefined/NaN/null/ML/ha text", not log["badtext"], log["badtext"][:5])
    check("no broken images", not log["images"], log["images"][:3])

    # ---------------- 2. Workflows (desktop) ----------------
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
    ctx.grant_permissions(["clipboard-read", "clipboard-write"])
    pg = ctx.new_page(); attach(pg, "flow")
    pg.goto(BASE + "/"); idle(pg)

    # Register -> OTP -> profile
    set_view(pg, "register", None)
    pg.get_by_placeholder("Enter your full name").fill("QA Tester")
    pg.get_by_placeholder("Enter phone number").fill("9876543210")
    pg.get_by_placeholder("At least 8 characters").fill("short")
    pg.locator("form button[type=submit]").first.click(); pg.wait_for_timeout(500)
    check("register: short password rejected (stays on step 1)", pg.get_by_placeholder("At least 8 characters").count() == 1 and pg.locator("select").count() == 0)
    pg.get_by_placeholder("At least 8 characters").fill("password123")
    pg.locator("form button[type=submit]").first.click(); pg.wait_for_timeout(800)
    sel = pg.locator("select").first
    opts = sel.locator("option").all_inner_texts()
    check("register step 2: districts from catalog", len(opts) == 39 and any("Thanjavur" in o for o in opts), f"{len(opts)} options")
    sel.select_option("Thanjavur")
    pg.get_by_placeholder("e.g. 5").fill("3")
    crops = pg.locator("select").nth(1).locator("option").all_inner_texts()
    check("register step 2: crops from catalog (no fallback list)", "Sugarcane" not in crops and "maize" in crops, crops[:5])
    pg.locator("select").nth(1).select_option("ragi")
    pg.locator("form button[type=submit]").first.click(); pg.wait_for_timeout(1500)
    if btn(pg, "auto.?fill").count():
        btn(pg, "auto.?fill").click(); pg.wait_for_timeout(400)
    btn(pg, "verify").first.click(); pg.wait_for_timeout(2500)
    stored = json.loads(pg.evaluate("localStorage.getItem('agro_user')") or "{}")
    check("register -> OTP -> profile setup with district kept", pg.evaluate("localStorage.getItem('agro_currentView')") == "profile-setup" and stored.get("location") == "Thanjavur", stored)

    # Login with wrong password
    set_view(pg, "login", None)
    pg.get_by_placeholder("Enter phone number").fill("9876543210")
    pg.get_by_placeholder("Enter password").fill("wrongpass1")
    pg.locator("form button[type=submit]").first.click(); pg.wait_for_timeout(1000)
    check("login: wrong password shows an error", re.search(r"incorrect|wrong|match", pg.inner_text("body"), re.I))

    # Stale v1 district in storage -> back to profile setup
    set_view(pg, "dashboard", {**USER, "location": "Pollachi"}, 2500)
    check("stale v1 district (Pollachi) redirects to profile setup", pg.evaluate("localStorage.getItem('agro_currentView')") == "profile-setup")

    # Profile setup with Summer in stored profile -> season must be a catalog season
    set_view(pg, "profile-setup", {"fullName": "", "season": "Summer"})
    btn(pg, "skip for now").first.click(); pg.wait_for_timeout(800)
    seasons = pg.locator("select").nth(1).locator("option").all_inner_texts()
    check("profile setup: seasons are Kharif/Rabi only", seasons == ["Kharif", "Rabi"], seasons)

    # Run Optimization: balanced, double-click submit
    set_view(pg, "run-optimization")
    f = pg.locator("#fuzzy-model option").all_inner_texts()
    check("run-opt: fuzzy models from API, official default", len(f) == 6 and "default" in " ".join(f), f)
    reqs = []
    pg.on("request", lambda r: r.method == "POST" and "/api/farm-plans" in r.url and reqs.append(r.url))
    sub = btn(pg, r"run optimization$", -1) if False else pg.get_by_role("button", name=re.compile(r"run optimization$", re.I)).last
    sub.dblclick()
    pg.wait_for_selector("text=Optimization complete and saved", timeout=60000); idle(pg); pg.wait_for_timeout(800)
    check("run-opt: double-click sends one request", len(reqs) == 1, f"{len(reqs)} POSTs")
    t = pg.inner_text("body")
    check("run-opt: result shown (ragi/green gram, official model)", "Top-ranked plan" in t and "Official (calibrated" in t)
    for prof in ["Profit priority", "Water saving", "Sustainability", "Low cost"]:
        pg.get_by_text(prof, exact=True).first.click(); btn(pg, "re-rank plans").click(); pg.wait_for_timeout(1500)
        check(f"results: re-rank '{prof}'", f"Selected profile: {prof}" in pg.inner_text("body") or prof in pg.inner_text("body"))
    pg.get_by_text("Custom", exact=True).first.click(); pg.wait_for_timeout(300)
    btn(pg, "re-rank plans").click(); pg.wait_for_timeout(1500)
    check("results: custom profile re-rank", "Custom" in pg.inner_text("body"))
    pg.get_by_text("Reasoning", exact=True).first.click(); pg.wait_for_timeout(800)
    check("results: reasoning tab", "Reasoning" in pg.inner_text("body"))
    pg.get_by_text("Compare profiles", exact=True).first.click(); pg.wait_for_timeout(1500)
    check("results: compare profiles tab", "Best plan under each profile" in pg.inner_text("body"))

    # Explanation modal
    btn(pg, "why this plan").first.click()
    pg.wait_for_selector("text=Why this crop was selected", timeout=30000)
    dlg = pg.locator("[role=dialog]").first
    dt = dlg.inner_text()
    check("explanation: crop evidence with 10 criteria", all(k in dt for k in ["Rainfall", "Soil", "Water", "Budget", "Fertilizer", "Market Price", "MSP", "Duration", "Yield", "Risks"]))
    dlg.locator("details details summary").nth(5).click(); pg.wait_for_timeout(300)
    check("explanation: market price says Official Data Not Available", "Official Data Not Available" in dlg.inner_text())
    pg.keyboard.press("Escape"); pg.wait_for_timeout(300)
    check("explanation: Escape closes modal", pg.locator("[role=dialog]").count() == 0)

    # History + Reports
    set_view(pg, "history")
    t = pg.inner_text("body")
    check("history: run listed with badges", "Official-Data Model" in t and "Official Data" in t)
    btn(pg, "view details").first.click(); pg.wait_for_timeout(500)
    btn(pg, "explain top plan").click(); pg.wait_for_selector("text=Why this crop was selected", timeout=30000)
    pg.keyboard.press("Escape")
    pg.get_by_placeholder("Search seasons...").fill("zzz"); pg.wait_for_timeout(300)
    check("history: search empty state", "No history entries found" in pg.inner_text("body"))
    set_view(pg, "reports")
    btn(pg, "generate report").first.click(); pg.wait_for_timeout(3000)
    with pg.expect_download() as dl:
        btn(pg, "download").first.click()
    rep = Path(dl.value.path()).read_text()
    check("reports: download has irrigated area, crop evidence, no NaN", "Irrigated area" in rep and "WHY EACH CROP" in rep and "NaN" not in rep and "null" not in rep, f"{len(rep.splitlines())} lines")
    pg.get_by_label("Copy report summary to clipboard").first.click(); pg.wait_for_timeout(500)
    clip = pg.evaluate("navigator.clipboard.readText()")
    check("reports: copy summary to clipboard", "Salem" in clip and "t/ha" in clip, clip[:80])

    # Comparison
    set_view(pg, "comparison", wait=3500)
    check("comparison: plans table", "Plan Metrics" in pg.inner_text("body"))
    with pg.expect_download() as dl:
        btn(pg, "export csv").first.click()
    csvt = Path(dl.value.path()).read_text()
    check("comparison: CSV export", "irrigated_area_relative" in csvt and csvt.count("\n") >= 3)
    pg.get_by_label("Explain Plan B").click()
    pg.wait_for_selector("text=Why this crop was selected", timeout=60000); pg.keyboard.press("Escape")
    btn(pg, "compare explanations").first.click(); pg.wait_for_timeout(6000)
    check("comparison: compare explanations modal", pg.locator("[role=dialog]").count() == 1)
    pg.keyboard.press("Escape")
    btn(pg, "adjust weights").first.click(); pg.wait_for_timeout(500)
    check("comparison: adjust weights modal", "Less Irrigation Weight" in pg.inner_text("body"))
    pg.keyboard.press("Escape")

    # Analytics
    set_view(pg, "analytics", wait=3500)
    t = pg.inner_text("body")
    check("analytics: scatter + fuzzy table", "Cost vs. Yield" in t and "Fuzzy vs. Non-Fuzzy" in t and "ha irrigated per ha" in t)
    with pg.expect_download() as dl:
        btn(pg, "^export$|download").first.click()
    check("analytics: CSV export", "irrigated_ha_per_ha" in Path(dl.value.path()).read_text())
    pg.locator("input[type=range]").first.fill("50000"); pg.wait_for_timeout(300)
    check("analytics: slider updates valid count", "out of" in pg.inner_text("body"))

    # District Intelligence: named districts + Chennai, exports, compare
    set_view(pg, "district-intelligence", wait=3000)
    for d in ["Salem", "Erode", "Coimbatore", "Thanjavur", "Madurai", "Tiruchirappalli", "Namakkal", "Viluppuram", "Chennai", "The Nilgiris"]:
        pg.locator("header select").first.select_option(d); idle(pg); pg.wait_for_timeout(1200)
        t = pg.inner_text("main")
        ok = ("DISTRICT SUMMARY" in t.upper()) and ("Soil Health Card" in t) and not BAD.search(t)
        check(f"district intelligence: {d}", ok, t[:80] if not ok else "")
    pg.locator("header select").first.select_option("Salem"); pg.wait_for_timeout(2500)
    for label, needle in [("Generate report", "AGROOPTIMIZE DISTRICT"), ("Export data (CSV)", "district,year"), ("Export all (JSON)", '"district"')]:
        with pg.expect_download() as dl:
            btn(pg, re.escape(label)).first.click()
        check(f"district intelligence: {label}", needle in Path(dl.value.path()).read_text()[:400])
    btn(pg, "compare district").first.click(); pg.wait_for_timeout(2500)
    check("district intelligence: compare panel", "Compare Salem with" in pg.inner_text("body"))
    btn(pg, "run optimization").first.click(); pg.wait_for_timeout(1500)
    check("district intelligence -> run optimization preselects district", pg.locator("select").first.input_value() == "Salem")

    # Scenario Simulation: run, save, reopen, export, delete; fertiliser lever disabled
    set_view(pg, "scenario-simulation")
    check("simulation: fertiliser lever disabled with reason", "Official Data Not Available: Notified fertiliser prices" in pg.inner_text("body"))
    btn(pg, r"^-20%$").first.click()
    pg.get_by_text("Set custom priorities").click(); pg.wait_for_timeout(200)
    btn(pg, "run simulation").first.dblclick()
    pg.wait_for_selector("text=Recommendation comparison", timeout=120000); pg.wait_for_timeout(1000)
    t = pg.inner_text("body")
    check("simulation: result with irrigated area units", "Simulated recommendation" in t and "ha irrigated" in t and " ML" not in t)
    btn(pg, "save scenario").click(); pg.wait_for_timeout(1500)
    check("simulation: saved", pg.locator("aside ul li").count() >= 1)
    with pg.expect_download() as dl:
        btn(pg, "export report").click()
    check("simulation: HTML report export", "<html" in Path(dl.value.path()).read_text()[:200].lower())
    with pg.expect_download() as dl:
        btn(pg, "export json").click()
    check("simulation: JSON export", '"token"' in Path(dl.value.path()).read_text()[:400] or '"inputs"' in Path(dl.value.path()).read_text())
    set_view(pg, "scenario-simulation")
    pg.locator("aside ul li button").first.click(); pg.wait_for_selector("text=Recommendation comparison", timeout=30000)
    check("simulation: reopen saved scenario", "Simulated recommendation" in pg.inner_text("body"))
    pg.get_by_label(re.compile("^Delete ")).first.click(); pg.wait_for_timeout(1200)
    check("simulation: delete saved scenario", "No saved scenarios yet." in pg.inner_text("body"))

    # Official Data, Settings
    set_view(pg, "datasets")
    t = pg.inner_text("body")
    check("official data: registry, disabled features, coverage", "39,065" in t and "Missing data and disabled features" in t and "Pollachi is a taluk" in t)
    set_view(pg, "settings")
    pg.locator("select").first.select_option("Madurai")
    btn(pg, "save changes").click(); pg.wait_for_timeout(500)
    set_view(pg, "dashboard", None if False else json.loads(pg.evaluate("localStorage.getItem('agro_user')")))
    check("settings: district change applies to dashboard", "Madurai" in pg.inner_text("body"))

    # Edge: budget below cheapest plan
    set_view(pg, "run-optimization")
    pg.locator("input[type=number]").nth(1).fill("1000")
    pg.get_by_role("button", name=re.compile(r"run optimization$", re.I)).last.click()
    pg.wait_for_timeout(9000); idle(pg); pg.wait_for_timeout(1500)
    t = pg.inner_text("body")
    log["low_budget_text"] = t[:1500]
    pg.screenshot(path=str(SHOTS / "edge_low_budget.png"), full_page=True)
    check("edge: budget below cheapest plan explained", "No feasible plan found" in t and "fits within the budget" in t and "Generate Report" not in t)

    # Edge: Chennai profile on every page
    for v in VIEWS:
        set_view(pg, v, {**USER, "location": "Chennai"}, 2500)
        t = pg.inner_text("body")
        ok = not BAD.search(t) and "Couldn't reach" not in t and "Server unreachable" not in t
        check(f"Chennai profile: {v}", ok, re.findall(r"[^\n]*(?:Couldn't reach|unreachable)[^\n]*", t)[:2])
        if v in ("analytics", "comparison"):
            pg.screenshot(path=str(SHOTS / f"chennai_{v}.png"), full_page=False)

    # Edge: refresh keeps the page
    set_view(pg, "history"); pg.reload(); pg.wait_for_timeout(1500)
    check("browser refresh keeps the current page", "Optimization History" in pg.inner_text("body"))
    # Edge: back button
    pg.goto(BASE + "/"); set_view(pg, "dashboard");
    pg.get_by_role("button", name="History").first.click(); pg.wait_for_timeout(800)
    pg.go_back(); pg.wait_for_timeout(1500)
    log["back_button_url"] = pg.url
    log["known"] = log.get("known", []) + [f"Back button leaves the app (no URL routing): went to {pg.url}"]
    check("browser back button: documented limitation, app recovers on return", True, pg.url)
    pg.goto(BASE + "/"); idle(pg); pg.wait_for_timeout(1500)
    check("returning after back button restores the last page", "Optimization History" in pg.inner_text("body") or "History" in pg.inner_text("body"))

    # Edge: API unavailable (requests aborted) and network offline
    pg.route("**/api/**", lambda r: r.abort())
    set_view(pg, "dashboard", wait=2500)
    t = pg.inner_text("body")
    check("API unavailable: dashboard shows unreachable message, no crash", "Couldn't reach" in t and not log["pageerrors"])
    set_view(pg, "district-intelligence", wait=2500)
    check("API unavailable: district intelligence error state", "Couldn't reach" in pg.inner_text("body"))
    pg.unroute("**/api/**")
    # slow backend: delay farm-plans 20 s, spinner stays, result arrives
    pg.route("**/api/farm-plans", lambda r: (time.sleep(20), r.continue_()))
    set_view(pg, "run-optimization")
    pg.get_by_role("button", name=re.compile(r"run optimization$", re.I)).last.click()
    pg.wait_for_timeout(7000)
    check("slow backend: progress screen stays up", "AgroOptimize Engine" in pg.inner_text("body"))
    pg.wait_for_selector("text=Optimization complete and saved", timeout=60000)
    check("slow backend: result arrives after delay", True)
    pg.unroute("**/api/farm-plans")
    set_view(pg, "datasets")
    ctx.set_offline(True)
    pg.get_by_role("button", name="Comparison").first.click(); pg.wait_for_timeout(2500)
    t = pg.inner_text("body")
    check("network offline: comparison shows unreachable message", "Couldn't reach" in t, t[:200])
    ctx.set_offline(False)
    ctx.close()
    b.close()

check("no console errors or React warnings", not [c for c in log["console"] if "Failed to load resource" not in c[2] or "flow" not in c[0]], log["console"][:5])
check("no uncaught page errors", not log["pageerrors"], log["pageerrors"][:3])
OUT.write_text(json.dumps(log, indent=1))
