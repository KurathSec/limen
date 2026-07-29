"""Drift guard tri-state truth table (LMN-DRF-001/002)."""

import pytest
from conftest import archive_from_grid

from limen.drift import drift_guard, exchangeable_fpr

# flips spread over different draws so no single draw carries a majority
GRID_CLEAN = {
    "a": {
        "i1": [1, 0, 1, 1],
        "i2": [1, 1, 1, 1],
        "i3": [0, 0, 1, 0],
        "i4": [0, 0, 0, 0],
    }
}


def test_all_fields_missing_is_unavailable_never_pass() -> None:
    guard = drift_guard(archive_from_grid(GRID_CLEAN), "a", "t")
    assert guard["state"] == "UNAVAILABLE"
    assert guard["basis"] is None
    for check in guard["subchecks"].values():
        assert check["state"] == "UNAVAILABLE"


def test_clean_time_basis_passes() -> None:
    archive = archive_from_grid(GRID_CLEAN, with_timestamps=True, with_versions=True)
    guard = drift_guard(archive, "a", "t")
    assert guard["state"] == "PASS"
    assert guard["basis"] == "collected_at"
    assert guard["subchecks"]["version_constancy"]["versions"] == ["v1"]


def test_version_change_fails() -> None:
    archive = archive_from_grid(
        GRID_CLEAN, with_timestamps=True, version_by_draw={2: "v2", 3: "v2"}
    )
    guard = drift_guard(archive, "a", "t")
    assert guard["subchecks"]["version_constancy"]["state"] == "FAIL"
    assert guard["state"] == "FAIL"


def test_single_draw_corruption_fails_lodo() -> None:
    # draw 3 flips every otherwise-constant item: it carries all the mixedness
    grid = {
        "a": {
            f"i{j}": [1, 1, 1, 0] for j in range(6)
        }
    }
    archive = archive_from_grid(grid, with_timestamps=True, with_versions=True)
    guard = drift_guard(archive, "a", "t")
    lodo = guard["subchecks"]["lodo"]
    assert lodo["state"] == "FAIL"
    assert lodo["max_carried"] == 6
    assert lodo["n_mixed"] == 6


def test_monotone_drift_fails_trend() -> None:
    # flip participation strictly increasing with draw index
    grid = {
        "a": {
            "i1": [0, 1, 1, 1, 1, 1, 1, 1],
            "i2": [0, 0, 1, 1, 1, 1, 1, 1],
            "i3": [0, 0, 0, 1, 1, 1, 1, 1],
            "i4": [0, 0, 0, 0, 1, 1, 1, 1],
        }
    }
    archive = archive_from_grid(grid, with_timestamps=True, with_versions=True)
    guard = drift_guard(archive, "a", "t")
    trend = guard["subchecks"]["trend"]
    assert trend["state"] == "FAIL"
    assert abs(trend["rho"]) > 0.8


def test_proxy_mode_clean_is_unavailable() -> None:
    archive = archive_from_grid(GRID_CLEAN)
    guard = drift_guard(archive, "a", "t", assume_index_is_collection_order=True)
    assert guard["basis"] == "draw_position"
    assert guard["state"] == "UNAVAILABLE"
    assert guard["subchecks"]["lodo"]["state"] == "UNAVAILABLE"
    assert guard["subchecks"]["lodo"]["clean"] is True
    assert guard["proxy_disclaimer"] is not None


def test_proxy_mode_can_still_fail() -> None:
    grid = {"a": {f"i{j}": [1, 1, 1, 0] for j in range(6)}}
    guard = drift_guard(
        archive_from_grid(grid), "a", "t", assume_index_is_collection_order=True
    )
    assert guard["subchecks"]["lodo"]["state"] == "FAIL"
    assert guard["state"] == "FAIL"


def test_trend_unavailable_below_k4() -> None:
    archive = archive_from_grid(
        {"a": {"i1": [1, 0, 1], "i2": [1, 1, 0]}}, with_timestamps=True, with_versions=True
    )
    guard = drift_guard(archive, "a", "t")
    assert guard["subchecks"]["trend"]["state"] == "UNAVAILABLE"
    assert guard["subchecks"]["lodo"]["state"] == "PASS"
    assert guard["state"] == "UNAVAILABLE"  # trend unavailable dominates PASS


def test_vacuous_lodo_no_mixed_items() -> None:
    archive = archive_from_grid(
        {"a": {"i1": [1, 1, 1, 1], "i2": [0, 0, 0, 0]}},
        with_timestamps=True,
        with_versions=True,
    )
    guard = drift_guard(archive, "a", "t")
    lodo = guard["subchecks"]["lodo"]
    assert lodo["state"] == "PASS"
    assert lodo["vacuous"] is True
    # trend: zero variance in participation -> clean PASS with rho null
    assert guard["subchecks"]["trend"]["rho"] is None
    assert guard["state"] == "PASS"


def test_exchangeable_fpr_exact_at_k4() -> None:
    # 24 orderings; only perfect monotone (2) exceed |rho| > 0.8
    assert exchangeable_fpr(4) == pytest.approx(2 / 24)
    assert exchangeable_fpr(3) is None
    assert exchangeable_fpr(9) is None
