"""Interfaces shared by all official datasets.

Each dataset module provides: validate (raw), clean, load (= read+validate+clean),
import_to_db, and a cached service object (see app/datasets/service.py)."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import pandas as pd

from app import config

RAW_DIR = config.PROJECT_ROOT / "data" / "official" / "raw"


class DataValidationError(ValueError):
    """Raised when a raw file does not have the structure the cleaner relies on."""


@dataclass
class Issue:
    level: str          # "error" | "warning" | "info"
    code: str
    message: str
    rows: int = 0


@dataclass
class CleanResult:
    frame: pd.DataFrame
    issues: List[Issue] = field(default_factory=list)
    rows_raw: int = 0

    def add(self, level, code, message, rows=0):
        self.issues.append(Issue(level, code, message, int(rows)))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class OfficialDataset:
    """Subclass and set name/filename/table/required_columns; implement _clean."""
    name: str = ""
    filename: str = ""
    table: str = ""
    required_columns: tuple = ()

    def path(self, raw_dir: Path | None = None) -> Path:
        return (raw_dir or RAW_DIR) / self.filename

    # ---- reader / validator ----
    def read_raw(self, raw_dir: Path | None = None) -> pd.DataFrame:
        p = self.path(raw_dir)
        if not p.exists():
            raise FileNotFoundError(f"Official dataset file missing: {p}")
        return pd.read_csv(p)

    def validate_raw(self, df: pd.DataFrame) -> List[Issue]:
        issues: List[Issue] = []
        missing = [c for c in self.required_columns if c not in df.columns]
        if missing:
            raise DataValidationError(f"{self.filename}: missing columns {missing}")
        if df.empty:
            raise DataValidationError(f"{self.filename}: no rows")
        n_dup = int(df.duplicated().sum())
        if n_dup:
            issues.append(Issue("warning", "duplicates_removed", f"{n_dup} exact duplicate rows removed", n_dup))
        return issues

    # ---- cleaner ----
    def clean(self, df: pd.DataFrame) -> CleanResult:
        issues = self.validate_raw(df)
        res = CleanResult(frame=pd.DataFrame(), issues=issues, rows_raw=len(df))
        df = df.drop_duplicates().reset_index(drop=True)
        res.frame = self._clean(df, res).reset_index(drop=True)
        return res

    def _clean(self, df: pd.DataFrame, res: CleanResult) -> pd.DataFrame:  # pragma: no cover
        raise NotImplementedError

    # ---- loader ----
    def load(self, raw_dir: Path | None = None) -> CleanResult:
        return self.clean(self.read_raw(raw_dir))

    # ---- database importer ----
    def import_to_db(self, engine, dataset_id: int, res: CleanResult) -> int:
        frame = res.frame.copy()
        if "dataset_id" in {c.name for c in _table(self.table).columns}:
            frame.insert(0, "dataset_id", dataset_id)
        frame.to_sql(self.table, engine, if_exists="append", index=False)
        return len(frame)


def _table(name):
    from app.db.schema import metadata
    return metadata.tables[name]
