"""Run every hand-computed corpus case through the ordinary report path."""

import tomllib
from pathlib import Path
from typing import Any

import pytest

from limen.model import VerdictRow, build_archive
from limen.report import ReportOptions, build_report

CASES = sorted((Path(__file__).parent / "corpus" / "cases").glob("*.toml"))


def _resolve(report: dict[str, Any], dotted: str) -> Any:
    node: Any = report
    for part in dotted.split("."):
        if isinstance(node, list):
            node = node[int(part)]
        else:
            node = node[part]
    return node


@pytest.mark.parametrize("case_path", CASES, ids=lambda p: p.stem)
def test_corpus_case(case_path: Path) -> None:
    case = tomllib.loads(case_path.read_text(encoding="utf-8"))
    rows = [
        VerdictRow(
            model=r["model"],
            task="t",
            item_id=r["item"],
            draw_id=str(d),
            verdict=v,
        )
        for r in case["rows"]
        for d, v in enumerate(r["verdicts"])
    ]
    archive = build_archive(rows)
    report = build_report(
        archive, rulings_version="corpus", options=ReportOptions(replicates=10)
    )
    for dotted, expected in case["expected"].items():
        actual = _resolve(report, dotted)
        if expected == "null":
            expected = None
        assert actual == expected, f"{case_path.stem}: {dotted} = {actual!r}, want {expected!r}"
