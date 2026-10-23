"""
Platform-independent Gaussian draws for the mutation operator.

The published results were produced with `np.random.normal` on an arm64
build of NumPy. Its legacy polar (Marsaglia) generator computes
r2 = x1*x1 + x2*x2 with a fused multiply-add there, while x86-64 builds
round the two products separately. About 14 % of the draws then differ in
the last bit, which is enough for an NSGA-II run on a Linux x86-64 server
to drift onto a different Pareto front after a few generations.

`legacy_normal` reproduces that generator exactly on every platform:

* it consumes the global RandomState (MT19937) exactly as
  `np.random.normal(0.0, scale, shape)` does, including the cached second
  value of each pair, so every later draw is unchanged;
* r2 is computed with a correctly rounded fused multiply-add
  (`math.fma`, or exact rational arithmetic before Python 3.13), which is
  what the arm64 build computes;
* the square root, division and products are IEEE-exact operations; the
  logarithm is the C library's `log`, as in NumPy.

Only the draws the caller will use (`needed`) are computed this way; the
others are returned as 0.0. GaussianMutation only adds noise to the genes
its mask selects, so the result is identical.
"""

from __future__ import annotations

import math
from fractions import Fraction

import numpy as np

_FMA = getattr(math, "fma", None)


def _sum_of_squares(x1: float, x2: float) -> float:
    """fl(x1*x1 + fl(x2*x2)) with a single rounding of the sum, as a fused
    multiply-add computes it."""
    if _FMA is not None:
        return _FMA(x1, x1, x2 * x2)
    return float(Fraction(x1) * Fraction(x1) + Fraction(x2 * x2))


def _accepted_pairs(n_pairs: int):
    """The first `n_pairs` accepted (x1, x2) pairs of the polar method,
    drawn from the global RandomState. Each round draws two uniforms per
    pair still missing; every pair drawn is one the legacy generator also
    draws (it never stops before n_pairs are accepted), so the stream ends
    exactly where np.random.normal leaves it."""
    got_x1, got_x2 = [], []
    while n_pairs > 0:
        u = np.random.random_sample(2 * n_pairs)
        x1 = 2.0 * u[0::2] - 1.0
        x2 = 2.0 * u[1::2] - 1.0
        r2 = x1 * x1 + x2 * x2
        ok = (r2 < 1.0) & (r2 != 0.0)
        # The fused and unfused sums can only disagree on acceptance right
        # at the boundaries; decide those few cases with the exact value.
        for j in np.flatnonzero((np.abs(r2 - 1.0) < 1e-12) | (r2 < 1e-300)):
            exact = _sum_of_squares(float(x1[j]), float(x2[j]))
            ok[j] = exact < 1.0 and exact != 0.0
        got_x1.append(x1[ok])
        got_x2.append(x2[ok])
        n_pairs -= int(ok.sum())
    if not got_x1:
        return np.empty(0), np.empty(0)
    return np.concatenate(got_x1), np.concatenate(got_x2)


def legacy_normal(scale: float, shape, needed: np.ndarray) -> np.ndarray:
    """Equivalent of `np.random.normal(0.0, scale, shape)` on the arm64
    build, evaluated where `needed` is True (0.0 elsewhere)."""
    n = int(np.prod(shape))
    need = np.asarray(needed, dtype=bool).reshape(-1)
    out = np.zeros(n)
    if n == 0:
        return out.reshape(shape)

    state = np.random.get_state()
    has_gauss, cached = bool(state[3]), float(state[4])
    first = 0
    if has_gauss:
        out[0] = cached
        first = 1
    remaining = n - first
    n_pairs = (remaining + 1) // 2

    x1, x2 = _accepted_pairs(n_pairs)

    # Pair k yields f*x2 at position first+2k and f*x1 at first+2k+1; when
    # `remaining` is odd the last pair's f*x1 becomes the cached value.
    pos_a = first + 2 * np.arange(n_pairs)
    pos_b = pos_a + 1
    use_a = need[pos_a]
    use_b = np.zeros(n_pairs, dtype=bool)
    in_range = pos_b < n
    use_b[in_range] = need[pos_b[in_range]]
    keeps_cache = n_pairs > 0 and not in_range[-1]
    wanted = use_a | use_b
    if keeps_cache:
        wanted[-1] = True

    # r2 and the logarithm one value at a time (fused sum, C library log);
    # sqrt, division and products are exact IEEE operations, so numpy's
    # vectorised versions give the same bits.
    k = np.flatnonzero(wanted)
    a, b = x1[k], x2[k]
    r2 = np.array([_sum_of_squares(p, q) for p, q in zip(a.tolist(), b.tolist())])
    logs = np.array([math.log(v) for v in r2.tolist()])
    f = np.sqrt(-2.0 * logs / r2)
    take_a, take_b = use_a[k], use_b[k]
    out[pos_a[k[take_a]]] = (f * b)[take_a]
    out[pos_b[k[take_b]]] = (f * a)[take_b]
    leftover = float(f[-1] * a[-1]) if keeps_cache else None

    if has_gauss and not need[0]:
        out[0] = 0.0
    out *= scale  # loc 0.0 + scale * gauss, as numpy's legacy normal

    # The cached second value, as numpy leaves it (only touched when it changes).
    if leftover is not None or has_gauss:
        new_state = np.random.get_state()
        np.random.set_state(new_state[:3] + ((1, leftover) if leftover is not None else (0, 0.0)))
    return out.reshape(shape)
