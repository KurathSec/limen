"""Variance components (LMN-VAR-001/002/006): exact EMS algebra, honest edges."""

import math
from fractions import Fraction

import pytest
from conftest import archive_from_grid

from limen.ranking import draw_scores, single_draw_score_list
from limen.stats import sample_sd
from limen.varcomp import (
    DRAW_LEVELS_FLOOR,
    bootstrap_components,
    design_effect,
    mean_squares,
    mt_variance_components,
    raw_components,
    task_variance_components,
    two_facet_sums,
)


def test_ems_hand_computed_2x2() -> None:
    # items: (1,0) and (1,1); T=3, s=(1,2), t=(2,1)
    ms = mean_squares(*two_facet_sums([(1, 0), (1, 1)]))
    # correction 9/4; SS_tot = 3-9/4 = 3/4; SS_item = 5/2-9/4 = 1/4;
    # SS_draw = 5/2-9/4 = 1/4; SS_res = 1/4; all df = 1
    assert ms == (Fraction(1, 4), Fraction(1, 4), Fraction(1, 4))
    raw = raw_components(ms, 2, 2)
    assert raw == (Fraction(0), Fraction(0), Fraction(1, 4))


def test_ems_hand_computed_3x4() -> None:
    rows = [(1, 1, 1, 1), (0, 0, 0, 0), (1, 0, 1, 0)]
    n, k, total, ssi, ssd = two_facet_sums(rows)
    assert (n, k, total) == (3, 4, 6)
    ms = mean_squares(n, k, total, ssi, ssd)
    # by hand: correction 3; SS_tot=3; SS_item=(16+0+4)/4-3=2; SS_draw=(4+1+4+1)/3-3=1/3
    # SS_res = 3-2-1/3 = 2/3; df: 2, 3, 6
    assert ms[0] == Fraction(2, 2)
    assert ms[1] == Fraction(1, 9)
    assert ms[2] == Fraction(2, 3) / 6


def test_score_sd_squared_equals_ms_draw_over_n() -> None:
    """The shipped noise_floor.score_sd is MS_draw/n in disguise (exact)."""
    grid = {
        "a": {"i1": [1, 0, 1, 1], "i2": [1, 1, 0, 1], "i3": [0, 0, 1, 0], "i4": [1, 1, 1, 1]},
        "b": {"i1": [0, 1, 0, 0], "i2": [1, 0, 1, 1], "i3": [0, 1, 0, 0], "i4": [1, 1, 0, 1]},
    }
    archive = archive_from_grid(grid)
    ds = draw_scores(archive, "t")
    for model in ds.models:
        rows = [archive.cell(model, "t", i).verdicts for i in ds.items]
        ms = mean_squares(*two_facet_sums(list(rows)))
        sd = sample_sd(single_draw_score_list(ds, model))
        assert sd**2 == pytest.approx(float(ms[1]) / len(ds.items), abs=1e-12)


def test_deterministic_mixed_rates_deff_equals_k() -> None:
    """Constant rows with differing rates: draw = residual = 0, deff = k, n_eff = n."""
    rows = [(1, 1, 1, 1)] * 3 + [(0, 0, 0, 0)] * 2
    ms = mean_squares(*two_facet_sums(rows))
    raw = raw_components(ms, 5, 4)
    assert raw[1] == 0 and raw[2] == 0 and raw[0] > 0
    deff, n_eff = design_effect(float(raw[0]), 0.0, 0.0, 5, 4)
    assert deff == pytest.approx(4.0)
    assert n_eff == pytest.approx(5.0)


def test_all_constant_archive_degenerate() -> None:
    archive = archive_from_grid({"a": {"i1": [1, 1], "i2": [1, 1]}})
    block = mt_variance_components(archive, "a", "t", rulings_version="v", replicates=10)
    assert block["state"] == "AVAILABLE"
    assert block["degenerate_all_constant"] is True
    assert block["shares"]["item"] is None
    assert block["design_effect"]["deff"] is None


def test_negative_draw_component_truncated_with_raw() -> None:
    # alternating pattern makes draws balanced but items mixed: MS_draw < MS_res
    rows = [(1, 0), (0, 1), (1, 0), (0, 1)]
    ms = mean_squares(*two_facet_sums(rows))
    raw = raw_components(ms, 4, 2)
    assert raw[0] < 0  # item component negative here too (all items 50%)
    archive = archive_from_grid(
        {"a": {"i1": [1, 0], "i2": [0, 1], "i3": [1, 0], "i4": [0, 1]}}
    )
    block = mt_variance_components(archive, "a", "t", rulings_version="v", replicates=10)
    item = block["components"]["item"]
    assert item["truncated"] is True
    assert item["raw"] < 0
    assert item["estimate"] == 0.0


