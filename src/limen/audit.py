"""Gap-survival audit: does a published ordering survive removing the items the
systems cannot reproduce against themselves?

This module implements the repaudit limbs (the programme's PF-11/B2-07 cell)
as report sections. Per within-task model pair:

- per-item instability ``u_i = min(s, k-s)/k`` — the fraction of a system's k
  draws disagreeing with the item's own majority verdict, computed for both
  systems symmetrically and never compounded with correctness (LMN-AUD-001);
  at even k with ``s == k/2`` there is no majority and ``u_i = 0.5`` exactly;
- the stable-for-both / unstable-for-either partition at the declared,
  versioned threshold ``u0``: ``u_i == 0`` for both systems — crude by
  design, with the IDR-style principled threshold named as the benchmark it
  must be measured against (LMN-AUD-002);
- the pairwise gap recomputed three ways (all / stable-for-both / unstable
  remainder), each with a two-stage paired bootstrap CI (items with
  replacement, then draws with replacement within each sampled cell), plus
  the signed share of the gap carried by unstable items;
- a replicate noise band: the p95 of |self-gap| over all complementary
  half-splits of one system's k draws, both systems pooled, enumerated with
  no RNG (LMN-AUD-003);
- one ruling — SURVIVES / SIGN-INVERTS / FALLS-INTO-NOISE / UNAVAILABLE —
  under a fixed precedence (LMN-AUD-006), carrying a capped deterministic
  decisive-item witness (LMN-AUD-004);
- the differentiation pass against retry-free coverage (arXiv 2606.00920),
  in every block: the two exclusion criteria differ exactly on
  stable-but-always-wrong items, and this section exists to falsify the
  re-labelling objection (LMN-AUD-007);
- BOTH selection-circularity mitigations, without which no ruling is emitted
  (LMN-AUD-005): disjoint classify/audit draw splits, and a selection null
  that resamples every cell i.i.d. Bernoulli(p-hat) and re-runs the entire
  partition-and-gap pipeline with the noise band held fixed;
- per-stratum rulings over item labels, floored (LMN-AUD-008), plus the
  saturation rollup: Spearman rho of unstable share against stratum
  saturation per label key.

A ruling is a verdict on the measurement. SIGN-INVERTS never means the other
model wins (NO_MODEL_QUALITY_CLAIM), the stable-only ordering is a view and
not a correction, and unstable items are not defective.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from fractions import Fraction
from random import Random
from typing import Any

from .canonical import counted, derive_seed, fmt_float
from .model import Archive
from .ranking import DrawScores
from .stats import quantile_lower, sign, spearman_midrank

THRESHOLD_VERSION = "u0"
THRESHOLD_RULE = "u_i == 0 for both systems of the pair"
IDR_NOTE = (
    "crude by design: any u_i > 0 excludes; the principled benchmark this "
    "threshold must be measured against is an IDR-style irreproducible-"
    "discovery-rate cutoff (Li, Brown, Huang, Bickel 2011); changing the rule "
    "is a new threshold version and a rulings-spec supersession, never an edit"
)
U_TIE_RULE = (
    "at even k with s = k/2 there is no majority verdict and u_i = 0.5, the "
    "maximum; such items are unstable under every threshold above zero"
)
RFC_CITATION = (
    "retry-free coverage (arXiv 2606.00920): an item counts as covered iff all "
    "k draws are correct; compounded with correctness by definition, unlike "
    "the symmetric instability rate u_i"
)
DIFFERENTIATION_NOTE = (
    "If the u_i and retry-free-coverage exclusions never disagree on any pair, "
    "the u_i partition re-labels retry-free coverage on this archive and the "
    "audit's contribution is packaging; the pairs where they disagree, driven "
    "by stable-but-always-wrong items, are where the symmetric definition "
    "earns its keep."
)
AUDIT_NULL_INTERPRETATION = (
    "If the observed gap shrinkage and unstable-share sit inside the null "
    "band, the erosion of the stable gap is explained by selection alone and "
    "must not be presented as instability structure. The ruling frequencies "
    "are the selection-only base rates: an observed SIGN-INVERTS or "
    "FALLS-INTO-NOISE is evidence against the comparison only to the extent "
    "that the null produces it rarely. The band is held fixed at its observed "
    "value; the null tests the partition selection, not the band."
)
AUDIT_VIEW_NOTE = (
    "A ruling is a verdict on the measurement: SIGN-INVERTS never means the "
    "other model wins, the stable-only gap is one view and not a correction, "
    "and unstable items are not defective."
)
BAND_NOTE = (
    "a draw-replicate band in absolute score units over the stated item set; "
    "not an item-sampling interval (the bootstrap CI carries that)"
)
WITNESS_CAP = 25
# complementary half-splits the band will enumerate before refusing; at even k
# the position-0 dedup halves C(k, k/2), so k <= 22 fits and k >= 23 refuses
BAND_ENUMERATION_CAP = 400_000


def item_instability(s: int, k: int) -> float:
    """u_i = min(s, k-s)/k; the fraction of draws disagreeing with the item's
    own majority verdict (LMN-AUD-001)."""
    if k < 2:
        raise ValueError(f"instability needs k >= 2, got k={k}")
    if not 0 <= s <= k:
        raise ValueError(f"passes s={s} outside [0, k={k}]")
    return min(s, k - s) / k


def majority_verdict(s: int, k: int) -> int | None:
    """1 or 0, or None when s == k - s (no majority at even k)."""
    if s * 2 > k:
        return 1
    if s * 2 < k:
        return 0
    return None


@dataclass(frozen=True)
class PairData:
    """Everything the audit needs for one canonical pair, integer substrate."""

    task: str
    model_a: str
    model_b: str
    items: tuple[str, ...]
    k: int
    verdicts_a: dict[str, tuple[int, ...]]
    verdicts_b: dict[str, tuple[int, ...]]

    def passes(self, side: str, item: str) -> int:
        vs = self.verdicts_a if side == "a" else self.verdicts_b
        return sum(vs[item])

    def c(self, item: str) -> int:
        """Per-item draw-count difference a - b, in [-k, k]."""
        return sum(self.verdicts_a[item]) - sum(self.verdicts_b[item])


def build_pair_data(
    archive: Archive, task: str, ds: DrawScores, model_a: str, model_b: str
) -> PairData:
    return PairData(
        task=task,
        model_a=model_a,
        model_b=model_b,
        items=ds.items,
        k=ds.k,
        verdicts_a={i: archive.cell(model_a, task, i).verdicts[: ds.k] for i in ds.items},
        verdicts_b={i: archive.cell(model_b, task, i).verdicts[: ds.k] for i in ds.items},
    )


# --------------------------------------------------------------------------- #
# partition, gaps, band
# --------------------------------------------------------------------------- #


def _partition(pd: PairData, items: tuple[str, ...]) -> tuple[list[str], list[str]]:
    """(stable_for_both, unstable_for_either) under threshold u0."""
    stable: list[str] = []
    unstable: list[str] = []
    for item in items:
        sa = sum(pd.verdicts_a[item])
        sb = sum(pd.verdicts_b[item])
        if sa in (0, pd.k) and sb in (0, pd.k):
            stable.append(item)
        else:
            unstable.append(item)
    return stable, unstable


def _gap_totals(pd: PairData, items: list[str] | tuple[str, ...]) -> tuple[int, int, int]:
    """(passes_a, passes_b, N = passes_a - passes_b) over the given items."""
    pa = sum(sum(pd.verdicts_a[i]) for i in items)
    pb = sum(sum(pd.verdicts_b[i]) for i in items)
    return pa, pb, pa - pb


def _bootstrap_ci(
    pd: PairData,
    items: list[str],
    *,
    seed_parts: tuple[str | int, ...],
    replicates: int,
) -> dict[str, Any] | None:
    if not items:
        return None
    n = len(items)
    deltas: list[float] = []
    for b in range(replicates):
        rng = Random(derive_seed(*seed_parts, b))
        total_c = 0
        for _ in range(n):
            item = items[rng.randrange(n)]
            va = pd.verdicts_a[item]
            vb = pd.verdicts_b[item]
            resampled_a = sum(va[rng.randrange(pd.k)] for _ in range(pd.k))
            resampled_b = sum(vb[rng.randrange(pd.k)] for _ in range(pd.k))
            total_c += resampled_a - resampled_b
        deltas.append(total_c / (n * pd.k))
    ordered = sorted(deltas)
    return {
        "lo": fmt_float(quantile_lower(ordered, 0.025)),
        "hi": fmt_float(quantile_lower(ordered, 0.975)),
        "replicates": replicates,
    }


def _gap_block(
    pd: PairData,
    items: list[str],
    *,
    seed_parts: tuple[str | int, ...] | None,
    replicates: int,
) -> dict[str, Any]:
    if not items:
        return {"state": "UNAVAILABLE", "n_items": 0, "pass_a": None, "pass_b": None,
                "delta": None, "sign": None, "ci95": None}
    pa, pb, n_delta = _gap_totals(pd, items)
    den = len(items) * pd.k
    return {
        "state": "AVAILABLE",
        "n_items": len(items),
        "pass_a": counted(pa, den),
        "pass_b": counted(pb, den),
        "delta": fmt_float(n_delta / den),
        "sign": sign(n_delta),
        "ci95": (
            _bootstrap_ci(pd, items, seed_parts=seed_parts, replicates=replicates)
            if seed_parts is not None
            else None
        ),
    }


def _half_splits(k: int) -> list[tuple[tuple[int, ...], tuple[int, ...]]]:
    """All complementary half-splits, unordered-deduplicated: at even k only
    splits containing position 0 are kept (each unordered pair once); at odd k
    the half sizes differ so every combination is kept (LMN-AUD-003)."""
    c = k // 2
    splits = []
    for combo in itertools.combinations(range(k), c):
        if k % 2 == 0 and 0 not in combo:
            continue
        rest = tuple(d for d in range(k) if d not in set(combo))
        splits.append((combo, rest))
    return splits


def n_half_splits(k: int) -> int:
    """The count _half_splits(k) would enumerate, without materializing it."""
    c = k // 2
    return math.comb(k, c) // 2 if k % 2 == 0 else math.comb(k, c)


def noise_band(pd: PairData, *, item_set: str = "all_aligned") -> dict[str, Any]:
    """p95 of |self-gap| over ALL complementary half-splits, both systems
    pooled, on the given item set (LMN-AUD-003). No RNG and no thinning:
    above the enumeration cap the band refuses rather than sample."""
    full = n_half_splits(pd.k)
    if full > BAND_ENUMERATION_CAP:
        return {
            "state": "UNAVAILABLE",
            "reason": (
                f"enumeration refused: {full} complementary half-splits at "
                f"k={pd.k} exceed the cap of {BAND_ENUMERATION_CAP}; the band "
                "is enumerated, never sampled or thinned (LMN-AUD-003)"
            ),
            "n_splits": counted(full * 2, full * 2),
            "enumeration_cap": BAND_ENUMERATION_CAP,
            "half_sizes": [pd.k // 2, pd.k - pd.k // 2],
            "item_set": item_set,
            "note": BAND_NOTE,
            "_p95_fraction": None,
        }
    splits = _half_splits(pd.k)
    n = len(pd.items)
    abs_gaps: list[Fraction] = []
    per_system_max = {}
    for side, verdicts in (("a", pd.verdicts_a), ("b", pd.verdicts_b)):
        # a half's pooled total is a sum of per-draw column totals, so the
        # item dimension folds once up front, not once per split
        col = [sum(verdicts[i][d] for i in pd.items) for d in range(pd.k)]
        side_max = Fraction(0)
        for h1, h2 in splits:
            p1 = sum(col[d] for d in h1)
            p2 = sum(col[d] for d in h2)
            gap = abs(Fraction(p1, len(h1) * n) - Fraction(p2, len(h2) * n))
            abs_gaps.append(gap)
            side_max = max(side_max, gap)
        per_system_max[side] = side_max
    ordered = sorted(abs_gaps)
    # lower-interpolation p95 kept EXACT on Fractions (quantile_lower is float-typed)
    p95 = ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]
    band_max = ordered[-1]
    return {
        "statistic": (
            "p95 of |self-gap| over all enumerated complementary half-splits, "
            "both systems pooled"
        ),
        "p95": fmt_float(float(p95)),
        "max": fmt_float(float(band_max)),
        "per_system_max": {
            "a": fmt_float(float(per_system_max["a"])),
            "b": fmt_float(float(per_system_max["b"])),
        },
        "n_splits": counted(len(splits) * 2, len(splits) * 2),
        "half_sizes": [pd.k // 2, pd.k - pd.k // 2],
        "enumeration_cap": BAND_ENUMERATION_CAP,
        "low_k": pd.k < 4,
        "item_set": item_set,
        "degenerate_zero_band": band_max == 0,
        "note": BAND_NOTE,
        "_p95_fraction": p95,  # internal exact value, stripped before emission
    }


# --------------------------------------------------------------------------- #
# ruling and witness
# --------------------------------------------------------------------------- #


def _rule(
    n_all: int,
    stable: list[str],
    n_stable_delta: int,
    stable_den: int,
    band_p95: Fraction,
) -> tuple[str, str | None, bool, bool | None]:
    """(ruling, reason, stable_tie, also_within_noise_band) per LMN-AUD-006."""
    if sign(n_all) == 0:
        return "UNAVAILABLE", "pooled_tie: no all-items direction exists to audit", False, None
    if not stable:
        return (
            "UNAVAILABLE",
            "empty_stable_partition: no item is stable for both systems",
            False,
            None,
        )
    stable_sign = sign(n_stable_delta)
    stable_gap = abs(Fraction(n_stable_delta, stable_den))
    if stable_sign != 0 and stable_sign == -sign(n_all):
        return "SIGN-INVERTS", None, False, bool(stable_gap < band_p95)
    if stable_sign == 0:
        return "FALLS-INTO-NOISE", None, True, None
    if stable_gap < band_p95:
        return "FALLS-INTO-NOISE", None, False, None
    return "SURVIVES", None, False, None


def decisive_items(
    pd: PairData,
    stable: list[str],
    unstable: list[str],
    ruling: str,
    band_p95: Fraction,
    *,
    cap: int = WITNESS_CAP,
) -> dict[str, Any] | None:
    """The auditable witness (LMN-AUD-004): greedy, deterministic, capped.

    SURVIVES: remove stable items (largest signed contribution first, item id
    ascending on ties, band held fixed) until the ruling changes — the count is
    the survival margin. SIGN-INVERTS / FALLS-INTO-NOISE: greedily re-include
    unstable items until the ruling becomes SURVIVES, or report NO_WITNESS.
    Greedy is exact on the stable side (contributions quantized to -k/0/+k);
    on the re-inclusion side it is a sufficient witness, not a proven-minimal
    set."""
    _, _, n_all = _gap_totals(pd, pd.items)
    if ruling == "UNAVAILABLE":
        return None
    all_sign = sign(n_all)

    if ruling == "SURVIVES":
        working = sorted(stable, key=lambda i: (-pd.c(i) * all_sign, i))
        removed: list[str] = []
        _, _, n_stable = _gap_totals(pd, stable)
        for item in working:
            n_stable -= pd.c(item)
            removed.append(item)
            remaining = len(stable) - len(removed)
            den = remaining * pd.k
            new_ruling, _, _, _ = _rule(
                n_all,
                ["sentinel"] * remaining,
                n_stable,
                den if den else 1,
                band_p95,
            )
            if new_ruling != "SURVIVES":
                return {
                    "state": "WITNESS",
                    "direction": "removal_from_stable",
                    "n_items": counted(len(removed), len(stable)),
                    "terminal_ruling": new_ruling,
                    "ids": removed[:cap],
                    "cap": cap,
                    "truncated": len(removed) > cap,
                }
        return {  # removing everything empties the partition: UNAVAILABLE
            "state": "WITNESS",
            "direction": "removal_from_stable",
            "n_items": counted(len(stable), len(stable)),
            "terminal_ruling": "UNAVAILABLE",
            "ids": working[:cap],
            "cap": cap,
            "truncated": len(stable) > cap,
        }

    # SIGN-INVERTS or FALLS-INTO-NOISE: re-include unstable items
    working = sorted(unstable, key=lambda i: (-pd.c(i) * all_sign, i))
    included: list[str] = []
    kept = list(stable)
    _, _, n_kept = _gap_totals(pd, stable)
    for item in working:
        included.append(item)
        kept.append(item)
        n_kept += pd.c(item)
        den = len(kept) * pd.k
        new_ruling, _, _, _ = _rule(n_all, kept, n_kept, den, band_p95)
        if new_ruling == "SURVIVES":
            return {
                "state": "WITNESS",
                "direction": "reinclusion_from_unstable",
                "n_items": counted(len(included), len(unstable)),
                "terminal_ruling": "SURVIVES",
                "ids": included[:cap],
                "cap": cap,
                "truncated": len(included) > cap,
            }
    return {
        "state": "NO_WITNESS",
        "direction": "reinclusion_from_unstable",
        "n_items": counted(len(included), len(unstable)),
        "terminal_ruling": ruling,
        "ids": [],
        "cap": cap,
        "truncated": False,
        "note": (
            "re-including every unstable item still does not rule SURVIVES; "
            "the all-items gap itself sits inside the replicate band"
        ),
    }


# --------------------------------------------------------------------------- #
# mitigations (LMN-AUD-005)
# --------------------------------------------------------------------------- #


def audit_split_half(pd: PairData, *, max_splits: int = 256) -> dict[str, Any]:
    """Disjoint classify/audit draw halves over all complementary splits."""
    c = pd.k // 2
    if c < 2:
        return {
            "state": "UNAVAILABLE",
            "reason": (
                f"no disjoint split with >= 2 classification draws exists at k = {pd.k}"
            ),
        }
    n_total = math.comb(pd.k, c)
    thinned = n_total > max_splits
    step = math.ceil(n_total / max_splits) if thinned else 1
    # islice with the same stride yields exactly [::step] without ever
    # materializing the full enumeration
    all_splits = list(
        itertools.islice(itertools.combinations(range(pd.k), c), 0, None, step)
    )
    _, _, n_all_full = _gap_totals(pd, pd.items)
    headline_sign = sign(n_all_full)
    survived = inverted = indeterminate = 0
    shares: list[float] = []
    stable_sizes: list[int] = []
    canonical: dict[str, Any] | None = None
    for split in all_splits:
        classify = tuple(split)
        audit_half = tuple(d for d in range(pd.k) if d not in set(split))
        stable_split = []
        unstable_split = []
        for item in pd.items:
            sa = sum(pd.verdicts_a[item][d] for d in classify)
            sb = sum(pd.verdicts_b[item][d] for d in classify)
            if sa in (0, len(classify)) and sb in (0, len(classify)):
                stable_split.append(item)
            else:
                unstable_split.append(item)
        stable_sizes.append(len(stable_split))
        n_stable_audit = sum(
            sum(pd.verdicts_a[i][d] for d in audit_half)
            - sum(pd.verdicts_b[i][d] for d in audit_half)
            for i in stable_split
        )
        n_all_audit = sum(
            sum(pd.verdicts_a[i][d] for d in audit_half)
            - sum(pd.verdicts_b[i][d] for d in audit_half)
            for i in pd.items
        )
        split_sign = sign(n_stable_audit)
        if headline_sign == 0 or not stable_split or split_sign == 0:
            indeterminate += 1
        elif split_sign == headline_sign:
            survived += 1
        else:
            inverted += 1
        if n_all_audit != 0:
            shares.append(
                float(Fraction(n_all_audit - n_stable_audit, n_all_audit))
            )
        if classify == tuple(range(c)):
            canonical = {
                "classify_positions": list(classify),
                "audit_positions": list(audit_half),
                "n_stable": counted(len(stable_split), len(pd.items)),
                "stable_sign": split_sign,
                "all_sign": sign(n_all_audit),
            }
    n_splits = len(all_splits)
    return {
        "state": "AVAILABLE",
        "n_splits": n_splits,
        "thinned": thinned,
        "classify_draws": c,
        "survived": counted(survived, n_splits),
        "inverted": counted(inverted, n_splits),
        "indeterminate": counted(indeterminate, n_splits),
        "share_unstable_over_splits": {
            "mean": fmt_float(sum(shares) / len(shares)) if shares else None,
            "min": fmt_float(min(shares)) if shares else None,
            "max": fmt_float(max(shares)) if shares else None,
        },
        "stable_both_size_over_splits": {
            "mean": fmt_float(sum(stable_sizes) / len(stable_sizes)),
            "min": min(stable_sizes),
            "max": max(stable_sizes),
        },
        "canonical_split": canonical,
    }


def audit_selection_null(
    pd: PairData,
    band_p95: Fraction,
    *,
    rulings_version: str,
    replicates: int,
    scope_extra: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Per-cell Bernoulli(p-hat) resampling re-running the whole pipeline; the
    observed band is held fixed (the null models per-cell rates; the band,
    alone among audit statistics, is within-cell-arrangement-sensitive)."""
    observed = _null_stats(pd, pd.verdicts_a, pd.verdicts_b, band_p95)
    if observed is None:
        return {
            "state": "UNAVAILABLE",
            "reason": "observed pooled tie; no direction exists for the null to test",
            "band_held_fixed": True,
        }
    p_hat_a = {i: sum(v) / pd.k for i, v in pd.verdicts_a.items()}
    p_hat_b = {i: sum(v) / pd.k for i, v in pd.verdicts_b.items()}
    null_shrink: list[float] = []
    null_share: list[float] = []
    rulings: dict[str, int] = {
        "SURVIVES": 0, "SIGN-INVERTS": 0, "FALLS-INTO-NOISE": 0, "UNAVAILABLE": 0,
    }
    skipped_tie = 0
    for b in range(replicates):
        rng = Random(
            derive_seed(
                rulings_version, pd.task, pd.model_a, pd.model_b,
                "audit-selection-null", *scope_extra, b,
            )
        )
        resampled_a = {
            i: tuple(1 if rng.random() < p_hat_a[i] else 0 for _ in range(pd.k))
            for i in pd.items
        }
        resampled_b = {
            i: tuple(1 if rng.random() < p_hat_b[i] else 0 for _ in range(pd.k))
            for i in pd.items
        }
        stats = _null_stats(pd, resampled_a, resampled_b, band_p95)
        if stats is None:
            skipped_tie += 1
            rulings["UNAVAILABLE"] += 1
            continue
        shrink, share, ruling = stats
        null_shrink.append(shrink)
        if share is not None:
            null_share.append(share)
        rulings[ruling] += 1

    def band(values: list[float]) -> dict[str, Any]:
        if not values:
            return {"mean": None, "p2_5": None, "p97_5": None}
        ordered = sorted(values)
        return {
            "mean": fmt_float(sum(ordered) / len(ordered)),
            "p2_5": fmt_float(quantile_lower(ordered, 0.025)),
            "p97_5": fmt_float(quantile_lower(ordered, 0.975)),
        }

    observed_shrink, observed_share, observed_ruling = observed
    n_eff = len(null_shrink)
    return {
        "state": "AVAILABLE" if n_eff else "UNAVAILABLE",
        "replicates": replicates,
        "replicates_effective": n_eff,
        "replicates_pooled_tie": skipped_tie,
        "band_held_fixed": True,
        "seed_procedure": (
            "sha256(rulings_version|task|model_a|model_b|audit-selection-null|"
            "[stratum]|replicate_index)"
        ),
        "low_k": pd.k < 4,
        "observed": {
            "t_shrink": fmt_float(observed_shrink),
            "t_share": fmt_float(observed_share) if observed_share is not None else None,
            "ruling": observed_ruling,
        },
        "null": (
            {
                "t_shrink": {
                    **band(null_shrink),
                    "p_value_one_sided_small": fmt_float(
                        (1 + sum(1 for v in null_shrink if v <= observed_shrink))
                        / (n_eff + 1)
                    ),
                    "p_value_one_sided_large": fmt_float(
                        (1 + sum(1 for v in null_shrink if v >= observed_shrink))
                        / (n_eff + 1)
                    ),
                },
                "t_share": (
                    {
                        **band(null_share),
                        "percentile_of_observed": (
                            fmt_float(
                                sum(1 for v in null_share if v <= observed_share)
                                / len(null_share)
                            )
                            if observed_share is not None and null_share
                            else None
                        ),
                    }
                ),
                "ruling_frequencies": {
                    name: counted(count, replicates)
                    for name, count in sorted(rulings.items())
                },
            }
            if n_eff
            else None
        ),
        "interpretation": AUDIT_NULL_INTERPRETATION,
    }


