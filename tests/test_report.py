"""Report assembly: byte determinism, scope block, confound stamping (LMN-EMIT-*)."""

import pytest
from conftest import archive_from_grid

from limen.canonical import canonical_json
from limen.errors import ReportError
from limen.report import ReportOptions, build_report

GRID = {
    "a": {"i1": [1, 0, 1, 1], "i2": [1, 1, 1, 1], "i3": [0, 0, 0, 0]},
    "b": {"i1": [0, 1, 1, 0], "i2": [1, 1, 0, 1], "i3": [0, 0, 0, 0]},
}


def _report(**kwargs):
    archive = archive_from_grid(GRID, **kwargs)
    return build_report(
        archive, rulings_version="test", options=ReportOptions(replicates=20)
    )


def test_regeneration_is_byte_identical() -> None:
    assert canonical_json(_report()) == canonical_json(_report())


def test_scope_block_present_with_all_codes() -> None:
    report = _report()
    codes = {item["code"] for item in report["scope"]["does_not_show"]}
    assert "NO_MODEL_QUALITY_CLAIM" in codes
    assert "STABLE_SUBSET_IS_A_VIEW" in codes
    assert "EXACT_MATCH_GRADING_ONLY" in codes
    assert "STABILITY_THRESHOLD_IS_CRUDE" in codes
    assert "NO_SATURATION_MECHANISM_CLAIM" in codes
    assert len(codes) == 11


def test_variance_components_present_and_subordinated() -> None:
    # LMN-EMIT-007: report/v2 carries the section under the LMN-VAR guardrails
    report = _report()
    for mt in report["rulings"]["mt"]:
        section = mt["variance_components"]
        assert section["state"] in ("AVAILABLE", "UNAVAILABLE")
        assert "never_headline_note" in section
        assert "bucket_note" in section
        if section["state"] == "AVAILABLE":
            assert section["low_draw_levels"] is True  # k=4 in the test grid
            for component in section["components"].values():
                assert "ci95" in component and "raw" in component


def test_ruling_ids_deterministic_and_ordered() -> None:
    report = _report()
    mt_ids = [b["ruling_id"] for b in report["rulings"]["mt"]]
    assert mt_ids == ["LIMEN-test-MT-0001", "LIMEN-test-MT-0002"]
    pair_ids = [b["ruling_id"] for b in report["rulings"]["pair"]]
    assert pair_ids == ["LIMEN-test-PAIR-0001"]


def test_content_hash_self_consistent() -> None:
    from limen.canonical import content_hash

    report = _report()
    for body in report["rulings"]["mt"]:
        assert content_hash(body) == body["content_hash"]
    assert content_hash(report) == report["content_hash"]


def test_no_timestamp_or_version_in_body() -> None:
    text = canonical_json(_report())
    assert "generated_at" not in text
    assert "limen_version" not in text  # package version lives in provenance only
    assert '"path"' not in text


def test_confound_stamp_propagates_to_pair() -> None:
    report = _report(with_timestamps=True, version_by_draw={3: "v2"})
    pair = report["rulings"]["pair"][0]
    assert pair["confounded_by_version_change"] is True


def test_bad_rulings_version_refused() -> None:
    archive = archive_from_grid(GRID)
    with pytest.raises(ReportError, match="rulings_version"):
        build_report(archive, rulings_version="bad version!")


def test_drift_unavailable_never_pass_in_report() -> None:
    report = _report()  # no timestamps, no versions
    for mt in report["rulings"]["mt"]:
        assert mt["drift"]["state"] == "UNAVAILABLE"
