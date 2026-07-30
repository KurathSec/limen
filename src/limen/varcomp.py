"""Variance components: the crossed items x draws decomposition, subordinated.

The estimator is exact ANOVA method-of-moments on the balanced two-facet
crossed design (G-theory's p x o), computed on integers in ``Fraction``
(LMN-VAR-001). For binary verdicts Y and per-item pass counts s_i, per-draw
pass counts t_d, total T over n items and k draws:

    SS_item     = (sum s_i^2)/k - T^2/(nk)          df = n-1
    SS_draw     = (sum t_d^2)/n - T^2/(nk)          df = k-1
    SS_residual = SS_total - SS_item - SS_draw      df = (n-1)(k-1)
    SS_total    = T - T^2/(nk)                      (Y^2 = Y for binary data)

    E[MS_item] = s2_res + k*s2_item,  E[MS_draw] = s2_res + n*s2_draw,
    E[MS_residual] = s2_res

A likelihood GLMM is deliberately not used: not computable pure-stdlib, not
byte-deterministic, and its components live on a link scale that does not
decompose the observed score. Negative moment estimates truncate to zero with
the raw value printed. Intervals are seeded item-bootstrap percentiles
(LMN-VAR-002; Satterthwaite rejected: continuous df with no stdlib chi-square
inverse, Bernoulli mean squares are not scaled chi-squares, truncation breaks
the pivot).

Everything here is a subordinate diagnostic: 'draw' is a bucket
(NO_FACTOR_ATTRIBUTION), the gate never reads this section (LMN-VAR-004), and
the fixed low-k warning fires whenever the draw facet has fewer than
``DRAW_LEVELS_FLOOR`` levels (LMN-VAR-003). The model facet is descriptive,
never a component (LMN-VAR-005). The design effect and planning numbers
(LMN-VAR-006) follow Kalibera & Jones, already limen's MDD authority.

One identity worth knowing (test-pinned): the sample variance of the k
single-draw scores equals MS_draw / n exactly, so the shipped
``noise_floor.score_sd`` is the draw-facet mean square in disguise; this
section decomposes a number the report already prints.
"""

from __future__ import annotations

import math
from fractions import Fraction
from random import Random
from typing import Any

from .canonical import counted, derive_seed, fmt_float
from .model import Archive
from .noise import MDD_CITATION
from .ranking import DrawScores
from .stats import quantile_lower

DRAW_LEVELS_FLOOR = 20

DESIGN_NOTE = (
    "items x draws crossed, one observation per cell (G-theory p x o); draw "
    "position in canonical order is the crossing key (LMN-CORE-004)"
)
LOW_K_NOTE = (
    "the draw facet has fewer than 20 levels: the draw and residual components "
    "rest on df_draw = k-1 and are wide by construction; this section is a "
    "subordinate diagnostic and never a headline (LMN-VAR-003)"
)
BUCKET_NOTE = (
    "'draw' is a bucket holding everything that varies between two identical "
    "calls; the components size the bucket and attribute nothing inside it "
    "(NO_FACTOR_ATTRIBUTION)"
)
NEVER_HEADLINE_NOTE = (
    "subordinate diagnostic: the gate never reads this section (LMN-VAR-004), "
    "and no top-line summary prints it"
)
MODEL_FACET_NOTE = (
    "the models are fixed choices, not a sample from a model universe; "
    "between_model_variance describes this panel's pooled scores; it is not a "
    "variance component and never a quality ranking (LMN-VAR-005)"
)
DEFF_DEFINITION = (
    "deff = 1 + (k-1)*icc_item + (n-1)*icc_draw = "
    "(k*s2_item + n*s2_draw + s2_residual) / s2_total; n_eff = nk / deff"
)
PLANNING_NOTE = (
    "the draw-facet contribution to the pooled score scales exactly as 1/k, so "
    "halving it always doubles k; no sufficiency certificate is issued for any "
    "k (NO_K1_CERTIFICATE)"
)
INTERVAL_ASSUMPTIONS: tuple[str, ...] = (
    "items are resampled with their whole draw vectors, preserving within-item dependence",
    "the draw-component interval is conditional on the observed k draws, not draws untaken",
    "percentile intervals undercover for facets with few levels; see the low-k warning",
    "intervals are taken over truncated estimates; the truncation share is printed",
)