def test_unavailable_states() -> None:
    single = archive_from_grid({"a": {"i1": [1, 0]}})
    block = mt_variance_components(single, "a", "t", rulings_version="v", replicates=5)
    assert block["state"] == "UNAVAILABLE"
    assert "n_items >= 2" in block["reason"]
    assert "bucket" in block["bucket_note"]  # limits travel even when unavailable
    ragged = archive_from_grid({"a": {"i1": [1, 0], "i2": [1, 0, 1]}})
    block = mt_variance_components(ragged, "a", "t", rulings_version="v", replicates=5)
    assert block["state"] == "UNAVAILABLE"
    assert "ragged" in block["reason"]


def test_low_k_warning_always_below_floor() -> None:
    archive = archive_from_grid({"a": {"i1": [1, 0] * 4, "i2": [1, 1] * 4}})
    block = mt_variance_components(archive, "a", "t", rulings_version="v", replicates=5)
    assert block["k"] == 8 < DRAW_LEVELS_FLOOR
    assert block["low_draw_levels"] is True
    assert block["low_k_note"] is not None


def test_bootstrap_deterministic_and_bounded() -> None:
    rows = [(1, 0, 1, 1), (0, 1, 0, 0), (1, 1, 1, 0), (0, 0, 1, 1)]
    kwargs = dict(seed_parts=("v", "t", "m", "varcomp-bootstrap"), replicates=50)
    b1 = bootstrap_components(rows, **kwargs)
    b2 = bootstrap_components(rows, **kwargs)
    assert b1 == b2
    for block in b1.values():
        assert 0.0 <= block["boot_share_truncated"] <= 1.0
        assert block["ci95"]["lo"] <= block["ci95"]["hi"]


def test_deff_two_forms_agree() -> None:
    item, draw, residual, n, k = 0.02, 0.001, 0.15, 200, 8
    deff, _ = design_effect(item, draw, residual, n, k)
    total = item + draw + residual
    kish = 1 + (k - 1) * (item / total) + (n - 1) * (draw / total)
    assert deff == pytest.approx(kish, abs=1e-12)
    assert 1.0 <= deff <= n * k


def test_task_level_model_facet_descriptive() -> None:
    grid = {
        "a": {"i1": [1, 1, 1, 1], "i2": [1, 0, 1, 1]},
        "b": {"i1": [0, 0, 1, 0], "i2": [0, 0, 0, 1]},
    }
    archive = archive_from_grid(grid)
    ds = draw_scores(archive, "t")
    block = task_variance_components(archive, "t", ds, rulings_version="v", replicates=10)
    assert block["state"] == "AVAILABLE"
    assert [e["model"] for e in block["per_model"]] == ["a", "b"]
    facet = block["model_facet"]
    assert facet["kind"] == "descriptive"
    scores = [7 / 8, 2 / 8]
    mean = sum(scores) / 2
    expected = sum((x - mean) ** 2 for x in scores)  # ddof=1 with 2 models
    assert facet["between_model_variance"] == pytest.approx(expected, abs=1e-6)
    assert facet["between_model_sd"] == pytest.approx(math.sqrt(expected), abs=1e-6)
    assert "never a quality ranking" in facet["note"]


def test_zero_replicates_rules_unavailable_not_null_intervals() -> None:
    # LMN-VAR-003: no component ships without its interval; replicates < 1
    # must refuse the whole section, never emit AVAILABLE with ci95 null
    archive = archive_from_grid({"a": {"i1": [1, 0, 1], "i2": [0, 0, 1]}})
    for replicates in (0, -5):
        block = mt_variance_components(
            archive, "a", "t", rulings_version="v", replicates=replicates
        )
        assert block["state"] == "UNAVAILABLE"
        assert "no bootstrap replicates" in block["reason"]
    from limen.ranking import draw_scores
    from limen.varcomp import task_variance_components

    two = archive_from_grid(
        {"a": {"i1": [1, 0, 1], "i2": [0, 0, 1]}, "b": {"i1": [1, 1, 1], "i2": [0, 1, 1]}}
    )
    ds = draw_scores(two, "t")
    task_block = task_variance_components(
        two, "t", ds, rulings_version="v", replicates=0
    )
    assert task_block["state"] == "UNAVAILABLE"
