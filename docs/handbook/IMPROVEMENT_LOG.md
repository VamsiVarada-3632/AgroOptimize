# Improvement Log

Why each change was made, how it was verified, and what was deliberately **not** changed. Code-level detail: [CHANGELOG.md](CHANGELOG.md).

## Principles applied
1. Do not change core model behaviour without a clear defect → every backend change was verified to leave the numeric outputs of 48 pipeline/endpoint calls bit-identical to the original code (fingerprint comparison against a `git archive HEAD` copy).
2. Prefer additive API changes (new fields default safely; deprecated fields kept).
3. Remove anything that presents non-existent functionality or data as real.
4. Back up before deleting (the local `stitch_agrooptimize_app/` working copy has no git history of its own).

## Implemented

| # | Improvement | Category | Evidence / verification |
|---|---|---|---|
| I-1 | Lock around NSGA-II runs | Correctness | New concurrency test; 20/40 → 0/40 mismatches |
| I-2 | Exclusive run-id reservation | Data integrity | `test_same_second_saves_get_distinct_run_ids` |
| I-3 | Redact `client_id` from `/api/results` | Security | `test_results_listing_never_exposes_client_ids` |
| I-4 | `run_id` allow-list, corrupt-file tolerance, atomic writes | Security / robustness | 16 tests in `test_hardening.py` |
| I-5 | Query/body validation | Validation | 11 parametrised 422 tests |
| I-6 | Case-insensitive location/season | Usability | tests; previously `"coimbatore"` → 400 on POST |
| I-7 | Estimated-year provenance flag + UI banner/notes | Scientific honesty | tests + browser check |
| I-8 | History ordering by save time | Bug fix | test |
| I-9 | Memoised dashboard fronts; cached run summaries | Performance | `/api/comparison` 369 → 3 ms warm; suite 19 → 14 s |
| I-10 | Logging instead of print | Operability | – |
| I-11 | CI runs tests before deploying | DevOps | workflow review |
| I-12 | Real CSV exports and text report instead of alerts | UX honesty | browser: 101-line plans CSV, A/B/C CSV, 50-line report without NaN/undefined |
| I-13 | Correct impact column, removed fake plot labels / calendar / threshold | UX honesty | browser |
| I-14 | Structured API errors, environment-aware messages | UX | build + browser |
| I-15 | Hashed demo password | Security | code review (SubtleCrypto; fallback for insecure contexts) |
| I-16 | Dead code removal, lint clean | Maintainability | `npm run lint` 0 warnings |
| I-17 | Accurate wording (greeting, footer, profile, settings, KPI labels) | UX | browser |
| I-18 | Documentation set | Knowledge transfer | this folder |
| I-19 | NSGA-II speed-ups (vectorised tournament/crossover, cached constants, monitor instead of `save_history`) | Performance | Saved run 748 → 287 ms, 57.8 → 1.6 MB; bit-identical on 96 runs + 3 recorded digests |
| I-20 | NSGA-II diversity monitoring and runtime profile | Observability | saved as `meta.optimizer`; does not change results (test) |
| I-21 | Enhanced NSGA-II mode (smart initialisation, adaptive mutation) | Optimisation quality | HV better in 147/160, IGD+ in 154/160 paired runs (p < 1e-25); opt-in |

## Considered but deliberately not implemented (need a team decision or change results)

| Candidate | Reason not done | Where tracked |
|---|---|---|
| Default to 2023 instead of estimated 2024 | Changes every default result and a test; the team chose to add 2024 | T-1 |
| Totals-based rainfall deviation, Rabi across year boundary | Shifts fuzzy outputs by up to 0.21 → all results change | T-3 |
| Yield response to irrigation/fertiliser | Needs sourced agronomic parameters; core model change | T-4 |
| Profit objective | Needs verified prices (current MSP column questionable) | T-10 |
| Remove inert fuzzy rules | No numeric effect, but changes the documented rule count – team should decide wording. Six rules (13, 15, 19, 21, 25, 26) are inert; explanations now mark them as masked/tied with zero importance | T-5 |
| Replace global RNG with pymoo `random_state` | Removes the lock but changes every seeded result | T-19 |
| Make the enhanced NSGA-II engine the default | Changes every result and the recommended plan; needs a team decision and re-run paper tables | T-48 |
| Adaptive crossover, tolerance duplicate removal, early stopping in the enhanced engine | No measurable benefit, or lower quality (NSGAII_PROFILE.md §5) | NSGAII_IMPROVEMENT_SUMMARY.md |
| Weather TTL cache | Would make the existing weather-fallback test order-dependent; needs a small test refactor | T-20 |
| Delete `agrooptimize-backend/frontend/` and `datasets/` | Tracked in git / possibly referenced by the team; decision first | T-7, T-8 |
| Wire `WATER_COST_RS_PER_MM_PER_HA` | Deliberately left unwired by the team; changes f2 | TD-17 |
| Replace arbitrary constants with official values | No constant could be *verified* in this environment beyond what the code already cites; recommendations and candidate sources are listed instead | CONFIGURATION.md, DATASETS.md §8 |
