# Deployment Report

What was done to put AgroOptimize on Render, how it was verified, and what is still open. How to deploy, update and roll back: [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md).

## 1. Summary

* **Live URL:** https://agrooptimize.onrender.com. One Docker web service on Render's free plan (Singapore) serves the React app, the API, the API docs and the health check from one origin.
* **Built from the repository.** `render.yaml` is a Render Blueprint, and the two-stage `Dockerfile` builds the frontend with Node 22, then installs the pinned Python dependencies on Python 3.13 from binary wheels only.
* **Every endpoint works.** The smoke test passes 34 of 34 checks against the live service: pages, assets, API, docs, saving and loading, and error cases.
* **Results.** Everything that does not run NSGA-II is identical to a local server. NSGA-II results are reproducible on Render from one deploy to the next, but differ from a Mac's at the last bits of floating-point arithmetic, so the fronts follow a different, equally good path (§4).
* **No code paths changed for local development.** Without a frontend build the API behaves as before; `npm run dev` and `uvicorn --reload` work unchanged.

## 2. Changes

| Area | Change | Files |
|---|---|---|
| Dependencies | `requirements.txt` pins the exact versions behind the tests and published results; test tools moved to `requirements-dev.txt` | `requirements.txt`, `requirements-dev.txt` |
| Storage | saved runs go to `AGROOPTIMIZE_RESULTS_DIR` (default `results/`) | `app/config.py` |
| Serving the frontend | FastAPI serves `frontend/dist`: hashed assets cached for a year, other page paths fall back to `index.html`, unknown `/api`, `/docs` and `/health` paths stay JSON 404s; gzip over 1 kB; HEAD answered for pages and `/health` | `app/frontend.py`, `app/main.py` |
| API address | production builds call the API on the page's own origin; `VITE_API_BASE` still overrides it | `frontend/src/services/api.js` |
| Page loading | each page is a lazily loaded chunk: initial JavaScript 476 → 211 kB (122 → 66 kB gzipped) | `frontend/src/App.jsx`, `utils/lazyView.js`, `components/ViewLoading.jsx` |
| Container | two-stage image, non-root user `agro`, listens on `$PORT`, refuses to compile packages from source | `Dockerfile`, `.dockerignore` |
| Render | service `agrooptimize`, health check `/health`, auto-deploy with `buildFilter` so documentation commits don't rebuild, `AGROOPTIMIZE_NSGA2_MODE=original`, a commented-out persistent disk | `render.yaml` |
| Verification | smoke test: 34 checks and 17 result fingerprints, recorded from one server and compared against another | `scripts/smoke_test_deployment.py` |
| Tests | serving, fallback and 404 rules, HEAD requests, results folder setting; API base and lazy loading in the frontend | `tests/test_deployment.py`, `frontend/src/services/api.test.js`, `frontend/src/utils/lazyView.test.js` |

## 3. Deployment history

| Step | Outcome | Fix |
|---|---|---|
| First Blueprint sync | build failed after 19 s: `COPY frontend/public` referred to a folder that is not in the repository | the line was removed; Vite copies `public/` into `dist/` anyway when it exists |
| Second build | live; smoke test 34/34 | — |
| Fingerprint comparison with a local server | NSGA-II results differ (§4) | an attempt to make the mutation's random draws platform-independent was reverted, because it would have changed every published result |
| Repeated comparisons | `last_dataset_update`, saved-file names and `-0.0` vs `0.0` caused false differences | the smoke test now ignores the first two and treats the zeros as equal |
| HEAD requests (used by uptime monitors) | `405 Method Not Allowed` | HEAD is answered for pages and `/health` |

## 4. Result reproducibility

Fingerprints are hashes of the response with timings, ids and dates removed.

| Endpoint group | Render vs local Mac | Render vs Render (redeploys) |
|---|---|---|
| Catalog, region profile, soil profile, dashboard, fuzzy vs non-fuzzy comparison, fuzzy audit, fuzzy explanation, the budget farm plan | identical | identical |
| Farm plans (saved and unsaved), saved result and its explanation, plans, comparison and its explanation, scenario simulation | different | identical |
| District Intelligence | changes with the date on any server | — |

**Why NSGA-II differs:** the mutation uses NumPy's legacy Gaussian generator. On arm64 NumPy computes `x1² + x2²` with a fused multiply-add, and macOS's `log` is not correctly rounded in about 0.07 % of cases; Linux on x86-64 does neither. The first different bit changes one mutation, and the evolutionary search then takes a different path. The quality is the same: over 12 district-seasons Render's fronts have 0.7 % higher hypervolume on average, within seed-to-seed variation.

**What this means:** results are reproducible per platform. Published tables must be regenerated on the machine they are reported for, or on the deployment itself. Making the random stream platform-independent would be one deliberate change to every result (NSGAII_IMPROVEMENTS.md §7).

## 5. Performance (free plan, warm instance)

| Request | Time |
|---|---|
| Health, catalog, pages, saved results | 0.2–0.4 s |
| Farm plan (one NSGA-II run) | 7–11 s |
| Comparison, plans | ~11 s |
| Fuzzy vs non-fuzzy comparison | ~18 s |
| Scenario simulation (5 seeds) | ~80 s |
| First request after the service has slept | 30–60 s extra |

The free instance has 0.1 CPU, so optimisation runs are 20–30 times slower than on a laptop. A paid instance (`starter` or higher) brings them close to local times.

## 6. Known limitations

* **Live weather falls back to the dataset.** On Render, `/api/weather/{district}` answers with "Historical CSV average (live weather unavailable)": the call to Open-Meteo fails from the service, and the reason is only in the service logs. Locally the same code returns live weather. The fallback keeps the dashboard working.
* **Saved runs are temporary on the free plan.** History, Reports and saved simulations are wiped on every redeploy, restart or wake-up. A persistent disk needs a paid plan (DEPLOYMENT_GUIDE.md §2).
* **Cold starts.** The free service sleeps after about 15 minutes without traffic.
* **Slow optimisation** on the free CPU (§5); one worker process, so concurrent runs wait.
* **Platform-dependent NSGA-II results** (§4).

## 7. Future improvements

1. Read the Open-Meteo error from the Render logs and fix live weather (likely an outbound timeout or DNS setting).
2. A paid instance with a persistent disk, or a small database, for saved runs.
3. Run the backend and frontend test suites in CI before Render deploys.
4. Move long simulations to a background job so the request does not wait 80 s.
5. A platform-independent random stream, if identical results on every machine become a requirement.
