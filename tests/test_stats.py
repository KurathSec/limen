"""Stdlib statistical primitives: tau-b with ties, Spearman midranks."""

from fractions import Fraction

import pytest

from limen.stats import kendall_tau_b, midranks, quantile_lower, spearman_midrank


def test_tau_b_perfect_agreement_and_reversal() -> None:
    x = {"a": Fraction(3), "b": Fraction(2), "c": Fraction(1)}
    y_same = dict(x)
    y_rev = {"a": Fraction(1), "b": Fraction(2), "c": Fraction(3)}
    assert kendall_tau_b(x, y_same)[0] == 1.0
    assert kendall_tau_b(x, y_rev)[0] == -1.0


def test_tau_b_with_tie_group_hand_computed() -> None:
    # x: a=b > c > d (tie group of 2); y: a > b > c > d
    x = {"a": Fraction(3), "b": Fraction(3), "c": Fraction(2), "d": Fraction(1)}
    y = {"a": Fraction(4), "b": Fraction(3), "c": Fraction(2), "d": Fraction(1)}
    tau_b, tau_a, conc, disc, ties_x, ties_y = kendall_tau_b(x, y)
    # pairs: 6 total; (a,b) tied in x; other 5 concordant
    assert (conc, disc, ties_x, ties_y) == (5, 0, 1, 0)
    assert tau_a == pytest.approx(5 / 6)
    assert tau_b == pytest.approx(5 / (30**0.5))  # (C-D)/sqrt((6-1)*(6-0))


def test_tau_b_undefined_when_fully_tied() -> None:
    x = {"a": Fraction(1), "b": Fraction(1)}
    y = {"a": Fraction(2), "b": Fraction(1)}
    tau_b, tau_a, *_ = kendall_tau_b(x, y)
    assert tau_b is None
    assert tau_a == 0.0


def test_midranks_ties() -> None:
    assert midranks([10.0, 20.0, 20.0, 30.0]) == [1.0, 2.5, 2.5, 4.0]


def test_spearman_shortcut_would_be_wrong_under_ties() -> None:
    # with ties, midrank Pearson is the defined value
    xs = [1.0, 2.0, 3.0, 4.0]
    ys = [1.0, 2.0, 2.0, 3.0]
    rho = spearman_midrank(xs, ys)
    assert rho == pytest.approx(0.9486832980505138, abs=1e-9)


def test_spearman_zero_variance_none() -> None:
    assert spearman_midrank([1.0, 2.0, 3.0], [5.0, 5.0, 5.0]) is None


def test_quantile_lower_interpolation() -> None:
    xs = [1.0, 2.0, 3.0, 4.0]
    assert quantile_lower(xs, 0.5) == 2.0
    assert quantile_lower(xs, 0.75) == 3.0
    assert quantile_lower(xs, 1.0) == 4.0
