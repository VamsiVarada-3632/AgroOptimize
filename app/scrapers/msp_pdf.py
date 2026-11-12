"""Parser for PIB / DA&FW MSP tables that have a text layer (cost-of-production layout).

Row shape: <crop [variety]>  MSP  cost|-  margin|-  previous-year MSP  increase"""
from __future__ import annotations
import re
import subprocess
from typing import List

ROW = re.compile(r"^\s*(?:\d+\s+)?(?P<name>[A-Za-z(][^\d]*?)\s{2,}(?P<msp>\d{3,5})\s+(?P<cost>\d{3,5}|-)\s+(?P<margin>\d{1,3}|-)\s+(?P<prev>\d{3,5})\s+(?P<inc>\d{1,4})\s*$")
VARIETY_ONLY = {"common", "grade a", "hybrid", "maldandi", "(long", "(medium"}


def pdf_text(path: str) -> str:
    return subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True, check=True).stdout


def _clean_name(raw: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[\^\"']", "", raw)).strip()


def parse_cost_table(text: str) -> List[dict]:
    rows, crop = [], None
    for line in text.splitlines():
        m = ROW.match(line)
        if not m:
            continue
        parts = [_clean_name(p) for p in re.split(r"\s{2,}", m["name"].strip()) if p.strip()]
        name = " ".join(parts)
        crop_part, variety = (parts[0], " ".join(parts[1:]) or None) if len(parts) > 1 else (parts[0], None)
        if len(parts) == 1 and crop_part.lower() in VARIETY_ONLY and crop:
            variety, crop_part = crop_part, crop
        elif crop_part.lower() in VARIETY_ONLY and crop:
            variety, crop_part = crop_part, crop
        elif len(parts) > 1 and parts[1] == "&":            # "Rapeseed &" / "Mustard" wrapped over two lines
            crop_part, variety = "Rapeseed & Mustard", None
        elif crop_part.lower().startswith("cotton"):
            variety = (variety or crop_part.replace("Cotton", "").strip() or None)
            crop_part = "Cotton"
        elif crop_part.lower().startswith("rapeseed"):
            crop_part, variety = "Rapeseed & Mustard", None
        crop = crop_part
        num = lambda s: None if s == "-" else float(s)
        rows.append({"crop": crop_part, "variety": variety, "msp": float(m["msp"]), "cost": num(m["cost"]),
                     "margin": num(m["margin"]), "prev": float(m["prev"]), "increase": float(m["inc"])})
    return rows