def _null_stats(
    pd: PairData,
    verdicts_a: dict[str, tuple[int, ...]],
    verdicts_b: dict[str, tuple[int, ...]],
    band_p95: Fraction,
) -> tuple[float, float | None, str] | None:
    """(t_shrink, t_share, ruling) of the naive pipeline on these verdicts, or
    None at a pooled tie."""
    stable: list[str] = []
    n_all = 0
    n_stable = 0
    for item in pd.items:
        sa = sum(verdicts_a[item])
        sb = sum(verdicts_b[item])
        c = sa - sb
        n_all += c
        if sa in (0, pd.k) and sb in (0, pd.k):
            stable.append(item)
            n_stable += c
    if sign(n_all) == 0:
        return None
    n = len(pd.items)
    delta_all = n_all / (n * pd.k)
    delta_stable = (n_stable / (len(stable) * pd.k)) if stable else 0.0
    shrink = abs(delta_stable) - abs(delta_all)
    share = float(Fraction(n_all - n_stable, n_all)) if n_all != 0 else None
    ruling, _, _, _ = _rule(
        n_all, stable, n_stable, (len(stable) * pd.k) if stable else 1, band_p95
    )
    return shrink, share, ruling


# --------------------------------------------------------------------------- #
# differentiation, saturation, strata
# --------------------------------------------------------------------------- #


