"""Compare the archived synthetic data (legacy/, paper) with the official datasets (runtime) - for the report / viva.
Read-only: nothing is written to the database or to results/. Run: python scripts/compare_legacy_vs_official.py [--json out.json]

Compares, for the four districts the paper used (Pollachi is a Coimbatore taluk in the official data):
  * crop-level yield (kg/ha) and area: synthetic Kharif/Rabi rows vs the official 2024-25 Season & Crop Report
  * seasonal rainfall (mm): synthetic 2023 vs official IMD actual
  * MSP (Rs/quintal): synthetic MSP_Rs_Qtl vs the official KMS/RMS 2024-25 notification"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from app.data import loader as official  # noqa: E402
from legacy import loader as old  # noqa: E402

MAP = {"Coimbatore": "Coimbatore", "Erode": "Erode", "Salem": "Salem", "Pollachi": "Coimbatore"}


def crops() -> pd.DataFrame:
    o, n = old.load_kind("crop"), official.load_all()["crop"]
    o = o[o.Year == o.Year.max()]
    rows = []
    for _, r in o.iterrows():
        match = n[(n.Location == MAP[r.Location]) & (n.Season == r.Season) & (n.Crop_Name.str.lower() == str(r.Crop_Name).lower())]
        if match.empty:
            continue
        m = match.iloc[0]
        rows.append({"district": r.Location, "season": r.Season, "crop": r.Crop_Name,
                     "legacy_yield_kg_ha": r.Yield_Kg_Ha, "official_yield_kg_ha": m.Yield_Kg_Ha,
                     "legacy_msp": r.MSP_Rs_Qtl, "official_msp": m.MSP_Rs_Qtl,
                     "legacy_area_ha": r.Area_Sown_Ha, "official_area_ha": m.Area_Ha})
    return pd.DataFrame(rows)


def rainfall() -> pd.DataFrame:
    o, n = old.load_kind("rainfall"), official.load_all()["rainfall"]
    o = o[o.Year == o.Year.max()].groupby("Location").Monthly_Rainfall_mm.sum()
    n = n.groupby("Location").Monthly_Rainfall_mm.sum()
    return pd.DataFrame({"legacy_mm": o, "official_mm": [n.get(MAP[k]) for k in o.index]}, index=o.index)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    args = ap.parse_args()
    c, r = crops(), rainfall()
    print("== crops (matched legacy rows) ==")
    print(c.to_string(index=False) if len(c) else "no matching crop rows")
    print("\n== annual rainfall (mm) ==")
    print(r.to_string())
    if args.json:
        Path(args.json).write_text(json.dumps({"crops": c.to_dict("records"), "rainfall": r.reset_index().to_dict("records")}, indent=2, default=str))


if __name__ == "__main__":
    main()
