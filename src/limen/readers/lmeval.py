"""Reader for lm-evaluation-harness ``--log_samples`` output.

Input: a ``samples_<task>_<timestamp>.jsonl`` file, a model output directory
containing such files, or a directory of model directories. Every sample line is
one draw of its ``doc_id``; repeated runs of the identical configuration appear
as repeated lines for the same doc (same file with repeats, or sibling files
from re-runs), and become draws of one cell. If no doc ends up with k >= 2 the
reader refuses: limen needs repeated draws, and the fix (re-run the harness) is
named in the message.

The verdict comes from a binary metric field. When exactly one candidate metric
takes only values in {0, 1} across the lines it is auto-selected; otherwise the
reader refuses and lists the candidates for ``--metric`` (LMN-CORE-001: no
thresholding, ever).

``collected_at`` is the run timestamp parsed from each filename — per-run, not
per-draw, granularity (draws from one run share it; the drift guard counts the
ties). ``raw_sha256`` hashes the line's logged responses, enabling the
grader-defect check across re-runs.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from pathlib import Path

from ..errors import ReaderError
from ..model import Archive, VerdictRow, build_archive
from .base import ReaderOptions

_FILE_RE = re.compile(r"^samples_(?P<task>.+?)_(?P<ts>\d{4}-\d{2}-\d{2}T[\d\-.:]+)\.jsonl$")
# Structural keys of a sample line; everything else numeric-and-binary is a metric candidate.
_STRUCTURAL = {
    "doc_id", "doc", "target", "arguments", "resps", "filtered_resps",
    "doc_hash", "prompt_hash", "target_hash", "input_hash", "filter",
}


def _parse_name(path: Path) -> tuple[str, str | None]:
    m = _FILE_RE.match(path.name)
    if m:
        return m.group("task"), m.group("ts")
    if path.name.startswith("samples_") and path.name.endswith(".jsonl"):
        return path.name[len("samples_"):-len(".jsonl")], None
    raise ReaderError(f"{path}: not an lm-eval samples file (expected samples_<task>_*.jsonl)")


def _binary(value: object) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int | float) and float(value) in (0.0, 1.0):
        return int(value)
    return None


class LmEvalReader:
    name = "lm-eval"

    def sniff(self, path: Path) -> bool:
        if path.is_file():
            return _FILE_RE.match(path.name) is not None
        if path.is_dir():
            return next(path.rglob("samples_*.jsonl"), None) is not None
        return False

    def read(self, path: Path, options: ReaderOptions) -> Archive:
        return build_archive(
            self.rows(path, options),
            meta={"reader": self.name, "source": path.name},
            min_k=options.min_k,
        )

    def rows(self, path: Path, options: ReaderOptions) -> list[VerdictRow]:
        files = self._collect(path)
        lines = self._load_lines(files, path, options)
        by_task: dict[str, list[dict[str, object]]] = {}
        for rec in lines:
            by_task.setdefault(str(rec["__task"]), []).append(rec)
        rows: list[VerdictRow] = []
        # metric resolution is PER TASK: two tasks legitimately use different
        # binary metric names, and --metric applies only to tasks carrying it
        for task in sorted(by_task):
            task_lines = by_task[task]
            if options.metric is not None and any(
                options.metric in rec for rec in task_lines
            ):
                metric = options.metric
            else:
                metric = self._pick_metric(task_lines, path, task, options.metric)
            rows.extend(self._rows(task_lines, metric))
        return rows

    def _collect(self, path: Path) -> list[Path]:
        if path.is_file():
            return [path]
        files = sorted(path.rglob("samples_*.jsonl"))
        if not files:
            raise ReaderError(
                f"{path}: no samples_*.jsonl found; produce them with "
                "lm-eval ... --log_samples --output_path <dir>"
            )
        return files

    def _load_lines(
        self, files: list[Path], root: Path, options: ReaderOptions
    ) -> list[dict[str, object]]:
        out: list[dict[str, object]] = []
        timestamps: list[str | None] = []
        for file in files:
            task, ts = _parse_name(file)
            timestamps.append(ts)
            if options.model_name is not None:
                model = options.model_name
            elif file.parent != root and file.parent.name:
                model = file.parent.name
            else:
                model = root.name if root.is_dir() else "model"
            with open(file, encoding="utf-8") as f:
                for lineno, raw in enumerate(f, start=1):
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        rec = json.loads(raw)
                    except json.JSONDecodeError as exc:
                        raise ReaderError(f"{file}:{lineno}: invalid JSON") from exc
                    rec["__model"] = model
                    rec["__task"] = task
                    rec["__ts"] = ts
                    out.append(rec)
        if not out:
            raise ReaderError(f"{root}: samples files contained no lines")
        if any(t is None for t in timestamps):
            for rec in out:
                rec["__ts"] = None  # all-or-nothing across the archive
        return out

    def _pick_metric(
        self,
        lines: list[dict[str, object]],
        root: Path,
        task: str,
        requested: str | None,
    ) -> str:
        candidates: dict[str, bool] = {}
        for rec in lines:
            for key, value in rec.items():
                if key.startswith("__") or key in _STRUCTURAL or key.endswith("_stderr"):
                    continue
                if _binary(value) is None:
                    if isinstance(value, bool | int | float):
                        candidates[key] = False  # numeric but not binary: disqualified
                else:
                    candidates.setdefault(key, True)
        binary_keys = sorted(k for k, ok in candidates.items() if ok)
        if requested is not None:
            raise ReaderError(
                f"{root}: task {task!r} has no field {requested!r}; its binary metric "
                f"candidates are {binary_keys or 'none'}"
            )
        if len(binary_keys) == 1:
            return binary_keys[0]
        if not binary_keys:
            raise ReaderError(
                f"{root}: task {task!r}: no binary metric field found in the sample "
                "lines; limen needs a 0/1 verdict and never thresholds a score (pass "
                "--metric if a binary field exists under an unexpected name)"
            )
        raise ReaderError(
            f"{root}: task {task!r}: multiple binary metric fields found: "
            f"{binary_keys}; pass --metric to choose the one that is the verdict"
        )

    def _rows(self, lines: list[dict[str, object]], metric: str) -> Iterator[VerdictRow]:
        counters: dict[tuple[str, str, str], int] = {}
        for rec in lines:
            model = str(rec["__model"])
            task = str(rec["__task"])
            doc_id = rec.get("doc_id")
            if doc_id is None:
                raise ReaderError("sample line without doc_id; not a --log_samples file?")
            item_id = f"doc{doc_id}"
            value = rec.get(metric)
            verdict = _binary(value)
            if verdict is None:
                raise ReaderError(
                    f"metric {metric!r} has non-binary value {value!r} for doc {doc_id}; "
                    "limen never thresholds a score into a verdict"
                )
            key = (model, task, item_id)
            occurrence = counters.get(key, 0)
            counters[key] = occurrence + 1
            resps = rec.get("filtered_resps") or rec.get("resps")
            raw_hash = (
                "sha256:"
                + hashlib.sha256(
                    json.dumps(resps, sort_keys=True, ensure_ascii=True).encode()
                ).hexdigest()
                if resps is not None
                else None
            )
            ts = rec.get("__ts")
            yield VerdictRow(
                model=model,
                task=task,
                item_id=item_id,
                draw_id=str(occurrence),
                verdict=verdict,
                collected_at=str(ts) if ts is not None else None,
                raw_sha256=raw_hash,
            )
