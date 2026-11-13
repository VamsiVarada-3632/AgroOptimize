"""Capture the working prototype for the review slides.

Prerequisites (from the repository root):
  1. Build the frontend against the local API (keeps frontend/dist untouched):
       cd frontend && VITE_API_BASE=http://localhost:8000 npx vite build --outDir /tmp/agro_dist_local --emptyOutDir
  2. Start the backend serving that build with an empty results folder:
       AGROOPTIMIZE_FRONTEND_DIST=/tmp/agro_dist_local AGROOPTIMIZE_RESULTS_DIR=/tmp/agro_ui_results \
         python -m uvicorn app.main:app --port 8000
  3. pip install playwright (uses the installed Google Chrome; no browser download)
Then:  python final_ppt/assets/scripts/capture_screenshots.py

The profile used for the dashboard pages is district Salem, season Rabi, 5 ha, primary crop maize
(values the real profile form accepts); no name is filled in. Long pages are saved full-page, with a
cropped "top" copy (suffix b) for slides.
"""
import html
import json
import os
import re
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8000"
OUT = Path(__file__).resolve().parents[2] / "screenshots"
USER = {"fullName": "", "location": "Salem", "landSize": "5", "primaryCrop": "maize", "season": "Rabi", "avatar": None}


def shot(pg, name, full=True):
    pg.screenshot(path=str(OUT / f"{name}.png"), full_page=full)
    print("captured", name, flush=True)


def goto_view(pg, view, user=USER):
    pg.evaluate("([u, v]) => { if (u) localStorage.setItem('agro_user', JSON.stringify(u)); else localStorage.removeItem('agro_user');"
                " localStorage.setItem('agro_currentView', v); }", [user, view])
    pg.reload()
    pg.wait_for_load_state("networkidle")
    pg.wait_for_timeout(2500)


def button(pg, pattern):
    return pg.get_by_role("button", name=re.compile(pattern, re.I))


def settle(pg, ms):
    pg.wait_for_timeout(ms)
    pg.wait_for_load_state("networkidle")
    pg.wait_for_timeout(1500)


def crop_top(src, dst, css_height):
    im = Image.open(OUT / src)
    w, h = im.size
    tmp = OUT / (dst + ".tmp.png")
    im.crop((0, 0, w, min(h, css_height * 2))).save(tmp)
    os.replace(tmp, OUT / dst)
    print("cropped", dst)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        pg = ctx.new_page()
        pg.goto(BASE + "/")
        pg.wait_for_timeout(3000)
        shot(pg, "01_homepage_onboarding", full=False)
        goto_view(pg, "login", None)
        shot(pg, "02_login", full=False)
        goto_view(pg, "profile-setup", {"fullName": ""})
        shot(pg, "03_profile_setup_step1")
        button(pg, r"skip for now").first.click()
        pg.wait_for_timeout(1500)
        shot(pg, "04_profile_setup_input_form")
        goto_view(pg, "dashboard")
        shot(pg, "05_dashboard")

        # Run Optimization (Salem, Rabi, 5 ha), its ranking, reasoning and explanation, then History and Reports
        goto_view(pg, "run-optimization")
        pg.locator("select").nth(0).select_option("Salem")
        pg.locator("select").nth(1).select_option("Rabi")
        pg.wait_for_timeout(500)
        shot(pg, "06_run_optimization_input_form")
        button(pg, r"run optimization$").last.click()
        settle(pg, 10000)
        shot(pg, "07_optimization_results_recommendation")
        pg.get_by_text("Reasoning", exact=True).first.click()
        pg.wait_for_timeout(1500)
        shot(pg, "07b_topsis_reasoning")
        button(pg, r"why this plan").first.click()
        settle(pg, 3000)
        shot(pg, "08_explainability_recommended_plan", full=False)
        dlg = pg.locator("[role=dialog]").first
        dlg.evaluate("el => { const s=[...el.querySelectorAll('*')].find(e => e.scrollHeight > e.clientHeight + 50);"
                     " if (s) s.scrollTop = s.scrollHeight * 0.55; }")
        pg.wait_for_timeout(800)
        shot(pg, "08b_explainability_details", full=False)
        # Per-crop official evidence: open the first crop's Rainfall card and capture the section
        pg.set_viewport_size({"width": 1440, "height": 2300})   # tall enough for the whole section inside the dialog
        pg.wait_for_timeout(500)
        sec = dlg.locator("section", has_text="Why this crop was selected").first
        sec.scroll_into_view_if_needed()
        sec.locator("details details summary").first.click()
        pg.wait_for_timeout(600)
        sec.screenshot(path=str(OUT / "08c_explainability_crop_evidence.png"))
        print("captured 08c_explainability_crop_evidence", flush=True)
        pg.set_viewport_size({"width": 1440, "height": 900})
        pg.keyboard.press("Escape")
        goto_view(pg, "history")
        shot(pg, "12_history")
        goto_view(pg, "reports")
        shot(pg, "13_reports")

        goto_view(pg, "analytics")
        pg.wait_for_timeout(2000)
        shot(pg, "09_analytics_pareto_front")
        goto_view(pg, "comparison")
        pg.wait_for_timeout(1500)
        shot(pg, "10_comparison_plans")
        button(pg, r"why this plan").first.click()
        settle(pg, 3000)
        shot(pg, "11_explainability_comparison_plan")

        goto_view(pg, "district-intelligence")
        pg.wait_for_timeout(1500)
        shot(pg, "14_district_intelligence")
        goto_view(pg, "scenario-simulation")
        pg.locator("select").nth(0).select_option("Salem")
        pg.locator("select").nth(1).select_option("Rabi")
        button(pg, r"^-20%$").first.click()          # rainfall -20 %
        pg.wait_for_timeout(400)
        shot(pg, "15_scenario_simulation_inputs")
        button(pg, r"run simulation").first.click()
        settle(pg, 15000)
        shot(pg, "16_scenario_simulation_results")
        goto_view(pg, "settings")
        shot(pg, "17_settings")
        goto_view(pg, "datasets")
        shot(pg, "21_official_datasets_page")

        pg.goto(BASE + "/docs")
        pg.wait_for_timeout(4000)
        shot(pg, "18_api_docs_swagger")
        for url, name in [("/api/datasets", "19_api_official_datasets_registry"), ("/api/soil-master/Salem", "20_api_soil_master_salem")]:
            r = pg.request.get(BASE + url)
            body = json.dumps(r.json(), indent=2, ensure_ascii=False)
            pg.set_content("<html><body style='margin:0;background:#fcfcfb;font-family:Menlo,monospace'>"
                           "<div style='padding:14px 22px;background:#eaf2fc;border-bottom:2px solid #2a78d6;font:600 16px Helvetica,Arial'>"
                           f"GET {BASE}{url} &nbsp;→&nbsp; HTTP {r.status} (live response, indented for reading)</div>"
                           "<pre style='margin:0;padding:16px 22px;font-size:13px;line-height:1.45;white-space:pre-wrap'>"
                           f"{html.escape(body)}</pre></body></html>")
            pg.wait_for_timeout(300)
            shot(pg, name)
        browser.close()
    crop_top("14_district_intelligence.png", "14b_district_intelligence_top.png", 1800)
    crop_top("16_scenario_simulation_results.png", "16b_scenario_simulation_results_top.png", 1800)
    crop_top("18_api_docs_swagger.png", "18b_api_docs_swagger_endpoints.png", 1150)


if __name__ == "__main__":
    main()
