"""Regressions for the adversarial-review findings: each test pins one defect
that was confirmed against the pre-fix code and must never return."""

import json
from pathlib import Path

import pytest
from conftest import archive_from_grid, rows_from_grid

from limen.cli import main
from limen.drift import drift_guard
from limen.errors import GateError, TableError
from limen.gate import GateOptions, evaluate_gate
from limen.model import VerdictRow, build_archive
from limen.report import ReportOptions, build_report
from limen.synth import PlantedConfig, generate

STABLE_GRID = {
    "a": {"i1": [1, 1, 1, 1], "i2": [1, 1, 1, 0], "i3": [1, 0, 1, 1], "i4": [1, 1, 1, 1]},
    "b": {"i1": [0, 0, 0, 0], "i2": [1, 0, 0, 1], "i3": [0, 0, 0, 0], "i4": [0, 1, 0, 0]},
}


def _report(grid, **kwargs):
    return build_report(
        archive_from_grid(grid, **kwargs),
        rulings_version="rr",
        options=ReportOptions(replicates=10),
    )


# --- gate: an empty selection can never pass ------------------------------- #


def test_task_filter_matching_nothing_is_exit_two_not_pass() -> None:
    result = evaluate_gate(
        _report(STABLE_GRID),
        GateOptions(require_sign_stable=True, tasks=("typo-task",)),
    )
    assert result.exit_code == 2
    assert any("no pair rulings selected" in line for line in result.lines)


def test_report_without_pairs_is_exit_two() -> None:
    grid = {"a": {"i1": [1, 0], "i2": [1, 1]}}  # single model: no pairs exist
    result = evaluate_gate(_report(grid), GateOptions(require_sign_stable=True))
    assert result.exit_code == 2


# --- gate: degenerate MDD is unevaluable, not a pass ----------------------- #


def test_degenerate_zero_spread_mdd_is_unevaluable() -> None:
    grid = {
        "a": {"i1": [1, 1, 1, 1], "i2": [1, 1, 1, 1]},
        "b": {"i1": [0, 0, 0, 0], "i2": [0, 0, 0, 0]},
    }
    result = evaluate_gate(_report(grid), GateOptions(min_effect_vs_noise=1.0))
    assert result.exit_code == 2
    assert result.pair_verdicts[0].verdict == "UNEVALUABLE"


# --- gate: conflicting --pair directions refuse ---------------------------- #


def test_conflicting_pair_directions_refused() -> None:
    with pytest.raises(GateError, match="both directions"):
        evaluate_gate(
            _report(STABLE_GRID), GateOptions(pairs=("t:a>b", "t:b>a"))
        )


def test_duplicate_same_direction_pair_deduped() -> None:
    result = evaluate_gate(
        _report(STABLE_GRID), GateOptions(pairs=("t:a>b", "t:a>b"))
    )
    assert len(result.pair_verdicts) == 1
    assert result.exit_code == 0


# --- gate: malformed reports raise GateError, never KeyError --------------- #


def test_hand_edited_report_raises_gate_error() -> None:
    report = _report(STABLE_GRID)
    del report["rulings"]["pair"][0]["noise"]
    with pytest.raises(GateError, match="missing or malforms"):
        evaluate_gate(report, GateOptions(min_effect_vs_noise=1.0))


def test_gate_cli_malformed_report_exit_two(tmp_path: Path, capsys) -> None:
    report = _report(STABLE_GRID)
    del report["rulings"]["pair"][0]["sign_stability"]
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(report))
    assert main(["gate", str(path), "--require-sign-stable"]) == 2


# --- gate: measured grader-defect FAIL outranks the other model's gap ------ #


def test_grader_defect_fail_not_downgraded_by_unavailable_sibling() -> None:
    rows = rows_from_grid({"a": {"i1": [1, 0], "i2": [1, 1]}}, with_hashes=True)
    # model a: a planted defect pair (identical hash, differing verdicts)
    rows = [
        VerdictRow(
            model=r.model, task=r.task, item_id=r.item_id, draw_id=r.draw_id,
            verdict=r.verdict, raw_sha256="sha256:same" if r.item_id == "i1" else r.raw_sha256,
        )
        for r in rows
    ]
    # model b: NO hashes at all -> grader defect UNAVAILABLE for b
    rows += rows_from_grid({"b": {"i1": [0, 1], "i2": [0, 0]}})
    report = build_report(
        build_archive(rows), rulings_version="rr", options=ReportOptions(replicates=10)
    )
    result = evaluate_gate(report, GateOptions(max_grader_defect_share=0.0))
    assert result.exit_code == 1  # the measured failure on a wins over b's UNAVAILABLE


# --- drift: vacuous timestamps cannot launder into PASS -------------------- #