def rfc_differentiation(
    pd: PairData,
    stable: list[str],
    band_p95: Fraction,
) -> dict[str, Any]:
    """Retry-free coverage vs the u_i partition (LMN-AUD-007).

    RFC is per-system: an item counts for a system's coverage iff that system
    passes all k draws, so the RFC comparison is coverage_a - coverage_b (the
    jointly-covered items cancel; a joint-kept gap would be identically zero
    by construction, a degenerate comparison this block deliberately avoids).
    The exclusion sets differ exactly on stable-but-always-wrong items
    (containment: mixed implies not covered)."""
    n = len(pd.items)
    always_pass_a = sum(1 for i in pd.items if sum(pd.verdicts_a[i]) == pd.k)
    always_pass_b = sum(1 for i in pd.items if sum(pd.verdicts_b[i]) == pd.k)
    rfc_kept = [
        i
        for i in pd.items
        if sum(pd.verdicts_a[i]) == pd.k and sum(pd.verdicts_b[i]) == pd.k
    ]
    excl_ui = n - len(stable)
    excl_rfc = n - len(rfc_kept)
    _, _, n_all = _gap_totals(pd, pd.items)
    # coverage difference in draw units so the band and precedence apply as-is
    n_coverage = (always_pass_a - always_pass_b) * pd.k
    rfc_ruling, rfc_reason, _, _ = _rule(
        n_all, ["coverage"], n_coverage, n * pd.k, band_p95
    )
    _, _, n_stable = _gap_totals(pd, stable)
    ui_ruling, _, _, _ = _rule(
        n_all, stable, n_stable, (len(stable) * pd.k) if stable else 1, band_p95
    )
    return {
        "citation": RFC_CITATION,
        "coverage_a": counted(always_pass_a, n),
        "coverage_b": counted(always_pass_b, n),
        "rfc_kept": counted(len(rfc_kept), n),
        "ui_kept": counted(len(stable), n),
        "excluded_intersection": counted(excl_ui, n),
        "excluded_union": counted(excl_rfc, n),
        "jaccard_excluded": (
            fmt_float(excl_ui / excl_rfc) if excl_rfc else None
        ),
        "stable_but_always_wrong": counted(excl_rfc - excl_ui, n),
        "ruling_under_rfc": {
            "ruling": rfc_ruling,
            "reason": rfc_reason,
            "delta": fmt_float((always_pass_a - always_pass_b) / n),
            "sign": sign(n_coverage),
        },
        "rulings_differ": rfc_ruling != ui_ruling,
    }


