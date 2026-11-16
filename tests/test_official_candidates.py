"""Every crop the optimiser may plant has a complete official record; every other crop says why not."""
from __future__ import annotations

import math

import pytest

from app import config
from app.data import preprocessing as pp

CASES = [(d, s) for d in config.LOCATIONS for s in ("Kharif", "Rabi")]


def _finite_positive(v):
    return v is not None and math.isfinite(v) and v > 0


@pytest.mark.parametrize("district,season", CASES)
def test_candidates_have_a_complete_official_record(district, season):
    try:
        profile = pp.get_region_season_profile(district, season)
    except ValueError as exc:
        # only districts with fewer than two complete crops may refuse, and they must say so
        assert "complete official data" in str(exc)
        return
    assert len(profile.candidate_crops) >= 2
    for c in profile.candidate_crops:
        assert _finite_positive(c.yield_kg_ha), (district, c.name, "yield")
        assert _finite_positive(c.msp_rs_qtl), (district, c.name, "MSP")
        assert _finite_positive(c.cost_rs_qtl), (district, c.name, "CACP cost")
        assert _finite_positive(c.fert_n_kg_ha + c.fert_p_kg_ha + c.fert_k_kg_ha), (district, c.name, "TNAU dose")
        assert 0.0 <= c.irrigated_share <= 1.0 and 0.0 <= c.rainfed_share <= 1.0
        assert c.irrigated_share + c.rainfed_share == pytest.approx(1.0, abs=1e-3)
    for e in profile.excluded_crops:
        assert e["reasons"], (district, e["crop"])
    assert not {c.name for c in profile.candidate_crops} & {e["crop"] for e in profile.excluded_crops}


def test_only_chennai_and_the_nilgiris_lack_two_complete_crops():
    refused = set()
    for district, season in CASES:
        try:
            pp.get_region_season_profile(district, season)
        except ValueError:
            refused.add(district)
    assert refused == {"Chennai", "The Nilgiris"}
