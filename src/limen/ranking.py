"""Single-draw leaderboards, sign-stability rulings, and the stable-items-only view.

Signs are computed on integer pass-count differences, never on floats
(LMN-RNK-001): a drawn tie must be exactly a tie. A pair is SIGN-STABLE iff the
pooled direction exists and no single-draw leaderboard reverses it; drawn ties
are their own printed count, neither agreement nor disagreement (LMN-RNK-002).
A pooled tie supports no directional claim and rules SIGN-UNSTABLE with
``pooled_tie`` set (LMN-RNK-003). When zero flips are observed the exact
one-sided 95% bound on the per-draw flip probability is printed —
``1 - 0.05**(1/k)`` — so "SIGN-STABLE at k=8" cannot be read as "flip
probability ~ 0" (LMN-RNK-004).

The stable-items-only re-ranking is never emitted bare (LMN-RNK-005): the same
draws that classify an item also rank the models, so a naive exclusion looks
tidier even under a null. Two mitigations ship with every stable-only number:
(a) disjoint classify/rank draw splits (all complementary splits, k >= 4), and
(b) a selection null that reproduces the whole selection pipeline under
per-cell Bernoulli resampling. Within-cell draw-label permutation would be
tautologically invariant here — every statistic depends on the draws only
through per-cell pass counts — which is exactly why the null must inject
verdict-level randomness (LMN-RNK-006).
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from fractions import Fraction
from random import Random
from typing import Any

from .canonical import counted, derive_seed, fmt_float
from .errors import TableError
from .model import Archive
from .stats import kendall_tau_b, quantile_lower, sign

SELECTION_NULL_INTERPRETATION = (
    "If the observed tidiness sits inside the null band, the stable-only ordering's "
    "tidiness is explained by selection alone and must not be presented as structure; "
    "only observed values outside the band license the claim that mixed items carry "
    "model-differential signal beyond selection."
)
STABLE_VIEW_NOTE = (
    "The stable-only ranking conditions on a selected subset enriched for easy items; "
    "it is one view of the data, not a corrected or true ranking."
)


@dataclass(frozen=True)
class DrawScores:
    """Aligned per-draw pass counts for one task; the substrate of every comparison."""

    task: str
    models: tuple[str, ...]
    items: tuple[str, ...]
    k: int
    pass_counts: dict[str, tuple[int, ...]]  # model -> passes per draw position
    pooled_pass: dict[str, int]
    n_cells_truncated: int


def draw_scores(archive: Archive, task: str, *, ragged: str = "error") -> DrawScores:
    """Compute per-draw pass counts over the aligned item set. Requires uniform k;
    ``ragged='truncate'`` opts into using the first min-k draws of every cell, counted."""
    models = archive.models_for(task)
    items = archive.aligned_items(task)
    if len(models) < 2:
        raise TableError(f"task {task!r} has {len(models)} model(s); comparison needs >= 2")
    if not items:
        raise TableError(f"task {task!r} has no items shared by all models")
    ks = {archive.cell(m, task, i).k for m in models for i in items}
    if len(ks) > 1:
        if ragged != "truncate":
            raise TableError(
                f"task {task!r} has ragged k across cells ({sorted(ks)}); pass "
                "--ragged truncate to use the first min-k draws of every cell"
            )
        k = min(ks)
        truncated = sum(
            1 for m in models for i in items if archive.cell(m, task, i).k > k
        )
    else:
        k = ks.pop()
        truncated = 0
    pass_counts: dict[str, tuple[int, ...]] = {}
    pooled: dict[str, int] = {}
    for m in models:
        per_draw = [0] * k
        for i in items:
            verdicts = archive.cell(m, task, i).verdicts[:k]
            for d, v in enumerate(verdicts):
                per_draw[d] += v
        pass_counts[m] = tuple(per_draw)
        pooled[m] = sum(per_draw)
    return DrawScores(
        task=task,
        models=models,
        items=items,
        k=k,
        pass_counts=pass_counts,
        pooled_pass=pooled,
        n_cells_truncated=truncated,
    )


def single_draw_score_list(ds: DrawScores, model: str) -> list[float]:
    n = len(ds.items)
    return [ds.pass_counts[model][d] / n for d in range(ds.k)]


def pair_stability(ds: DrawScores, model_a: str, model_b: str) -> dict[str, Any]:
    """The sign-stability block for one canonical pair (model_a < model_b)."""
    n = len(ds.items)
    nk = n * ds.k
    pa, pb = ds.pooled_pass[model_a], ds.pooled_pass[model_b]
    pooled_sign = sign(pa - pb)
    pooled_tie = pooled_sign == 0

    block: dict[str, Any] = {
        "model_a": model_a,
        "model_b": model_b,
        "pooled": {
            "pass_a": counted(pa, nk),
            "pass_b": counted(pb, nk),
            "delta_pool": fmt_float((pa - pb) / nk),
            "pooled_sign": pooled_sign,
            "pooled_tie": pooled_tie,
        },
    }
    if pooled_tie:
        block["sign_stability"] = {
            "ruling": "SIGN-UNSTABLE",
            "pooled_tie": True,
            "n_agree": None,
            "n_flip": None,
            "n_tie": counted(
                sum(
                    1
                    for d in range(ds.k)
                    if ds.pass_counts[model_a][d] == ds.pass_counts[model_b][d]
                ),
                ds.k,
            ),
            "rank_flip_rate": None,
            "flip_rate_excl_ties": None,
            "flip_prob_upper95": None,
        }
        return block

    n_agree = n_flip = n_tie = 0
    for d in range(ds.k):
        s_d = sign(ds.pass_counts[model_a][d] - ds.pass_counts[model_b][d])
        if s_d == 0:
            n_tie += 1
        elif s_d == pooled_sign:
            n_agree += 1
        else:
            n_flip += 1
    ruling = "SIGN-STABLE" if n_flip == 0 else "SIGN-UNSTABLE"
    block["sign_stability"] = {
        "ruling": ruling,
        "pooled_tie": False,
        "n_agree": counted(n_agree, ds.k),
        "n_flip": counted(n_flip, ds.k),
        "n_tie": counted(n_tie, ds.k),
        "rank_flip_rate": fmt_float(n_flip / ds.k),
        "flip_rate_excl_ties": (
            fmt_float(n_flip / (n_flip + n_agree)) if (n_flip + n_agree) > 0 else None
        ),
        "flip_prob_upper95": (
            fmt_float(1.0 - 0.05 ** (1.0 / ds.k)) if n_flip == 0 else None
        ),
    }
    return block


def canonical_pairs(models: tuple[str, ...]) -> list[tuple[str, str]]:
    return [(a, b) for a, b in itertools.combinations(sorted(models), 2)]


def misrank_summary(ds: DrawScores) -> dict[str, Any]:
    """Share of single-draw leaderboards that reverse at least one pair's pooled sign."""
    n_misrank = 0
    for d in range(ds.k):
        for a, b in canonical_pairs(ds.models):
            pooled_sign = sign(ds.pooled_pass[a] - ds.pooled_pass[b])
            if pooled_sign == 0:
                continue
            s_d = sign(ds.pass_counts[a][d] - ds.pass_counts[b][d])
            if s_d == -pooled_sign:
                n_misrank += 1
                break
    return {"draws_misranking_any_pair": counted(n_misrank, ds.k)}