def saturation_rollup(
    archive: Archive, pd: PairData
) -> list[dict[str, Any]]:
    """Per label key: Spearman rho of unstable share against stratum saturation
    (the KT3 directional statistic). Association only; no mechanism claimed
    (NO_SATURATION_MECHANISM_CLAIM)."""
    out: list[dict[str, Any]] = []
    for key in archive.label_keys(pd.task):
        strata: dict[str, list[str]] = {}
        for item in pd.items:
            labels = archive.item_labels(pd.task, item)
            if labels and key in labels:
                strata.setdefault(labels[key], []).append(item)
        points: list[dict[str, Any]] = []
        for value in sorted(strata):
            items = strata[value]
            stable, unstable = _partition(pd, tuple(items))
            pa = sum(sum(pd.verdicts_a[i]) for i in items)
            pb = sum(sum(pd.verdicts_b[i]) for i in items)
            points.append(
                {
                    "value": value,
                    "n_items": len(items),
                    "saturation": fmt_float((pa + pb) / (2 * len(items) * pd.k)),
                    "unstable_share": counted(len(unstable), len(items)),
                }
            )
        rho = None
        if len(points) >= 3:
            rho = spearman_midrank(
                [p["saturation"] for p in points],
                [p["unstable_share"]["count"] / p["unstable_share"]["denominator"] for p in points],
            )
        out.append(
            {
                "label": key,
                "n_strata": len(points),
                "spearman_rho": fmt_float(rho) if rho is not None else None,
                "points": points,
            }
        )
    return out


