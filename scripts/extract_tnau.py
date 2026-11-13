#!/usr/bin/env python3
"""Write data/official/raw/agronomy_tnau.csv from the page-cited TNAU guide transcription."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd  # noqa: E402
from app.scrapers.tnau_guide import COLUMNS, rows  # noqa: E402
from app.datasets.agronomy import AgronomyTnau  # noqa: E402

df = pd.DataFrame(rows(), columns=COLUMNS)
AgronomyTnau().clean(df)
out = Path("data/official/raw/agronomy_tnau.csv"); df.to_csv(out, index=False); print(f"wrote {len(df)} rows -> {out}")
