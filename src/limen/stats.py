"""Stdlib-only statistical helpers.

Nothing here knows about verdicts or rulings; these are the shared numeric
primitives: sample moments, a hardcoded t-quantile table (scipy is deliberately
not a dependency), Kendall tau-b on exact rationals, and Spearman correlation
with midranks for ties.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from fractions import Fraction

# Two-sided 95% Student-t quantiles t_{0.975, df}. Source: standard tables
# (Abramowitz & Stegun / R qt(0.975, df)), 5-6 significant figures.
T_975: dict[int, float] = {
    1: 12.7062, 2: 4.30265, 3: 3.18245, 4: 2.77645, 5: 2.57058, 6: 2.44691,
    7: 2.36462, 8: 2.30600, 9: 2.26216, 10: 2.22814, 11: 2.20099, 12: 2.17881,
    13: 2.16037, 14: 2.14479, 15: 2.13145, 16: 2.11991, 17: 2.10982, 18: 2.10092,
    19: 2.09302, 20: 2.08596, 21: 2.07961, 22: 2.07387, 23: 2.06866, 24: 2.06390,
    25: 2.05954, 26: 2.05553, 27: 2.05183, 28: 2.04841, 29: 2.04523, 30: 2.04227,
    40: 2.02108, 60: 2.00030, 120: 1.97993,
}
def t_quantile_975(df: int) -> float:
    """t_{0.975, df}; for untabulated df use the largest tabulated df <= df (larger t,
    conservative). df >= 1 required. Above df=120 the value stays at T_975[120] —
    still conservative; the normal quantile is deliberately not used, so the floor
    rule holds for every finite df."""
    if df < 1:
        raise ValueError(f"t quantile needs df >= 1, got {df}")
    if df in T_975:
        return T_975[df]
    return T_975[max(d for d in T_975 if d <= df)]


def mean(xs: Sequence[float]) -> float:
    if not xs:
        raise ValueError("mean of empty sequence")
    return sum(xs) / len(xs)


def sample_sd(xs: Sequence[float]) -> float:
    """Sample standard deviation, ddof=1. Needs len >= 2."""
    n = len(xs)
    if n < 2:
        raise ValueError("sample sd needs at least 2 observations")
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def quantile_lower(sorted_xs: Sequence[float], p: float) -> float:
    """Deterministic 'lower interpolation' quantile: sorted values, index ceil(p*n)-1."""
    n = len(sorted_xs)
    if n == 0:
        raise ValueError("quantile of empty sequence")
    if not 0.0 < p <= 1.0:
        raise ValueError(f"p must be in (0, 1], got {p}")
    return sorted_xs[max(0, math.ceil(p * n) - 1)]


def sign(x: int) -> int:
    """Sign of an integer: -1, 0, or +1. Signs in limen are computed on integers only."""
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


def kendall_tau_b(
    scores_x: dict[str, Fraction], scores_y: dict[str, Fraction]
) -> tuple[float | None, float, int, int, int, int]:
    """Kendall tau-b between two rankings of the same keys, exact-rational ties.

    Returns ``(tau_b, tau_a, C, D, n1, n2)`` where C/D are concordant/discordant
    pair counts and n1/n2 the tie corrections; tau_b is None (undefined) when a
    ranking is entirely tied.
    """
    if set(scores_x) != set(scores_y):
        raise ValueError("rankings must cover identical key sets")
    keys = sorted(scores_x)
    n = len(keys)
    n0 = n * (n - 1) // 2
    if n0 == 0:
        raise ValueError("tau needs at least 2 keys")
    concordant = discordant = 0
    ties_x = ties_y = 0
    for i in range(n):
        for j in range(i + 1, n):
            dx = scores_x[keys[i]] - scores_x[keys[j]]
            dy = scores_y[keys[i]] - scores_y[keys[j]]
            if dx == 0:
                ties_x += 1
            if dy == 0:
                ties_y += 1
            prod = (1 if dx > 0 else -1 if dx < 0 else 0) * (
                1 if dy > 0 else -1 if dy < 0 else 0
            )
            if prod > 0:
                concordant += 1
            elif prod < 0:
                discordant += 1
    tau_a = (concordant - discordant) / n0
    denom = math.sqrt((n0 - ties_x) * (n0 - ties_y))
    tau_b = None if denom == 0 else (concordant - discordant) / denom
    return tau_b, tau_a, concordant, discordant, ties_x, ties_y


def midranks(xs: Sequence[float]) -> list[float]:
    """Ranks 1..n with tied values receiving the mean of their rank range."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j + 2) / 2  # ranks are 1-based: positions i..j -> ranks i+1..j+1
        for pos in range(i, j + 1):
            ranks[order[pos]] = avg
        i = j + 1
    return ranks


def spearman_midrank(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Spearman rho as Pearson correlation on midranks; None when either side has
    zero rank variance. The 1 - 6*sum(d^2)/... shortcut is wrong under ties and is
    deliberately not used."""
    if len(xs) != len(ys):
        raise ValueError("sequences must have equal length")
    if len(xs) < 2:
        raise ValueError("spearman needs at least 2 observations")
    rx = midranks(xs)
    ry = midranks(ys)
    mx = mean(rx)
    my = mean(ry)
    sxx = sum((r - mx) ** 2 for r in rx)
    syy = sum((r - my) ** 2 for r in ry)
    if sxx == 0 or syy == 0:
        return None
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    return sxy / math.sqrt(sxx * syy)


def normal_cdf(x: float) -> float:
    """Phi(x) via math.erf; used by synth's closed-form expectations only."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
