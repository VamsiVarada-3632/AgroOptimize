#!/usr/bin/env python3
"""Rebuild the official-data database and the clean CSVs from data/official/raw/.
Usage: python scripts/preprocess_all.py [--raw DIR] [--db-url URL]"""
import argparse, json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ap = argparse.ArgumentParser(); ap.add_argument("--raw"); ap.add_argument("--db-url")
a = ap.parse_args()
if a.db_url:
    os.environ["AGROOPTIMIZE_DB_URL"] = a.db_url
from app.datasets.pipeline import build_database  # noqa: E402

report = build_database(Path(a.raw) if a.raw else None)
for r in report:
    print(f"{r['dataset']:22s} raw={r['rows_raw']:6d} clean={r['rows_clean']:6d}")
    for i in r["issues"]:
        print(f"    [{i['level']}] {i['code']}: {i['message']}")
Path("data/official").mkdir(parents=True, exist_ok=True)
Path("data/official/validation_report.json").write_text(json.dumps(report, indent=2, default=str))
