"""Read-only adapter over a Spaghetti-Architect checkout: archives -> verdict tables.

Grades the checkout's committed k=8 archives into per-draw verdict tables using
ONLY the checkout's public regrade API, one singleton record per draw — the
aggregate rate of a one-element ``raw_outputs`` list is exactly that draw's
verdict. Refuses anything non-integral rather than rounding (LMN-ADP-003).

The checkout is never modified: imports run with ``sys.dont_write_bytecode``
held for the whole build so no ``__pycache__`` lands in the foreign tree, and
the adapter only reads.

Landmines this module exists to defuse (verified against the checkout):

- ``bench.tasks`` reads ``BENCH_STRIP_ANNOTATIONS`` **at import time**; a
  truthy value silently switches every regrade to the unannotated corpus. The
  adapter refuses to proceed before importing anything (LMN-ADP-001).
- ``regrade_*_record`` falls back to ``rec.get("split", "dev")``; test-split
  records grade against the wrong oracle silently (tier A) or crash (B/C).
  The adapter injects ``split`` from the archive filename on every record,
  always (LMN-ADP-002).
- The checkout's root exposes the generic top-level names ``bench``, ``src``,
  ``eval``; the path is appended, never prepended, so it can never shadow the
  host environment.
- refactor x test is declared not reproducible by the checkout's own g3 README
  (the pre-graded finalize files are gitignored); requesting it is a hard
  refusal, not a degraded run.

Refactor grading executes model-generated code (Python ``exec`` plus compile-
and-run subprocesses for js/go/java/cpp) — the same path the benchmark itself
uses. Run it only where you would run the benchmark.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import sys
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ..errors import AdapterError
from ..model import Archive, VerdictRow, build_archive
from ..readers.longcsv import write_archive

ENV_REPO = "LIMEN_SPAGHETTI_REPO"
ENV_POISON = "BENCH_STRIP_ANNOTATIONS"

#: task name -> (glob relative to repo, split to inject, regrade fn, rate key)
TASKS: dict[str, tuple[str, str, str, str]] = {
    "comprehend_dev": (
        "bench/out/ladder/comprehend__*.jsonl.gz",
        "dev",
        "regrade_comprehend_record",
        "exact_match_rate",
    ),
    "comprehend_test": (
        "bench/out/g3/comprehend_test__*.jsonl.gz",
        "test",
        "regrade_comprehend_record",
        "exact_match_rate",
    ),
    "refactor_dev": (
        "bench/out/g3/refactor_dev__*.jsonl.gz",
        "dev",
        "regrade_refactor_record",
        "semantic_ok_rate",
    ),
}

REFUSED_TASKS = {
    "refactor_test": (
        "refactor x test regrade is declared non-reproducible by the checkout's own "
        "bench/out/g3/README.md (pre-graded finalize files are gitignored); limen "
        "refuses rather than grading against the wrong oracle"
    ),
}

_CACHE: dict[str, dict[str, Callable[[dict[str, Any]], dict[str, Any]]]] = {}


def resolve_repo(explicit: str | os.PathLike[str] | None = None) -> Path:
    """Explicit path wins, else $LIMEN_SPAGHETTI_REPO; validated, never guessed."""
    raw = str(explicit) if explicit is not None else os.environ.get(ENV_REPO, "")
    if not raw:
        raise AdapterError(
            f"no Spaghetti-Architect checkout given: pass --repo or set ${ENV_REPO}"
        )
    repo = Path(raw).expanduser().resolve()
    if not (repo / "bench" / "tasks.py").is_file():
        raise AdapterError(f"{repo}: not a Spaghetti-Architect checkout (no bench/tasks.py)")
    return repo


def _refuse_poisoned_env() -> None:
    value = os.environ.get(ENV_POISON, "")
    if value not in ("", "0", "false"):
        raise AdapterError(
            f"{ENV_POISON}={value!r} is set: bench.tasks reads it AT IMPORT and would "
            "silently regrade against the unannotated corpus; unset it and rerun"
        )


#: top-level module names a Spaghetti-Architect checkout exposes; all must be
#: purged together — bench.tasks pulls in src.* and eval.* transitively, and a
#: survivor from checkout A would silently poison a later checkout B.
_FOREIGN_TOP_LEVEL = ("bench", "src", "eval")


def _purge_foreign_modules() -> None:
    for name in list(sys.modules):
        if any(name == top or name.startswith(f"{top}.") for top in _FOREIGN_TOP_LEVEL):
            del sys.modules[name]


def _load_bench(repo: Path) -> dict[str, Callable[[dict[str, Any]], dict[str, Any]]]:
    """Import the checkout's graders lazily, cached per repo root, byte-cache-free.

    One checkout per process: the checkout's modules occupy the generic names
    ``bench``/``src``/``eval`` in sys.modules, so loading a second, different
    checkout would silently reuse the first one's graders. That is refused;
    tests use :func:`reset_import_state` between checkouts."""
    key = str(repo)
    if key in _CACHE:
        return _CACHE[key]
    if _CACHE:
        loaded = next(iter(_CACHE))
        raise AdapterError(
            f"checkout {loaded} is already loaded in this process; grading a second "
            f"checkout ({key}) would silently reuse the first one's graders — use a "
            "fresh interpreter (or reset_import_state() in tests)"
        )
    _refuse_poisoned_env()
    if "bench" in sys.modules:
        raise AdapterError(
            "a module named 'bench' is already imported from elsewhere; refusing to "
            "shadow it (start a fresh interpreter)"
        )
    if any(str(Path(p).resolve()) == key for p in sys.path if p):
        path_added = False
    else:
        sys.path.append(key)
        path_added = True
    sys.dont_write_bytecode = True
    try:
        import importlib

        tasks_mod = importlib.import_module("bench.tasks")
    except AdapterError:
        raise
    except Exception as exc:
        # a failed import may leave partial foreign modules behind; purge them so
        # the next attempt does not hit a misleading "imported from elsewhere"
        _purge_foreign_modules()
        if path_added:
            sys.path.remove(key)
        raise AdapterError(f"cannot import bench.tasks from {repo}: {exc}") from exc
    # NOTE: sys.dont_write_bytecode stays True for the process lifetime once a
    # foreign checkout is loaded: grading triggers lazy imports later, and no
    # __pycache__ may ever be written into the read-only checkout.
    funcs = {
        "regrade_comprehend_record": tasks_mod.regrade_comprehend_record,
        "regrade_refactor_record": tasks_mod.regrade_refactor_record,
    }
    _CACHE[key] = funcs
    return funcs


def reset_import_state() -> None:
    """Test hook: forget cached graders and every imported foreign module
    (bench, src, eval — the checkout's whole top-level surface)."""
    for key in list(_CACHE):
        while key in sys.path:
            sys.path.remove(key)
    _CACHE.clear()
    _purge_foreign_modules()


def _read_records(path: Path) -> list[dict[str, Any]]:
    records = []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise AdapterError(f"{path}:{lineno}: invalid JSON") from exc
    if not records:
        raise AdapterError(f"{path}: empty archive")
    return records


def _model_slug(path: Path) -> str:
    name = path.name
    if "__" not in name or not name.endswith(".jsonl.gz"):
        raise AdapterError(f"{path}: unexpected archive filename (want <task>__<model>.jsonl.gz)")
    return name.split("__", 1)[1][: -len(".jsonl.gz")]


def is_stub(rec: dict[str, Any]) -> bool:
    """A record with no stored completions (upstream failed-fetch stub). These
    cells have no draws; they are skipped and counted, never silently graded."""
    raw_outputs = rec.get("raw_outputs")
    return not isinstance(raw_outputs, list) or not raw_outputs


def _grade_record(
    rec: dict[str, Any],
    *,
    task: str,
    split: str,
    model: str,
    regrade: Callable[[dict[str, Any]], dict[str, Any]],
    rate_key: str,
) -> list[VerdictRow]:
    raw_outputs = rec.get("raw_outputs")
    if not isinstance(raw_outputs, list) or not raw_outputs:
        raise AdapterError(f"record without raw_outputs in {task}: {rec.get('sample')!r}")
    if raw_outputs == ["<mock>"]:
        raise AdapterError(
            f"mock record in {task} ({rec.get('sample')!r}): sentinel raw_outputs "
            "cannot be regraded"
        )
    item_id = "|".join(
        str(rec.get(field, "")) for field in ("sample", "variant", "profile", "language")
    )
    labels = _record_labels(rec)
    rows: list[VerdictRow] = []
    for draw_index, out in enumerate(raw_outputs):
        singleton = {**rec, "split": split, "raw_outputs": [out]}
        graded = regrade(singleton)
        if graded.get("skip"):
            raise AdapterError(
                f"{task} {item_id!r} draw {draw_index}: the upstream grader skipped "
                f"this record ({graded.get('skip')!r}) — usually a missing language "
                "toolchain; install it or exclude the task, do not grade around it"
            )
        rate = graded.get(rate_key)
        if rate not in (0, 1, 0.0, 1.0):
            raise AdapterError(
                f"{task} {item_id!r} draw {draw_index}: singleton regrade returned "
                f"{rate_key}={rate!r}, not an integral 0/1 verdict; refusing to round"
            )
        rows.append(
            VerdictRow(
                model=model,
                task=task,
                item_id=item_id,
                draw_id=str(draw_index),
                verdict=int(rate),
                raw_sha256="sha256:" + hashlib.sha256(out.encode("utf-8")).hexdigest(),
                labels=labels,
            )
        )
    return rows


def _record_labels(rec: dict[str, Any]) -> tuple[tuple[str, str], ...] | None:
    """Stratum labels from a record: language / variant / profile (the item-id
    parts), the by-construction intrinsic scale, and the tier where present
    (g3 archives). Intrinsic values must be str/int/bool; anything else is
    refused rather than rounded (LMN-ADP-003 ethos)."""
    labels: list[tuple[str, str]] = []
    for field in ("language", "variant", "profile"):
        value = rec.get(field)
        if value:
            labels.append((field, str(value)))
    intrinsic = rec.get("intrinsic")
    if isinstance(intrinsic, dict) and intrinsic:
        parts = []
        for key in sorted(intrinsic):
            value = intrinsic[key]
            if not isinstance(value, str | int | bool):
                raise AdapterError(
                    f"intrinsic[{key!r}] = {value!r} for {rec.get('sample')!r} is not "
                    "a str/int/bool; refusing to coerce a scale label"
                )
            parts.append(f"{key}={value}")
        labels.append(("scale", ",".join(parts)))
    elif intrinsic not in (None, {}, ""):
        labels.append(("scale", str(intrinsic)))
    tier = rec.get("tier")
    if tier:
        labels.append(("tier", str(tier)))
    return tuple(sorted(labels)) or None


def build_task_archive(
    repo: Path, task: str, *, max_workers: int = 8
) -> Archive:
    """Grade one task's archives into an in-memory verdict table."""
    if task in REFUSED_TASKS:
        raise AdapterError(REFUSED_TASKS[task])
    if task not in TASKS:
        raise AdapterError(f"unknown task {task!r}; available: {sorted(TASKS)}")
    pattern, split, regrade_name, rate_key = TASKS[task]
    files = sorted(repo.glob(pattern))
    if not files:
        raise AdapterError(f"{repo}: no archives match {pattern}")
    regrade = _load_bench(repo)[regrade_name]
    rows: list[VerdictRow] = []
    stub_counts: dict[str, int] = {}
    for path in files:
        model = _model_slug(path)
        records = _read_records(path)
        stubs = sum(1 for rec in records if is_stub(rec))
        if stubs:
            stub_counts[model] = stubs
        records = [rec for rec in records if not is_stub(rec)]
        if not records:
            raise AdapterError(f"{path}: every record is a stub; nothing to grade")

        def grade(rec: dict[str, Any], model: str = model) -> list[VerdictRow]:
            return _grade_record(
                rec, task=task, split=split, model=model, regrade=regrade, rate_key=rate_key
            )

        if task.startswith("refactor") and max_workers > 1:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                for graded_rows in pool.map(grade, records):
                    rows.extend(graded_rows)
        else:
            for rec in records:
                rows.extend(grade(rec))
    meta = {"reader": "spaghetti-adapter", "task": task, "repo": repo.name}
    if stub_counts:
        meta["skipped_stub_records"] = json.dumps(stub_counts, sort_keys=True)
    return build_archive(rows, meta=meta)


def build_tables(
    repo_path: str | os.PathLike[str] | None,
    out_dir: Path,
    *,
    tasks: Sequence[str] = tuple(TASKS),
    max_workers: int = 8,
) -> tuple[Path, ...]:
    """Grade the requested tasks and write one deterministic verdict table each."""
    repo = resolve_repo(repo_path)
    written: list[Path] = []
    for task in tasks:
        archive = build_task_archive(repo, task, max_workers=max_workers)
        out_path = out_dir / f"{task}.verdicts.csv.gz"
        write_archive(archive, out_path)
        written.append(out_path)
    return tuple(written)
