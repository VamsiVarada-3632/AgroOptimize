# Dependencies

## 1. Backend (`agrooptimize-backend/requirements.txt`)

Only lower bounds are pinned (`>=`); there is no lock file, so a fresh install today can resolve to different versions than the ones tested. Versions below are what the 205-test suite passed with on 2026-09-29 (Python 3.13.9, Anaconda); the Docker image uses Python 3.11.

| Package | Constraint | Tested | Why it exists | Used in |
|---|---|---|---|---|
| fastapi | ≥0.110 | 0.141.1 | HTTP API, validation, OpenAPI docs | `app/main.py` |
| uvicorn[standard] | ≥0.27 | 0.52.2 | ASGI server | Dockerfile CMD |
| pydantic | ≥2.5 | 2.12.4 | request/response models | `app/schemas.py` |
| pandas | ≥2.1 | 2.3.3 | CSV loading, filtering, aggregation, CSV output | `data/`, `services/` |
| numpy | ≥1.26 | 2.3.5 | vectorised objectives, operators, TOPSIS | `optimization/`, `decision/` |
| pymoo | ≥0.6.1 | 0.6.2 | NSGA-II survival/selection, `Problem`, hypervolume `HV` | `optimization/` |
| scikit-fuzzy | ≥0.4.2 | 0.5.0 | Mamdani `ControlSystem`, `trimf` | `fuzzy/engine.py` |
| scipy | ≥1.10 | 1.16.3 | paired t-test (`stats.ttest_rel`); was already installed as a dependency of pymoo and scikit-fuzzy, now listed because it is imported directly | `services/simulation_service.py` |
| networkx | ≥3.2 | (installed) | **indirect**: imported by `skfuzzy.control` (rule graph); not imported by app code | – |
| matplotlib | ≥3.8 | 3.11.1 | convergence PNG (Agg backend) | `results_store._plot_convergence` |
| requests | ≥2.31 | 2.32.5 | Open-Meteo call | `dashboard_service._get_weather_live` |
| pytest | ≥8.0 | 8.4.2 | tests | `tests/` – **test-only, but installed in the production image** |
| httpx | ≥0.28 | 0.28.1 | required by `fastapi.testclient` | tests – **test-only** |

Since the Render deployment: `requirements.txt` pins exact versions (the ones the tests and published results use) and `requirements-dev.txt` adds pytest and httpx; the Dockerfile installs binary wheels only (no gcc/g++). A full lock with hashes (`pip-compile --generate-hashes`) remains a possible next step.

## 2. Frontend (`stitch_agrooptimize_app/package.json`)

| Package | Range | Locked | Why | Kind |
|---|---|---|---|---|
| react, react-dom | ^19.2.8 | 19.2.8 | UI | runtime |
| tailwindcss | ^4.3.3 | 4.3.3 | utility CSS, `@theme` tokens | build |
| @tailwindcss/vite | ^4.3.3 | 4.3.3 | Tailwind v4 Vite integration | build |
| vite | ^8.2.0 | 8.2.1 | dev server, bundler | dev |
| @vitejs/plugin-react | ^6.0.4 | 6.0.5 | JSX transform, fast refresh | dev |
| oxlint | ^1.75.0 | 1.78.0 | lint (`react`, `oxc` plugins) | dev |
| @types/react, @types/react-dom | ^19 | 19.2.18 / 19.2.4 | editor type hints only (project is JS, not TS) | dev |
| vitest | ^5.0.4 | 5.0.4 | frontend unit/render tests (`npm test`); components rendered with react-dom/server | dev |

`package-lock.json` is committed → reproducible installs. Tailwind is listed under `dependencies` though it is build-time only (harmless for a static build).

## 3. Runtime external services

| Service | Used for | Failure mode |
|---|---|---|
| Open-Meteo `api.open-meteo.com/v1/forecast` | live weather (no key; free for non-commercial use per Open-Meteo's terms) | 5 s timeout → CSV fallback |
| Google Fonts (Inter, Montserrat, Material Symbols) | typography and **all icons** | icons render as words (observed) |
| `lh3.googleusercontent.com/aida-public/...` | logo, onboarding images, favicon (Stitch-generated asset URLs) | broken images; URLs are not guaranteed to be permanent |
| Vercel | frontend hosting | – |
| Fly.io | backend hosting + volume | – |
| GitHub Actions + `superfly/flyctl-actions@master` | CI/CD | action pinned to a moving branch (`@master`) – pin a tag/SHA |

## 4. Dependency hygiene findings

| Finding | Recommendation |
|---|---|
| No backend lock file | add one |
| Test tools shipped to production | split requirements |
| `flyctl-actions@master` | pin to a release |
| External logo/images | vendor into `public/` |
| Material Symbols font (~all icons) loaded from Google at runtime | self-host or subset the icon font |
