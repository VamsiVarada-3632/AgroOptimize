# legacy/tests - the paper-version test files

Verbatim copies of the test modules as they were on the `published-v1` tag, when the system ran on the synthetic CSVs.
They assert synthetic-data facts (4 districts, 2020-2024, estimated years, golden NSGA-II digests) and **do not run against
the migrated code**. They are not collected by `pytest` (`testpaths = tests`).

To reproduce the paper's numbers: `git checkout published-v1 && python -m pytest tests` (golden digests are
platform-dependent; they were recorded on the author's machine).

The migrated suite lives in `tests/` and runs on the official datasets only.
