"""Noise floor and MDD (LMN-NSE-001)."""

import pytest

from limen.noise import draw_spread, mdd_pair
from limen.stats import t_quantile_975


def test_t_table_lookups() -> None:
    assert t_quantile_975(1) == 12.7062
    assert t_quantile_975(7) == 2.36462
    assert t_quantile_975(35) == t_quantile_975(30)  # conservative floor
    assert t_quantile_975(1000) == 1.97993  # floor at df=120, never the normal quantile
    with pytest.raises(ValueError):
        t_quantile_975(0)


def test_draw_spread_k2() -> None:
    spread = draw_spread([0.5, 0.7])
    assert spread["score_range"] == pytest.approx(0.2)
    assert spread["score_sd"] == pytest.approx(abs(0.7 - 0.5) / 2**0.5, abs=1e-6)


def test_mdd_formula_and_flags() -> None:
    mdd = mdd_pair(0.01, 0.02, 8, 1500)
    expected = 2.36462 * ((0.0001 + 0.0004) / 8) ** 0.5
    assert mdd["value"] == pytest.approx(expected, abs=1e-6)
    assert mdd["df"] == 7
    assert mdd["low_k"] is False
    assert mdd["degenerate_zero_spread"] is False
    assert mdd["score_resolution"] == pytest.approx(1 / 1500, abs=1e-6)
    assert len(mdd["assumptions"]) == 5
    assert "Kalibera" in mdd["citation"]


def test_mdd_low_k_and_degenerate() -> None:
    low = mdd_pair(0.01, 0.01, 2, 100)
    assert low["low_k"] is True
    assert low["t"] == 12.7062
    degenerate = mdd_pair(0.0, 0.0, 8, 100)
    assert degenerate["value"] == 0.0
    assert degenerate["degenerate_zero_spread"] is True
