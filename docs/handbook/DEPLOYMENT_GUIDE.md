# Deployment Guide

AgroOptimize runs on [Render](https://render.com) as **one Docker web service** that serves the React frontend, the FastAPI backend and the API docs from a single URL. This guide explains how that works and how to deploy, redeploy, update and roll back.

## 1. How the deployment works

```
GitHub repo ──push──► Render (Blueprint: render.yaml)
                         │ docker build (Dockerfile)
                         │   stage 1  node:22-slim      npm ci → vite build → frontend/dist
                         │   stage 2  python:3.13-slim  pip install pinned wheels; copy app/, data/, dist/
                         ▼
                  container: uvicorn app.main:app --port $PORT   (user "agro", 1 worker)
                         │
   https://<service>.onrender.com
       /                → React app (index.html; any page path falls back to it)
       /assets/*        → hashed JS/CSS, cached for a year
       /api/*           → FastAPI endpoints (JSON, gzip over 1 kB)
       /docs, /redoc    → Swagger UI / ReDoc;  /openapi.json
       /health          → {"status": "ok"}  (Render health check)
```

* **Same origin.** The production build calls the API on `window.location.origin` (`frontend/src/services/api.js` → `resolveApiBase`), so no CORS setup and no API URL are needed. `VITE_API_BASE` still overrides it for a frontend hosted elsewhere, e.g. Vercel (`frontend/vercel.json`), together with `CORS_ALLOW_ORIGINS` on the backend.
* **Frontend serving.** `app/frontend.py` mounts `frontend/dist` after every API route. Unknown `/api/…`, `/docs/…` and `/health/…` paths stay JSON 404s, and nothing is mounted when there is no build, so local development is unchanged.
* **Identical results.** `requirements.txt` pins the exact library versions the tests and published results use, and `AGROOPTIMIZE_NSGA2_MODE=original` selects the published NSGA-II engine. `scripts/smoke_test_deployment.py` checks that a deployment gives the same results as a local server (§6).

## 2. Configuration

| Setting | Where | Value | Purpose |
|---|---|---|---|
| Service | `render.yaml` | `agrooptimize`, Docker, plan `free`, region `singapore` | One web service |
| Health check | `render.yaml` | `/health` | Render restarts or keeps the old version if it fails |
| Auto-deploy | `render.yaml` | on, with `buildFilter` paths | Docs-only commits don't trigger a rebuild |
| `PORT` | set by Render | e.g. `10000` | uvicorn listens on it (the Dockerfile defaults to 8000) |
| `AGROOPTIMIZE_NSGA2_MODE` | `render.yaml` | `original` | Published engine; `enhanced` is experimental |
| `AGROOPTIMIZE_RESULTS_DIR` | optional | e.g. `/var/data/results` | Folder for saved runs and simulations (default `/app/results`) |
| `AGROOPTIMIZE_FRONTEND_DIST` | optional | path | Use a different frontend build |
| `CORS_ALLOW_ORIGINS` | optional | comma-separated origins | Only for a frontend on another domain |
| `VITE_API_BASE` | frontend build time, optional | URL | Only for a frontend on another domain |

There are **no secrets**: the only external API (Open-Meteo weather) needs no key.

### Storage
Saved runs (History, Reports, explanations of saved runs) and saved simulations are files in `/app/results`. On the **free plan the filesystem is temporary**: it is wiped when the service redeploys, restarts or wakes up after sleeping (free services sleep after about 15 minutes without traffic). Everything else is computed from the bundled dataset and needs no storage.

To keep saved runs, use a paid instance type with a persistent disk: in `render.yaml` change `plan: free` to `starter`, uncomment the `disk` block (mounted at `/var/data`) and add `AGROOPTIMIZE_RESULTS_DIR=/var/data/results`. The container runs as a non-root user (uid 10001). If the disk is not writable by that user, saving a run fails; check the logs after the first save.

## 3. First deployment

1. Push the branch to GitHub (the repository is public).
2. In the Render dashboard: **New → Blueprint**, connect the GitHub repository `VamsiVarada-3632/AgroOptimize`, and choose the branch to deploy (`main` once merged, or a feature branch for a preview).
3. Render reads `render.yaml`, shows the `agrooptimize` web service and creates it. The first build takes a few minutes: Node install and build, then Python wheels (~110 MB).
4. When the deploy is **Live**, open `https://<service>.onrender.com` and run the smoke test (§6).

## 4. Redeploy and update

| Task | How |
|---|---|
| Deploy new code | Merge or push to the deployed branch. Auto-deploy builds it if a path in `buildFilter` changed |
| Redeploy without changes | Dashboard → service → **Manual Deploy → Deploy latest commit** |
| Rebuild from scratch | **Manual Deploy → Clear build cache & deploy** (after dependency changes, or if a cached layer is suspect) |
| Change an environment variable | Dashboard → **Environment**, edit, save (Render redeploys). Keep `render.yaml` in sync |
| Change the dataset | Edit `data/raw/*.csv` and push. The data is loaded once per process, so the redeploy picks it up |
| Update dependencies | Change the pins in `requirements.txt` (and `package-lock.json` for the frontend), run the full test suites and the smoke-test comparison locally, then push. A new numpy/pymoo/scikit-fuzzy version can change optimisation results |

Zero-downtime: Render keeps the previous version running until the new one passes `/health`.

## 5. Rollback

1. Dashboard → service → **Events**: every deploy is listed with its commit.
2. Pick the last good deploy → **Rollback** (Render redeploys that build).
3. Auto-deploy stays on, so the next push deploys again. Revert the bad commit in git (`git revert <sha>`) so the branch matches what runs. Rollback alone does not change the repository.

Saved runs are not affected by a rollback on a persistent disk; on the free plan they are lost on any redeploy anyway.

## 6. Verifying a deployment

```bash
# reference from a local server on the same commit
uvicorn app.main:app --port 8000 &
python scripts/smoke_test_deployment.py --base-url http://localhost:8000 --record ref.json
# check the deployment
python scripts/smoke_test_deployment.py --base-url https://<service>.onrender.com --compare ref.json
```

The script calls 34 endpoints and pages: health, docs, the frontend and an asset, the SPA fallback, catalog, region profile, farm plans (saved and unsaved), saved result and its explanation, history, dashboard, weather, soil profile, plans, comparison and its explanation, fuzzy vs non-fuzzy, District Intelligence, fuzzy explain and audit, simulation run, save, list, load and delete, and three error cases. It compares 17 result fingerprints: optimisation, ranking, fuzzy and simulation outputs with timings and ids removed. It exits non-zero on any failure or difference.

The first request after the free service has slept takes ~30–60 s while the instance starts.

## 7. Local production run (without Docker)

```bash
cd frontend && npm ci && npm run build && cd ..
pip install -r requirements.txt
uvicorn app.main:app --port 8000          # http://localhost:8000 serves the app and the API
```

For development, keep using `npm run dev` (port 5173) and `uvicorn app.main:app --reload --port 8000`. The Vite dev server calls the backend on port 8000. If a local `frontend/.env.production` sets `VITE_API_BASE`, local production builds use that URL instead of the same origin.

## 8. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Build fails in `pip install` with "no matching distribution" | a pin without a Linux wheel for Python 3.13; pick a version that has one (the Dockerfile refuses to compile) |
| Build fails in `npm ci` | `package-lock.json` out of sync with `package.json`; run `npm install` locally and commit the lock |
| Deploy stuck "in progress", then fails the health check | the app did not start: check the logs for an import error or a wrong `PORT` |
| Page loads but shows "Couldn't reach the AgroOptimize server" | the build was made with a `VITE_API_BASE` pointing elsewhere; remove it |
| History empty after a while | free-plan storage was reset (§2) |
| First request very slow | free instance waking up |
| `/api/...` returns the HTML page | should never happen (tested); check that `mount_frontend` is still called last in `app/main.py` |
