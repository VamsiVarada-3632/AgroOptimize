# Performance Review

Measured 2026-09-29 on an Apple-Silicon laptop, Python 3.13, in-process (`TestClient`) unless stated. Production runs on 1 shared vCPU / 512 MB (Fly.io), so expect roughly 2–4× slower CPU-bound numbers there.

## 1. Baseline measurements

| Operation | Time | Notes |
|---|---|---|
| Load 16 CSVs | part of first request | cached for process life |
| First fuzzy call (build 26-rule system) | 66 ms (≈600 ms incl. first imports on `/api/region-profile`) | `lru_cache` afterwards |
| Warm fuzzy call | 3.7 ms | new `ControlSystemSimulation` each call |
| Build region profile | 22 ms | pandas boolean filtering on small frames |
| NSGA-II pop 80 × 200 gen, no history | ≈0.29 s | the `/api/farm-plans` default |
| NSGA-II pop 100 × 200 gen, with history | ≈0.8 s | `/api/plans`; retained **≈71 MB** until the request ended – **fixed**: pop 80 saved run 748 → 287 ms, 57.8 → 1.6 MB ([NSGAII_PROFILE.md](NSGAII_PROFILE.md)) |
| `/api/comparison` cold / warm | 369 ms / 3 ms | warm = new memoisation |
| `/api/plans` cold / warm | 966 ms / 3 ms | |
| `/api/compare-fuzzy` | 746 ms | two runs, not memoised |
| Full test suite | 19 s → 14 s | after memoisation |

Responses: `/api/farm-plans` ≈33 KB (50 plans + 200-point history when saved), `/api/plans` ≈24 KB. Frontend bundle: 361 KB JS (94 KB gzip), 74 KB CSS (12 KB gzip).

**Verdict:** computation is not a bottleneck at the current scale. The real performance risks are the global run lock under concurrency, uncached third-party weather calls, unbounded result files, and simulated UI delays.

## 2. Findings

| ID | Finding | Impact | Status |
|---|---|---|---|
| P-1 | Every dashboard/comparison/plans page visit re-ran NSGA-II with identical inputs (deterministic seed) | 0.4–1 s per visit, CPU on a shared VM | **Fixed**: `lru_cache(32)` over plain-data results (warm 3 ms) |
| P-2 | Global-RNG operators forced serialisation (now an explicit lock) – requests queue behind each other; a `pop_size=300, n_gen=500` request (allowed by the schema) blocks everyone | Head-of-line blocking; DoS lever | Open – pass pymoo's `random_state` into operators (removes the lock), and cap pop×gen or rate-limit |
| P-3 | `list_saved_runs` parsed every run JSON (each embeds a 200-generation history) on every dashboard/history request | O(#runs × file size) per request | **Fixed**: mtime/size-keyed summary cache |
| P-4 | `get_history` re-parses each matching run in full to read plan #1 | O(#matching runs) | Open – store plan #1 metrics in the summary |
| P-5 | Weather: every dashboard load triggers 5 Open-Meteo requests (own district + 4 districts), no caching; each up to a 5 s timeout | Slow dashboard when Open-Meteo is slow; third-party load | Open – 10–15 min TTL cache per district |
| P-6 | `/api/compare-fuzzy` performs two fresh runs every time | 0.75 s per Analytics visit | Open – route both through the memoised front helper |
| P-7 | `track_history=True` deep-copies the population every generation (≈71 MB retained per run) | Memory spikes on 512 MB VM | Mitigated (cache keeps only derived data); consider recording only F per generation via a callback |
| P-8 | Analytics fires `/api/plans` and `/api/compare-fuzzy` simultaneously; with the lock they serialise (≈1.7 s cold) | Perceived latency | Improves with P-6 |
| P-9 | `evaluate_uncertainty` allocates a new `ControlSystemSimulation` per call | 3.7 ms – negligible | Accept |
| P-10 | Run Optimization shows a fixed ≈5.7 s animation although the run takes ≈0.3 s | UX latency ×19 | Open (UI) – drive progress from the real promise, keep a short minimum |
| P-11 | `results/` grows forever (4 files per run: JSON ≈130 KB, PNG ≈75–81 KB, two CSVs – ≈250 KB per saved run) | Disk exhaustion on a fixed volume | Open – retention policy / max runs per client |
| P-12 | Large avatar data-URLs stored in `localStorage` | 5 MB quota per origin; JSON.stringify on every user change | Open – downscale images before storing |
| P-13 | Frontend has no request de-duplication or caching; every navigation refetches | Extra calls (cheap now thanks to P-1) | Accept or add a small SWR-style cache |
| P-14 | Radar/scatter SVGs render ≤100 points | fine | – |

## 3. Scalability outlook

* **Vertical:** CPU-bound work is < 1 s per request; one machine comfortably serves a class-demo load.
* **Horizontal:** each Fly machine has its own lock and caches (fine) but a Fly volume attaches to one machine, so saved runs are not shared – moving results to object storage or a small database is the prerequisite for >1 machine.
* **Algorithmic:** chromosome length ≤ 15 (5 crops). Scaling to many crops or plots would benefit from the LP formulation noted in ALGORITHMS §4.5 rather than a bigger GA.

## 4. Parallelisation opportunities
* `get_fuzzy_comparison`'s two runs are independent (blocked today only by the global RNG).
* Weather for 4 districts could be fetched concurrently server-side in one endpoint instead of 4 browser round trips.
* Batch evaluation is already vectorised over the population; no Python per-individual loops except in crossover (`for k in range(n_matings)`, 40–50 iterations – negligible).