def two_facet_sums(verdict_rows: list[tuple[int, ...]]) -> tuple[int, int, int, int, int]:
    """(n, k, T, sum s_i^2, sum t_d^2) for a balanced item x draw matrix."""
    n = len(verdict_rows)
    if n == 0:
        raise ValueError("no items")
    k = len(verdict_rows[0])
    if any(len(row) != k for row in verdict_rows):
        raise ValueError("ragged draw vectors; balanced design required")
    total = sum(sum(row) for row in verdict_rows)
    sum_sq_items = sum(sum(row) ** 2 for row in verdict_rows)
    sum_sq_draws = sum(sum(row[d] for row in verdict_rows) ** 2 for d in range(k))
    return n, k, total, sum_sq_items, sum_sq_draws


def mean_squares(
    n: int, k: int, total: int, sum_sq_items: int, sum_sq_draws: int
) -> tuple[Fraction, Fraction, Fraction]:
    """(ms_item, ms_draw, ms_residual), exact. Requires n >= 2 and k >= 2."""
    if n < 2 or k < 2:
        raise ValueError("EMS needs n_items >= 2 and k >= 2 (zero df otherwise)")
    correction = Fraction(total * total, n * k)
    ss_total = Fraction(total) - correction
    ss_item = Fraction(sum_sq_items, k) - correction
    ss_draw = Fraction(sum_sq_draws, n) - correction
    ss_residual = ss_total - ss_item - ss_draw
    return (
        ss_item / (n - 1),
        ss_draw / (k - 1),
        ss_residual / ((n - 1) * (k - 1)),
    )


def raw_components(
    ms: tuple[Fraction, Fraction, Fraction], n: int, k: int
) -> tuple[Fraction, Fraction, Fraction]:
    """Method-of-moments (item, draw, residual); item/draw may be negative."""
    ms_item, ms_draw, ms_residual = ms
    return (
        (ms_item - ms_residual) / k,
        (ms_draw - ms_residual) / n,
        ms_residual,
    )


def _component_block(raw: Fraction) -> dict[str, Any]:
    truncated = raw < 0
    return {
        "estimate": fmt_float(float(raw)) if not truncated else 0.0,
        "raw": fmt_float(float(raw)),
        "truncated": truncated,
    }


def design_effect(
    item: float, draw: float, residual: float, n: int, k: int
) -> tuple[float | None, float | None]:
    total = item + draw + residual
    if total == 0:
        return None, None
    deff = (k * item + n * draw + residual) / total
    return deff, (n * k) / deff


def bootstrap_components(
    verdict_rows: list[tuple[int, ...]],
    *,
    seed_parts: tuple[str | int, ...],
    replicates: int,
) -> dict[str, dict[str, Any]]:
    """Percentile CIs per component from a seeded item bootstrap (whole draw
    vectors travel with their items)."""
    n = len(verdict_rows)
    values: dict[str, list[float]] = {"item": [], "draw": [], "residual": []}
    truncated_counts = {"item": 0, "draw": 0, "residual": 0}
    effective = 0
    for b in range(replicates):
        rng = Random(derive_seed(*seed_parts, b))
        sample = [verdict_rows[rng.randrange(n)] for _ in range(n)]
        try:
            ms = mean_squares(*two_facet_sums(sample))
        except ValueError:
            continue
        raw = raw_components(ms, n, len(sample[0]))
        effective += 1
        for name, value in zip(("item", "draw", "residual"), raw, strict=True):
            if value < 0:
                truncated_counts[name] += 1
                values[name].append(0.0)
            else:
                values[name].append(float(value))
    out: dict[str, dict[str, Any]] = {}
    for name, series in values.items():
        if not series:
            out[name] = {"ci95": None, "boot_share_truncated": None}
            continue
        ordered = sorted(series)
        out[name] = {
            "ci95": {
                "lo": fmt_float(quantile_lower(ordered, 0.025)),
                "hi": fmt_float(quantile_lower(ordered, 0.975)),
            },
            "boot_share_truncated": fmt_float(truncated_counts[name] / effective),
        }
    return out