# --------------------------------------------------------------------------- #
# stable-items-only re-ranking, with its mandatory mitigations
# --------------------------------------------------------------------------- #


def stable_items(
    verdicts: dict[tuple[str, str], tuple[int, ...]],
    models: tuple[str, ...],
    items: tuple[str, ...],
    positions: tuple[int, ...] | None = None,
) -> frozenset[str]:
    """Items whose verdict is constant across the given draw positions for every model."""
    stable: set[str] = set()
    for item in items:
        ok = True
        for model in models:
            vs = verdicts[(model, item)]
            picked = vs if positions is None else tuple(vs[p] for p in positions)
            if 0 < sum(picked) < len(picked):
                ok = False
                break
        if ok:
            stable.add(item)
    return frozenset(stable)


def _scores(
    verdicts: dict[tuple[str, str], tuple[int, ...]],
    models: tuple[str, ...],
    items: frozenset[str] | tuple[str, ...],
    positions: tuple[int, ...] | None,
    k: int,
) -> dict[str, tuple[int, int]]:
    """Per model: (passes, denominator) over the given items and draw positions."""
    width = k if positions is None else len(positions)
    den = len(items) * width
    out: dict[str, tuple[int, int]] = {}
    for model in models:
        total = 0
        for item in items:
            vs = verdicts[(model, item)]
            total += sum(vs) if positions is None else sum(vs[p] for p in positions)
        out[model] = (total, den)
    return out


def _as_fractions(scores: dict[str, tuple[int, int]]) -> dict[str, Fraction]:
    return {m: Fraction(c, d) if d else Fraction(0) for m, (c, d) in scores.items()}


