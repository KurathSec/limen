"""The grader-defect count: flakiness manufactured by the grader, not the model.

A verdict flip whose raw completion is byte-identical across the disagreeing
draws is a grader defect (LMN-GRD-001): the model produced the same bytes and
the grader decided differently. Identity is byte identity of the stored hash —
no strip, no case-fold, no normalization; whitespace sensitivity is precisely
what is being hunted. The count is reported as a share of all discordant draw
pairs (it composes with the flakiness U-statistic, which counts the same
pairs), and separately as affected items. The adjusted mean subtracts only the
*detected* defect pairs — it is "flakiness excluding detected grader defects",
not a proof the remainder is model-attributable (a grader can also be
inconsistent across texts that differ, which byte identity cannot see).

When raw hashes are absent the state is UNAVAILABLE with null counts — never 0:
"no defects found" is a finding, "no text to check" is not (LMN-GRD-002).
Constancy is not correctness either way: a constant-but-wrong completion is
invisible to this check.
"""

from __future__ import annotations

from typing import Any

from .canonical import counted, fmt_float
from .flakiness import discordant_pairs, item_flakiness
from .model import Archive, Cell

CONSTANCY_NOTE = (
    "this check detects grader nondeterminism only, not grader wrongness: "
    "a constant-but-wrong completion is invisible here"
)


def _cell_defect_pairs(cell: Cell) -> int:
    """Unordered draw pairs of this cell with identical raw bytes and differing verdicts."""
    assert cell.raw_sha256 is not None
    groups: dict[str, list[int]] = {}
    for i, h in enumerate(cell.raw_sha256):
        groups.setdefault(h, []).append(i)
    pairs = 0
    for indices in groups.values():
        ones = sum(cell.verdicts[i] for i in indices)
        zeros = len(indices) - ones
        pairs += ones * zeros
    return pairs


def grader_defects(archive: Archive, model: str, task: str) -> dict[str, Any]:
    items = archive.items(model, task)
    cells = [archive.cell(model, task, item) for item in items]
    n_with_text = sum(1 for c in cells if c.raw_sha256 is not None)
    if n_with_text < len(cells):
        return {
            "state": "UNAVAILABLE",
            "n_cells_with_text": n_with_text,
            "n_cells": len(cells),
            "defect_pairs": None,
            "defect_items": None,
            "mean_flakiness_excluding_detected_defects": None,
            "note": CONSTANCY_NOTE,
        }
    total_discordant = sum(discordant_pairs(c) for c in cells)
    per_cell = [_cell_defect_pairs(c) for c in cells]
    defect_pairs = sum(per_cell)
    defect_items = sum(1 for p in per_cell if p > 0)
    n_mixed = sum(1 for c in cells if 0 < c.passes < c.k)
    adjusted = [
        (discordant_pairs(c) - p) / (c.k * (c.k - 1) // 2)
        for c, p in zip(cells, per_cell, strict=True)
    ]
    raw_mean = sum(item_flakiness(c.passes, c.k) for c in cells) / len(cells)
    return {
        "state": "AVAILABLE",
        "n_cells_with_text": n_with_text,
        "n_cells": len(cells),
        "defect_pairs": counted(defect_pairs, total_discordant),
        "defect_items": counted(defect_items, n_mixed),
        "mean_flakiness_raw": fmt_float(raw_mean),
        "mean_flakiness_excluding_detected_defects": fmt_float(sum(adjusted) / len(adjusted)),
        "note": CONSTANCY_NOTE,
    }
