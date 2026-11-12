#!/usr/bin/env python3
"""Extract MSP from the official PDFs into data/official/raw/msp_extracted.csv.
Text PDFs are parsed; scanned PDFs come from app/scrapers/msp_transcribed.py (image-verified).
Usage: python scripts/extract_msp.py --pdf-dir "GOVT DATASETS" """
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.datasets import msp  # noqa: E402

ap = argparse.ArgumentParser(); ap.add_argument("--pdf-dir", required=True); a = ap.parse_args()
df = msp.extract(Path(a.pdf_dir)); msp.clean(df)
out = Path("data/official/raw/msp_extracted.csv"); df.to_csv(out, index=False); print(f"wrote {len(df)} rows -> {out}")
