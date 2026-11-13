#!/usr/bin/env python3
"""Write data/official/raw/soil_master.csv from the raw Soil Health Card feed (soil_health_tn.csv): official counts
only, canonical district names, per-parameter totals and dominant class. soil_type stays NULL (not in the feed)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd  # noqa: E402
from app import config  # noqa: E402
from app.datasets import soil_master as sm  # noqa: E402
from app.datasets.normalize import district_key  # noqa: E402

SOURCE_URL = "https://soilhealth.dac.gov.in/"


def build() -> pd.DataFrame:
    raw = pd.read_csv(sm.SOURCE_REF)
    canon = {district_key(d): d for d in config.LOCATIONS}
    rows = []
    for _, s in raw.iterrows():
        name = canon.get(district_key(s["district"]))
        if name is None:
            raise SystemExit(f"district {s['district']} has no canonical name")
        r = {"district": name, "district_code": int(s["district_code"]), "cycle": s["cycle"], "soil_type": None}
        totals = []
        for p, (_, _, classes) in sm.PARAMS.items():
            vals = [int(s[f"{p}_{c}"]) for c in classes]
            for c, v in zip(classes, vals):
                r[f"{p}_{c}".lower()] = v
            r[f"{p.lower()}_samples"] = sum(vals)
            top = max(vals)
            r[f"{p.lower()}_dominant_class"] = "tie" if vals.count(top) > 1 else classes[vals.index(top)]
            totals.append(sum(vals))
        r["samples_tested"] = max(totals)
        r["last_processed"], r["source_url"], r["retrieved_at"] = s["last_processed"], SOURCE_URL, "2026-11-12"
        rows.append(r)
    return pd.DataFrame(rows).sort_values("district")[sm.COLUMNS]


if __name__ == "__main__":
    df = build(); df.to_csv("data/official/raw/soil_master.csv", index=False)
    print(f"wrote {len(df)} districts -> data/official/raw/soil_master.csv")
