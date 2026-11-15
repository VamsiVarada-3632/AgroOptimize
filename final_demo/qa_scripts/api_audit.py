"""Backend QA: every endpoint for every district and season, edge cases and profiles (in-process TestClient).

    python final_demo/qa_scripts/api_audit.py api_audit.json      # from the repository root
"""
import json, math, os, sys, time, tempfile
sys.path.insert(0, os.getcwd())
os.environ.setdefault("AGROOPTIMIZE_RESULTS_DIR", tempfile.mkdtemp())
from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app, raise_server_exceptions=False)
R = {"rows": [], "fails": []}


def bad_numbers(obj, path=""):
    out = []
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        out.append(path)
    elif isinstance(obj, dict):
        for k, v in obj.items(): out += bad_numbers(v, f"{path}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:200]): out += bad_numbers(v, f"{path}[{i}]")
    return out


def call(name, method, path, expect, **kw):
    t = time.perf_counter()
    r = getattr(c, method)(path, **kw)
    ms = (time.perf_counter() - t) * 1000
    ok = r.status_code in (expect if isinstance(expect, tuple) else (expect,))
    body = None
    try:
        body = r.json()
    except Exception:
        body = r.text[:200]
    note = ""
    if ok and isinstance(body, (dict, list)):
        bn = bad_numbers(body)
        if bn: ok, note = False, f"NaN/Inf at {bn[:3]}"
    if not ok and not note:
        note = f"HTTP {r.status_code}: {str(body)[:200]}"
    R["rows"].append({"check": name, "status": r.status_code, "ok": ok, "ms": round(ms, 1), "note": note})
    if not ok: R["fails"].append(R["rows"][-1])
    return r.status_code, body


cat = call("catalog", "get", "/api/catalog", 200)[1]
districts, seasons = cat["locations"], cat["seasons"]
call("datasets", "get", "/api/datasets", 200)
call("health", "get", "/health", 200)
call("openapi", "get", "/openapi.json", 200)
call("fuzzy-models", "get", "/api/fuzzy/models", 200)
call("topsis-profiles", "get", "/api/topsis/profiles", 200)
call("soil-master-list", "get", "/api/soil-master", 200)
call("fuzzy-audit", "get", "/api/fuzzy/audit", 200)
call("fuzzy-explain", "get", "/api/fuzzy/explain", 200, params={"rainfall_dev": 10, "water_storage": 50, "soil_fert": 40})

matrix = []
for d in districts:
    for s in seasons:
        st, b = call(f"farm-plans {d} {s}", "post", "/api/farm-plans", (200, 400),
                     json={"location": d, "season": s, "total_land_ha": 5, "save_results": False})
        row = {"district": d, "season": s, "status": st}
        if st == 200:
            p = b["plans"][0]
            row.update(top=[(n, round(a, 1)) for n, a in zip(p["crop_names"], p["allocation_percent"]) if a > 1],
                       closeness=p["composite_score"], n_plans=len(b["plans"]), fuzzy=b["fuzzy_assessment"]["applied"],
                       cy=b["fuzzy_assessment"]["yield_confidence"], ri=b["fuzzy_assessment"]["irrigation_risk"],
                       rain_dev=b["region_profile"]["rainfall"]["avg_deviation_percent"],
                       storage=b["region_profile"]["water"]["avg_storage_percent"],
                       candidates=[x["name"] for x in b["region_profile"]["candidate_crops"]],
                       yield_t=p["yield_tonnes"], cost=p["cost_rs"], irr=p["irrigated_ha"], npk=p["env_impact_score"])
        else:
            row["detail"] = b.get("detail") if isinstance(b, dict) else b
        matrix.append(row)
        call(f"region-profile {d} {s}", "get", "/api/region-profile", (200, 400), params={"location": d, "season": s})
    lo = d.lower()
    call(f"dashboard {d}", "get", f"/api/dashboard/{lo}", 200)
    call(f"history {d}", "get", f"/api/history/{lo}", 200, params={"client_id": "qa"})
    call(f"soil-profile {d}", "get", f"/api/soil-profile/{lo}", 200)
    call(f"soil-master {d}", "get", f"/api/soil-master/{lo}", 200)
    call(f"district-intelligence {d}", "get", f"/api/district-intelligence/{lo}", 200)
    call(f"weather {d}", "get", f"/api/weather/{lo}", 501)
    call(f"plans {d}", "get", f"/api/plans/{lo}", (200, 404, 503), params={"total_land_ha": 5})
    call(f"comparison {d}", "get", f"/api/comparison/{lo}", (200, 404), params={"total_land_ha": 5})

# Edge cases on Salem Rabi
base = {"location": "Salem", "season": "Rabi", "total_land_ha": 5, "save_results": False}
E = [
    ("budget 0", {**base, "budget_rs": 0}, 422),
    ("budget negative", {**base, "budget_rs": -5}, 422),
    ("budget below cheapest plan", {**base, "budget_rs": 1000}, (200, 400, 422)),
    ("very high budget", {**base, "budget_rs": 1e12}, 200),
    ("land 0", {**base, "total_land_ha": 0}, 422),
    ("land 0.01 ha", {**base, "total_land_ha": 0.01}, 200),
    ("land 100000 ha", {**base, "total_land_ha": 100000}, 200),
    ("land 1e9 ha", {**base, "total_land_ha": 1e9}, (200, 422)),
    ("missing land", {k: v for k, v in base.items() if k != "total_land_ha"}, 422),
    ("missing location", {k: v for k, v in base.items() if k != "location"}, 422),
    ("empty location", {**base, "location": ""}, (400, 422)),
    ("invalid district", {**base, "location": "Atlantis"}, (400, 404)),
    ("taluk Pollachi", {**base, "location": "Pollachi"}, (400, 404)),
    ("invalid season", {**base, "season": "Summer"}, 400),
    ("lower-case inputs", {**base, "location": "salem", "season": "rabi"}, 200),
    ("year 2024", {**base, "year": 2024}, 200),
    ("invalid year 2019", {**base, "year": 2019}, (400, 422)),
    ("invalid year 3000", {**base, "year": 3000}, (400, 422)),
    ("string land", {**base, "total_land_ha": "abc"}, 422),
    ("unknown fuzzy model", {**base, "fuzzy_model": "nope"}, 422),
    ("Chennai (no data)", {**base, "location": "Chennai"}, 400),
    ("The Nilgiris (no data)", {**base, "location": "The Nilgiris"}, 400),
    ("Salem Kharif (fuzzy skipped)", {**base, "season": "Kharif"}, 200),
    ("custom weights not summing to 1", {**base, "profile": "custom", "custom_weights": {"yield": 0.5, "cost": 0.1}}, 422),
    ("custom weights valid", {**base, "profile": "custom", "custom_weights": {"yield": 0.4, "cost": 0.2, "water": 0.2, "env": 0.2}}, 200),
    ("custom_weights without custom profile", {**base, "custom_weights": {"yield": 1.0}}, 422),
    ("profile + non-balanced preference", {**base, "profile": "profit", "preference": "min_cost"}, 422),
    ("pop_size 7 (below min)", {**base, "pop_size": 7}, 422),
    ("n_gen 501 (above max)", {**base, "n_gen": 501}, 422),
    ("client_id 129 chars", {**base, "client_id": "x" * 129}, 422),
]
edge = []
for name, body, exp in E:
    st, b = call(f"edge: {name}", "post", "/api/farm-plans", exp, json=body)
    edge.append({"case": name, "status": st, "detail": (b.get("detail") if isinstance(b, dict) and "detail" in b else
                 (f"{len(b['plans'])} plans, top {b['plans'][0]['crop_names'][0] if b.get('plans') else '-'}" if isinstance(b, dict) and "plans" in b else ""))})

# Profiles
profiles = {}
for prof in ["balanced", "profit", "water", "sustainability", "low_cost"]:
    st, b = call(f"profile {prof}", "post", "/api/farm-plans", 200, json={**base, "profile": prof})
    p = b["plans"][0]
    profiles[prof] = {"top": [(n, round(a, 1)) for n, a in zip(p["crop_names"], p["allocation_percent"]) if a > 1], "closeness": p["composite_score"]}
for pref in ["max_yield", "min_cost", "min_water", "min_env_impact"]:
    call(f"preference {pref}", "post", "/api/farm-plans", 200, json={**base, "preference": pref})

# Saved run, explanation, topsis, simulation lifecycle, error paths
st, run = call("saved run", "post", "/api/farm-plans", 200, json={**base, "save_results": True, "client_id": "qa"})
rid = run["run_id"]
call("result", "get", f"/api/results/{rid}", 200)
call("results list", "get", "/api/results", 200)
st, ex = call("explanation rank1", "get", f"/api/results/{rid}/explanation", 200, params={"rank": 1})
call("explanation rank 9999", "get", f"/api/results/{rid}/explanation", (400, 422), params={"rank": 9999})
call("explanation rank 0", "get", f"/api/results/{rid}/explanation", 422, params={"rank": 0})
for prof in ["balanced", "profit", "water", "sustainability", "low_cost"]:
    call(f"rerank {prof}", "get", f"/api/results/{rid}/topsis", 200, params={"profile": prof})
call("rerank custom", "post", f"/api/results/{rid}/topsis", 200, json={"profile": "custom", "custom_weights": {"yield": 0.25, "cost": 0.25, "water": 0.25, "env": 0.25}})
call("rerank custom bad", "post", f"/api/results/{rid}/topsis", 422, json={"profile": "custom", "custom_weights": {"yield": 0.9}})
call("rerank unknown profile", "get", f"/api/results/{rid}/topsis", 422, params={"profile": "nope"})
call("result bad id", "get", "/api/results/../../etc", (404, 422))
call("result unknown id", "get", "/api/results/does_not_exist", 404)
call("history no client", "get", "/api/history/salem", 200)
call("dashboard unknown", "get", "/api/dashboard/atlantis", 404)
call("soil-master unknown", "get", "/api/soil-master/atlantis", 404)
call("soil-master chennai", "get", "/api/soil-master/chennai", 200)
call("district-intel unknown", "get", "/api/district-intelligence/atlantis", 404)
call("comparison explanation C", "get", "/api/comparison/salem/explanation", 200, params={"plan": "C"})
call("comparison explanation bad plan", "get", "/api/comparison/salem/explanation", 422, params={"plan": "Z"})
call("plans land 0", "get", "/api/plans/salem", 422, params={"total_land_ha": 0})
call("compare-fuzzy salem rabi", "get", "/api/compare-fuzzy/salem", 200, params={"season": "Rabi"})
call("compare-fuzzy salem kharif", "get", "/api/compare-fuzzy/salem", 200, params={"season": "Kharif"})
call("fuzzy explain non-finite", "get", "/api/fuzzy/explain", 422, params={"rainfall_dev": "nan", "water_storage": 50, "soil_fert": 40})
call("fuzzy explain unknown model", "get", "/api/fuzzy/explain", 400, params={"rainfall_dev": 1, "water_storage": 50, "soil_fert": 40, "model": "x"})
simb = {"base": {"location": "Salem", "season": "Rabi", "total_land_ha": 5}, "scenario": {"rainfall_change_pct": -20}, "client_id": "qa"}
st, sim = call("simulation run", "post", "/api/simulations/run", 200, json=simb)
call("simulation bad rainfall", "post", "/api/simulations/run", 422, json={**simb, "scenario": {"rainfall_change_pct": -45}})
call("simulation unknown district", "post", "/api/simulations/run", 422, json={**simb, "base": {**simb["base"], "location": "Atlantis"}})
call("simulation fertiliser lever", "post", "/api/simulations/run", (200, 422), json={**simb, "scenario": {"fertilizer_cost_change_pct": 10}})
call("simulation infeasible budget", "post", "/api/simulations/run", (200, 422), json={**simb, "base": {**simb["base"], "budget_rs": 1000}})
st, saved = call("simulation save", "post", "/api/simulations", 201, json={"token": sim["token"], "name": "qa", "client_id": "qa"})
call("simulation save other browser", "post", "/api/simulations", 404, json={"token": sim["token"], "client_id": "other"})
call("simulation list", "get", "/api/simulations", 200, params={"client_id": "qa"})
call("simulation get", "get", f"/api/simulations/{saved['simulation_id']}", 200, params={"client_id": "qa"})
call("simulation get other browser", "get", f"/api/simulations/{saved['simulation_id']}", 404, params={"client_id": "other"})
call("simulation delete", "delete", f"/api/simulations/{saved['simulation_id']}", 200, params={"client_id": "qa"})
call("simulation delete again", "delete", f"/api/simulations/{saved['simulation_id']}", 404, params={"client_id": "qa"})
call("unknown api path", "get", "/api/nope", 404)

R["matrix"], R["edge"], R["profiles"] = matrix, edge, profiles
R["explanation_keys"] = sorted(ex.keys())
R["crop_evidence_criteria"] = [[x["id"] for x in ce["criteria"]] for ce in ex["crop_evidence"]]
json.dump(R, open(sys.argv[1], "w"), indent=1, default=str)
print(len(R["rows"]), "checks;", len(R["fails"]), "failed")
for f in R["fails"]: print("FAIL", f)
