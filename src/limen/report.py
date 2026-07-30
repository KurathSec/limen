"""Ruling-document assembly: the deterministic body every other surface consumes.

One report per archive: MT rulings per (model, task), PAIR rulings per within-
task model pair, TASK rulings per task, in one envelope. The body contains no
timestamp, package version, or path (LMN-EMIT-004) — provenance is the CLI's
sidecar — and every document embeds the fixed ``does_not_show`` scope codes
(LMN-EMIT-005) so it cannot circulate without its own limits. Ruling ids are
``LIMEN-<rulings_version>-<KIND>-<NNNN>`` with ordinals assigned by
lexicographic scope sort, plus a content hash per body.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .audit import gap_survival_block, item_instability, task_differentiation_summary
from .canonical import content_hash, counted, fmt_float
from .drift import drift_guard
from .errors import ReportError
from .flakiness import model_task_flakiness, task_pooled_flakiness
from .graderdefect import grader_defects
from .model import Archive
from .noise import draw_spread, mdd_pair
from .ranking import (
    canonical_pairs,
    draw_scores,
    misrank_summary,
    pair_stability,
    single_draw_score_list,
    stable_only_block,
)
from .spec import require, spec_version
from .stats import quantile_lower, sample_sd
from .varcomp import mt_variance_components, task_variance_components

SCHEMA = "report/v2"

DOES_NOT_SHOW: tuple[tuple[str, str], ...] = (
    (
        "NO_MODEL_QUALITY_CLAIM",
        "A sign ruling is a verdict on the measurement, never on the models; a flip "
        "means 'this comparison is not supported by its own data', never 'the other "
        "model wins'.",
    ),
    (
        "NO_PRIVILEGED_DRAW",
        "No draw is the correct one; all k are equally legitimate executions of the "
        "declared configuration, and there is no true score behind them to prefer.",
    ),
    (
        "NO_FACTOR_ATTRIBUTION",
        "'Draw' is a bucket holding everything that varies between two identical "
        "calls; no seed / hardware / order / version decomposition is claimed.",
    ),
    (
        "NO_DRIFT_ABSENCE_CLAIM",
        "A drift PASS means the checks that could run found nothing; UNAVAILABLE is "
        "not PASS, and absence of evidence of drift is not evidence of its absence.",
    ),
    (
        "STABLE_SUBSET_IS_A_VIEW",
        "The stable-items-only ranking conditions on a selected subset enriched for "
        "easy items; it is one view, not a corrected or true ranking.",
    ),
    (
        "UNSTABLE_ITEMS_NOT_DEFECTIVE",
        "Instability is a joint property of item, model, serving stack, grader and "
        "protocol; an item unstable for one model and stable for another is not "
        "defective.",
    ),
    (
        "NO_K1_CERTIFICATE",
        "The spread and MDD are reported at the observed k; no sufficiency "
        "certificate is issued for k=1 or any other k, on any benchmark or provider.",
    ),
    (
        "EXACT_MATCH_GRADING_ONLY",
        "Validity is scoped to deterministic exact-match grading; nothing here says "
        "anything about judge-scored, rubric-scored or preference-scored tasks.",
    ),
    (
        "CONSTANCY_IS_NOT_CORRECTNESS",
        "Flakiness and TARa measure repeatability only; a constant-but-wrong verdict "
        "is invisible to this instrument.",
    ),
    (
        "STABILITY_THRESHOLD_IS_CRUDE",
        "The v1 stable/unstable threshold (u_i == 0 for both systems) is deliberately "
        "crude; the principled benchmark is an IDR-style threshold, and every ruling "
        "is stamped with the threshold version it used.",
    ),
    (
        "NO_SATURATION_MECHANISM_CLAIM",
        "The unstable-share-versus-saturation correlation is an association across "
        "strata of one archive; no causal mechanism and no generalization beyond it "
        "is claimed.",
    ),
)


@dataclass(frozen=True, slots=True)
class ReportOptions:
    replicates: int = 1000
    max_splits: int = 256
    assume_index_is_collection_order: bool = False
    ragged: str = "error"
    bootstrap: int = 1000
    stratify_by: tuple[str, ...] = ()
    stratum_replicates: int = 200
    stratum_floor: int = 30


def _ruling_id(rulings_version: str, kind: str, ordinal: int) -> str:
    return f"LIMEN-{rulings_version}-{kind}-{ordinal:04d}"


def scope_block() -> dict[str, Any]:
    return {
        "does_not_show": [
            {"code": code, "text": text} for code, text in DOES_NOT_SHOW
        ]
    }


def build_report(
    archive: Archive, *, rulings_version: str, options: ReportOptions | None = None
) -> dict[str, Any]:
    """Assemble the full ruling document. Deterministic given (archive, version, options)."""
    require("LMN-EMIT-001")
    require("LMN-EMIT-004")
    opts = options or ReportOptions()
    if not rulings_version or not all(c.isalnum() or c in "._-" for c in rulings_version):
        raise ReportError(
            f"rulings_version {rulings_version!r} must be non-empty [A-Za-z0-9._-]+"
        )

    tasks = archive.tasks
    ds_by_task = {}
    for task in tasks:
        if len(archive.models_for(task)) >= 2:
            ds_by_task[task] = draw_scores(archive, task, ragged=opts.ragged)

    mt_bodies: list[dict[str, Any]] = []
    mt_scopes = sorted(
        (task, model) for task in tasks for model in archive.models_for(task)
    )
    drift_by_scope: dict[tuple[str, str], dict[str, Any]] = {}
    for ordinal, (task, model) in enumerate(mt_scopes, start=1):
        drift = drift_guard(
            archive,
            model,
            task,
            assume_index_is_collection_order=opts.assume_index_is_collection_order,
        )
        drift_by_scope[(task, model)] = drift
        body: dict[str, Any] = {
            "ruling_id": _ruling_id(rulings_version, "MT", ordinal),
            "kind": "MT",
            "scope_key": {"task": task, "model": model},
            "flakiness": model_task_flakiness(archive, model, task),
            "instability": _mt_instability(archive, model, task),
            "drift": drift,
            "grader_defect": grader_defects(archive, model, task),
            "variance_components": mt_variance_components(
                archive, model, task,
                rulings_version=rulings_version, replicates=opts.replicates,
            ),
        }
        ds = ds_by_task.get(task)
        if ds is not None and model in ds.models:
            scores = single_draw_score_list(ds, model)
            body["noise_floor"] = {
                **draw_spread(scores),
                "n_items_aligned": len(ds.items),
                "score_resolution": fmt_float(1.0 / len(ds.items)),
            }
        else:
            body["noise_floor"] = None
        body["content_hash"] = content_hash(body)
        mt_bodies.append(body)

    pair_bodies: list[dict[str, Any]] = []
    pair_audits_by_task: dict[str, list[dict[str, Any]]] = {}
    pair_scopes = sorted(
        (task, a, b)
        for task, ds in ds_by_task.items()
        for a, b in canonical_pairs(ds.models)
    )
    for ordinal, (task, a, b) in enumerate(pair_scopes, start=1):
        ds = ds_by_task[task]
        stability = pair_stability(ds, a, b)
        scores_a = single_draw_score_list(ds, a)
        scores_b = single_draw_score_list(ds, b)
        sd_a, sd_b = sample_sd(scores_a), sample_sd(scores_b)
        confounded = any(
            drift_by_scope[(task, m)]["subchecks"]["version_constancy"]["state"] == "FAIL"
            for m in (a, b)
        )
        gap_survival = gap_survival_block(
            archive, task, ds, a, b,
            rulings_version=rulings_version,
            bootstrap=opts.bootstrap,
            replicates=opts.replicates,
            max_splits=opts.max_splits,
            stratify_by=opts.stratify_by,
            stratum_replicates=opts.stratum_replicates,
            stratum_floor=opts.stratum_floor,
        )
        pair_audits_by_task.setdefault(task, []).append(gap_survival)
        body = {
            "ruling_id": _ruling_id(rulings_version, "PAIR", ordinal),
            "kind": "PAIR",
            "scope_key": {"task": task, "model_a": a, "model_b": b},
            "n": {
                "items_aligned": len(ds.items),
                "k": ds.k,
                "draws_total": len(ds.items) * ds.k,
            },
            "gap_survival": gap_survival,
            **stability,
            "noise": {
                "sd_a": fmt_float(sd_a),
                "sd_b": fmt_float(sd_b),
                "range_a": fmt_float(max(scores_a) - min(scores_a)),
                "range_b": fmt_float(max(scores_b) - min(scores_b)),
                "mdd": mdd_pair(sd_a, sd_b, ds.k, len(ds.items)),
            },
            "confounded_by_version_change": confounded,
            "drift_ref": {
                "model_a": drift_by_scope[(task, a)]["state"],
                "model_b": drift_by_scope[(task, b)]["state"],
            },
        }
        body["content_hash"] = content_hash(body)
        pair_bodies.append(body)

    task_bodies: list[dict[str, Any]] = []
    for ordinal, task in enumerate(sorted(ds_by_task), start=1):
        ds = ds_by_task[task]
        body = {
            "ruling_id": _ruling_id(rulings_version, "TASK", ordinal),
            "kind": "TASK",
            "scope_key": {"task": task},
            "n": {
                "items_aligned": len(ds.items),
                "k": ds.k,
                "models": list(ds.models),
                "cells_truncated": ds.n_cells_truncated,
            },
            "pooled_flakiness": task_pooled_flakiness(archive, task),
            "misrank": misrank_summary(ds),
            "stable_only": stable_only_block(
                archive,
                task,
                ds,
                rulings_version=rulings_version,
                replicates=opts.replicates,
                max_splits=opts.max_splits,
            ),
            "variance_components": task_variance_components(
                archive, task, ds,
                rulings_version=rulings_version, replicates=opts.replicates,
            ),
            "differentiation": task_differentiation_summary(
                pair_audits_by_task.get(task, [])
            ),
            "labels": _task_labels_summary(archive, task, ds.items),
        }
        body["content_hash"] = content_hash(body)
        task_bodies.append(body)

    envelope: dict[str, Any] = {
        "limen_schema": SCHEMA,
        "rulings_version": rulings_version,
        "spec_version": spec_version(),
        "dataset_digest": archive.dataset_digest(),
        "options": {
            "replicates": opts.replicates,
            "max_splits": opts.max_splits,
            "assume_index_is_collection_order": opts.assume_index_is_collection_order,
            "ragged": opts.ragged,
            "bootstrap": opts.bootstrap,
            "stratify_by": sorted(opts.stratify_by),
            "stratum_replicates": opts.stratum_replicates,
            "stratum_floor": opts.stratum_floor,
        },
        "n": {
            "models": list(archive.models),
            "tasks": list(archive.tasks),
            "cells": len(archive.cells),
            "excluded_low_k": [
                {"model": model, "task": task, "count": count}
                for (model, task), count in sorted(archive.excluded_low_k.items())
            ],
        },
        "scope": scope_block(),
        "rulings": {"mt": mt_bodies, "pair": pair_bodies, "task": task_bodies},
    }
    envelope["content_hash"] = content_hash(envelope)
    return envelope


def _mt_instability(archive: Archive, model: str, task: str) -> dict[str, Any]:
    """The per-(model, task) instability block (LMN-AUD-001), sibling of the
    flakiness block: u_i against the item's own majority verdict."""
    items = archive.items(model, task)
    cells = [archive.cell(model, task, item) for item in items]
    us = sorted(item_instability(c.passes, c.k) for c in cells)
    n = len(us)
    n_unstable = sum(1 for u in us if u > 0)
    n_tie = sum(1 for c in cells if c.k % 2 == 0 and c.passes * 2 == c.k)
    return {
        "mean_u": fmt_float(sum(us) / n),
        "u_p50": fmt_float(quantile_lower(us, 0.50)),
        "u_p90": fmt_float(quantile_lower(us, 0.90)),
        "u_p99": fmt_float(quantile_lower(us, 0.99)),
        "u_max": fmt_float(us[-1]),
        "n_unstable": counted(n_unstable, n),
        "n_majority_tie": counted(n_tie, n),
    }


def _task_labels_summary(
    archive: Archive, task: str, items: tuple[str, ...]
) -> dict[str, Any] | None:
    keys = archive.label_keys(task)
    if not keys:
        return None
    out = []
    for key in keys:
        values: dict[str, int] = {}
        labelled = 0
        for item in items:
            labels = archive.item_labels(task, item)
            if labels and key in labels:
                labelled += 1
                values[labels[key]] = values.get(labels[key], 0) + 1
        out.append(
            {
                "key": key,
                "n_items_labelled": counted(labelled, len(items)),
                "values": [
                    {"value": v, "n_items": c} for v, c in sorted(values.items())
                ],
            }
        )
    return {"keys": out}