def test_all_tied_timestamps_do_not_pass() -> None:
    # four mixed cells with flips on DIFFERENT draws: clean under LODO and trend,
    # which on an informative time basis would be PASS — the tied stamps must
    # downgrade that clean result to UNAVAILABLE
    flip_patterns = [[0, 1, 1, 1], [1, 0, 1, 1], [1, 1, 0, 1], [1, 1, 1, 0]]
    rows = [
        VerdictRow(
            model="a", task="t", item_id=f"i{j}", draw_id=str(d),
            verdict=flip_patterns[j][d] if j < 4 else 1,
            collected_at="2026-01-01T00:00:00Z",  # identical everywhere
            model_version="v1",
        )
        for j in range(6)
        for d in range(4)
    ]
    guard = drift_guard(build_archive(rows), "a", "t")
    assert guard["basis"] == "collected_at"
    assert guard["time_ordering_vacuous"] is True
    assert guard["state"] == "UNAVAILABLE"  # clean-on-vacuous-basis is not PASS


def test_lodo_single_mixed_cell_cannot_trivially_fail() -> None:
    # one mixed cell always has one draw carrying all its flips; that must be
    # UNAVAILABLE (not discriminative), never a FAIL
    grid = {"a": {"i0": [1, 0, 1, 1], "i1": [1, 1, 1, 1], "i2": [0, 0, 0, 0]}}
    guard = drift_guard(
        archive_from_grid(grid, with_timestamps=True, with_versions=True), "a", "t"
    )
    lodo = guard["subchecks"]["lodo"]
    assert lodo["state"] == "UNAVAILABLE"
    assert lodo["n_mixed"] == 1


# --- model: the digest pins excluded rows and refuses bad identities ------- #


def test_digest_pins_low_k_excluded_rows() -> None:
    base = rows_from_grid({"a": {"i1": [1, 0]}, "b": {"i1": [0, 1]}})
    extra = base + [VerdictRow(model="a", task="t", item_id="i9", draw_id="0", verdict=1)]
    assert build_archive(base).dataset_digest() != build_archive(extra).dataset_digest()


def test_empty_identity_fields_refused() -> None:
    with pytest.raises(TableError, match="empty model"):
        build_archive([VerdictRow(model=" ", task="t", item_id="i", draw_id="0", verdict=1)])


def test_numeric_draw_id_collision_orders_deterministically() -> None:
    rows_fwd = [
        VerdictRow(model="a", task="t", item_id="i", draw_id="01", verdict=1),
        VerdictRow(model="a", task="t", item_id="i", draw_id="1", verdict=0),
    ]
    cell_fwd = build_archive(rows_fwd).cell("a", "t", "i")
    cell_rev = build_archive(list(reversed(rows_fwd))).cell("a", "t", "i")
    assert cell_fwd.draw_ids == cell_rev.draw_ids == ("01", "1")


# --- synth: truth reflects the effective flaky fraction -------------------- #


def test_truth_uses_effective_fraction_not_requested_phi() -> None:
    cfg = PlantedConfig(
        n_items=10, k=8, models=("a",), mu=(0.6,), flaky_fraction=0.25
    )
    _, truth = generate(cfg, seed=0)
    # round(0.25*10)=2 flaky items -> effective fraction 0.2, not 0.25
    assert truth.expected["effective_flaky_fraction"] == pytest.approx(0.2)
    assert truth.expected["mean_flakiness_per_model"]["a"] == pytest.approx(0.2 * 0.5)


def test_truth_accounts_for_planted_q_shift() -> None:
    cfg = PlantedConfig(
        n_items=100, k=8, models=("a",), mu=(0.6,), flaky_fraction=0.2,
        q_shift_at_draw=(4, 0.4),
    )
    _, truth = generate(cfg, seed=0)
    # per-draw q = [0.5]*4 + [0.9]*4; E[f] = mean pairwise disagreement
    qs = [0.5] * 4 + [0.9] * 4
    total = sum(
        qs[i] * (1 - qs[j]) + qs[j] * (1 - qs[i])
        for i in range(8) for j in range(i + 1, 8)
    ) / 28
    assert truth.expected["mean_flakiness_per_model"]["a"] == pytest.approx(0.2 * total)
    assert truth.expected["single_draw_score_sigma"]["a"] is None  # not i.i.d.


# --- cli: multi-input merge stacks draws before min-k ---------------------- #


def test_multi_input_merge_stacks_draws_before_min_k(tmp_path: Path, capsys) -> None:
    header = "model,task,item_id,draw_id,verdict\n"
    (tmp_path / "run1.csv").write_text(
        header + "a,t,i1,0,1\na,t,i2,0,1\nb,t,i1,0,0\nb,t,i2,0,1\n"
    )
    (tmp_path / "run2.csv").write_text(
        header + "a,t,i1,1,0\na,t,i2,1,1\nb,t,i1,1,1\nb,t,i2,1,0\n"
    )
    # each file alone has k=1 everywhere; merged they form k=2 cells
    code = main(
        [
            "report",
            str(tmp_path / "run1.csv"),
            str(tmp_path / "run2.csv"),
            "--out",
            str(tmp_path / "out"),
            "--replicates",
            "5",
        ]
    )
    assert code == 0
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["rulings"]["task"][0]["n"]["k"] == 2
    assert report["n"]["excluded_low_k"] == []
