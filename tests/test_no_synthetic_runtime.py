"""The official datasets are the ONLY runtime data source: nothing under app/ may import legacy/ or read the archived synthetic CSVs."""
import ast
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / "app"
SYNTHETIC_COLUMNS = ("Rainfall_Dependency", "Water_Req_mm_Season", "Carbon_Emission", "FERTILIZER_PRICE")
OLD_CSV = re.compile(r"(crop|land|rainfall|water)\.csv|data/raw|RAW_DATA_DIR|DISTRICT_COORDINATES|DATASET_KINDS")


def _py_files():
    return sorted(p for p in APP.rglob("*.py"))


def test_app_never_imports_legacy():
    offenders = []
    for f in _py_files():
        for node in ast.walk(ast.parse(f.read_text())):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            if any(m == "legacy" or m.startswith("legacy.") for m in mods):
                offenders.append(str(f.relative_to(ROOT)))
    assert not offenders, offenders


def test_app_never_references_old_synthetic_csvs():
    offenders = []
    for f in _py_files():
        code = "\n".join(line for line in f.read_text().splitlines() if not line.lstrip().startswith(("#", '"""')))
        if OLD_CSV.search(code):
            offenders.append(str(f.relative_to(ROOT)))
    assert not offenders, offenders


def test_archived_csvs_exist_only_under_legacy():
    assert not (ROOT / "data" / "raw").exists() or not list((ROOT / "data" / "raw").glob("*.csv"))
    assert list((ROOT / "legacy" / "data" / "raw").glob("*.csv")), "archive must be intact for paper reproduction"


def test_runtime_frames_carry_official_provenance_only():
    from app.data.loader import load_all
    for kind, df in load_all().items():
        src = df["data_source"].dropna().astype(str)
        assert len(src) and src.str.startswith("Official").all(), (kind, src[~src.str.startswith("Official")].unique()[:3])


def test_runtime_has_no_estimated_rows():
    from app.data.loader import load_all
    for kind, df in load_all().items():
        if "data_source" in df:
            assert not df["data_source"].astype(str).str.contains("Estimated|Synthetic", case=False).any(), kind


def test_missing_official_data_raises_not_falls_back(monkeypatch):
    from app.errors import FeatureUnavailable
    from app.services import dashboard_service
    with pytest.raises(FeatureUnavailable):
        dashboard_service.get_weather("Coimbatore")
