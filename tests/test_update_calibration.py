"""The calibration tool's evolution ceremony, exercised on a temp tree via --root."""

import json
import subprocess
import sys
from pathlib import Path

from limen.canonical import canonical_json
from limen.readers.longcsv import write_archive
from limen.synth import PlantedConfig, generate

TOOL = Path(__file__).parent.parent / "tools" / "update_calibration.py"


def _make_tree(tmp_path: Path) -> tuple[Path, Path]:
    cfg = PlantedConfig(n_items=30, k=4, models=("a", "b"), mu=(0.6, 0.5), flaky_fraction=0.1)
    archive, _ = generate(cfg, seed=3)
    tables = tmp_path / "calibration" / "spaghetti" / "tables"
    write_archive(archive, tables / "mini.verdicts.csv.gz")
    golden_dir = tmp_path / "calibration" / "spaghetti" / "rulings" / "cal1"
    golden_dir.mkdir(parents=True)
    return tables / "mini.verdicts.csv.gz", golden_dir / "mini.report.json"


def _run(tmp_path: Path, *flags: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *flags, "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_write_creates_then_check_green(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    assert _run(tmp_path, "--write").returncode == 0
    result = _run(tmp_path, "--check")
    assert result.returncode == 0, result.stdout + result.stderr


def test_changed_value_refused_without_major(tmp_path: Path) -> None:
    _table, golden = _make_tree(tmp_path)
    assert _run(tmp_path, "--write").returncode == 0
    doc = json.loads(golden.read_text())
    doc["rulings"]["mt"][0]["flakiness"]["mean_flakiness"] = 0.999999
    golden.write_text(canonical_json(doc), encoding="utf-8", newline="")
    check = _run(tmp_path, "--check")
    assert check.returncode == 1
    write = _run(tmp_path, "--write")
    assert write.returncode == 1
    assert "REFUSED" in write.stdout and "confirm-spec-bump" in write.stdout
    # even with the flag, same spec MAJOR refuses
    write2 = _run(tmp_path, "--write", "--confirm-spec-bump")
    assert write2.returncode == 1
    assert "not beyond the committed golden's" in write2.stdout


def test_additive_refused_without_minor_spec_move(tmp_path: Path) -> None:
    """Plant a golden that is a strict subset of the regenerated document while
    carrying the CURRENT spec version: additive, but no spec movement -> refuse."""
    _table, golden = _make_tree(tmp_path)
    assert _run(tmp_path, "--write").returncode == 0
    doc = json.loads(golden.read_text())
    del doc["rulings"]["mt"][0]["grader_defect"]  # subset: regeneration only adds
    golden.write_text(canonical_json(doc), encoding="utf-8", newline="")
    write = _run(tmp_path, "--write")
    assert write.returncode == 1  # the requested write did not complete
    assert "REFUSED" in write.stdout and "MINOR" in write.stdout
    check = _run(tmp_path, "--check")
    assert check.returncode == 1


def test_additive_accepted_after_minor_spec_move(tmp_path: Path) -> None:
    _table, golden = _make_tree(tmp_path)
    assert _run(tmp_path, "--write").returncode == 0
    doc = json.loads(golden.read_text())
    del doc["rulings"]["mt"][0]["grader_defect"]
    doc["spec_version"] = "0.1.0"  # older spec: current spec is at least MINOR ahead
    golden.write_text(canonical_json(doc), encoding="utf-8", newline="")
    write = _run(tmp_path, "--write")
    assert write.returncode == 0
    assert "ADDITIVE refresh" in write.stdout
    assert _run(tmp_path, "--check").returncode == 0


def test_orphaned_golden_fails_check_and_write(tmp_path: Path) -> None:
    table, golden = _make_tree(tmp_path)
    assert _run(tmp_path, "--write").returncode == 0
    table.unlink()
    check = _run(tmp_path, "--check")
    assert check.returncode == 1
    assert "ORPHANED" in check.stdout
    # a tampered orphan must not survive either mode, even with the flag
    doc = json.loads(golden.read_text())
    doc["rulings"]["mt"][0]["flakiness"]["mean_flakiness"] = 0.999999
    golden.write_text(canonical_json(doc), encoding="utf-8", newline="")
    write = _run(tmp_path, "--write", "--confirm-spec-bump")
    assert write.returncode == 1
    assert "ORPHANED" in write.stdout
    assert golden.is_file()  # the tool never deletes


def test_refusing_write_never_repins_manifest(tmp_path: Path) -> None:
    table, golden = _make_tree(tmp_path)
    assert _run(tmp_path, "--write").returncode == 0
    manifest = tmp_path / "calibration" / "spaghetti" / "MANIFEST.json"
    manifest.write_text(
        canonical_json({"tables": {table.name: {"sha256": "sha256:STALE_PIN"}}}),
        encoding="utf-8",
        newline="",
    )
    pinned = manifest.read_bytes()
    doc = json.loads(golden.read_text())
    doc["rulings"]["mt"][0]["flakiness"]["mean_flakiness"] = 0.999999
    golden.write_text(canonical_json(doc), encoding="utf-8", newline="")
    write = _run(tmp_path, "--write")
    assert write.returncode == 1
    assert manifest.read_bytes() == pinned, (
        "a refusing run must leave the tamper-evidence pin exactly as it found it"
    )


def test_spec_downgrade_refused_even_with_flag(tmp_path: Path) -> None:
    _table, golden = _make_tree(tmp_path)
    assert _run(tmp_path, "--write").returncode == 0
    doc = json.loads(golden.read_text())
    doc["spec_version"] = "9.0.0"
    doc["rulings"]["mt"][0]["flakiness"]["mean_flakiness"] = 0.999999
    golden.write_text(canonical_json(doc), encoding="utf-8", newline="")
    write = _run(tmp_path, "--write", "--confirm-spec-bump")
    assert write.returncode == 1
    assert "not beyond the committed golden's" in write.stdout
