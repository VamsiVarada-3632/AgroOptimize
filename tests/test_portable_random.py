"""
portable_random.legacy_normal: the mutation operator's Gaussian draws must
be the same on every platform (the published results came from an arm64
NumPy build, deployments run on x86-64 Linux) and must leave the global
random stream exactly where np.random.normal leaves it.
"""

from __future__ import annotations

import math
from fractions import Fraction

import numpy as np
import pytest

from app.optimization import portable_random
from app.optimization.portable_random import legacy_normal


def _fused(x1, x2):
    return float(Fraction(x1) * Fraction(x1) + Fraction(x2 * x2))


def reference_normals(rs: np.random.RandomState, n: int, cache):
    """NumPy's legacy polar generator written out in plain Python, with the
    fused sum computed exactly: the specification legacy_normal implements."""
    out = []
    while len(out) < n:
        if cache is not None:
            out.append(cache)
            cache = None
            continue
        while True:
            x1 = 2.0 * rs.random_sample() - 1.0
            x2 = 2.0 * rs.random_sample() - 1.0
            r2 = _fused(x1, x2)
            if r2 < 1.0 and r2 != 0.0:
                break
        f = math.sqrt(-2.0 * math.log(r2) / r2)
        out.append(f * x2)
        cache = f * x1
    return np.array(out), cache


SHAPES = [(80, 15), (40, 9), (24, 6), (1, 1), (3, 1), (0, 5), (7, 3)]


@pytest.mark.parametrize("seed", [0, 7, 42, 2024])
def test_matches_the_reference_generator(seed):
    np.random.seed(seed)
    ref = np.random.RandomState(seed)
    cache = None
    for shape in SHAPES * 3:
        need = np.ones(shape, dtype=bool)
        got = legacy_normal(0.12, shape, need)
        expected, cache = reference_normals(ref, int(np.prod(shape)), cache)
        assert np.array_equal(got.ravel(), 0.12 * expected)


@pytest.mark.parametrize("seed", [1, 42])
def test_stream_and_cache_end_where_numpy_leaves_them(seed):
    rng = np.random.default_rng(seed)
    for shape in SHAPES * 4:
        need = rng.random(shape) < 0.12
        np.random.seed(seed)
        np.random.random(5)
        np.random.normal(0.0, 0.12, shape)
        np.random.normal(0.0, 0.12, (3,))  # leaves an odd cache state
        np.random.normal(0.0, 0.12, shape)
        a = np.random.get_state()
        after_a = np.random.random(4)

        np.random.seed(seed)
        np.random.random(5)
        legacy_normal(0.12, shape, need)
        legacy_normal(0.12, (3,), np.ones(3, dtype=bool))
        legacy_normal(0.12, shape, need)
        b = np.random.get_state()
        after_b = np.random.random(4)

        assert a[2] == b[2] and np.array_equal(a[1], b[1])  # MT19937 position
        assert (a[3], a[4]) == (b[3], pytest.approx(b[4], abs=1e-12))  # cached value (fused vs unfused)
        assert np.array_equal(after_a, after_b)


def test_unneeded_draws_are_zero_and_needed_ones_unchanged():
    shape = (30, 7)
    need = np.random.default_rng(3).random(shape) < 0.2
    np.random.seed(5)
    full = legacy_normal(0.12, shape, np.ones(shape, dtype=bool))
    np.random.seed(5)
    part = legacy_normal(0.12, shape, need)
    assert np.array_equal(part[need], full[need])
    assert not part[~need].any()


def test_close_to_numpy_on_any_platform():
    np.random.seed(9)
    expected = np.random.normal(0.0, 0.12, (200, 15))
    np.random.seed(9)
    got = legacy_normal(0.12, (200, 15), np.ones((200, 15), dtype=bool))
    assert np.allclose(got, expected, rtol=0, atol=1e-14)


def test_exact_rational_fallback_matches_fma(monkeypatch):
    if portable_random._FMA is None:
        pytest.skip("math.fma needs Python 3.13")
    np.random.seed(11)
    with_fma = legacy_normal(0.12, (50, 12), np.ones((50, 12), dtype=bool))
    monkeypatch.setattr(portable_random, "_FMA", None)
    np.random.seed(11)
    without = legacy_normal(0.12, (50, 12), np.ones((50, 12), dtype=bool))
    assert np.array_equal(with_fma, without)
