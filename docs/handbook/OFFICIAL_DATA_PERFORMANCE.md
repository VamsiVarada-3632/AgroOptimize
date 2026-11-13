# Runtime performance after the official-data migration

Measured cost of moving the runtime from the synthetic v1 CSVs to the official database: startup, dataset loading, preprocessing, API latency, optimisation runtime and memory. Every number below is a measurement; the raw output is in [`benchmarks/runtime/`](benchmarks/runtime/).

## 1. Method

| | |
|---|---|
| Script | `scripts/benchmark_runtime.py` (same file run on both versions) |
| Before | tag `published-v1` (commit 91f0607): synthetic CSVs in `data/raw/`, 4 locations, 3 seasons |
| After | commit 3752053: official database `data/official/official_v1.db`, 38 districts, 2 seasons |
| Machine | Apple Silicon (arm64), macOS 27.0, Python 3.13.9, nothing else running |
| Cold measurements | 5 fresh Python processes each (startup, build, load, preprocessing); one warm-up process first so both versions read the libraries from the OS cache |
| API | in-process `TestClient`, one warm-up call, then 20 calls per GET endpoint; `POST /api/farm-plans` 3 calls with no warm-up |
| Optimisation | `run_pipeline()` (preprocessing, fuzzy, NSGA-II 80 x 200, TOPSIS), seeds 0-2, `save_results=False`, no convergence tracking |
| Cases | the six district/season pairs both versions support: Coimbatore, Erode, Salem x Kharif, Rabi (5 ha, no budget) |
| Saved runs | a temporary empty results folder, so dashboard/history see the same history in both versions |

Values are the median, with the minimum and maximum over the repeats in brackets. Re-run with:

```bash
python scripts/benchmark_runtime.py --json docs/handbook/benchmarks/runtime/official.json
git worktree add /tmp/agro-v1 published-v1 && cp scripts/benchmark_runtime.py /tmp/agro-v1/scripts/
(cd /tmp/agro-v1 && python scripts/benchmark_runtime.py --json v1.json)
```

## 2. Results

### Startup

| | published-v1 | official |
|---|---|---|
| `import app.main` | 471 ms (446–504) | 533 ms (518–593) |
| first `GET /health` | 8.9 ms (8.6–9.8) | 2.7 ms (2.6–2.8) |
| process RSS after startup | 130 MB | 141 MB (140–141) |

Importing the app does not touch the data in either version (`config.LOCATIONS` is resolved lazily from the database), so the data cost appears on the first data request instead (next table).

### Database build and dataset loading

| | published-v1 | official |
|---|---|---|
| Database build from `data/official/raw` (10 datasets, 39,065 clean rows; temporary SQLite file) | – | 331 ms (317–342) |
| `loader.load_all()` cold | 11.9 ms (11.6–15.8) | 744 ms (710–788) |
| `loader.load_all()` warm (cached) | 0.1 µs | 0.1 µs |
| RSS added by loading | 0.4 MB (0–0.8) | 4.7 MB (3.1–7.6) |
| Rows served (crop / land / rainfall / water) | 205 / 60 / 240 / 240 | 985 / 76 / 456 / 456 |

The database build runs once, when the Docker image is built or with `scripts/preprocess_all.py`. Cold loading is 62x slower than reading the four small CSVs: it queries the database and assembles the four frames (`app/data/official_view.py`) from 4.8x more crop rows. It is paid once per process and then cached.

### Preprocessing (`get_region_season_profile`, data already loaded)

| Case | published-v1 first / warm | candidates | official first / warm | candidates |
|---|---|---|---|---|
| Coimbatore Kharif | 2.49 / 1.18 ms | 5 | 3.35 / 1.50 ms | 6 |
| Coimbatore Rabi | 1.15 / 1.13 ms | 4 | 1.48 / 1.47 ms | 6 |
| Erode Kharif | 1.28 / 1.14 ms | 5 | 2.30 / 1.50 ms | 6 |
| Erode Rabi | 1.11 / 1.17 ms | 3 | 1.48 / 1.47 ms | 6 |
| Salem Kharif | 1.16 / 1.10 ms | 5 | 2.26 / 1.48 ms | 6 |
| Salem Rabi | 1.17 / 1.13 ms | 3 | 1.48 / 1.48 ms | 6 |