# --------------------------------------------------------------------------- #
# the sole public entry (LMN-AUD-005: no naive ruling without mitigations)
# --------------------------------------------------------------------------- #


def gap_survival_block(
    archive: Archive,
    task: str,
    ds: DrawScores,
    model_a: str,
    model_b: str,
    *,
    rulings_version: str,
    bootstrap: int = 1000,
    replicates: int = 1000,
    max_splits: int = 256,
    stratify_by: tuple[str, ...] = (),
    stratum_replicates: int = 200,
    stratum_floor: int = 30,
) -> dict[str, Any]:
    pd = build_pair_data(archive, task, ds, model_a, model_b)
    block = _pair_audit(
        archive,
        pd,
        rulings_version=rulings_version,
        bootstrap=bootstrap,
        replicates=replicates,
        max_splits=max_splits,
        scope_extra=(),
        include_differentiation=True,
    )
    block["strata"] = _strata_blocks(
        archive,
        pd,
        rulings_version=rulings_version,
        stratify_by=stratify_by,
        stratum_replicates=stratum_replicates,
        stratum_floor=stratum_floor,
        max_splits=max_splits,
    )
    block["unstable_share_vs_saturation"] = saturation_rollup(archive, pd)
    return block


def _pair_audit(
    archive: Archive,
    pd: PairData,
    *,
    rulings_version: str,
    bootstrap: int,
    replicates: int,
    max_splits: int,
    scope_extra: tuple[str, ...],
    include_differentiation: bool,
    band_item_set: str = "all_aligned",
) -> dict[str, Any]:
    stable, unstable = _partition(pd, pd.items)
    band = noise_band(pd, item_set=band_item_set)
    band_p95: Fraction | None = band.pop("_p95_fraction")

    _, _, n_all = _gap_totals(pd, pd.items)
    _, _, n_stable = _gap_totals(pd, stable)
    _, _, n_unstable = _gap_totals(pd, unstable)
    stable_den = (len(stable) * pd.k) if stable else 1

    if band_p95 is None:
        ruling = "UNAVAILABLE"
        reason = band["reason"]
        stable_tie = False
        within_band = None
    else:
        ruling, reason, stable_tie, within_band = _rule(
            n_all, stable, n_stable, stable_den, band_p95
        )

    seed_base: tuple[str | int, ...] = (
        rulings_version, pd.task, pd.model_a, pd.model_b, "audit-bootstrap",
        *scope_extra,
    )
    u_a = [item_instability(sum(pd.verdicts_a[i]), pd.k) for i in pd.items]
    u_b = [item_instability(sum(pd.verdicts_b[i]), pd.k) for i in pd.items]

    block: dict[str, Any] = {
        "note": AUDIT_VIEW_NOTE,
        "threshold": {
            "version": THRESHOLD_VERSION,
            "rule": THRESHOLD_RULE,
            "note": IDR_NOTE,
        },
        "instability": {
            "u_tie_rule": U_TIE_RULE,
            "a": {"mean_u": fmt_float(sum(u_a) / len(u_a)), "max_u": fmt_float(max(u_a))},
            "b": {"mean_u": fmt_float(sum(u_b) / len(u_b)), "max_u": fmt_float(max(u_b))},
        },
        "partition": {
            "stable_both": counted(len(stable), len(pd.items)),
            "unstable_either": counted(len(unstable), len(pd.items)),
            "unstable_a_only": counted(
                sum(
                    1
                    for i in pd.items
                    if sum(pd.verdicts_a[i]) not in (0, pd.k)
                    and sum(pd.verdicts_b[i]) in (0, pd.k)
                ),
                len(pd.items),
            ),
            "unstable_b_only": counted(
                sum(
                    1
                    for i in pd.items
                    if sum(pd.verdicts_b[i]) not in (0, pd.k)
                    and sum(pd.verdicts_a[i]) in (0, pd.k)
                ),
                len(pd.items),
            ),
            "unstable_both": counted(
                sum(
                    1
                    for i in pd.items
                    if sum(pd.verdicts_a[i]) not in (0, pd.k)
                    and sum(pd.verdicts_b[i]) not in (0, pd.k)
                ),
                len(pd.items),
            ),
        },
        "gaps": {
            "all": _gap_block(
                pd, list(pd.items), seed_parts=(*seed_base, "all"), replicates=bootstrap
            ),
            "stable_both": _gap_block(
                pd, stable, seed_parts=(*seed_base, "stable_both"), replicates=bootstrap
            ),
            "unstable_either": _gap_block(
                pd,
                unstable,
                seed_parts=(*seed_base, "unstable_either"),
                replicates=bootstrap,
            ),
        },
        "share_unstable": {
            "carried_draw_delta": n_unstable,
            "total_draw_delta": n_all,
            "share": (
                fmt_float(float(Fraction(n_unstable, n_all))) if n_all != 0 else None
            ),
            "opposing_partition_signs": sign(n_stable) * sign(n_unstable) == -1,
        },
        "bootstrap": {
            "method": (
                "two-stage paired bootstrap: items with replacement, then draws "
                "with replacement within each sampled cell"
            ),
            "replicates": bootstrap,
            "seed_procedure": (
                "sha256(rulings_version|task|model_a|model_b|audit-bootstrap|"
                "[stratum]|estimand|replicate_index)"
            ),
            "note": (
                "CIs are conditional on the observed stable/unstable partition; "
                "selection effects are the mitigations' job"
            ),
        },
        "noise_band": band,
        "ruling": {
            "ruling": ruling,
            "reason": reason,
            "stable_tie": stable_tie,
            "also_within_noise_band": within_band,
            "band_statistic_used": "p95",
        },
        "decisive_items": (
            decisive_items(pd, stable, unstable, ruling, band_p95)
            if band_p95 is not None
            else None
        ),
        "mitigations": {
            "split_half": audit_split_half(pd, max_splits=max_splits),
            "selection_null": (
                audit_selection_null(
                    pd,
                    band_p95,
                    rulings_version=rulings_version,
                    replicates=replicates,
                    scope_extra=scope_extra,
                )
                if band_p95 is not None
                else {
                    "state": "UNAVAILABLE",
                    "reason": (
                        "the null holds the noise band fixed and the band "
                        "refused enumeration"
                    ),
                }
            ),
        },
    }
    if include_differentiation:
        block["rfc_differentiation"] = (
            rfc_differentiation(pd, stable, band_p95)
            if band_p95 is not None
            else {
                "state": "UNAVAILABLE",
                "reason": (
                    "the coverage comparison rules against the noise band and "
                    "the band refused enumeration"
                ),
                "citation": RFC_CITATION,
            }
        )
    return block


