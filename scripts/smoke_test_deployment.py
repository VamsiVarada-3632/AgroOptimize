"""
End-to-end smoke test for a running AgroOptimize deployment.

Calls every API endpoint the frontend uses (plus the docs and the served
frontend), checks status codes and response shapes, and fingerprints the
deterministic outputs (optimisation, fuzzy, ranking, district and
simulation results) so two deployments can be compared exactly:

    # record a reference on the local server
    python scripts/smoke_test_deployment.py --base-url http://localhost:8000 --record ref.json
    # check the deployed server gives the same results
    python scripts/smoke_test_deployment.py --base-url https://<service>.onrender.com --compare ref.json

Standard library only, so it runs anywhere Python 3.9+ is available.
Saved runs and simulations it creates are tagged with a throw-away client
id; the simulation is deleted again at the end.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

# Keys whose values legitimately differ between two identical runs
# (wall-clock timings, timestamps, generated identifiers).
VOLATILE_KEYS = {
    "optimize_seconds", "total_seconds", "avg_generation_ms", "saved_at", "run_id",
    "token", "simulation_id", "client_id", "seconds", "elapsed_seconds", "generated_at",
    "saved_files",  # absolute paths on the server
    "last_dataset_update",  # modification date of the CSV files on the server (checkout time)
}

TIMEOUT = 300


def _strip(obj):
    if isinstance(obj, dict):
        return {k: _strip(v) for k, v in obj.items() if k not in VOLATILE_KEYS}
    if isinstance(obj, list):
        return [_strip(v) for v in obj]
    if isinstance(obj, float) and obj == 0.0:
        return 0.0  # -0.0 and 0.0 are equal; linear-algebra libraries differ in the sign
    return obj


def fingerprint(obj) -> str:
    text = json.dumps(_strip(obj), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class Client:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")

    def request(self, method: str, path: str, params=None, body=None):
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                raw, status, ctype = resp.read(), resp.status, resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            raw, status, ctype = exc.read(), exc.code, exc.headers.get("Content-Type", "")
        elapsed = time.perf_counter() - start
        payload = json.loads(raw) if "json" in ctype and raw else raw.decode(errors="replace")
        return status, payload, ctype, elapsed


def run(base_url: str) -> tuple[list, dict]:
    c = Client(base_url)
    client_id = f"smoke-{uuid.uuid4().hex[:12]}"
    checks, prints = [], {}

    def check(name, method, path, expect=200, params=None, body=None, record=False, test=None):
        status, payload, ctype, elapsed = c.request(method, path, params, body)
        ok = status == expect
        note = ""
        if ok and test is not None:
            try:
                ok = bool(test(payload, ctype))
                note = "" if ok else "unexpected content"
            except Exception as exc:  # noqa: BLE001 - report any shape problem as a failed check
                ok, note = False, f"{type(exc).__name__}: {exc}"
        if not ok and not note:
            note = f"HTTP {status}: {str(payload)[:160]}"
        checks.append({"check": name, "ok": ok, "status": status, "seconds": round(elapsed, 2), "note": note})
        if ok and record:
            prints[name] = fingerprint(payload)
        return payload if ok else None

    farm = {"location": "Salem", "season": "Kharif", "year": 2023, "total_land_ha": 5.0, "preference": "balanced"}
    is_html = lambda p, t: "text/html" in t and "<div id=\"root\">" in p  # noqa: E731

    # Platform and frontend
    check("health", "GET", "/health", test=lambda p, t: p.get("status") == "ok")
    check("openapi", "GET", "/openapi.json", test=lambda p, t: "/api/farm-plans" in p["paths"])
    check("swagger-ui", "GET", "/docs", test=lambda p, t: "swagger" in p.lower())
    index = check("frontend-index", "GET", "/", test=is_html)
    check("frontend-spa-fallback", "GET", "/history", test=is_html)
    if index:
        asset = next((part.split('"')[0] for part in index.split('src="/assets/')[1:]), None)
        if asset:
            check("frontend-asset", "GET", f"/assets/{asset}", test=lambda p, t: "javascript" in t)
    check("api-unknown-404", "GET", "/api/does-not-exist", expect=404, test=lambda p, t: "json" in t)

    # Data and optimisation
    check("catalog", "GET", "/api/catalog", record=True, test=lambda p, t: len(p["locations"]) == 4)
    check("region-profile", "GET", "/api/region-profile", params={"location": "Salem", "season": "Kharif", "year": 2023},
          record=True)
    check("farm-plans", "POST", "/api/farm-plans", body={**farm, "save_results": False}, record=True,
          test=lambda p, t: len(p["plans"]) > 0)
    check("farm-plans-budget", "POST", "/api/farm-plans",
          body={**farm, "location": "Erode", "season": "Rabi", "budget_rs": 120000, "preference": "min_water",
                "save_results": False}, record=True)
    saved = check("farm-plans-saved", "POST", "/api/farm-plans", body={**farm, "client_id": client_id}, record=True,
                  test=lambda p, t: bool(p.get("run_id")))
    run_id = saved["run_id"] if saved else None
    if run_id:
        check("result", "GET", f"/api/results/{run_id}", record=True)
        check("result-explanation", "GET", f"/api/results/{run_id}/explanation", params={"rank": 1}, record=True)
        check("history", "GET", "/api/history/salem", params={"client_id": client_id},
              test=lambda p, t: any(h["id"] == run_id for h in p["history"]))
    check("results-list", "GET", "/api/results", test=lambda p, t: isinstance(p, list))

    # Dashboard pages
    check("dashboard", "GET", "/api/dashboard/coimbatore", params={"client_id": f"{client_id}-dash"}, record=True)
    check("weather", "GET", "/api/weather/erode", test=lambda p, t: "temp" in p and "forecast" in p)
    check("soil-profile", "GET", "/api/soil-profile/pollachi", record=True)
    check("plans", "GET", "/api/plans/salem", params={"total_land_ha": 5}, record=True)
    check("comparison", "GET", "/api/comparison/erode", params={"total_land_ha": 5}, record=True)
    check("comparison-explanation", "GET", "/api/comparison/erode/explanation", params={"plan": "A", "total_land_ha": 5},
          record=True)
    check("compare-fuzzy", "GET", "/api/compare-fuzzy/coimbatore", params={"total_land_ha": 5}, record=True)
    check("district-intelligence", "GET", "/api/district-intelligence/salem", record=True)
    check("fuzzy-explain", "GET", "/api/fuzzy/explain",
          params={"rainfall_dev": -20, "water_storage": 60, "soil_fert": 65}, record=True)
    check("fuzzy-audit", "GET", "/api/fuzzy/audit", record=True)

    # Scenario simulation: run, save, list, load, delete
    sim = check("simulation-run", "POST", "/api/simulations/run",
                body={"base": {"location": "Salem", "season": "Kharif", "year": 2023, "total_land_ha": 5},
                      "scenario": {"rainfall_change_pct": -20, "water_availability": "low"}, "client_id": client_id},
                record=True, test=lambda p, t: bool(p.get("token")))
    if sim:
        stored = check("simulation-save", "POST", "/api/simulations", expect=201,
                       body={"token": sim["token"], "name": "smoke test", "client_id": client_id})
        if stored:
            sid = stored["simulation_id"]
            check("simulation-list", "GET", "/api/simulations", params={"client_id": client_id},
                  test=lambda p, t: any(s["simulation_id"] == sid for s in p))
            check("simulation-get", "GET", f"/api/simulations/{sid}", params={"client_id": client_id})
            check("simulation-delete", "DELETE", f"/api/simulations/{sid}", params={"client_id": client_id})

    # Input validation and safe errors
    check("validation-422", "POST", "/api/farm-plans", expect=422, body={**farm, "total_land_ha": -1})
    check("unknown-district-404", "GET", "/api/district-intelligence/atlantis", expect=404)
    check("bad-run-id-404", "GET", "/api/results/..%2F..%2Fetc", expect=404)
    return checks, prints


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--record", help="write the result fingerprints to this JSON file")
    ap.add_argument("--compare", help="compare the result fingerprints with this JSON file")
    args = ap.parse_args()

    checks, prints = run(args.base_url)
    width = max(len(c["check"]) for c in checks)
    for c in checks:
        print(f"{'PASS' if c['ok'] else 'FAIL'}  {c['check']:<{width}}  {c['status']:>3}  {c['seconds']:>6.2f}s  {c['note']}")
    failed = [c for c in checks if not c["ok"]]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed against {args.base_url}")

    mismatched = []
    if args.compare:
        with open(args.compare) as fh:
            reference = json.load(fh)["fingerprints"]
        for name, digest in reference.items():
            if prints.get(name) != digest:
                mismatched.append(name)
                print(f"DIFF  {name}: expected {digest}, got {prints.get(name)}")
        print(f"{len(reference) - len(mismatched)}/{len(reference)} result fingerprints identical to {args.compare}")
    if args.record:
        with open(args.record, "w") as fh:
            json.dump({"base_url": args.base_url, "fingerprints": prints}, fh, indent=2)
        print(f"Recorded {len(prints)} fingerprints to {args.record}")
    return 1 if failed or mismatched else 0


if __name__ == "__main__":
    sys.exit(main())
