"""The generic long-format CSV reader and its deterministic writer.

This is the canonical on-disk form of the long verdict table (spec ruling
LMN-CORE-005) and the entry path for any source limen has no native reader for.
Columns: ``model, task, item_id, draw_id, verdict`` required; ``score,
collected_at, model_version, raw_sha256`` optional, empty string meaning absent.
``verdict`` must be literally ``0`` or ``1`` — limen never thresholds a score
into a verdict (LMN-CORE-001).

The writer is deterministic: fixed header, canonical row order, gzip mtime=0.
The calibration corpus and ``limen synth`` both write through it.
"""

from __future__ import annotations

import csv
import gzip
import io
import re
from collections.abc import Iterator
from pathlib import Path

from ..canonical import write_gzip_deterministic
from ..errors import ReaderError
from ..model import Archive, VerdictRow, build_archive
from .base import ReaderOptions

REQUIRED = ("model", "task", "item_id", "draw_id", "verdict")
OPTIONAL = ("score", "collected_at", "model_version", "raw_sha256")
HEADER = REQUIRED + OPTIONAL
#: per-item stratum labels ride as additional columns (LMN-CORE-008)
LABEL_COLUMN_RE = re.compile(r"label_([a-z0-9_]+)")


def _open_text(path: Path) -> io.TextIOBase:
    if path.name.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return open(path, encoding="utf-8", newline="")  # noqa: SIM115


class LongCsvReader:
    name = "long-csv"

    def sniff(self, path: Path) -> bool:
        if not path.is_file():
            return False
        if not (path.name.endswith(".csv") or path.name.endswith(".csv.gz")):
            return False
        try:
            with _open_text(path) as f:
                first = f.readline()
        except OSError:
            return False
        fields = [c.strip() for c in first.strip().split(",")]
        return all(col in fields for col in REQUIRED)

    def read(self, path: Path, options: ReaderOptions) -> Archive:
        return build_archive(
            self.rows(path, options),
            meta={"reader": self.name, "source": path.name},
            min_k=options.min_k,
        )

    def rows(self, path: Path, options: ReaderOptions) -> list[VerdictRow]:
        return list(self._rows(path))

    def _rows(self, path: Path) -> Iterator[VerdictRow]:
        with _open_text(path) as f:
            reader = csv.DictReader(f)
            header = reader.fieldnames
            if header is None:
                raise ReaderError(f"{path}: empty file, no CSV header")
            duplicated = sorted({c for c in header if header.count(c) > 1})
            if duplicated:
                raise ReaderError(
                    f"{path}: duplicated column(s) {duplicated}; csv keeps only "
                    "the last of a duplicated column, which silently drops data"
                )
            missing = [c for c in REQUIRED if c not in header]
            if missing:
                raise ReaderError(
                    f"{path}: missing required column(s) {missing}; "
                    f"the long-csv format needs {list(REQUIRED)}"
                )
            label_keys = sorted(
                m.group(1) for c in header if (m := LABEL_COLUMN_RE.fullmatch(c))
            )
            unknown = [
                c for c in header
                if c not in HEADER and not LABEL_COLUMN_RE.fullmatch(c)
            ]
            if unknown:
                raise ReaderError(
                    f"{path}: unknown column(s) {unknown}; "
                    f"long-csv accepts exactly {list(HEADER)} plus label_<name> columns"
                )
            for lineno, rec in enumerate(reader, start=2):
                verdict_raw = (rec.get("verdict") or "").strip()
                if verdict_raw not in ("0", "1"):
                    raise ReaderError(
                        f"{path}:{lineno}: verdict must be literally 0 or 1, got "
                        f"{verdict_raw!r}; limen never derives a verdict from a score"
                    )
                score_raw = (rec.get("score") or "").strip()
                try:
                    score = float(score_raw) if score_raw else None
                except ValueError as exc:
                    raise ReaderError(
                        f"{path}:{lineno}: score {score_raw!r} is not a number"
                    ) from exc
                labels = tuple(
                    (key, value)
                    for key in label_keys
                    if (value := (rec.get(f"label_{key}") or "").strip())
                )
                yield VerdictRow(
                    model=(rec.get("model") or "").strip(),
                    task=(rec.get("task") or "").strip(),
                    item_id=(rec.get("item_id") or "").strip(),
                    draw_id=(rec.get("draw_id") or "").strip(),
                    verdict=int(verdict_raw),
                    score=score,
                    collected_at=(rec.get("collected_at") or "").strip() or None,
                    model_version=(rec.get("model_version") or "").strip() or None,
                    raw_sha256=(rec.get("raw_sha256") or "").strip() or None,
                    labels=labels or None,
                )


def write_archive(archive: Archive, path: Path) -> None:
    """Write the archive as long CSV, byte-deterministically (gzip mtime=0 for .gz).
    Label columns appear, sorted, only when any row carries labels, so label-free
    archives keep their exact pre-label bytes (LMN-CORE-008)."""
    rows = archive.rows()
    label_keys = sorted({name for row in rows if row.labels for name, _ in row.labels})
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(HEADER + tuple(f"label_{key}" for key in label_keys))
    for row in rows:
        row_labels = dict(row.labels) if row.labels else {}
        writer.writerow(
            (
                row.model,
                row.task,
                row.item_id,
                row.draw_id,
                str(row.verdict),
                "" if row.score is None else repr(row.score),
                row.collected_at or "",
                row.model_version or "",
                row.raw_sha256 or "",
            )
            + tuple(row_labels.get(key, "") for key in label_keys)
        )
    data = buf.getvalue().encode("utf-8")
    if path.name.endswith(".gz"):
        write_gzip_deterministic(path, data)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
