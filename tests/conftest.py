"""Shared fixtures: row builders and the fake Spaghetti-Architect repo factory."""

from __future__ import annotations

import gzip
import json
import textwrap
from pathlib import Path

import pytest

from limen.model import Archive, VerdictRow, build_archive


def rows_from_grid(
    grid: dict[str, dict[str, list[int]]],
    *,
    task: str = "t",
    with_hashes: bool = False,
    with_timestamps: bool = False,
    with_versions: bool = False,
    version_by_draw: dict[int, str] | None = None,
) -> list[VerdictRow]:
    """grid[model][item] = verdicts per draw position."""
    rows = []
    for model, items in grid.items():
        for item, verdicts in items.items():
            for d, v in enumerate(verdicts):
                version = None
                if version_by_draw is not None:
                    version = version_by_draw.get(d, "v1")
                elif with_versions:
                    version = "v1"
                rows.append(
                    VerdictRow(
                        model=model,
                        task=task,
                        item_id=item,
                        draw_id=str(d),
                        verdict=v,
                        collected_at=(
                            f"2026-01-01T00:00:{d:02d}Z" if with_timestamps else None
                        ),
                        model_version=version,
                        raw_sha256=(
                            f"sha256:{model}:{item}:{d}" if with_hashes else None
                        ),
                    )
                )
    return rows


def archive_from_grid(grid: dict[str, dict[str, list[int]]], **kwargs: object) -> Archive:
    return build_archive(rows_from_grid(grid, **kwargs))  # type: ignore[arg-type]


FAKE_TASKS_PY = textwrap.dedent(
    '''
    """Miniature stand-in for Spaghetti-Architect's bench.tasks.

    Reproduces the three behaviours the adapter must defuse: the import-time
    BENCH_STRIP_ANNOTATIONS read, the split-defaults-to-dev trap (tier A grades
    silently against the wrong gold; tier B/C crash), and aggregate-rate
    regrading of raw_outputs lists.
    """
    import os

    STRIP_ANNOTATIONS = os.environ.get("BENCH_STRIP_ANNOTATIONS", "") not in ("", "0", "false")

    _GOLD = {"dev": "G-dev", "test": "G-test"}
    _IDENTITY = ("sample", "profile", "language", "variant", "intrinsic", "snapshot",
                 "tier", "prompt_hash", "raw_outputs")


    def _regrade(rec, rate_key):
        split = rec.get("split", "dev")
        sample = rec.get("sample", "")
        if sample.startswith(("tierB_", "tierC_")) and split == "dev":
            raise KeyError(f"no dataset item for sample={sample!r}")
        outs = rec["raw_outputs"]
        if outs == ["<mock>"]:
            return dict(rec)
        if sample == "halfling":
            rate = 0.5
        else:
            gold = _GOLD[split]
            hits = sum(1 for o in outs if (o == gold) != STRIP_ANNOTATIONS)
            rate = hits / len(outs)
        fresh = {k: rec[k] for k in _IDENTITY if k in rec}
        fresh[rate_key] = rate
        return fresh


    def regrade_comprehend_record(rec):
        return _regrade(rec, "exact_match_rate")


    def regrade_refactor_record(rec):
        return _regrade(rec, "semantic_ok_rate")
    '''
)


def _write_archive_gz(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


@pytest.fixture
def fake_spaghetti(tmp_path: Path) -> Path:
    """A fake checkout with dev/test archives exercising every adapter code path."""
    repo = tmp_path / "fake-spaghetti"
    bench = repo / "bench"
    bench.mkdir(parents=True)
    (bench / "__init__.py").write_text("")
    (bench / "tasks.py").write_text(FAKE_TASKS_PY)

    def rec(sample: str, outs: list[str], tier: str | None = None) -> dict[str, object]:
        r: dict[str, object] = {
            "sample": sample,
            "variant": "base",
            "profile": "standard",
            "language": "python",
            "intrinsic": {"n_ops": 1},
            "raw_outputs": outs,
        }
        if tier is not None:
            r["tier"] = tier
        return r

    _write_archive_gz(
        bench / "out/ladder/comprehend__fake-a.jsonl.gz",
        [
            rec("s1", ["G-dev", "G-dev", "wrong", "G-dev"]),
            rec("s2", ["G-dev", "G-dev", "G-dev", "G-dev"]),
        ],
    )
    _write_archive_gz(
        bench / "out/ladder/comprehend__fake-b.jsonl.gz",
        [
            rec("s1", ["wrong", "wrong", "wrong", "wrong"]),
            rec("s2", ["G-dev", "wrong", "G-dev", "wrong"]),
            # an upstream failed-fetch stub: no raw_outputs at all
            {"sample": "stub1", "profile": "standard", "language": "python"},
        ],
    )
    _write_archive_gz(
        bench / "out/g3/comprehend_test__fake-a.jsonl.gz",
        [
            rec("tierA_s1", ["G-test", "G-test", "G-dev", "G-test"], tier="A"),
            rec("tierB_s2", ["G-test", "wrong", "G-test", "G-test"], tier="B"),
        ],
    )
    _write_archive_gz(
        bench / "out/g3/refactor_dev__fake-a.jsonl.gz",
        [rec("s1", ["G-dev", "wrong", "G-dev", "G-dev"])],
    )
    return repo


@pytest.fixture
def fake_spaghetti_halfling(tmp_path: Path) -> Path:
    """A fake checkout whose grader returns a non-integral singleton rate."""
    repo = tmp_path / "fake-spaghetti-half"
    bench = repo / "bench"
    bench.mkdir(parents=True)
    (bench / "__init__.py").write_text("")
    (bench / "tasks.py").write_text(FAKE_TASKS_PY)
    _write_archive_gz(
        bench / "out/ladder/comprehend__fake-a.jsonl.gz",
        [
            {
                "sample": "halfling",
                "variant": "base",
                "profile": "standard",
                "language": "python",
                "intrinsic": {},
                "raw_outputs": ["a", "b"],
            }
        ],
    )
    return repo


@pytest.fixture(autouse=True)
def _clean_adapter_state() -> object:
    """Keep foreign-import state from leaking between tests."""
    yield
    from limen.adapters.spaghetti import reset_import_state

    reset_import_state()
