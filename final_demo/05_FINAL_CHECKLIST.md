# 05 – Final checklist (before the review)

**The day before**
- [ ] QA fixes merged to `main` and Render shows the new deploy as **Live** (Settings → branch `main`)
- [ ] https://agrooptimize.onrender.com/api/datasets returns 10 datasets, 39,065 rows
- [ ] Smoke test: `python scripts/smoke_test_deployment.py --base-url https://agrooptimize.onrender.com` → 37/37
- [ ] Optional browser check: `python scripts/verify_production_ui.py https://agrooptimize.onrender.com shots out.json` → all PASS
- [ ] Slides: numbers on the results slide say which platform they came from (Mac run vs live site)
- [ ] Laptop charged; Chrome updated; second browser profile without extensions

**30 minutes before**
- [ ] Open the site to wake the free server (first request 30–60 s)
- [ ] Profile: Salem, Rabi, 5 ha (Settings → Farm Location)
- [ ] One Salem Rabi run saved (History not empty)
- [ ] Second tab: Scenario Simulation run for Salem, Rabi, rainfall −20 % (≈70 s)
- [ ] Zoom 100 %, close other tabs, notifications off, screen-share tested

**During the demo (see 03_DEMO_SCRIPT.md)**
- [ ] Home → weather card "Official Data Not Available"
- [ ] Official Data → 10 datasets, 39,065 rows, 9 disabled features
- [ ] Run Optimization Salem Rabi 5 ha → maize 37 / ragi 45 / red gram 8 / green gram 10, TOPSIS 0.6485
- [ ] Re-rank Sustainability, back to Balanced
- [ ] Why this plan? → confidence 64.8 %; ragi → Rainfall evidence; Market Price "Official Data Not Available"
- [ ] Budget ₹1,00,000 → jowar 24 / green gram 76, ₹84,287, "Use with caution"
- [ ] District Intelligence Salem → Soil Health Card
- [ ] Scenario Simulation tab → verdicts and paired test
- [ ] History badges

**Answers ready (04_COMMON_FAILURES.md)**
- [ ] Why one year / district level / 9 fuzzy districts
- [ ] Why Chennai and Nilgiris have no plan
- [ ] Why the live mix differs from the slides
- [ ] Why it is slow on the live site
- [ ] What "Official Data Not Available" means

**Backup if the live site fails**
- [ ] Local run: `uvicorn app.main:app --port 8000` with the built frontend (`AGROOPTIMIZE_FRONTEND_DIST=frontend/dist`), then http://localhost:8000
- [ ] Screenshots: `final_ppt/screenshots/`, `docs/deployment/screenshots/`
