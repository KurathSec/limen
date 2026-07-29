"""The long verdict table and its cell view: limen's single input contract.

One row per ``(model, task, item_id, draw_id)`` with a binary verdict
(spec ruling LMN-CORE-001: limen never thresholds a score into a verdict).
Rows compile into cells — all draws of one ``(model, task, item)`` in canonical
draw order — and every analyzer consumes cells, never raw rows.

Invariants enforced here, hard (LMN-CORE-002):
- verdict is 0 or 1;
- no duplicate ``(model, task, item_id, draw_id)``;
- a cell's optional per-draw fields (score, collected_at, model_version,
  raw_sha256) are present for all of its draws or none of them;
- cells with fewer than ``min_k`` draws are excluded *and counted*; the build
  refuses only when nothing remains (LMN-CORE-003).

Canonical draw order (LMN-CORE-004): if every draw_id in the table parses as an
integer, draws order numerically; otherwise lexicographically by the raw string.
"Draw position d" everywhere in limen means the d-th draw in this order.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from .errors import TableError

_KEY_FIELDS = ("model", "task", "item_id", "draw_id")


@dataclass(frozen=True, slots=True)
class VerdictRow:
    """One draw of one item for one model on one task."""

    model: str
    task: str
    item_id: str
    draw_id: str
    verdict: int
    score: float | None = None
    collected_at: str | None = None
    model_version: str | None = None
    raw_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class Cell:
    """All draws of one (model, task, item), in canonical draw order."""

    verdicts: tuple[int, ...]
    draw_ids: tuple[str, ...]
    scores: tuple[float, ...] | None
    collected_at: tuple[str, ...] | None
    model_version: tuple[str, ...] | None
    raw_sha256: tuple[str, ...] | None

    @property
    def k(self) -> int:
        return len(self.verdicts)

    @property
    def passes(self) -> int:
        return sum(self.verdicts)


@dataclass(frozen=True)
class Archive:
    """The compiled table: cells keyed by (model, task, item_id), plus exclusion counts."""

    cells: Mapping[tuple[str, str, str], Cell]
    meta: Mapping[str, str]
    excluded_low_k: Mapping[tuple[str, str], int]
    _items_index: dict[tuple[str, str], tuple[str, ...]] = field(
        init=False, repr=False, compare=False, default_factory=dict
    )
    _digest: str = field(init=False, repr=False, compare=False, default="")

    def __post_init__(self) -> None:
        index: dict[tuple[str, str], list[str]] = {}
        for model, task, item_id in self.cells:
            index.setdefault((model, task), []).append(item_id)
        for key, items in index.items():
            self._items_index[key] = tuple(sorted(items))

    @property
    def models(self) -> tuple[str, ...]:
        return tuple(sorted({m for m, _, _ in self.cells}))

    @property
    def tasks(self) -> tuple[str, ...]:
        return tuple(sorted({t for _, t, _ in self.cells}))

    def models_for(self, task: str) -> tuple[str, ...]:
        return tuple(sorted({m for m, t, _ in self.cells if t == task}))

    def items(self, model: str, task: str) -> tuple[str, ...]:
        return self._items_index.get((model, task), ())

    def cell(self, model: str, task: str, item_id: str) -> Cell:
        return self.cells[(model, task, item_id)]

    def aligned_items(self, task: str) -> tuple[str, ...]:
        """Items present for every model of the task, sorted (the comparison substrate)."""
        models = self.models_for(task)
        if not models:
            return ()
        common: set[str] = set(self.items(models[0], task))
        for model in models[1:]:
            common &= set(self.items(model, task))
        return tuple(sorted(common))

    def alignment_excluded(self, task: str) -> dict[str, int]:
        """Per model: how many of its items fell out of the aligned intersection."""
        aligned = set(self.aligned_items(task))
        return {
            model: len(self.items(model, task)) - len(aligned)
            for model in self.models_for(task)
        }

    def common_k(self, task: str) -> int | None:
        """The uniform k across all aligned cells of the task, or None if ragged."""
        ks = {
            self.cell(model, task, item).k
            for model in self.models_for(task)
            for item in self.aligned_items(task)
        }
        if len(ks) == 1:
            return ks.pop()
        return None

    def rows(self) -> tuple[VerdictRow, ...]:
        """The table back in long form, in canonical sort order."""
        out: list[VerdictRow] = []
        for (model, task, item_id), cell in sorted(self.cells.items()):
            for i, draw_id in enumerate(cell.draw_ids):
                out.append(
                    VerdictRow(
                        model=model,
                        task=task,
                        item_id=item_id,
                        draw_id=draw_id,
                        verdict=cell.verdicts[i],
                        score=cell.scores[i] if cell.scores is not None else None,
                        collected_at=cell.collected_at[i] if cell.collected_at else None,
                        model_version=cell.model_version[i] if cell.model_version else None,
                        raw_sha256=cell.raw_sha256[i] if cell.raw_sha256 else None,
                    )
                )
        return tuple(out)

    def dataset_digest(self) -> str:
        """sha256 pinning the FULL input — including rows excluded for low k —
        so a report and its exclusion counts are functions of the digest. Rows
        are encoded unambiguously (JSON per line, no injectable separators)."""
        return self._digest


def _row_digest(rows: list[VerdictRow]) -> str:
    import json as _json

    h = hashlib.sha256()
    for row in sorted(
        rows, key=lambda r: (r.model, r.task, r.item_id, r.draw_id)
    ):
        line = _json.dumps(
            [
                row.model,
                row.task,
                row.item_id,
                row.draw_id,
                row.verdict,
                None if row.score is None else repr(row.score),
                row.collected_at,
                row.model_version,
                row.raw_sha256,
            ],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        h.update(line.encode("utf-8"))
        h.update(b"\n")
    return f"sha256:{h.hexdigest()}"


def build_archive(
    rows: Iterable[VerdictRow],
    *,
    meta: Mapping[str, str] | None = None,
    min_k: int = 2,
) -> Archive:
    """Compile rows into an Archive, enforcing every table invariant."""
    if min_k < 2:
        raise TableError("min_k must be >= 2: one draw cannot be observed to flip")

    grouped: dict[tuple[str, str, str], list[VerdictRow]] = {}
    seen: set[tuple[str, str, str, str]] = set()
    all_rows: list[VerdictRow] = []
    all_numeric = True
    n_rows = 0
    for row in rows:
        n_rows += 1
        for field_name in ("model", "task", "item_id", "draw_id"):
            if not getattr(row, field_name).strip():
                raise TableError(
                    f"empty {field_name} at row {n_rows}: identity fields must be "
                    "non-empty, non-whitespace strings"
                )
        if row.verdict not in (0, 1):
            raise TableError(
                f"verdict must be 0 or 1, got {row.verdict!r} at "
                f"({row.model!r}, {row.task!r}, {row.item_id!r}, draw {row.draw_id!r}); "
                "limen never derives a verdict from a score"
            )
        key4 = (row.model, row.task, row.item_id, row.draw_id)
        if key4 in seen:
            raise TableError(f"duplicate (model, task, item_id, draw_id): {key4!r}")
        seen.add(key4)
        all_rows.append(row)
        if all_numeric:
            try:
                int(row.draw_id)
            except ValueError:
                all_numeric = False
        grouped.setdefault((row.model, row.task, row.item_id), []).append(row)
    if n_rows == 0:
        raise TableError("no rows: the input contained no verdicts")

    cells: dict[tuple[str, str, str], Cell] = {}
    excluded: dict[tuple[str, str], int] = {}
    for key, cell_rows in grouped.items():
        model, task, _item = key
        if len(cell_rows) < min_k:
            excluded[(model, task)] = excluded.get((model, task), 0) + 1
            continue
        if all_numeric:
            # tiebreak on the raw string so "1" vs "01" orders deterministically
            cell_rows.sort(key=lambda r: (int(r.draw_id), r.draw_id))
        else:
            cell_rows.sort(key=lambda r: r.draw_id)
        cells[key] = _compile_cell(key, cell_rows)

    if not cells:
        raise TableError(
            f"no cell has k >= {min_k} draws; limen needs repeated draws of the same "
            "configuration (re-run the evaluation with repeats/epochs >= 2)"
        )
    archive = Archive(cells=cells, meta=dict(meta or {}), excluded_low_k=excluded)
    object.__setattr__(archive, "_digest", _row_digest(all_rows))
    return archive


def _compile_cell(key: tuple[str, str, str], cell_rows: list[VerdictRow]) -> Cell:
    def optional(name: str) -> tuple[str, ...] | None:
        values = [getattr(r, name) for r in cell_rows]
        present = [v for v in values if v is not None]
        if not present:
            return None
        if len(present) != len(values):
            raise TableError(
                f"cell {key!r}: field {name!r} is present for {len(present)} of "
                f"{len(values)} draws; a cell's optional fields are all-or-nothing"
            )
        return tuple(present)

    score_values = [r.score for r in cell_rows]
    scores_present = [s for s in score_values if s is not None]
    scores: tuple[float, ...] | None
    if not scores_present:
        scores = None
    elif len(scores_present) != len(score_values):
        raise TableError(
            f"cell {key!r}: field 'score' is present for {len(scores_present)} of "
            f"{len(score_values)} draws; a cell's optional fields are all-or-nothing"
        )
    else:
        scores = tuple(scores_present)

    return Cell(
        verdicts=tuple(r.verdict for r in cell_rows),
        draw_ids=tuple(r.draw_id for r in cell_rows),
        scores=scores,
        collected_at=optional("collected_at"),
        model_version=optional("model_version"),
        raw_sha256=optional("raw_sha256"),
    )
