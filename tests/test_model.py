"""IR invariants: the table refuses bad input loudly (LMN-CORE-002/003/004)."""

import pytest
from conftest import archive_from_grid, rows_from_grid

from limen.errors import TableError
from limen.model import VerdictRow, build_archive


def test_grid_roundtrip() -> None:
    archive = archive_from_grid({"a": {"i1": [1, 0], "i2": [1, 1]}, "b": {"i1": [0, 0]}})
    assert archive.models == ("a", "b")
    assert archive.cell("a", "t", "i1").verdicts == (1, 0)
    assert archive.aligned_items("t") == ("i1",)
    assert archive.alignment_excluded("t") == {"a": 1, "b": 0}
    assert archive.common_k("t") == 2


def test_non_binary_verdict_refused() -> None:
    rows = [VerdictRow(model="a", task="t", item_id="i", draw_id="0", verdict=2)]
    with pytest.raises(TableError, match="verdict must be 0 or 1"):
        build_archive(rows)


def test_duplicate_key_refused() -> None:
    row = VerdictRow(model="a", task="t", item_id="i", draw_id="0", verdict=1)
    with pytest.raises(TableError, match="duplicate"):
        build_archive([row, row])


def test_low_k_cells_excluded_and_counted() -> None:
    rows = rows_from_grid({"a": {"i1": [1, 0], "i2": [1]}})
    archive = build_archive(rows)
    assert ("a", "t", "i1") in archive.cells
    assert ("a", "t", "i2") not in archive.cells
    assert archive.excluded_low_k == {("a", "t"): 1}


def test_nothing_left_refused() -> None:
    rows = rows_from_grid({"a": {"i1": [1]}})
    with pytest.raises(TableError, match="k >= 2"):
        build_archive(rows)


def test_partial_optional_field_refused() -> None:
    rows = [
        VerdictRow(model="a", task="t", item_id="i", draw_id="0", verdict=1, raw_sha256="x"),
        VerdictRow(model="a", task="t", item_id="i", draw_id="1", verdict=0),
    ]
    with pytest.raises(TableError, match="all-or-nothing"):
        build_archive(rows)


def test_numeric_draw_order() -> None:
    rows = [
        VerdictRow(model="a", task="t", item_id="i", draw_id="10", verdict=0),
        VerdictRow(model="a", task="t", item_id="i", draw_id="2", verdict=1),
    ]
    cell = build_archive(rows).cell("a", "t", "i")
    assert cell.draw_ids == ("2", "10")  # numeric, not lexicographic
    assert cell.verdicts == (1, 0)


def test_lexicographic_fallback_when_any_non_numeric() -> None:
    rows = [
        VerdictRow(model="a", task="t", item_id="i", draw_id="10", verdict=0),
        VerdictRow(model="a", task="t", item_id="i", draw_id="run-2", verdict=1),
    ]
    cell = build_archive(rows).cell("a", "t", "i")
    assert cell.draw_ids == ("10", "run-2")


def test_dataset_digest_stable_under_row_order() -> None:
    rows = rows_from_grid({"a": {"i1": [1, 0]}, "b": {"i1": [0, 1]}})
    d1 = build_archive(rows).dataset_digest()
    d2 = build_archive(list(reversed(rows))).dataset_digest()
    assert d1 == d2


def test_min_k_below_two_refused() -> None:
    with pytest.raises(TableError, match="min_k"):
        build_archive(rows_from_grid({"a": {"i": [1, 0]}}), min_k=1)