def _decompose(
    verdict_rows: list[tuple[int, ...]],
    *,
    seed_parts: tuple[str | int, ...],
    replicates: int,
) -> dict[str, Any]:
    n, k, total, ssi, ssd = two_facet_sums(verdict_rows)
    ms = mean_squares(n, k, total, ssi, ssd)
    raw = raw_components(ms, n, k)
    est = tuple(max(value, Fraction(0)) for value in raw)
    boot = bootstrap_components(
        verdict_rows, seed_parts=seed_parts, replicates=replicates
    )
    components = {}
    for name, raw_v in zip(("item", "draw", "residual"), raw, strict=True):
        components[name] = {**_component_block(raw_v), **boot[name]}
    total_var = float(sum(est))
    shares = {
        name: (fmt_float(float(value) / total_var) if total_var > 0 else None)
        for name, value in zip(("item", "draw", "residual"), est, strict=True)
    }
    icc_item = float(est[0]) / total_var if total_var > 0 else None
    icc_draw = float(est[1]) / total_var if total_var > 0 else None
    deff, n_eff = design_effect(float(est[0]), float(est[1]), float(est[2]), n, k)

    # planning: Var(pooled) = A + B/k with A = s2_item/n, B = s2_draw + s2_res/n
    a_term = float(est[0]) / n
    b_term = float(est[1]) + float(est[2]) / n
    pooled_var = a_term + b_term / k
    return {
        "design": DESIGN_NOTE,
        "n_items": n,
        "k": k,
        "grand_mean": counted(total, n * k),
        "mean_squares": {
            "item": fmt_float(float(ms[0])),
            "draw": fmt_float(float(ms[1])),
            "residual": fmt_float(float(ms[2])),
            "df_item": n - 1,
            "df_draw": k - 1,
            "df_residual": (n - 1) * (k - 1),
        },
        "components": components,
        "shares": shares,
        "icc_item": fmt_float(icc_item) if icc_item is not None else None,
        "icc_draw": fmt_float(icc_draw) if icc_draw is not None else None,
        "design_effect": {
            "deff": fmt_float(deff) if deff is not None else None,
            "n_eff": fmt_float(n_eff) if n_eff is not None else None,
            "definition": DEFF_DEFINITION,
        },
        "planning": {
            "model_implied_single_draw_score_sd": fmt_float(math.sqrt(float(ms[1]) / n)),
            "pooled_sd_at_observed_k": fmt_float(math.sqrt(pooled_var)),
            "draw_facet_share_of_pooled_variance": (
                fmt_float((b_term / k) / pooled_var) if pooled_var > 0 else None
            ),
            "k_to_halve_draw_contribution": 2 * k,
            "k_where_item_facet_dominates": (
                math.ceil(b_term / a_term) if a_term > 0 and b_term > 0 else None
            ),
            "note": PLANNING_NOTE,
            "citation": MDD_CITATION,
        },
        "interval": {
            "method": "percentile bootstrap over items; cells resampled with their whole draw vectors",
            "replicates": replicates,
            "seed_procedure": "sha256(rulings_version|task|model|varcomp-bootstrap|replicate_index)",
            "assumptions": list(INTERVAL_ASSUMPTIONS),
        },
        "low_draw_levels": k < DRAW_LEVELS_FLOOR,
        "draw_levels_floor": DRAW_LEVELS_FLOOR,
        "low_k_note": LOW_K_NOTE if k < DRAW_LEVELS_FLOOR else None,
        "bucket_note": BUCKET_NOTE,
        "never_headline_note": NEVER_HEADLINE_NOTE,
        "degenerate_all_constant": total_var == 0.0,
    }


