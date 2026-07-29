"""Grader-defect counting (LMN-GRD-001/002)."""

from conftest import archive_from_grid

from limen.graderdefect import grader_defects
from limen.model import VerdictRow, build_archive


def _rows(hashes_verdicts: list[tuple[str, int]], item: str = "i1") -> list[VerdictRow]:
    return [
        VerdictRow(
            model="a",
            task="t",
            item_id=item,
            draw_id=str(d),
            verdict=v,
            raw_sha256=h,
        )
        for d, (h, v) in enumerate(hashes_verdicts)
    ]


def test_no_hashes_is_unavailable_not_zero() -> None:
    archive = archive_from_grid({"a": {"i1": [1, 0]}})
    result = grader_defects(archive, "a", "t")
    assert result["state"] == "UNAVAILABLE"
    assert result["defect_pairs"] is None


def test_identical_bytes_differing_verdicts_counted() -> None:
    # three identical texts with verdicts (1,1,0) -> 2 defect pairs, 1 defect item
    archive = build_archive(_rows([("h1", 1), ("h1", 1), ("h1", 0)]))
    result = grader_defects(archive, "a", "t")
    assert result["defect_pairs"]["count"] == 2
    assert result["defect_pairs"]["denominator"] == 2  # s(k-s) = 2*1
    assert result["defect_items"] == {"count": 1, "denominator": 1, "rate": 1.0}
    assert result["mean_flakiness_excluding_detected_defects"] == 0.0


def test_differing_bytes_not_counted() -> None:
    archive = build_archive(_rows([("h1", 1), ("h2", 0)]))
    result = grader_defects(archive, "a", "t")
    assert result["defect_pairs"]["count"] == 0
    assert result["defect_pairs"]["denominator"] == 1


def test_identical_bytes_identical_verdicts_not_counted() -> None:
    archive = build_archive(_rows([("h1", 1), ("h1", 1)]))
    result = grader_defects(archive, "a", "t")
    assert result["defect_pairs"]["count"] == 0
    assert result["defect_items"]["denominator"] == 0  # no mixed items
