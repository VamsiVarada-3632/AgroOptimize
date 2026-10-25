"""
Tests for the second round of NSGA-II engine work: run-time improvements
that must not change any result, the new switchable features, the quality
metrics and their exposure through the API.
"""

from __future__ import annotations

import numpy as np
import pytest
from pymoo.indicators.hv import HV

from app.optimization import monitoring
from app.optimization.nsga2_runner import run_nsga2

from tests.test_nsga2_engine import _digest, _problem

# Digests of the enhanced engine as merged in PR #12 (recorded on main):
# any later speed-up must reproduce them exactly.
ENHANCED_GOLDEN = [
    (dict(location="Salem", season="Kharif"), "1e64a443331f689f"),
    (dict(location="Erode", season="Rabi", budget=120000.0), "c5747c91779d74a5"),
    (dict(location="Coimbatore", season="Summer"), "51ead5e790b5a25b"),
]


@pytest.mark.parametrize("args,digest", ENHANCED_GOLDEN)
def test_enhanced_engine_reproduces_its_recorded_results(args, digest):
    result = run_nsga2(_problem(**args), pop_size=40, n_gen=60, seed=3, mode="enhanced")
    assert _digest(result) == digest


# ---------------------------------------------------------------------------
# Speed-ups that must be exact
# ---------------------------------------------------------------------------

def _hypervolume_from_getters(algorithm):
    """front_hypervolume as it was computed before: algorithm.opt filtered by
    FEAS, read through pymoo's per-individual getters."""
    lo, span = algorithm.data["_hv_bounds"]
    opt = algorithm.opt
    feasible = opt[np.ravel(opt.get("FEAS")).astype(bool)]
    if not len(feasible):
        return 0.0
    F = (feasible.get("F") - lo) / span
    return float(HV(ref_point=np.full(F.shape[1], 1.1))(F))


@pytest.mark.parametrize("budget", [None, 150000.0, 20000.0])  # 20000: no feasible plan at all
def test_front_hypervolume_matches_the_getter_computation(budget):
    result = run_nsga2(_problem("Erode", "Kharif", budget=budget), pop_size=30, n_gen=12, seed=5, mode="enhanced")
    algorithm = result.algorithm
    algorithm.data.pop("_hv_cache", None)
    assert monitoring.front_hypervolume(algorithm) == _hypervolume_from_getters(algorithm)