def _unavailable(reason: str) -> dict[str, Any]:
    return {
        "state": "UNAVAILABLE",
        "reason": reason,
        "bucket_note": BUCKET_NOTE,
        "never_headline_note": NEVER_HEADLINE_NOTE,
    }


def mt_variance_components(
    archive: Archive,
    model: str,
    task: str,
    *,
    rulings_version: str,
    replicates: int,
) -> dict[str, Any]:
    """The per-(model, task) decomposition over the model's own item set."""
    if replicates < 1:
        return _unavailable(
            "no bootstrap replicates requested; no component ships without "
            "its interval (LMN-VAR-003)"
        )
    items = archive.items(model, task)
    cells = [archive.cell(model, task, item) for item in items]
    ks = {c.k for c in cells}
    if len(ks) != 1:
        return _unavailable("ragged k across cells; the balanced EMS algebra does not apply")
    if len(cells) < 2:
        return _unavailable("needs n_items >= 2 (df_item and df_residual are zero at n_items = 1)")
    block = _decompose(
        [c.verdicts for c in cells],
        seed_parts=(rulings_version, task, model, "varcomp-bootstrap"),
        replicates=replicates,
    )
    return {"state": "AVAILABLE", **block}


def task_variance_components(
    archive: Archive,
    task: str,
    ds: DrawScores,
    *,
    rulings_version: str,
    replicates: int,
) -> dict[str, Any]:
    """Per-model decompositions over the aligned substrate, plus the descriptive
    model facet (never a component: LMN-VAR-005)."""
    if replicates < 1:
        return _unavailable(
            "no bootstrap replicates requested; no component ships without "
            "its interval (LMN-VAR-003)"
        )
    if len(ds.items) < 2:
        return _unavailable("needs at least 2 aligned items")
    per_model = []
    for model in ds.models:
        block = _decompose(
            [archive.cell(model, task, item).verdicts[: ds.k] for item in ds.items],
            seed_parts=(rulings_version, task, model, "varcomp-bootstrap-aligned"),
            replicates=replicates,
        )
        per_model.append(
            {
                "model": model,
                "grand_mean": block["grand_mean"],
                "components": block["components"],
                "shares": block["shares"],
                "icc_item": block["icc_item"],
                "icc_draw": block["icc_draw"],
                "design_effect": {
                    "deff": block["design_effect"]["deff"],
                    "n_eff": block["design_effect"]["n_eff"],
                },
            }
        )
    scores = [ds.pooled_pass[m] / (len(ds.items) * ds.k) for m in ds.models]
    mean_score = sum(scores) / len(scores)
    if len(scores) >= 2:
        between = sum((x - mean_score) ** 2 for x in scores) / (len(scores) - 1)
    else:
        between = 0.0
    return {
        "state": "AVAILABLE",
        "substrate": {"items_aligned": len(ds.items), "k": ds.k},
        "per_model": per_model,
        "model_facet": {
            "kind": "descriptive",
            "n_models": len(ds.models),
            "between_model_variance": fmt_float(between),
            "between_model_sd": fmt_float(math.sqrt(between)),
            "note": MODEL_FACET_NOTE,
        },
        "low_draw_levels": ds.k < DRAW_LEVELS_FLOOR,
        "draw_levels_floor": DRAW_LEVELS_FLOOR,
        "low_k_note": LOW_K_NOTE if ds.k < DRAW_LEVELS_FLOOR else None,
        "bucket_note": BUCKET_NOTE,
        "never_headline_note": NEVER_HEADLINE_NOTE,
    }