def _ranking_list(scores: dict[str, tuple[int, int]]) -> list[dict[str, Any]]:
    ordered = sorted(scores.items(), key=lambda kv: (-Fraction(kv[1][0], kv[1][1] or 1), kv[0]))
    return [
        {"model": m, "passes": counted(c, d)} for m, (c, d) in ordered
    ]


def _tau_dict(scores_x: dict[str, tuple[int, int]], scores_y: dict[str, tuple[int, int]]) -> dict[str, Any]:
    tau_b, tau_a, conc, disc, ties_x, ties_y = kendall_tau_b(
        _as_fractions(scores_x), _as_fractions(scores_y)
    )
    return {
        "tau_b": fmt_float(tau_b) if tau_b is not None else None,
        "tau_a": fmt_float(tau_a),
        "concordant": conc,
        "discordant": disc,
        "ties_x": ties_x,
        "ties_y": ties_y,
        "undefined": tau_b is None,
    }


def collect_verdicts(
    archive: Archive, task: str, models: tuple[str, ...], items: tuple[str, ...], k: int
) -> dict[tuple[str, str], tuple[int, ...]]:
    return {
        (m, i): archive.cell(m, task, i).verdicts[:k] for m in models for i in items
    }


def _stable_stats(
    verdicts: dict[tuple[str, str], tuple[int, ...]],
    models: tuple[str, ...],
    items: tuple[str, ...],
    k: int,
) -> tuple[float | None, int | None, float | None, int]:
    """(T_gap, T_flip, T_tau, n_stable) of the naive stable-only pipeline on these
    verdicts — the statistic triple the selection null reproduces.

    T_gap and T_tau come from the full-k stable set. T_flip cannot: items stable
    across all k draws contribute a constant to every per-draw sum, so full-k
    stable-only signs can never flip and the statistic would be identically
    zero. T_flip therefore reproduces the canonical split selection — classify
    on the first floor(k/2) draws, count rank-half sign flips among the
    classify-stable items — and is None when k < 4."""
    stable = stable_items(verdicts, models, items)
    all_scores = _scores(verdicts, models, items, None, k)
    if not stable:
        return None, None, None, 0
    stable_scores = _scores(verdicts, models, stable, None, k)
    all_f = _as_fractions(all_scores)
    stable_f = _as_fractions(stable_scores)

    pairs = canonical_pairs(models)
    gaps = [
        abs(float(stable_f[a] - stable_f[b])) - abs(float(all_f[a] - all_f[b]))
        for a, b in pairs
    ]
    t_gap = sum(gaps) / len(gaps)

    t_flip: int | None = None
    c = k // 2
    if c >= 2:
        classify = tuple(range(c))
        rank = tuple(range(c, k))
        split_stable = stable_items(verdicts, models, items, classify)
        if split_stable:
            t_flip = 0
            per_draw: dict[str, list[int]] = {m: [0] * len(rank) for m in models}
            for m in models:
                for item in sorted(split_stable):
                    vs = verdicts[(m, item)]
                    for j, d in enumerate(rank):
                        per_draw[m][j] += vs[d]
            for a, b in pairs:
                ref = sign(sum(per_draw[a]) - sum(per_draw[b]))
                if ref == 0:
                    continue
                for j in range(len(rank)):
                    s_j = sign(per_draw[a][j] - per_draw[b][j])
                    if s_j == -ref:
                        t_flip += 1

    tau_b, _, _, _, _, _ = kendall_tau_b(stable_f, all_f)
    return t_gap, t_flip, tau_b, len(stable)