def _strata_blocks(
    archive: Archive,
    pd: PairData,
    *,
    rulings_version: str,
    stratify_by: tuple[str, ...],
    stratum_replicates: int,
    stratum_floor: int,
    max_splits: int,
) -> dict[str, Any]:
    available_keys = archive.label_keys(pd.task)
    if not stratify_by:
        return {
            "state": "UNAVAILABLE",
            "reason": (
                "stratification not requested"
                if available_keys
                else "no label columns in the input"
            ),
            "by": None,
        }
    entries = []
    for key in sorted(stratify_by):
        strata: dict[str, list[str]] = {}
        unlabelled = 0
        for item in pd.items:
            labels = archive.item_labels(pd.task, item)
            if labels and key in labels:
                strata.setdefault(labels[key], []).append(item)
            else:
                unlabelled += 1
        value_blocks = []
        for value in sorted(strata):
            items = tuple(strata[value])
            if len(items) < stratum_floor:
                value_blocks.append(
                    {
                        "value": value,
                        "state": "UNAVAILABLE",
                        "reason": "below_stratum_floor",
                        "n_items": counted(len(items), len(pd.items)),
                        "floor": stratum_floor,
                    }
                )
                continue
            sub = PairData(
                task=pd.task,
                model_a=pd.model_a,
                model_b=pd.model_b,
                items=items,
                k=pd.k,
                verdicts_a={i: pd.verdicts_a[i] for i in items},
                verdicts_b={i: pd.verdicts_b[i] for i in items},
            )
            inner = _pair_audit(
                archive,
                sub,
                rulings_version=rulings_version,
                bootstrap=stratum_replicates,
                replicates=stratum_replicates,
                max_splits=max_splits,
                scope_extra=(key, value),
                include_differentiation=False,
                band_item_set="stratum",
            )
            value_blocks.append(
                {
                    "value": value,
                    "state": "AVAILABLE",
                    "n_items": counted(len(items), len(pd.items)),
                    "audit": inner,
                }
            )
        entries.append(
            {
                "label": key,
                "n_items_unlabelled": counted(unlabelled, len(pd.items)),
                "strata": value_blocks,
            }
        )
    return {"state": "AVAILABLE", "by": entries}


def task_differentiation_summary(pair_blocks: list[dict[str, Any]]) -> dict[str, Any]:
    """TASK-level rollup of the per-pair RFC differentiation (LMN-AUD-007)."""
    diffs = [b["rfc_differentiation"] for b in pair_blocks if "rfc_differentiation" in b]
    jaccards = [d["jaccard_excluded"] for d in diffs if d["jaccard_excluded"] is not None]
    sbaw = [d["stable_but_always_wrong"] for d in diffs]
    return {
        "n_pairs": len(diffs),
        "pairs_rulings_differ": counted(
            sum(1 for d in diffs if d["rulings_differ"]), len(diffs)
        ),
        "jaccard_min": fmt_float(min(jaccards)) if jaccards else None,
        "jaccard_max": fmt_float(max(jaccards)) if jaccards else None,
        "stable_but_always_wrong_max": (
            max(sbaw, key=lambda c: c["count"]) if sbaw else None
        ),
        "interpretation": DIFFERENTIATION_NOTE,
    }
