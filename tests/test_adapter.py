"""Adapter mechanics against the fake checkout (LMN-ADP-001/002/003)."""

import sys
from pathlib import Path

import pytest

from limen.adapters.spaghetti import (
    build_tables,
    build_task_archive,
    resolve_repo,
)
from limen.errors import AdapterError
from limen.readers import load


def test_resolve_repo_refuses_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LIMEN_SPAGHETTI_REPO", raising=False)
    with pytest.raises(AdapterError, match="LIMEN_SPAGHETTI_REPO"):
        resolve_repo(None)
    with pytest.raises(AdapterError, match="bench/tasks.py"):
        resolve_repo(tmp_path)


def test_resolve_repo_env_var(fake_spaghetti: Path, monkeypatch) -> None:
    monkeypatch.setenv("LIMEN_SPAGHETTI_REPO", str(fake_spaghetti))
    assert resolve_repo(None) == fake_spaghetti.resolve()


def test_poisoned_env_refused_before_import(fake_spaghetti: Path, monkeypatch) -> None:
    monkeypatch.setenv("BENCH_STRIP_ANNOTATIONS", "1")
    with pytest.raises(AdapterError, match="AT IMPORT"):
        build_task_archive(fake_spaghetti, "comprehend_dev")
    assert "bench" not in sys.modules  # refused BEFORE importing anything


def test_comprehend_dev_per_draw_verdicts(fake_spaghetti: Path) -> None:
    archive = build_task_archive(fake_spaghetti, "comprehend_dev")
    assert archive.models == ("fake-a", "fake-b")
    # fake-a s1: ["G-dev","G-dev","wrong","G-dev"] -> [1,1,0,1]
    cell = archive.cell("fake-a", "comprehend_dev", "s1|base|standard|python")
    assert cell.verdicts == (1, 1, 0, 1)
    assert cell.raw_sha256 is not None and len(set(cell.raw_sha256)) == 2


def test_stub_records_skipped_and_counted(fake_spaghetti: Path) -> None:
    archive = build_task_archive(fake_spaghetti, "comprehend_dev")
    assert len(archive.items("fake-b", "comprehend_dev")) == 2  # stub1 not graded
    assert archive.meta["skipped_stub_records"] == '{"fake-b": 1}'


def test_split_injection_defuses_the_test_trap(fake_spaghetti: Path) -> None:
    """tierA records grade against the TEST gold (not silently against dev), and
    tierB records do not crash — both prove rec['split'] was injected."""
    archive = build_task_archive(fake_spaghetti, "comprehend_test")
    tier_a = archive.cell("fake-a", "comprehend_test", "tierA_s1|base|standard|python")
    assert tier_a.verdicts == (1, 1, 0, 1)  # G-test hits; the G-dev draw misses
    tier_b = archive.cell("fake-a", "comprehend_test", "tierB_s2|base|standard|python")
    assert tier_b.verdicts == (1, 0, 1, 1)


def test_the_trap_is_real_without_injection(fake_spaghetti: Path) -> None:
    """Prove the fake reproduces upstream: without split, tierB crashes and tierA
    silently grades against the wrong gold."""
    sys.path.append(str(fake_spaghetti))
    try:
        import importlib

        tasks = importlib.import_module("bench.tasks")
        with pytest.raises(KeyError, match="tierB"):
            tasks.regrade_comprehend_record(
                {"sample": "tierB_s2", "raw_outputs": ["G-test"]}
            )
        wrong = tasks.regrade_comprehend_record(
            {"sample": "tierA_s1", "raw_outputs": ["G-test"]}
        )
        assert wrong["exact_match_rate"] == 0.0  # silently graded against dev gold
    finally:
        sys.path.remove(str(fake_spaghetti))


def test_refactor_test_hard_refusal(fake_spaghetti: Path) -> None:
    with pytest.raises(AdapterError, match="non-reproducible"):
        build_task_archive(fake_spaghetti, "refactor_test")


def test_unknown_task_refused(fake_spaghetti: Path) -> None:
    with pytest.raises(AdapterError, match="unknown task"):
        build_task_archive(fake_spaghetti, "judge_dev")


def test_non_integral_rate_refused(fake_spaghetti_halfling: Path) -> None:
    with pytest.raises(AdapterError, match="refusing to round"):
        build_task_archive(fake_spaghetti_halfling, "comprehend_dev")


def test_build_tables_roundtrip(fake_spaghetti: Path, tmp_path: Path) -> None:
    paths = build_tables(
        fake_spaghetti, tmp_path / "tables", tasks=("comprehend_dev", "refactor_dev")
    )
    assert [p.name for p in paths] == [
        "comprehend_dev.verdicts.csv.gz",
        "refactor_dev.verdicts.csv.gz",
    ]
    archive = load(paths[0])
    assert archive.cell("fake-a", "comprehend_dev", "s1|base|standard|python").verdicts == (
        1,
        1,
        0,
        1,
    )
    # determinism: writing again gives identical bytes
    first = paths[0].read_bytes()
    build_tables(fake_spaghetti, tmp_path / "tables", tasks=("comprehend_dev",))
    assert paths[0].read_bytes() == first


def test_no_pycache_written_into_checkout(fake_spaghetti: Path, tmp_path: Path) -> None:
    build_tables(fake_spaghetti, tmp_path / "t", tasks=("comprehend_dev",))
    assert not list(fake_spaghetti.rglob("__pycache__"))


def test_second_checkout_in_one_process_refused(
    fake_spaghetti: Path, fake_spaghetti_halfling: Path
) -> None:
    """Loading a second checkout would silently reuse the first one's graders
    (its modules occupy the generic names bench/src/eval); it must refuse."""
    from limen.adapters.spaghetti import reset_import_state

    build_task_archive(fake_spaghetti, "comprehend_dev")
    with pytest.raises(AdapterError, match="already loaded"):
        build_task_archive(fake_spaghetti_halfling, "comprehend_dev")
    reset_import_state()
    # after an explicit reset the second checkout loads (and hits its own trap)
    with pytest.raises(AdapterError, match="refusing to round"):
        build_task_archive(fake_spaghetti_halfling, "comprehend_dev")
