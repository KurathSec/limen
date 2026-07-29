"""Flakiness U-statistic and TARa@N (LMN-FLK-001/002)."""

import pytest
from conftest import archive_from_grid

from limen.flakiness import (
    classify_item,
    item_flakiness,
    model_task_flakiness,
    task_pooled_flakiness,
)


def test_item_flakiness_exact_values() -> None:
    assert item_flakiness(0, 8) == 0.0
    assert item_flakiness(8, 8) == 0.0
    assert item_flakiness(1, 2) == 1.0
    assert item_flakiness(4, 8) == pytest.approx(4 / 7)


def test_item_flakiness_refusals() -> None:
    with pytest.raises(ValueError):
        item_flakiness(0, 1)
    with pytest.raises(ValueError):
        item_flakiness(9, 8)


def test_classification() -> None:
    assert classify_item((1, 1)) == "always_pass"
    assert classify_item((0, 0)) == "always_fail"
    assert classify_item((1, 0)) == "mixed"


def test_model_task_block_denominators() -> None:
    archive = archive_from_grid(
        {"a": {"i1": [1, 0, 1, 0], "i2": [1, 1, 1, 1], "i3": [0, 0, 0, 0]}}
    )
    block = model_task_flakiness(archive, "a", "t")
    assert block["mixed"] == {"count": 1, "denominator": 3, "rate": pytest.approx(1 / 3, abs=1e-6)}
    assert block["constant_verdict_fraction"] == pytest.approx(2 / 3, abs=1e-6)
    assert block["constant_verdict_n"] == 4
    assert "upper bound on TARa@N" in block["tara_upper_bound_note"]
    # i1: s=2,k=4 -> f = 2*2/6 = 2/3; mean over 3 items = 2/9
    assert block["mean_flakiness"] == pytest.approx(2 / 9, abs=1e-6)
    assert block["mean_flakiness_mixed_only"] == pytest.approx(2 / 3, abs=1e-6)
    assert block["pooled_pair_discordance"]["count"] == 4
    assert block["pooled_pair_discordance"]["denominator"] == 18


def test_no_mixed_gives_null_not_zero() -> None:
    archive = archive_from_grid({"a": {"i1": [1, 1], "i2": [0, 0]}})
    block = model_task_flakiness(archive, "a", "t")
    assert block["mean_flakiness_mixed_only"] is None
    assert block["mixed"]["count"] == 0


def test_ragged_k_nulls_tara_and_splits_pooled() -> None:
    archive = archive_from_grid({"a": {"i1": [1, 0], "i2": [1, 0, 0, 0]}})
    block = model_task_flakiness(archive, "a", "t")
    assert block["constant_verdict_fraction"] is None
    assert block["k_uniform"] is None
    # mean f: i1 f=1, i2 f=2*1*3/12=0.5 -> 0.75; pooled: (1+3)/(1+6)=4/7 — different
    assert block["mean_flakiness"] == pytest.approx(0.75)
    assert block["pooled_pair_discordance"]["rate"] == pytest.approx(4 / 7, abs=1e-6)


def test_task_pooled_uses_both_units() -> None:
    archive = archive_from_grid(
        {
            "a": {"i1": [1, 0], "i2": [1, 1]},
            "b": {"i1": [1, 1], "i2": [1, 1]},
        }
    )
    pooled = task_pooled_flakiness(archive, "t")
    assert pooled["cell_pooled_mixed"] == {"count": 1, "denominator": 4, "rate": 0.25}
    assert pooled["item_union_mixed"]["count"] == 1
    assert pooled["item_union_mixed"]["denominator"] == 2
