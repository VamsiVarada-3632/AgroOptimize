"""Engine factory. Default DB: data/official/official_v1.db (override with AGROOPTIMIZE_DB_URL)."""
from __future__ import annotations
import os
from functools import lru_cache
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from app import config

DEFAULT_DB_PATH = config.PROJECT_ROOT / "data" / "official" / "official_v1.db"

def db_url() -> str:
    return os.environ.get("AGROOPTIMIZE_DB_URL") or f"sqlite:///{DEFAULT_DB_PATH}"

@lru_cache(maxsize=4)
def get_engine(url: str | None = None) -> Engine:
    return create_engine(url or db_url(), future=True)

def reset_engine_cache() -> None:
    get_engine.cache_clear()
