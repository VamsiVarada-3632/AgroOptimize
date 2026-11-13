"""Run ONE complete AgroOptimize optimisation on the official data and record every stage.

Everything goes through the real code: the FastAPI app (TestClient), app.data.preprocessing,
app.fuzzy.engine, app.optimization and app.decision. Stage timings are measured here with
time.perf_counter. Output: final_ppt/assets/data/pipeline_run.json (used by the pipeline
snapshot, the markdown log and the result graphs).

Usage (from the repository root):  python final_ppt/assets/scripts/run_pipeline_snapshot.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("AGROOPTIMIZE_RESULTS_DIR", tempfile.mkdtemp(prefix="agro-ppt-"))
OUT = ROOT / "final_ppt" / "assets" / "data" / "pipeline_run.json"

REQUEST = {"location": "Salem", "season": "Rabi", "year": 2024, "total_land_ha": 5.0,
           "preference": "balanced", "save_results": True, "client_id": "ppt-snapshot"}


def ms(t0):
    return round((time.perf_counter() - t0) * 1000, 2)


def main():
    rec = {"request": REQUEST, "stages": []}

    t = time.perf_counter()
    from fastapi.testclient import TestClient
    import app.main as main_mod
    from app import config
    from app.data import loader
    from app.data import preprocessing as pp
    from app.fuzzy import engine as fz
    from app.schemas import FarmPlanRequest
    from app.services import plan_service
    client = TestClient(main_mod.app)
    rec["stages"].append({"stage": "Start-up", "ms": ms(t), "detail": "import app.main (FastAPI app)"})

    # 1. Input validation (pydantic FarmPlanRequest + location/season checks)
    t = time.perf_counter()
    req = FarmPlanRequest(**REQUEST)
    rejected = []
    for bad in ({**REQUEST, "total_land_ha": -1}, {**REQUEST, "season": "Summer"}, {**REQUEST, "location": "Pollachi"}):
        r = client.post("/api/farm-plans", json={**bad, "save_results": False})
        rejected.append({"input": {k: bad[k] for k in ("location", "season", "total_land_ha")},
                         "status": r.status_code, "detail": str(r.json().get("detail"))[:160]})
    rec["stages"].append({"stage": "Input validation", "ms": ms(t), "accepted": req.model_dump(include=set(REQUEST)),
                          "rejected_examples": rejected})

    # 2. Official dataset loading (database -> four frames) + registry
    t = time.perf_counter()
    loader.clear_cache()
    frames = loader.load_all()
    load_ms = ms(t)
    reg = client.get("/api/datasets").json()
    rec["stages"].append({"stage": "Official dataset loading", "ms": load_ms,
                          "frames_rows": {k: int(len(v)) for k, v in frames.items()},
                          "registry": [{k: d[k] for k in ("name", "filename", "report_year", "rows_clean", "sha256")} for d in reg["datasets"]],
                          "disabled_features": reg["disabled_features"]})

    # 3. Preprocessing: district resolution, season months, crop filtering
    t = time.perf_counter()
    profile = pp.get_region_season_profile(REQUEST["location"], REQUEST["season"], REQUEST["year"])
    rec["stages"].append({"stage": "Preprocessing and crop filtering", "ms": ms(t),
                          "district": profile.location, "season": profile.season, "year": profile.year,
                          "rainfall": {"months": profile.rainfall.months_used,
                                       "season_actual_mm": getattr(profile.rainfall, "season_actual_mm", None),
                                       "season_normal_mm": getattr(profile.rainfall, "season_normal_mm", None),
                                       "deviation_pct": profile.rainfall.avg_deviation_percent},
                          "water": {"storage_pct": profile.water.avg_storage_percent,
                                    "reservoirs": getattr(profile.water, "reservoirs", None)},
                          "soil": {"fertility_index": profile.soil.fertility_index, "N": profile.soil.n_status,
                                   "P": profile.soil.p_status, "K": profile.soil.k_status},
                          "candidate_crops": [c.name for c in profile.candidate_crops],
                          "excluded_crops": profile.excluded_crops,
                          "notes": profile.notes})

    # 4. Fuzzy inference
    t = time.perf_counter()
    model = fz.resolve_model(None)
    assessment = fz.assess_profile(profile, model=model)
    rec["stages"].append({"stage": "Fuzzy inference", "ms": ms(t), "model": model.name,
                          "assessment": fz.assessment_payload(assessment, profile)})

    # 5-7. NSGA-II + TOPSIS + recommendation through the real API (saved run)
    t = time.perf_counter()
    r = client.post("/api/farm-plans", json=REQUEST)
    api_ms = ms(t)
    resp = r.json()
    meta = resp["meta"]
    rec["stages"].append({"stage": "NSGA-II optimisation", "ms": round(meta["optimize_seconds"] * 1000, 1),
                          "pop_size": meta["pop_size"], "n_gen": meta["n_gen"],
                          "crossover_prob": meta["crossover_prob"], "mutation_prob": meta["mutation_prob"],
                          "pareto_solutions": meta["n_pareto_solutions_found"],
                          "quality_metrics": meta.get("quality_metrics")})
    rec["stages"].append({"stage": "TOPSIS ranking", "plans_ranked": meta["n_plans_returned"],
                          "topsis": meta.get("topsis"),
                          "top5": [{k: p[k] for k in ("rank", "composite_score", "yield_tonnes", "cost_rs", "irrigated_ha", "env_impact_score")}
                                   for p in resp["plans"][:5]]})
    top = resp["plans"][0]
    rec["stages"].append({"stage": "Recommendation", "api_status": r.status_code, "api_ms": api_ms, "run_id": resp["run_id"],
                          "plan": {"crops": [(c, a) for c, a in zip(top["crop_names"], top["allocation_percent"]) if a >= 1],
                                   **{k: top[k] for k in ("yield_tonnes", "cost_rs", "irrigated_ha", "env_impact_score",
                                                          "composite_score", "confidence_label", "trade_off_summary")}}})

    # 8. Explanation of the recommended plan
    t = time.perf_counter()
    e = client.get(f"/api/results/{resp['run_id']}/explanation", params={"rank": 1})
    ex = e.json()
    rec["stages"].append({"stage": "Explanation", "ms": ms(t), "api_status": e.status_code,
                          "summary": {k: ex["summary"].get(k) for k in ("recommendation", "confidence_pct", "closeness", "crop_mix")},
                          "sections": list(ex.keys()),
                          "n_reasons": len(ex["reasons"]), "n_risks": len(ex["risks"]),
                          "reasons": [x["title"] for x in ex["reasons"]],
                          "confidence_components": [{"id": c["id"], "score": c["score"]} for c in ex["confidence"]["components"]],
                          "crop_evidence": [{"crop": c["crop"], "criteria": [{"id": k["id"], "status": k["status"]} for k in c["criteria"]]}
                                            for c in ex.get("crop_evidence", [])]})

    # Data for the graphs: convergence (saved run) and the full feasible front (same request, same seed)
    run = plan_service.run_pipeline(FarmPlanRequest(**{**REQUEST, "save_results": False}))
    rec["convergence_history"] = resp["convergence_history"]
    rec["front"] = [{"yield_tonnes": p.yield_tonnes, "cost_rs": p.cost_rs, "irrigated_ha": p.irrigated_ha,
                     "env_impact_score": p.env_impact_score} for p in run.feasible_plans]
    rec["ranked_plans"] = [{k: p[k] for k in ("rank", "composite_score", "yield_tonnes", "cost_rs", "irrigated_ha", "env_impact_score", "crop_names", "allocation_percent")}
                           for p in resp["plans"]]
    rec["same_top_plan_as_rerun"] = abs(run.response["plans"][0]["composite_score"] - top["composite_score"]) < 1e-9
    rec["environment"] = {"nsga2_mode": config.NSGA2_ENGINE_MODE, "seed": config.NSGA2_SEED, "fuzzy_model": model.name}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rec, indent=2, default=str))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
