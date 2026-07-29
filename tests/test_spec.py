"""Spec registry integrity and coverage: every ruling cited, every citation resolves."""

import re
from pathlib import Path

import pytest

from limen.errors import SpecError
from limen.spec import all_decisions, require, spec_version

ROOT = Path(__file__).resolve().parent.parent
ID_RE = re.compile(r"LMN-[A-Z]+-\d{3}")


def test_spec_version_present() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", spec_version())


def test_require_known_and_unknown() -> None:
    decision = require("LMN-CORE-001")
    assert "never" in decision.text
    with pytest.raises(SpecError, match="unknown"):
        require("LMN-XX-999")


def test_every_active_ruling_is_cited_somewhere() -> None:
    cited: set[str] = set()
    for base in (ROOT / "src", ROOT / "tests", ROOT / "docs"):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix in (".py", ".md", ".toml") and "spec/rulings" not in str(path):
                cited.update(ID_RE.findall(path.read_text(encoding="utf-8", errors="ignore")))
    active = {d.id for d in all_decisions() if d.status == "active"}
    uncited = active - cited
    assert not uncited, f"spec rulings never cited from code, tests or docs: {sorted(uncited)}"


def test_every_cited_id_resolves() -> None:
    known = {d.id for d in all_decisions()}
    here = Path(__file__)
    for base in (ROOT / "src", ROOT / "tests"):
        for path in base.rglob("*.py"):
            if path == here:  # this file deliberately cites an unknown id above
                continue
            for cited in ID_RE.findall(path.read_text(encoding="utf-8")):
                assert cited in known, f"{path} cites unknown spec ruling {cited}"