def split_half_analysis(
    verdicts: dict[tuple[str, str], tuple[int, ...]],
    models: tuple[str, ...],
    items: tuple[str, ...],
    k: int,
    pooled_signs: dict[tuple[str, str], int],
    *,
    max_splits: int = 256,
) -> dict[str, Any]:
    """Mitigation (a): classify on one half of the draws, rank on the other, over all
    complementary splits. Needs classify-half >= 2 draws, hence k >= 4."""
    c = k // 2
    if c < 2:
        return {
            "state": "UNAVAILABLE",
            "reason": "no disjoint split with >= 2 classification draws exists at k "
            f"= {k}; the naive stable-only numbers cannot be de-biased on this archive",
        }
    all_splits = list(itertools.combinations(range(k), c))
    thinned = False
    if len(all_splits) > max_splits:
        step = math.ceil(len(all_splits) / max_splits)
        all_splits = all_splits[::step]
        thinned = True

    pairs = canonical_pairs(models)
    survive: dict[tuple[str, str], int] = dict.fromkeys(pairs, 0)
    indeterminate: dict[tuple[str, str], int] = dict.fromkeys(pairs, 0)
    taus: list[float] = []
    n_tau_undefined = 0
    stable_sizes: list[int] = []
    canonical_detail: dict[str, Any] | None = None

    for split in all_splits:
        classify = tuple(split)
        rank = tuple(d for d in range(k) if d not in set(split))
        stable = stable_items(verdicts, models, items, classify)
        stable_sizes.append(len(stable))
        rank_all = _scores(verdicts, models, items, rank, k)
        if stable:
            rank_stable = _scores(verdicts, models, stable, rank, k)
            tau = _tau_dict(rank_stable, rank_all)
            if tau["undefined"]:
                n_tau_undefined += 1
            else:
                taus.append(float(tau["tau_b"]))
            stable_f = _as_fractions(rank_stable)
        else:
            tau = None
            n_tau_undefined += 1
            stable_f = None
        for a, b in pairs:
            headline = pooled_signs[(a, b)]
            if stable_f is None or headline == 0:
                indeterminate[(a, b)] += 1
                continue
            gap_sign = 1 if stable_f[a] > stable_f[b] else -1 if stable_f[a] < stable_f[b] else 0
            if gap_sign == 0:
                indeterminate[(a, b)] += 1
            elif gap_sign == headline:
                survive[(a, b)] += 1
        if classify == tuple(range(c)):
            canonical_detail = {
                "classify_positions": list(classify),
                "rank_positions": list(rank),
                "n_stable": counted(len(stable), len(items)),
                "tau": tau,
            }

    n_splits = len(all_splits)
    return {
        "state": "AVAILABLE",
        "n_splits": n_splits,
        "thinned": thinned,
        "classify_draws": c,
        "sign_survival": [
            {
                "model_a": a,
                "model_b": b,
                "survived": counted(survive[(a, b)], n_splits),
                "indeterminate": counted(indeterminate[(a, b)], n_splits),
            }
            for a, b in pairs
        ],
        "tau_over_splits": {
            "mean": fmt_float(sum(taus) / len(taus)) if taus else None,
            "min": fmt_float(min(taus)) if taus else None,
            "max": fmt_float(max(taus)) if taus else None,
            "n_undefined": n_tau_undefined,
        },
        "stable_set_size_over_splits": {
            "mean": fmt_float(sum(stable_sizes) / len(stable_sizes)),
            "min": min(stable_sizes),
            "max": max(stable_sizes),
        },
        "canonical_split": canonical_detail,
    }


