import pandas as pd
import pytest

from app.datasets import conversion_loader as cl
from app.datasets.units import UNIT_BASIS_MISMATCH


def test_table_valid_and_cited():
    t = cl.load_table()
    assert list(t.columns) == cl.COLUMNS
    assert (t.official_source != "").all() and (t.page_number != "").all() and (t.year != "").all()


def test_rice_norm_recorded_with_both_sources():
    r = cl.rows_for("rice")
    assert set(r.conversion_factor) == {0.67}
    assert len(r) == 2 and set(r.year) == {"2024", "1994"}


def test_rice_not_applied_until_applicability_verified():
    with pytest.raises(cl.ConversionUnavailable):
        cl.conversion_factor("rice", "paddy", "rice")
    assert cl.conversion_factor("rice", "paddy", "rice", require_applicable=False) == 0.67
    assert cl.conversion_factor("rice", "rice", "paddy", require_applicable=False) == pytest.approx(1 / 0.67)


def test_cotton_has_no_conversion():
    assert cl.rows_for("cotton").empty
    for a, b in (("kapas", "lint"), ("lint", "kapas")):
        with pytest.raises(cl.ConversionUnavailable):
            cl.conversion_factor("cotton", a, b, require_applicable=False)


def test_rice_and_cotton_remain_excluded_from_optimisation():
    assert set(UNIT_BASIS_MISMATCH) == {"rice", "cotton"}


def test_validation_rejects_unofficial_host_and_missing_citation():
    df = pd.read_csv(cl.PATH, dtype=str).fillna("")
    bad = df.copy(); bad.loc[0, "source_url"] = "https://blog.example.com/x"
    with pytest.raises(ValueError):
        cl.validate(bad)
    bad = df.copy(); bad.loc[0, "page_number"] = ""
    with pytest.raises(ValueError):
        cl.validate(bad)
    bad = df.copy(); bad.loc[0, "conversion_factor"] = "0"
    with pytest.raises(ValueError):
        cl.validate(bad)
