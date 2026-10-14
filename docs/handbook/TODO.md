# TODO – Remaining Work

Ordered by priority. IDs are referenced from the other documents. "Decision" items need the team/guide, not code.

## P0 – before the next review / viva

| ID | Task | Why | Owner hint |
|---|---|---|---|
| T-1 | **Decision:** default to the latest *observed* year (2023) or delete the 2024 estimated rows | Every default result and the dashboard trend currently use synthetic 2024 data (flagged in UI now) | Team + guide |
| T-2 | **Decision:** establish and write down the provenance of the 2020–2023 baseline; align the paper, survey and viva answers with it | Paper says "government" data; repo says "course-provided"; data shows synthetic signatures | Team |
| T-7 | Work only in the repo's `frontend/`; retire the local `stitch_agrooptimize_app/` copy | Two copies drift; the backup tarball in `_backups/` is the only copy of the pre-audit state | Frontend owner |
| T-12 | Regenerate `agrooptimize-backend/docs/results/*.md` and API examples from the current data; update `README.md` (use `docs/README_UPDATED.md`) and `notes/viva_prep.md` (rule count, test count, prices, "real data" wording) | Reported numbers are not reproducible today | Docs owner |
| T-9 | Move `final_year_project/.github/workflows/deploy-backend.yml` into the repo as `.github/workflows/`, dropping the `agrooptimize-backend/` path prefix and `cd`, and add the `FLY_API_TOKEN` secret | The file sits outside the git repo, so GitHub has never run it | Backend owner |

## P1 – model and research quality

| ID | Task |
|---|---|
| T-4 | Add agronomic response: irrigation via FAO-33 `Ky`, nitrogen via Mitscherlich/quadratic-plateau, so multipliers can pay off (RESEARCH_REVIEW R-1) |
| T-10 | Replace the tonnage objective with net return using verified MSP/market prices (R-2) |
| T-3 | Seasonal rainfall deviation from totals; Rabi = Oct(Y)–Mar(Y+1) (DATA_VALIDATION D5–D6) |
| T-5 | Remove or rewrite fuzzy rules 15, 19, 21, 25, 26 (no effect); fix rule comments |
| T-17 | Multi-seed evaluation script (≥20 seeds), fixed-bounds hypervolume, NSGA-III and ε-constraint LP baselines |
| T-18 | Let uncertainty affect water/feasibility (e.g. irrigation_risk scales effective rainfall) or add rainfall scenarios |

## P2 – engineering

| ID | Task |
|---|---|
| T-6 | Schema/range validation of CSVs at load time (pandera or explicit checks) |
| T-8 | Delete or archive `final_year_project/datasets/` |
| T-11 | Unify recommendation logic (TOPSIS vs Comparison weight badge vs "cheapest compliant") |
| T-13 | Golden-master regression test (fingerprint of key outputs, as used during the audit) |
| T-14 | Read `RESULTS_DIR`, seed, log level from env; drop unused `.env.example` keys |
| T-15 | Printable/PDF report (print stylesheet or server-side PDF) |
| T-16 | `pip-audit` and `npm audit` in CI; pin `flyctl-actions` to a SHA; non-root Docker user; split dev requirements |
| T-19 | Thread pymoo `random_state` through operators and remove the run lock (re-baseline results) |
| T-20 | TTL cache for Open-Meteo; memoise compare-fuzzy; store plan-#1 metrics in run summaries |
| T-21 | Rate limiting + per-client quota + retention policy for `results/`; require `client_id` on `GET /api/results/{id}` |
| T-22 | Return relative file names instead of absolute `saved_files` paths |
| T-23 | Split `dashboard_service.py`; typed response models for all endpoints |

## P3 – UX

| ID | Task |
|---|---|
| T-24 | react-router with per-page URLs |
| T-25 | Pass the user's land size (and a season selector) to Analytics/Comparison |
| T-26 | Accessibility pass (buttons not divs, aria-labels, dialog focus trap, `aria-hidden` icons, label association) |
| T-27 | Hide the language switcher or implement i18n (English/Tamil) |
| T-28 | Progress indicator tied to the real request |
| T-29 | Persist generated reports; history sort/delete |
| T-30 | Self-host logo, images and the icon font |
| T-31 | Frontend tests (Vitest + RTL) and a Playwright e2e flow |