def selection_null(
    verdicts: dict[tuple[str, str], tuple[int, ...]],
    models: tuple[str, ...],
    items: tuple[str, ...],
    k: int,
    *,
    rulings_version: str,
    task: str,
    replicates: int = 1000,
) -> dict[str, Any]:
    """Mitigation (b): the conditional parametric selection null. Each replicate
    resamples every cell i.i.d. Bernoulli(p-hat) and re-runs the entire naive
    stable-only pipeline, reproducing the selection exactly (LMN-RNK-006)."""
    observed_gap, observed_flip, observed_tau, observed_stable = _stable_stats(
        verdicts, models, items, k
    )
    p_hat = {key: sum(vs) / k for key, vs in verdicts.items()}

    null_gap: list[float] = []
    null_flip: list[int] = []
    null_tau: list[float] = []
    n_empty_stable = 0
    for b in range(replicates):
        rng = Random(derive_seed(rulings_version, task, "selection-null", b))
        resampled: dict[tuple[str, str], tuple[int, ...]] = {}
        for model in models:
            for item in items:
                p = p_hat[(model, item)]
                resampled[(model, item)] = tuple(
                    1 if rng.random() < p else 0 for _ in range(k)
                )
        gap, flip, tau, n_stable = _stable_stats(resampled, models, items, k)
        if gap is None:
            n_empty_stable += 1
            continue
        null_gap.append(gap)
        if flip is not None:
            null_flip.append(flip)
        if tau is not None:
            null_tau.append(tau)

    def band(values: list[float]) -> dict[str, Any]:
        if not values:
            return {"mean": None, "p2_5": None, "p97_5": None}
        ordered = sorted(values)
        return {
            "mean": fmt_float(sum(ordered) / len(ordered)),
            "p2_5": fmt_float(quantile_lower(ordered, 0.025)),
            "p97_5": fmt_float(quantile_lower(ordered, 0.975)),
        }

    n_eff = len(null_gap)
    result: dict[str, Any] = {
        "state": "AVAILABLE" if observed_gap is not None and n_eff > 0 else "UNAVAILABLE",
        "replicates": replicates,
        "replicates_effective": n_eff,
        "replicates_empty_stable_set": n_empty_stable,
        "seed_procedure": "sha256(rulings_version|task|selection-null|replicate_index)",
        "low_k": k < 4,
        "observed": {
            "t_gap": fmt_float(observed_gap) if observed_gap is not None else None,
            "t_flip": observed_flip,
            "t_tau": fmt_float(observed_tau) if observed_tau is not None else None,
            "n_stable": observed_stable,
        },
        "t_flip_definition": (
            "rank-half sign flips among classify-half-stable items (canonical split); "
            "null when k < 4 or the split-stable set is empty"
        ),
        "interpretation": SELECTION_NULL_INTERPRETATION,
    }
    if result["state"] == "UNAVAILABLE":
        result["null"] = None
        return result
    assert observed_gap is not None
    result["null"] = {
        "t_gap": {
            **band(null_gap),
            "p_value_one_sided_large": fmt_float(
                (1 + sum(1 for g in null_gap if g >= observed_gap)) / (n_eff + 1)
            ),
        },
        "t_flip": (
            {
                **band([float(f) for f in null_flip]),
                "p_value_one_sided_large": fmt_float(
                    (1 + sum(1 for f in null_flip if f >= observed_flip))
                    / (len(null_flip) + 1)
                ),
                "p_value_one_sided_small": fmt_float(
                    (1 + sum(1 for f in null_flip if f <= observed_flip))
                    / (len(null_flip) + 1)
                ),
            }
            if observed_flip is not None and null_flip
            else None
        ),
        "t_tau": {
            **band(null_tau),
            "percentile_of_observed": (
                fmt_float(
                    sum(1 for t in null_tau if t <= observed_tau) / len(null_tau)
                )
                if observed_tau is not None and null_tau
                else None
            ),
        },
    }
    return result


def stable_only_block(
    archive: Archive,
    task: str,
    ds: DrawScores,
    *,
    rulings_version: str,
    replicates: int = 1000,
    max_splits: int = 256,
) -> dict[str, Any]:
    """The complete stable-items-only section: naive view plus BOTH mitigations.
    This is the only public entry; the naive numbers cannot be emitted without
    their mitigations (LMN-RNK-005)."""
    models, items, k = ds.models, ds.items, ds.k
    verdicts = collect_verdicts(archive, task, models, items, k)

    stable = stable_items(verdicts, models, items)
    all_scores = _scores(verdicts, models, items, None, k)
    pooled_signs = {
        (a, b): sign(ds.pooled_pass[a] - ds.pooled_pass[b])
        for a, b in canonical_pairs(models)
    }
    per_model_constant = {
        m: counted(
            sum(
                1
                for i in items
                if verdicts[(m, i)].count(1) in (0, len(verdicts[(m, i)]))
            ),
            len(items),
        )
        for m in models
    }

    naive: dict[str, Any] = {
        "n_stable": counted(len(stable), len(items)),
        "ranking_all_items": _ranking_list(all_scores),
    }
    if stable:
        stable_scores = _scores(verdicts, models, stable, None, k)
        stable_f = _as_fractions(stable_scores)
        naive["ranking_stable_only"] = _ranking_list(stable_scores)
        naive["tau_stable_vs_all"] = _tau_dict(stable_scores, all_scores)
        naive["pair_sign_survives"] = [
            {
                "model_a": a,
                "model_b": b,
                "survives": (
                    None
                    if pooled_signs[(a, b)] == 0
                    else bool(
                        (stable_f[a] > stable_f[b]) - (stable_f[a] < stable_f[b])
                        == pooled_signs[(a, b)]
                    )
                ),
            }
            for a, b in canonical_pairs(models)
        ]
    else:
        naive["ranking_stable_only"] = None
        naive["tau_stable_vs_all"] = None
        naive["pair_sign_survives"] = None

    return {
        "note": STABLE_VIEW_NOTE,
        "per_model_constant": per_model_constant,
        "naive": naive,
        "mitigations": {
            "split_half": split_half_analysis(
                verdicts, models, items, k, pooled_signs, max_splits=max_splits
            ),
            "selection_null": selection_null(
                verdicts,
                models,
                items,
                k,
                rulings_version=rulings_version,
                task=task,
                replicates=replicates,
            ),
        },
    }
