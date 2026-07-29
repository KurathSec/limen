"""End-to-end CLI invocations over real files."""

import json
from pathlib import Path

from limen.cli import main


def test_synth_report_gate_pipeline(tmp_path: Path, capsys) -> None:
    assert (
        main(
            [
                "synth",
                "--out",
                str(tmp_path / "s"),
                "--models",
                "2",
                "--items",
                "80",
                "--draws",
                "4",
                "--flaky-fraction",
                "0.1",
                "--gap",
                "0.1",
                "--seed",
                "2",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "report",
                str(tmp_path / "s" / "archive.verdicts.csv.gz"),
                "--out",
                str(tmp_path / "r"),
                "--rulings-version",
                "clitest",
                "--replicates",
                "10",
            ]
        )
        == 0
    )
    report_path = tmp_path / "r" / "report.json"
    assert report_path.is_file()
    assert (tmp_path / "r" / "provenance.json").is_file()
    assert (tmp_path / "r" / "report.md").is_file()
    report = json.loads(report_path.read_text())
    assert report["rulings_version"] == "clitest"
    capsys.readouterr()
    code = main(["gate", str(report_path), "--require-sign-stable", "--min-effect-vs-noise", "1.0"])
    out = capsys.readouterr().out
    assert code == 0
    assert "OVERALL: PASS" in out


def test_gate_missing_report_exit_two(tmp_path: Path, capsys) -> None:
    assert main(["gate", str(tmp_path / "nope.json")]) == 2


def test_report_unreadable_input_exit_two(tmp_path: Path, capsys) -> None:
    bad = tmp_path / "bad.csv"
    bad.write_text("not,a,verdict,table\n1,2,3,4\n")
    assert main(["report", str(bad)]) == 2
    assert "limen:" in capsys.readouterr().err


def test_spec_and_env_commands(capsys) -> None:
    assert main(["spec", "list"]) == 0
    assert "LMN-CORE-001" in capsys.readouterr().out
    assert main(["spec", "show", "LMN-GTE-001"]) == 0
    assert "Exit codes" in capsys.readouterr().out
    assert main(["env"]) == 0
    assert "limen" in capsys.readouterr().out


def test_report_provenance_is_outside_the_byte_body(tmp_path: Path) -> None:
    for run in ("r1", "r2"):
        main(
            [
                "synth",
                "--out",
                str(tmp_path / "s"),
                "--items",
                "40",
                "--draws",
                "4",
                "--seed",
                "5",
            ]
        )
        main(
            [
                "report",
                str(tmp_path / "s" / "archive.verdicts.csv.gz"),
                "--out",
                str(tmp_path / run),
                "--rulings-version",
                "v",
                "--replicates",
                "5",
            ]
        )
    b1 = (tmp_path / "r1" / "report.json").read_bytes()
    b2 = (tmp_path / "r2" / "report.json").read_bytes()
    assert b1 == b2  # bodies identical across runs; provenance may differ
