"""
Fuzzy-layer benchmark: time and memory of the Mamdani engine and of the
workflows that call it. Uses only the public engine API, so the same
script measures any version of app/fuzzy/engine.py.

    python3 scripts/benchmark_fuzzy.py [label] [--json out.json]
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
import tracemalloc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import config  # noqa: E402
from app.data import preprocessing as pp  # noqa: E402
from app.fuzzy import engine as fz  # noqa: E402


def dataset_inputs():
    """(rainfall deviation, storage, fertility) of every location/season/year profile."""
    years = sorted(pp.load_all()["crop"]["Year"].unique())
    out = []
    for loc in config.LOCATIONS:
        for season in config.AG_SEASONS:
            for year in years:
                try:
                    p = pp.get_region_season_profile(loc, season, int(year))
                except ValueError:
                    continue
                out.append((p.rainfall.avg_deviation_percent, p.water.avg_storage_percent, p.soil.fertility_index))
    return out


def timed(fn, repeat=5):
    runs = []
    for _ in range(repeat):
        t = time.perf_counter()
        fn()
        runs.append(time.perf_counter() - t)
    return statistics.median(runs)


def clear_caches():
    for name in ("_evaluate_cached", "_memberships_cached", "_fired_cached"):
        cached = getattr(fz, name, None)
        if cached is not None:
            cached.cache_clear()


def main():
    label = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "run"
    inputs = dataset_inputs()
    fz.evaluate_uncertainty(*inputs[0])   # build the rule base once

    def distinct():
        clear_caches()
        for x in inputs:
            fz.evaluate_uncertainty(*x)

    def repeated():
        for _ in range(10):
            for x in inputs:
                fz.evaluate_uncertainty(*x)

    def explain_calls():
        clear_caches()
        for x in inputs:
            fz.input_memberships(*x)
            fz.fired_rules(*x)

    from app.schemas import FarmPlanRequest
    from app.services import explanation_service as es
    from app.services import plan_service as ps
    from app.services import simulation_service as sim

    run = ps.run_pipeline(FarmPlanRequest(location="Salem", season="Kharif", total_land_ha=5, save_results=False),
                          track_history=True).response

    tracemalloc.start()
    distinct()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    result = {
        "label": label,
        "profiles": len(inputs),
        "evaluate_distinct_ms_per_call": round(timed(distinct) / len(inputs) * 1000, 3),
        "evaluate_repeated_ms_per_call": round(timed(repeated) / (10 * len(inputs)) * 1000, 4),
        "memberships_plus_fired_rules_ms_per_input": round(timed(explain_calls) / len(inputs) * 1000, 3),
        "explain_saved_run_ms": round(timed(lambda: es.explain(es.context_from_saved_run(run, 1))) * 1000, 1),
        "simulation_s": round(timed(lambda: sim.simulate({"base": {"location": "Salem", "season": "Kharif", "total_land_ha": 5},
                                                          "scenario": {"rainfall_change_pct": -20}}), repeat=3), 2),
        "peak_memory_kb_distinct": round(peak / 1024, 1),
    }
    print(json.dumps(result, indent=1))
    if "--json" in sys.argv:
        with open(sys.argv[sys.argv.index("--json") + 1], "w") as f:
            json.dump(result, f, indent=1)


if __name__ == "__main__":
    main()
