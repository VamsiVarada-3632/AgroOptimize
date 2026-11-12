#!/usr/bin/env python3
"""Write data/official/raw/agronomy_master.csv from the page-cited TNAU transcription (app/scrapers/tnau_master.py).

N/P2O5/K2O are filled only where the guide gives a single recommendation for the crop (all conditions agree in
agronomy_tnau.csv); otherwise they stay NULL and every condition is listed in npk_by_condition."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd  # noqa: E402
from app.scrapers import tnau_master as m  # noqa: E402


def _num(x):
    return None if pd.isna(x) else float(x)


def build() -> pd.DataFrame:
    npk = pd.read_csv("data/official/raw/agronomy_tnau.csv")
    out = []
    for rec in m.RECORDS:
        r = {c: None for c in m.COLUMNS}
        r.update(rec)
        if r["suitable_districts"] == m.SAME_AS_SEASON:
            r["suitable_districts"] = r["season"]
        sub = npk[npk.crop == r["crop"]]
        if rec.get("npk_by_condition"):        # the guide gives conditions that agronomy_tnau.csv does not carry
            r["npk_by_condition"] = rec["npk_by_condition"]
        elif len(sub):
            trip = {(_num(a), _num(b), _num(c)) for a, b, c in zip(sub.n_kg_ha, sub.p_kg_ha, sub.k_kg_ha)}
            if len(trip) == 1 and None not in next(iter(trip)):
                r["n_kg_ha"], r["p_kg_ha"], r["k_kg_ha"] = next(iter(trip))
            r["npk_by_condition"] = "; ".join(
                f"{c}: N {'' if pd.isna(n) else n:g} P2O5 {'NULL' if pd.isna(p) else format(p, 'g')} K2O {'' if pd.isna(k) else k:g}"
                + ("" if pd.isna(s) else f" S {s:g}") + f" (pdf p{int(pg)})"
                for c, n, p, k, s, pg in zip(sub.condition, sub.n_kg_ha, sub.p_kg_ha, sub.k_kg_ha, sub.s_kg_ha, sub.pdf_page))
        r["source_url"], r["retrieved_at"] = m.SOURCE_URL, m.RETRIEVED_AT
        out.append(r)
    return pd.DataFrame(out, columns=m.COLUMNS)


if __name__ == "__main__":
    df = build()
    Path("data/official/raw").mkdir(parents=True, exist_ok=True)
    df.to_csv("data/official/raw/agronomy_master.csv", index=False)
    print(f"wrote {len(df)} crops -> data/official/raw/agronomy_master.csv")
