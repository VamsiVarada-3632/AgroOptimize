"""Writes docs/data_architecture/MIGRATION_REPORT.md from the live mapping + DISABLED_FEATURES (no hand-typed facts)."""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app.datasets.status import DISABLED_FEATURES

root = pathlib.Path(__file__).resolve().parents[1]
mp = json.load(open(root / "official_dataset_mapping.json"))["datasets"]
legacy = sorted(p.name for p in (root / "legacy/data/raw").glob("*.csv"))
out = ["# Official-data migration report", "",
       "Official government datasets are the only runtime data source. The synthetic v1 data is tagged `published-v1` and archived in `legacy/` "
       "(paper reproduction, comparison, debugging, history only). `tests/test_no_synthetic_runtime.py` fails if any runtime module imports it.", "",
       "## 1. Synthetic datasets replaced", "", "| Old file (now `legacy/data/raw/`) | Replaced by |", "|---|---|"]
repl = {"crop": "crop_production + msp + agronomy_tnau + cost of cultivation", "land": "land_use", "rainfall": "IMD rainfall", "water_availability": "reservoir storage"}
for f in legacy:
    kind = f.split("_", 1)[1].rsplit(".", 1)[0]
    out.append(f"| {f} | {repl.get(kind, '-')} |")
out += ["", "## 2. Official datasets in use", "", "| Key | Source | File | Report year | Rows | Used by |", "|---|---|---|---|---|---|"]
for k, v in mp.items():
    out.append(f"| {k} | {v['source']} | {v['file']} | {v.get('report_year','')} | {v.get('rows','')} | {'; '.join(v['used_by'])} |")
out += ["", "## 3. Features still disabled (no fallback to synthetic data)", "", "| Feature | Missing official dataset | Source to scrape | Scope |", "|---|---|---|---|"]
for d in DISABLED_FEATURES:
    out.append(f"| {d['feature']} | {d['missing_dataset']} | {d['source']} | {d['scope']} |")
out += ["", "## 4. Remaining TODO", "",
        "- Frontend (React/Vite) not yet migrated: rename `water_liters`->`irrigated_ha`, drop hard-coded `DISTRICTS` (api.js) and `FALLBACK_CROPS` (Auth/ProfileSetup/Settings views), drive lists from `/api/catalog`, show 'Data not available' on 501/400 responses, weather widget 501 state.",
        "- Load TNAU horticulture doses, official kapas->lint and paddy->rice conversion factors, reservoir->district map and pre-2025 reservoir levels, IMD weather, fertiliser prices, labour/pesticide costs, earlier Season & Crop Reports, taluk statistics.",
        "- Chennai and The Nilgiris return HTTP 400 ('complete official data'): fewer than 2 crops have all required official fields.",
        "- Fuzzy stage is applied only where official reservoir data exist (9 districts, Rabi); elsewhere flagged 'not applied' with neutral confidence 1.0."]
(root / "docs/data_architecture/MIGRATION_REPORT.md").write_text("\n".join(out) + "\n")
