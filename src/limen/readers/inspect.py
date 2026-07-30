"""Reader for inspect_ai ``.eval`` logs, at the per-epoch layer.

An ``.eval`` file is a zip archive with one JSON entry per (sample, epoch)
under ``samples/`` and run metadata in ``header.json``. This reader consumes
exactly the layer inspect's epoch reducers collapse: each epoch of each sample
becomes one draw of that item's cell. Multiple ``.eval`` files for the same
(task, model) stack: re-runs become additional draws, ordered by run start
time then epoch.

No inspect_ai import is involved (limen has zero runtime dependencies); the
zip and JSON are read directly, and the committed fixtures were produced by a
real inspect_ai run so the parsing is pinned to the actual format.

Verdicts come from a scorer's ``value``: ``"C"`` maps to 1, ``"I"`` to 0, and
exact 0/1 numerics map through. Anything else (``"P"``, ``"N"``, fractional
scores) is refused with the value named: limen never thresholds a score
(LMN-CORE-001). One scorer is auto-selected when a sample carries exactly one;
otherwise ``--metric`` names the scorer. Per-sample ``completed_at``
timestamps feed the drift guard when every sample in scope carries one.
"""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Any

from ..errors import ReaderError
from ..model import Archive, VerdictRow, build_archive
from .base import ReaderOptions

_SAMPLE_RE = re.compile(r"^samples/(?P<stem>.+)_epoch_(?P<epoch>\d+)\.json$")


def _verdict_from(value: object, scorer: str, sample_id: object, path: Path) -> int:
    if value == "C":
        return 1
    if value == "I":
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int | float) and float(value) in (0.0, 1.0):
        return int(value)
    raise ReaderError(
        f"{path.name}: scorer {scorer!r} has non-binary value {value!r} for sample "
        f"{sample_id!r}; limen never thresholds a score into a verdict"
    )


class InspectReader:
    name = "inspect"

    def sniff(self, path: Path) -> bool:
        if path.is_file():
            return path.name.endswith(".eval") and zipfile.is_zipfile(path)
        if path.is_dir():
            return any(
                p.name.endswith(".eval") and zipfile.is_zipfile(p)
                for p in path.rglob("*.eval")
            )
        return False

    def read(self, path: Path, options: ReaderOptions) -> Archive:
        return build_archive(
            self.rows(path, options),
            meta={"reader": self.name, "source": path.name},
            min_k=options.min_k,
        )

    def rows(self, path: Path, options: ReaderOptions) -> list[VerdictRow]:
        files = self._collect(path)
        rows: list[VerdictRow] = []
        timestamps_ok = True
        raw: list[tuple[str, str, str, str, int, str | None, str]] = []
        for run_index, file in enumerate(files):
            raw_entries, has_all_timestamps = self._read_file(file, options, run_index)
            timestamps_ok = timestamps_ok and has_all_timestamps
            raw.extend(raw_entries)
        for model, task, item_id, draw_id, verdict, completed_at, raw_hash in raw:
            rows.append(
                VerdictRow(
                    model=model,
                    task=task,
                    item_id=item_id,
                    draw_id=draw_id,
                    verdict=verdict,
                    collected_at=completed_at if timestamps_ok else None,
                    raw_sha256=raw_hash,
                )
            )
        return rows

    def _collect(self, path: Path) -> list[Path]:
        if path.is_file():
            return [path]
        files = sorted(p for p in path.rglob("*.eval") if zipfile.is_zipfile(p))
        if not files:
            raise ReaderError(f"{path}: no .eval logs found")
        return files

    def _read_file(
        self, path: Path, options: ReaderOptions, run_index: int
    ) -> tuple[list[tuple[str, str, str, str, int, str | None, str]], bool]:
        try:
            archive = zipfile.ZipFile(path)
        except zipfile.BadZipFile as exc:
            raise ReaderError(f"{path}: not a valid .eval (zip) file") from exc
        with archive:
            try:
                header = json.loads(archive.read("header.json"))
            except KeyError as exc:
                raise ReaderError(f"{path}: no header.json; not an .eval log") from exc
            eval_info = header.get("eval", {})
            task = str(eval_info.get("task") or "task")
            model = options.model_name or str(eval_info.get("model") or "model")
            run_stamp = f"{path.stem.split('_')[0]}-r{run_index:04d}"

            entries = []
            all_timestamped = True
            sample_names = [n for n in archive.namelist() if _SAMPLE_RE.match(n)]
            if not sample_names:
                raise ReaderError(
                    f"{path}: no samples/*_epoch_*.json entries; empty or truncated log"
                )
            for name in sorted(sample_names):
                match = _SAMPLE_RE.match(name)
                assert match is not None
                sample = json.loads(archive.read(name))
                scores: dict[str, Any] = sample.get("scores") or {}
                scorer = self._pick_scorer(scores, options, path, sample.get("id"))
                verdict = _verdict_from(
                    scores[scorer].get("value"), scorer, sample.get("id"), path
                )
                completed_at = sample.get("completed_at")
                if not isinstance(completed_at, str) or not completed_at:
                    completed_at = None
                    all_timestamped = False
                completion = self._completion(sample)
                entries.append(
                    (
                        model,
                        task,
                        str(sample.get("id", match.group("stem"))),
                        f"{run_stamp}-e{int(match.group('epoch')):04d}",
                        verdict,
                        completed_at,
                        "sha256:"
                        + hashlib.sha256(
                            json.dumps(completion, sort_keys=True, ensure_ascii=True).encode()
                        ).hexdigest(),
                    )
                )
            return entries, all_timestamped

    def _pick_scorer(
        self,
        scores: dict[str, Any],
        options: ReaderOptions,
        path: Path,
        sample_id: object,
    ) -> str:
        if not scores:
            raise ReaderError(
                f"{path.name}: sample {sample_id!r} carries no scores; grade the log "
                "before handing it to limen"
            )
        if options.metric is not None:
            if options.metric in scores:
                return options.metric
            raise ReaderError(
                f"{path.name}: sample {sample_id!r} has no scorer {options.metric!r}; "
                f"available: {sorted(scores)}"
            )
        if len(scores) == 1:
            return next(iter(scores))
        raise ReaderError(
            f"{path.name}: multiple scorers {sorted(scores)}; pass --metric to choose "
            "the one that is the verdict"
        )

    def _completion(self, sample: dict[str, Any]) -> Any:
        output = sample.get("output") or {}
        choices = output.get("choices") or []
        if choices:
            return choices[0].get("message", {}).get("content")
        return None
