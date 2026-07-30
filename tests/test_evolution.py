"""Document-diff classification (LMN-EMIT-008): adding is cheap, changing is not."""

import copy
import json
from pathlib import Path

from limen.evolution import compare_documents, spec_moved_minor_or_more
from limen.report import ReportOptions, build_report
from limen.synth import PlantedConfig, generate

FROZEN = Path(__file__).parent / "data" / "frozen_v1" / "report.json"


def _doc() -> dict:
    return {
        "limen_schema": "report/v1",
        "spec_version": "0.2.0",
        "content_hash": "sha256:abc",
        "n": {"cells": 4, "models": ["a", "b"]},
        "rulings": {"mt": [{"ruling_id": "X-1", "value": 0.5, "content_hash": "sha256:d"}]},
    }


def test_identical() -> None:
    assert compare_documents(_doc(), _doc()).classification == "identical"


def test_stamp_only() -> None:
    other = _doc()
    other["spec_version"] = "0.3.0"
    other["content_hash"] = "sha256:different"
    diff = compare_documents(_doc(), other)
    assert diff.classification == "stamp_only"


def test_additive_records_paths() -> None:
    other = _doc()
    other["spec_version"] = "0.3.0"
    other["rulings"]["mt"][0]["new_section"] = {"x": 1}
    other["extra_top"] = True
    diff = compare_documents(_doc(), other)
    assert diff.classification == "additive"
    assert "extra_top" in diff.added_paths
    assert "rulings.mt[0].new_section" in diff.added_paths


def test_changed_float_is_changed() -> None:
    other = _doc()
    other["rulings"]["mt"][0]["value"] = 0.500001
    diff = compare_documents(_doc(), other)
    assert diff.classification == "changed"
    assert any("value" in v for v in diff.violations)


def test_removed_key_is_changed() -> None:
    other = _doc()
    del other["n"]["cells"]
    assert compare_documents(_doc(), other).classification == "changed"


def test_array_reorder_is_changed() -> None:
    other = _doc()
    other["n"]["models"] = ["b", "a"]
    assert compare_documents(_doc(), other).classification == "changed"


def test_array_append_is_changed() -> None:
    other = _doc()
    other["n"]["models"] = ["a", "b", "c"]
    assert compare_documents(_doc(), other).classification == "changed"


def test_int_vs_float_is_changed() -> None:
    committed = _doc()
    committed["n"]["cells"] = 0
    other = copy.deepcopy(committed)
    other["n"]["cells"] = 0.0
    assert compare_documents(committed, other).classification == "changed"


def test_content_hashes_stripped_at_depth() -> None:
    other = _doc()
    other["rulings"]["mt"][0]["content_hash"] = "sha256:moved"
    assert compare_documents(_doc(), other).classification == "identical"


def test_spec_movement_rules() -> None:
    assert spec_moved_minor_or_more("0.2.0", "0.3.0")
    assert spec_moved_minor_or_more("0.2.0", "1.0.0")
    assert not spec_moved_minor_or_more("0.2.0", "0.2.9")
    assert not spec_moved_minor_or_more("1.0.0", "0.9.0")


def test_frozen_v1_vs_current_build_is_at_most_additive() -> None:
    """The migration pin: rebuilding the frozen config on current code may only
    ADD relative to the genuine v1 bytes captured from the 0.1.x tree — with
    exactly one sanctioned exception, the scope-code list growing (a spec-MAJOR
    event this release), where the old codes must be a strict prefix."""
    committed = json.loads(FROZEN.read_text(encoding="utf-8"))
    cfg = PlantedConfig(
        n_items=60, k=8, models=("frozen-a", "frozen-b", "frozen-c"),
        mu=(0.7, 0.65, 0.5), flaky_fraction=0.15, defect_items=2,
    )
    archive, _ = generate(cfg, seed=1234)
    regenerated = build_report(
        archive, rulings_version="frozen", options=ReportOptions(replicates=50)
    )
    old_codes = committed["scope"]["does_not_show"]
    new_codes = regenerated["scope"]["does_not_show"]
    assert new_codes[: len(old_codes)] == old_codes  # strict prefix, nothing reworded
    committed_stripped = {k: v for k, v in committed.items() if k != "scope"}
    regenerated_stripped = {k: v for k, v in regenerated.items() if k != "scope"}
    diff = compare_documents(committed_stripped, regenerated_stripped)
    assert diff.classification in ("identical", "stamp_only", "additive"), diff.violations
    assert diff.added_paths  # v2 did add sections
