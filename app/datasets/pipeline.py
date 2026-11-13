"""Run every dataset pipeline: raw -> validate -> clean -> clean CSV -> SQLite, with registry + log."""
from __future__ import annotations
import datetime as dt
from pathlib import Path
from typing import Dict, List

import pandas as pd
from sqlalchemy import insert, text

from app import config
from app.datasets.base import RAW_DIR, CleanResult, sha256_file
from app.datasets.crops import CropsByDistrict, CropsStateSeries
from app.datasets.groundwater import Groundwater
from app.datasets.irrigation import Irrigation
from app.datasets.land_use import LandUse
from app.datasets.rainfall import Rainfall
from app.datasets.reference import DISTRICT_RESERVOIR_MAP
from app.datasets.reservoir import ReservoirDaily
from app.datasets.msp import MspExtracted
from app.datasets.agronomy import AgronomyTnau
from app.datasets.soil_health import SoilHealthTN
from app.db import schema
from app.db.session import get_engine

CLEAN_DIR = config.PROJECT_ROOT / "data" / "official" / "clean"


def all_datasets():
    return [CropsByDistrict(), CropsStateSeries(), LandUse(), Irrigation(), Rainfall(), Groundwater(), ReservoirDaily(), MspExtracted(), AgronomyTnau(), SoilHealthTN()]


def _district_rows(frames: Dict[str, pd.DataFrame], raw_dir: Path) -> pd.DataFrame:
    from app.datasets.normalize import district_key
    raw = pd.read_csv(raw_dir / "crops_by_district.csv", usecols=["district", "district_code"]).drop_duplicates()
    raw["norm_name"] = raw["district"].map(district_key)
    raw["is_state"] = raw["norm_name"].eq("tamil nadu")
    codes = raw.dropna(subset=["district_code"]).drop_duplicates("norm_name").set_index("norm_name")["district_code"]
    out = raw.drop_duplicates("norm_name")[["norm_name", "district", "is_state"]].rename(columns={"district": "name"})
    out["code"] = out["norm_name"].map(codes).astype("Int64")
    return out


def _crop_rows(raw_dir: Path) -> pd.DataFrame:
    from app.datasets.normalize import crop_key
    r = pd.read_csv(raw_dir / "crops_by_district.csv", usecols=["crop", "group"]).drop_duplicates("crop")
    return pd.DataFrame({"norm_name": r["crop"].map(crop_key), "name": r["crop"], "crop_group": r["group"]})


def build_database(raw_dir: Path | None = None, engine=None, clean_dir: Path | None = CLEAN_DIR) -> List[dict]:
    """(Re)build the database from the raw official files. Idempotent: drops and recreates all tables."""
    raw_dir = raw_dir or RAW_DIR
    engine = engine or get_engine()
    schema.metadata.drop_all(engine)
    schema.metadata.create_all(engine)
    report = []
    frames: Dict[str, pd.DataFrame] = {}
    if clean_dir:
        Path(clean_dir).mkdir(parents=True, exist_ok=True)
    for ds in all_datasets():
        res: CleanResult = ds.load(raw_dir)
        frames[ds.name] = res.frame
        with engine.begin() as cx:
            reg = cx.execute(insert(schema.dataset_registry).values(
                name=ds.name, filename=ds.filename, sha256=sha256_file(ds.path(raw_dir)), report_year="2024-25",
                rows_raw=res.rows_raw, rows_clean=len(res.frame), imported_at=dt.datetime.now(dt.timezone.utc).isoformat()))
            dataset_id = reg.inserted_primary_key[0]
        ds.import_to_db(engine, dataset_id, res)   # CropsByDistrict etc. may add dataset_id themselves
        with engine.begin() as cx:
            for i in res.issues:
                cx.execute(insert(schema.ingestion_log).values(dataset_id=dataset_id, level=i.level, code=i.code, message=i.message, rows=i.rows))
        if clean_dir:
            res.frame.to_csv(Path(clean_dir) / f"{ds.name}.csv", index=False)
        report.append({"dataset": ds.name, "rows_raw": res.rows_raw, "rows_clean": len(res.frame),
                       "issues": [vars(i) for i in res.issues]})
    _district_rows(frames, raw_dir).to_sql("district", engine, if_exists="append", index=False)
    _crop_rows(raw_dir).to_sql("crop", engine, if_exists="append", index=False)
    pd.DataFrame(DISTRICT_RESERVOIR_MAP, columns=["district", "slug", "basis"]).to_sql("district_reservoir_map", engine, if_exists="append", index=False)
    return report
