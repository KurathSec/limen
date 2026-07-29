"""Gate semantics: exit-code matrix, direction assertion, UNAVAILABLE handling."""

import pytest
from conftest import archive_from_grid

from limen.errors import GateError
from limen.gate import GateOptions, evaluate_gate
from limen.report import ReportOptions, build_report


def _report(grid, **grid_kwargs):
    archive = archive_from_grid(grid, **grid_kwargs)
    return build_report(archive, rulings_version="g", options=ReportOptions(replicates=10))


STABLE_GRID = {
    # a beats b every draw; both models have spread so the MDD is nonzero
    "a": {"i1": [1, 1, 1, 1], "i2": [1, 1, 1, 0], "i3": [1, 0, 1, 1], "i4": [1, 1, 1, 1]},
    "b": {"i1": [0, 0, 0, 0], "i2": [1, 0, 0, 1], "i3": [0, 0, 0, 0], "i4": [0, 1, 0, 0]},
}

FLIP_GRID = {
    "a": {"i1": [1, 0], "i2": [1, 0], "i3": [1, 0]},
    "b": {"i1": [0, 1], "i2": [0, 1], "i3": [0, 0]},
}

TIE_GRID = {
    "a": {"i1": [1, 0], "i2": [0, 1]},
    "b": {"i1": [0, 1], "i2": [1, 0]},
}


def test_pass_exit_zero() -> None:
    result = evaluate_gate(
        _report(STABLE_GRID),
        GateOptions(require_sign_stable=True, min_effect_vs_noise=1.0),
    )
    assert result.exit_code == 0
    assert result.pair_verdicts[0].verdict == "PASS"


def test_flip_fails_exit_one_with_quality_note() -> None:
    result = evaluate_gate(_report(FLIP_GRID), GateOptions(require_sign_stable=True))
    assert result.exit_code == 1
    assert any("never 'the other model wins'" in line for line in result.lines)


def test_pooled_tie_fails_both_checks() -> None:
    report = _report(TIE_GRID)
    r1 = evaluate_gate(report, GateOptions(require_sign_stable=True))
    r2 = evaluate_gate(report, GateOptions(min_effect_vs_noise=1.0))
    assert r1.exit_code == 1
    assert r2.exit_code == 1


def test_drift_unavailable_gives_exit_two() -> None:
    result = evaluate_gate(_report(STABLE_GRID), GateOptions(require_drift_pass=True))
    assert result.exit_code == 2
    assert result.pair_verdicts[0].verdict == "UNEVALUABLE"


def test_fail_outranks_unevaluable() -> None:
    result = evaluate_gate(
        _report(FLIP_GRID),
        GateOptions(require_sign_stable=True, require_drift_pass=True),
    )
    assert result.exit_code == 1


def test_direction_assertion_contradiction() -> None:
    result = evaluate_gate(
        _report(STABLE_GRID),
        GateOptions(pairs=("t:b>a",)),  # b does not beat a
    )
    assert result.exit_code == 1
    assert any("claim_contradicts_pooled_data" in d for v in result.pair_verdicts for _, _, d in v.checks)


def test_direction_assertion_match_passes() -> None:
    result = evaluate_gate(_report(STABLE_GRID), GateOptions(pairs=("t:a>b",)))
    assert result.exit_code == 0


def test_missing_pair_spec_exit_two() -> None:
    result = evaluate_gate(_report(STABLE_GRID), GateOptions(pairs=("t:a>zebra",)))
    assert result.exit_code == 2


def test_bad_pair_spec_raises() -> None:
    with pytest.raises(GateError, match="task:modelA>modelB"):
        evaluate_gate(_report(STABLE_GRID), GateOptions(pairs=("nonsense",)))


def test_grader_defect_check_unavailable_without_hashes() -> None:
    result = evaluate_gate(
        _report(STABLE_GRID), GateOptions(max_grader_defect_share=0.0)
    )
    assert result.exit_code == 2


def test_grader_defect_check_passes_with_clean_hashes() -> None:
    result = evaluate_gate(
        _report(STABLE_GRID, with_hashes=True),
        GateOptions(max_grader_defect_share=0.0),
    )
    assert result.exit_code == 0


def test_not_a_report_raises() -> None:
    with pytest.raises(GateError, match="report/v1"):
        evaluate_gate({"limen_schema": "nope"}, GateOptions())
