# AgroOptimize: one image with the React frontend and the FastAPI backend
# (NSGA-II via pymoo, Mamdani fuzzy via scikit-fuzzy). The backend serves the
# built frontend (app/frontend.py), so the browser calls the API on the same
# origin. Used by Render (render.yaml); runs anywhere Docker does.

# ---- 1. Build the frontend ---------------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/index.html frontend/vite.config.js ./
COPY frontend/public ./public
COPY frontend/src ./src
RUN npm run build

# ---- 2. Runtime --------------------------------------------------------------
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MPLCONFIGDIR=/tmp/matplotlib \
    PORT=8000

WORKDIR /app

# Every pinned package ships a manylinux wheel for Python 3.13, so no
# compiler is needed; --only-binary makes a missing wheel fail the build
# instead of silently compiling a different binary.
COPY requirements.txt .
RUN pip install --only-binary=:all: -r requirements.txt

COPY app ./app
COPY data ./data
COPY --from=frontend /frontend/dist ./frontend/dist

# Run as an unprivileged user; it owns only the results folder (saved runs
# and simulations). AGROOPTIMIZE_RESULTS_DIR can point elsewhere, e.g. a
# persistent disk.
RUN useradd --create-home --uid 10001 agro \
    && mkdir -p /app/results \
    && chown agro:agro /app/results
USER agro

EXPOSE 8000

# One worker: optimisation runs are serialised by a lock anyway, and a
# single process keeps memory within a 512 MB instance. Render sets PORT.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" --proxy-headers --forwarded-allow-ips="*"
