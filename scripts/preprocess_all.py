#!/usr/bin/env python3
"""Rebuild the official-data database and the clean CSVs from data/official/raw/.
Usage: python scripts/preprocess_all.py [--raw DIR] [--db-url URL] [--check]

--check rebuilds nothing: it compares the dataset registry in the existing
database with the raw files (SHA-256) and exits 1 if a file is missing,
changed or not yet imported."""
import argparse, json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ap = argparse.ArgumentParser(); ap.add_argument("--raw"); ap.add_argument("--db-url")
ap.add_argument("--check", action="store_true", help="verify the database registry against the raw files; build nothing")
a = ap.parse_args()
if a.db_url:
    os.environ["AGROOPTIMIZE_DB_URL"] = a.db_url
from app.datasets.pipeline import all_datasets, build_database  # noqa: E402


def check(raw_dir):
    from app.datasets import service
    from app.datasets.base import RAW_DIR, sha256_file
    registry = {p["name"]: p for p in service.provenance()}
    problems = 0
    for ds in all_datasets():
        path = ds.path(raw_dir or RAW_DIR)
        row = registry.get(ds.name)
        if not path.exists():
            status = "MISSING raw file"
        elif row is None:
            status = "NOT IMPORTED (rebuild the database)"
        elif row["sha256"] != sha256_file(path):
            status = "CHANGED since import (rebuild the database)"
        else:
            status = "ok"
        problems += status != "ok"
        print(f"{ds.name:22s} {status}")
    return problems


if a.check:
    n = check(Path(a.raw) if a.raw else None)
    print("registry matches the raw files" if n == 0 else f"{n} dataset(s) need attention")
    sys.exit(1 if n else 0)

report = build_database(Path(a.raw) if a.raw else None)
for r in report:
    print(f"{r['dataset']:22s} raw={r['rows_raw']:6d} clean={r['rows_clean']:6d}")
    for i in r["issues"]:
        print(f"    [{i['level']}] {i['code']}: {i['message']}")
Path("data/official").mkdir(parents=True, exist_ok=True)
Path("data/official/validation_report.json").write_text(json.dumps(report, indent=2, default=str))
