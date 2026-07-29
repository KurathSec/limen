"""Per-item verdict flakiness: limb (a) of the instrument.

The per-item rate is the U-statistic ``f = s(k-s) / C(k,2)`` — the fraction of
draw pairs whose verdict differs, unbiased for the pairwise-disagreement
probability ``2q(1-q)`` whatever k is (spec ruling LMN-FLK-001). Items classify
as always_pass / always_fail / mixed; ``mixed`` iff ``f > 0``.

The constant-verdict fraction relates to the published metric TARa@N (Atil et
al., *Non-Determinism of "Deterministic" LLM Settings*, arXiv:2408.04667) as an
**upper bound**: TARa@N counts agreement of parsed answers, and two different
wrong answers grade to the same 0 verdict, so verdict constancy >= TARa@N with
equality only when every always-fail cell's answers coincide — which a verdict
table cannot check. The field says so, is emitted only at uniform k, and never
borrows the metric's name outright (LMN-FLK-002). Constancy is not correctness
either way: a constant-but-wrong verdict is invisible here (scope code
CONSTANCY_IS_NOT_CORRECTNESS).
"""

from __future__ import annotations

from typing import Any, Literal

from .canonical import counted, fmt_float
from .model import Archive, Cell
from .stats import quantile_lower

TARA_NOTE = (
    "upper bound on TARa@N (Atil et al., arXiv:2408.04667): verdict constancy; "
    "parsed-answer agreement can be lower on always-fail items"
)


def item_flakiness(s: int, k: int) -> float:
    """f = s(k-s)/C(k,2): the fraction of draw pairs whose verdict differs."""
    if k < 2:
        raise ValueError(f"flakiness needs k >= 2, got k={k}")
    if not 0 <= s <= k:
        raise ValueError(f"passes s={s} outside [0, k={k}]")
    return 2.0 * s * (k - s) / (k * (k - 1))


def classify_item(verdicts: tuple[int, ...]) -> Literal["always_pass", "always_fail", "mixed"]:
    s = sum(verdicts)
    if s == len(verdicts):
        return "always_pass"
    if s == 0:
        return "always_fail"
    return "mixed"


def discordant_pairs(cell: Cell) -> int:
    """s(k-s): the number of draw pairs of this cell whose verdicts differ."""
    return cell.passes * (cell.k - cell.passes)


def model_task_flakiness(archive: Archive, model: str, task: str) -> dict[str, Any]:
    """The per-(model, task) flakiness block, every count with its denominator."""
    items = archive.items(model, task)
    if not items:
        raise ValueError(f"no items for ({model!r}, {task!r})")
    cells = [archive.cell(model, task, item) for item in items]
    n = len(cells)
    ks = {c.k for c in cells}
    k_uniform = ks.pop() if len(ks) == 1 else None

    f_values = sorted(item_flakiness(c.passes, c.k) for c in cells)
    classes = [classify_item(c.verdicts) for c in cells]
    n_pass = classes.count("always_pass")
    n_fail = classes.count("always_fail")
    n_mixed = classes.count("mixed")
    mixed_f = [item_flakiness(c.passes, c.k) for c in cells if classify_item(c.verdicts) == "mixed"]

    total_disc = sum(discordant_pairs(c) for c in cells)
    total_pairs = sum(c.k * (c.k - 1) // 2 for c in cells)

    return {
        "n_items": n,
        "k_uniform": k_uniform,
        "always_pass": counted(n_pass, n),
        "always_fail": counted(n_fail, n),
        "mixed": counted(n_mixed, n),
        "constant_verdict_fraction": (
            fmt_float((n_pass + n_fail) / n) if k_uniform is not None else None
        ),
        "constant_verdict_n": k_uniform,
        "tara_upper_bound_note": TARA_NOTE if k_uniform is not None else None,
        "mean_flakiness": fmt_float(sum(f_values) / n),
        "mean_flakiness_mixed_only": (
            fmt_float(sum(mixed_f) / len(mixed_f)) if mixed_f else None
        ),
        "pooled_pair_discordance": counted(total_disc, total_pairs),
        "f_max": fmt_float(f_values[-1]),
        "f_p50": fmt_float(quantile_lower(f_values, 0.50)),
        "f_p90": fmt_float(quantile_lower(f_values, 0.90)),
        "f_p99": fmt_float(quantile_lower(f_values, 0.99)),
    }


def task_pooled_flakiness(archive: Archive, task: str) -> dict[str, Any]:
    """Task-level pooling: cell-pooled counts (unit item x model) and the item-union
    count over aligned items (the denominator the stable-set analysis uses)."""
    models = archive.models_for(task)
    total_cells = 0
    total_mixed = 0
    for model in models:
        for item in archive.items(model, task):
            total_cells += 1
            if classify_item(archive.cell(model, task, item).verdicts) == "mixed":
                total_mixed += 1
    aligned = archive.aligned_items(task)
    union_mixed = sum(
        1
        for item in aligned
        if any(
            classify_item(archive.cell(model, task, item).verdicts) == "mixed"
            for model in models
        )
    )
    return {
        "cell_pooled_mixed": counted(total_mixed, total_cells),
        "item_union_mixed": counted(union_mixed, len(aligned)) if aligned else None,
        "n_items_aligned": len(aligned),
        "alignment_excluded": {
            model: count for model, count in sorted(archive.alignment_excluded(task).items())
        },
    }
