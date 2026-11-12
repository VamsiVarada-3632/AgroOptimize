"""
Runtime benchmark of the backend: startup, dataset loading, preprocessing,
API latency, optimisation runtime and memory.

Every measurement runs in a fresh Python process (so "cold" really is cold)
and is repeated; the report gives the median and the spread. The script only
uses entry points that exist both before and after the official-data
migration, so the same file can be run inside a checkout of the
`published-v1` tag to compare the two data layers:

    git worktree add /tmp/agro-v1 published-v1
    cp scripts/benchmark_runtime.py /tmp/agro-v1/scripts/
    (cd /tmp/agro-v1 && python scripts/benchmark_runtime.py --json v1.json)
    python scripts/benchmark_runtime.py --json official.json

Measured stages
  startup        import app.main, then the first GET /health (process RSS after)
  build          rebuild of the official database from data/official/raw into a
                 temporary SQLite file (official data layer only; skipped on
                 versions without app.datasets.pipeline)
  load           loader.load_all() cold (cache cleared) and warm
  preprocess     get_region_season_profile() per case, cold and warm
  api            latency of read endpoints (after one warm-up call) and
                 POST /api/farm-plans
  optimize       run_pipeline() per case and seed (preprocessing -> fuzzy ->
                 NSGA-II -> TOPSIS), wall time, plus tracemalloc peak and
                 process peak RSS

Saved runs are written to a temporary results directory, so the dashboard and
history endpoints see the same (empty) history in both versions.

Usage:
    python scripts/benchmark_runtime.py [--repeats 5] [--seeds 3] [--json out.json]
        [--cases Coimbatore:Kharif,Erode:Rabi,...]
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = "Coimbatore:Kharif,Coimbatore:Rabi,Erode:Kharif,Erode:Rabi,Salem:Kharif,Salem:Rabi"
API_REPEATS = 20


def _rss_mb() -> float:
    import resource

    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # bytes on macOS, kilobytes on Linux
    return rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024


def _cases(spec: str):
    return [tuple(c.split(":")) for c in spec.split(",") if c]


# ---------------------------------------------------------------------------
# Workers (run in a child process, print one JSON object)
# ---------------------------------------------------------------------------


def work_startup(_args) -> dict:
    t0 = time.perf_counter()
    import app.main as main  # noqa: F401

    t1 = time.perf_counter()
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    t2 = time.perf_counter()
    r = client.get("/health")
    t3 = time.perf_counter()
    return {
        "import_s": t1 - t0,
        "first_health_s": t3 - t2,
        "health_status": r.status_code,
        "rss_mb": _rss_mb(),
    }


def work_build(_args) -> dict:
    try:
        from app.datasets.pipeline import build_database
    except ImportError:
        return {"available": False}
    from sqlalchemy import create_engine

    with tempfile.TemporaryDirectory() as tmp:
        engine = create_engine(f"sqlite:///{tmp}/bench.db")
        t = time.perf_counter()
        report = build_database(engine=engine, clean_dir=None)
        elapsed = time.perf_counter() - t
        engine.dispose()
    return {
        "available": True,
        "build_s": elapsed,
        "datasets": len(report),
        "rows_clean": sum(int(r["rows_clean"]) for r in report),
    }


def work_load(_args) -> dict:
    from app.data import loader

    rss0 = _rss_mb()
    loader.clear_cache()
    t0 = time.perf_counter()
    frames = loader.load_all()
    cold = time.perf_counter() - t0
    warm = []
    for _ in range(5):
        t = time.perf_counter()
        loader.load_all()
        warm.append(time.perf_counter() - t)
    return {
        "cold_s": cold,
        "warm_s": statistics.median(warm),
        "rows": {k: int(len(v)) for k, v in frames.items()},
        "rss_before_mb": rss0,
        "rss_after_mb": _rss_mb(),
    }


def work_preprocess(args) -> dict:
    from app.data import loader
    from app.data import preprocessing as pp

    loader.load_all()  # dataset loading is measured separately
    out = {}
    for loc, season in _cases(args.cases):
        t = time.perf_counter()
        try:
            p = pp.get_region_season_profile(loc, season)
        except ValueError as exc:
            out[f"{loc}:{season}"] = {"error": str(exc)}
            continue
        first = time.perf_counter() - t
        warm = []
        for _ in range(5):
            t = time.perf_counter()
            pp.get_region_season_profile(loc, season)
            warm.append(time.perf_counter() - t)
        out[f"{loc}:{season}"] = {
            "first_s": first,
            "warm_s": statistics.median(warm),
            "candidates": len(p.candidate_crops),
            "year": int(p.year),
        }
    return out


def _api_calls(cases):
    loc, season = cases[0]
    return [
        ("GET /health", "get", "/health", None),
        ("GET /api/catalog", "get", "/api/catalog", None),
        ("GET /api/region-profile", "get", f"/api/region-profile?location={loc}&season={season}", None),
        ("GET /api/soil-profile/{location}", "get", f"/api/soil-profile/{loc}", None),
        ("GET /api/dashboard/{location}", "get", f"/api/dashboard/{loc}", None),
        ("GET /api/district-intelligence/{location}", "get", f"/api/district-intelligence/{loc}", None),
    ]


def work_api(args) -> dict:
    import app.main as main
    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    cases = _cases(args.cases)
    out = {}
    for label, method, url, body in _api_calls(cases):
        r = getattr(client, method)(url)  # warm-up
        times = []
        for _ in range(API_REPEATS):
            t = time.perf_counter()
            r = getattr(client, method)(url)
            times.append(time.perf_counter() - t)
        times.sort()
        out[label] = {
            "status": r.status_code,
            "median_ms": statistics.median(times) * 1000,
            "p95_ms": times[int(0.95 * (len(times) - 1))] * 1000,
        }
    loc, season = cases[0]
    body = {"location": loc, "season": season, "total_land_ha": 5.0, "save_results": False}
    times = []
    for _ in range(3):
        t = time.perf_counter()
        r = client.post("/api/farm-plans", json=body)
        times.append(time.perf_counter() - t)
    out["POST /api/farm-plans"] = {
        "status": r.status_code,
        "median_ms": statistics.median(times) * 1000,
        "p95_ms": max(times) * 1000,
    }
    return out


def work_optimize(args) -> dict:
    import tracemalloc

    from app.data import loader
    from app.schemas import FarmPlanRequest
    from app.services import plan_service

    loader.load_all()
    out = {}
    for loc, season in _cases(args.cases):
        runs = []
        for seed in range(args.seeds):
            req = FarmPlanRequest(location=loc, season=season, total_land_ha=5.0, save_results=False)
            t = time.perf_counter()
            try:
                run = plan_service.run_pipeline(req, track_history=False, seed=seed)
            except ValueError as exc:
                runs = {"error": str(exc)}
                break
            runs.append({
                "seed": seed,
                "runtime_s": time.perf_counter() - t,
                "front_size": len(run.feasible_plans),
                "candidates": len(run.problem.crops) if hasattr(run.problem, "crops") else None,
            })
        out[f"{loc}:{season}"] = runs
    # tracemalloc slows Python down, so the peak is taken from a separate run
    loc, season = _cases(args.cases)[0]
    tracemalloc.start()
    plan_service.run_pipeline(
        FarmPlanRequest(location=loc, season=season, total_land_ha=5.0, save_results=False),
        track_history=False, seed=0,
    )
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {"runs": out, "tracemalloc_peak_mb": peak / (1024 * 1024), "rss_peak_mb": _rss_mb()}


WORKERS = {
    "startup": work_startup,
    "build": work_build,
    "load": work_load,
    "preprocess": work_preprocess,
    "api": work_api,
    "optimize": work_optimize,
}


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def _run_worker(task: str, args, env) -> dict:
    cmd = [sys.executable, str(Path(__file__).resolve()), "--worker", task,
           "--cases", args.cases, "--seeds", str(args.seeds)]
    res = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
    if res.returncode != 0:
        raise SystemExit(f"worker {task} failed:\n{res.stderr[-3000:]}")
    return json.loads(res.stdout.strip().splitlines()[-1])


def _summary(values):
    values = [v for v in values if v is not None]
    return {
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
        "n": len(values),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--worker", choices=sorted(WORKERS))
    ap.add_argument("--repeats", type=int, default=5, help="fresh processes per cold measurement")
    ap.add_argument("--seeds", type=int, default=3, help="NSGA-II seeds per case")
    ap.add_argument("--cases", default=DEFAULT_CASES)
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()

    if args.worker:
        sys.path.insert(0, str(ROOT))
        print(json.dumps(WORKERS[args.worker](args)))
        return

    env = dict(os.environ)
    env["AGROOPTIMIZE_RESULTS_DIR"] = tempfile.mkdtemp(prefix="agro-bench-results-")
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    _run_worker("startup", args, env)  # let the OS cache the libraries first
    startup = [_run_worker("startup", args, env) for _ in range(args.repeats)]
    build = [_run_worker("build", args, env) for _ in range(args.repeats)]
    load = [_run_worker("load", args, env) for _ in range(args.repeats)]
    preprocess = [_run_worker("preprocess", args, env) for _ in range(args.repeats)]
    api = _run_worker("api", args, env)
    optimize = _run_worker("optimize", args, env)

    cases = [f"{l}:{s}" for l, s in _cases(args.cases)]
    pre = {}
    for c in cases:
        if "error" in preprocess[0][c]:
            pre[c] = preprocess[0][c]
            continue
        pre[c] = {
            "first_s": _summary([p[c]["first_s"] for p in preprocess]),
            "warm_s": _summary([p[c]["warm_s"] for p in preprocess]),
            "candidates": preprocess[0][c]["candidates"],
            "year": preprocess[0][c]["year"],
        }
    opt = {}
    for c, runs in optimize["runs"].items():
        opt[c] = runs if isinstance(runs, dict) else {
            "runtime_s": _summary([r["runtime_s"] for r in runs]),
            "front_size": [r["front_size"] for r in runs],
        }
    all_opt = [r["runtime_s"] for runs in optimize["runs"].values() if isinstance(runs, list) for r in runs]

    report = {
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "git_commit": subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                         capture_output=True, text=True).stdout.strip(),
            "repeats": args.repeats,
            "seeds": args.seeds,
            "cases": cases,
        },
        "startup": {
            "import_s": _summary([s["import_s"] for s in startup]),
            "first_health_s": _summary([s["first_health_s"] for s in startup]),
            "rss_mb": _summary([s["rss_mb"] for s in startup]),
        },
        "build": {
            "build_s": _summary([b["build_s"] for b in build]),
            "datasets": build[0]["datasets"],
            "rows_clean": build[0]["rows_clean"],
        } if build[0]["available"] else None,
        "load": {
            "cold_s": _summary([x["cold_s"] for x in load]),
            "warm_s": _summary([x["warm_s"] for x in load]),
            "rows": load[0]["rows"],
            "rss_added_mb": _summary([x["rss_after_mb"] - x["rss_before_mb"] for x in load]),
        },
        "preprocess": pre,
        "api": api,
        "optimize": {
            "per_case": opt,
            "all_runs_s": _summary(all_opt) if all_opt else None,
            "tracemalloc_peak_mb": optimize["tracemalloc_peak_mb"],
            "rss_peak_mb": optimize["rss_peak_mb"],
        },
    }
    text = json.dumps(report, indent=2)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