Warm preprocessing is about 0.3 ms slower per profile (it builds provenance and exclusion reasons for every crop). Every case now has 6 candidates, the default cap, against 3–5 before.

### API latency (Coimbatore Kharif)

| Endpoint | published-v1 median / p95 | official median / p95 |
|---|---|---|
| `GET /health` | 0.66 / 1.39 ms | 0.60 / 0.76 ms |
| `GET /api/catalog` | 0.94 / 1.24 ms | 1.31 / 1.78 ms |
| `GET /api/region-profile` | 1.97 / 2.52 ms | 2.35 / 2.72 ms |
| `GET /api/soil-profile/{location}` | 0.98 / 1.17 ms | 0.91 / 1.27 ms |
| `GET /api/dashboard/{location}` | 2.82 / 3.42 ms | 2.68 / 3.22 ms |
| `GET /api/district-intelligence/{location}` | 1.77 / 2.08 ms | 1.41 / 1.90 ms |
| `POST /api/farm-plans` (3 calls, first included; "p95" = slowest) | 606 / 950 ms | 280 / 658 ms |

All responses were 200. Warm read latencies stay within about ±0.4 ms. The `POST /api/farm-plans` slowest call is the first one in the process, which builds the fuzzy system; the median was 326 ms lower after the migration, but with three calls per version this is a single observation, not an established difference.

### Optimisation runtime (`run_pipeline`, 3 seeds per case)

| Case | published-v1 | official | Pareto front size |
|---|---|---|---|
| Coimbatore Kharif | 291 ms (289–333) | 287 ms (279–297) | 80 / 80 |
| Coimbatore Rabi | 298 ms (288–312) | 278 ms (275–409) | 80 / 80 |
| Erode Kharif | 284 ms (283–287) | 274 ms (274–277) | 80 / 80 |
| Erode Rabi | 310 ms (306–313) | 296 ms (278–300) | 80 / 80 |
| Salem Kharif | 283 ms (282–285) | 277 ms (276–289) | 80 / 80 |
| Salem Rabi | 305 ms (302–312) | 280 ms (275–282) | 80 / 80 |
| All 18 runs | 295 ms (282–333) | 278 ms (274–409) | |

The optimiser does the same work (80 x 200 = 16,000 evaluations) in both versions, so the runtime is essentially unchanged (−6 % median) even though every official case optimises 6 crops instead of 3–5.

### Memory

| | published-v1 | official |
|---|---|---|
| Python allocations, peak during one pipeline run (tracemalloc) | 1.40 MB | 1.36 MB |
| Process peak RSS after 18 pipeline runs | 199 MB | 233 MB |

The extra 34 MB of RSS is the SQLAlchemy engine, the official frames and the per-dataset caches. Peak RSS stays below half of a 512 MB instance.

## 3. Summary

| Stage | Change | Matters for |
|---|---|---|
| Startup | +62 ms import, +11 MB RSS | cold start of a sleeping free-tier instance |
| First data request | +732 ms (one-off dataset load) | first request after a cold start |
| Database build | 331 ms, at image build time | build only |
| Preprocessing | +0.3 ms per profile (warm) | negligible |
| Read endpoints | within ±0.4 ms | negligible |
| Optimisation | 278 ms vs 295 ms median | unchanged |
| Memory | +34 MB peak RSS (233 MB) | fits a 512 MB instance |

The migration's runtime cost is concentrated in one place: the first data request in a new process pays about 0.75 s to load the official frames. Everything after that runs at the v1 speed. Loading the frames at startup (e.g. in the FastAPI lifespan) would move that cost out of the first user request; it has not been done here.

## 4. Limitations

- One machine, in-process `TestClient`; network, TLS and the hosting platform add to the API numbers.
- Only the six cases both versions support are compared. The official data serves 36 working districts (Chennai and The Nilgiris return 400: fewer than 2 crops with complete official data), and the fuzzy stage runs only where an official reservoir reading exists (e.g. Salem Rabi, not Salem Kharif).
- `POST /api/farm-plans` has 3 samples per version; read its numbers as indicative.
- The two versions solve different problems (different crops, prices and objectives), so runtime is compared, not plan quality.
