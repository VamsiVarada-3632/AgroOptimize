# legacy/ - archived synthetic data (published paper)

| What | Where |
|---|---|
| Original synthetic CSVs (4 locations x crop/land/rainfall/water, 2020-2024, partly "Estimated") | `legacy/data/raw/` |
| Saved optimisation runs produced from them | `legacy/results/` |
| Original data layer, verbatim (`loader_v1.py`, `preprocessing_v1.py`, `config_v1.py`) | `legacy/` |
| Read-only loader for comparison | `legacy/loader.py` |

**Reproduce the published paper exactly:** `git checkout published-v1` (tag on the last commit before the migration), then use the README of that revision.

**Rules**
- Runtime code never imports `legacy` or reads these files (`tests/test_no_synthetic_runtime.py`).
- Permitted: paper reproduction, comparing results old-vs-new (`scripts/compare_legacy_vs_official.py`), debugging, historical reference.
- Fully reversible: `git mv legacy/data/raw data/raw` and `git revert` the migration commits, or check out the tag.
