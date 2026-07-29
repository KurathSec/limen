"""The drift guard: refuses to attribute movement to the draw facet blindly.

Three sub-checks per (model, task): model-version constancy, leave-one-draw-out
flip attribution (does one draw carry a majority of the flips), and a Spearman
trend of flip participation against collection order (the dossier's KT2
threshold, |rho| > 0.8). Overall state: any FAIL -> FAIL, else any UNAVAILABLE
-> UNAVAILABLE, else PASS — a missing field can never launder into PASS
(LMN-DRF-001: UNAVAILABLE is not PASS).

Position-proxy mode (LMN-DRF-002): when timestamps are absent but the caller
declares that within-cell draw order is collection order, the order-based
sub-checks run on draw positions. The ruling asymmetry is load-bearing: a
positional effect is real evidence of trouble, so FAIL stays FAIL, but a clean
result yields UNAVAILABLE, never PASS — ``collected_at`` *is* missing.
"""

from __future__ import annotations

import itertools
from functools import cache
from typing import Any

from .canonical import fmt_float
from .model import Archive, Cell
from .stats import spearman_midrank

PROXY_DISCLAIMER = (
    "index order within item assumed to be collection order; no timestamps; "
    "cross-item simultaneity unknown; clean results report UNAVAILABLE, not PASS"
)

LODO_THRESHOLD = 0.5
#: below this many mixed cells the majority rule cannot discriminate (a single
#: mixed cell ALWAYS has one draw carrying all of its flips)
LODO_MIN_MIXED = 4
TREND_THRESHOLD = 0.8


@cache
def exchangeable_fpr(k: int) -> float | None:
    """Exact P(|rho| > 0.8) for a random untied ordering of k ranks — the false-positive
    rate of the trend threshold under exchangeability, printed so a FAIL at small k can
    be weighted. Enumerated exactly for 4 <= k <= 8."""
    if not 4 <= k <= 8:
        return None
    denom = k * (k * k - 1)
    hits = 0
    total = 0
    for perm in itertools.permutations(range(k)):
        d2 = sum((i - p) ** 2 for i, p in enumerate(perm))
        rho = 1.0 - 6.0 * d2 / denom
        total += 1
        if abs(rho) > TREND_THRESHOLD:
            hits += 1
    return hits / total


def _time_ranks(cell: Cell) -> tuple[tuple[int, ...], int]:
    """Map draw position -> time rank (0-based), ties broken by canonical position and
    counted (number of draws sharing a timestamp with another draw of the cell)."""
    stamps = cell.collected_at
    assert stamps is not None
    order = sorted(range(cell.k), key=lambda i: (stamps[i], i))
    ranks = [0] * cell.k
    for rank, pos in enumerate(order):
        ranks[pos] = rank
    n_ties = sum(1 for s in stamps if stamps.count(s) > 1)
    return tuple(ranks), n_ties


def _mixed_after_removal(cells: list[Cell], rank_of: list[tuple[int, ...]], r: int) -> int:
    """How many cells stay mixed when the draw holding time-rank r is removed."""
    n = 0
    for cell, ranks in zip(cells, rank_of, strict=True):
        pos = ranks.index(r)
        s = cell.passes - cell.verdicts[pos]
        if 0 < s < cell.k - 1:
            n += 1
    return n


def drift_guard(
    archive: Archive,
    model: str,
    task: str,
    *,
    assume_index_is_collection_order: bool = False,
) -> dict[str, Any]:
    items = archive.items(model, task)
    cells = [archive.cell(model, task, item) for item in items]

    # --- sub-check 1: model_version constancy -------------------------------- #
    missing_version = sum(1 for c in cells if c.model_version is None)
    if missing_version:
        version_check: dict[str, Any] = {
            "state": "UNAVAILABLE",
            "versions": None,
            "n_cells_missing": missing_version,
        }
    else:
        versions = sorted({v for c in cells for v in (c.model_version or ())})
        version_check = {
            "state": "FAIL" if len(versions) > 1 else "PASS",
            "versions": versions,
            "n_cells_missing": 0,
        }

    # --- ordering basis ------------------------------------------------------ #
    ks = {c.k for c in cells}
    uniform_k = ks.pop() if len(ks) == 1 else None
    have_time = all(c.collected_at is not None for c in cells)
    basis: str | None
    proxy = False
    time_ordering_vacuous = False
    if have_time:
        basis = "collected_at"
        # Timestamps that never differ within any cell carry zero ordering
        # information: the "time" ranks are just canonical draw order wearing a
        # timestamp costume. That must not launder into PASS (LMN-DRF-001) —
        # apply the same clean-means-UNAVAILABLE asymmetry as proxy mode.
        if not any(
            c.collected_at is not None and len(set(c.collected_at)) > 1 for c in cells
        ):
            time_ordering_vacuous = True
            proxy = True
    elif assume_index_is_collection_order:
        basis = "draw_position"
        proxy = True
    else:
        basis = None

    def unavailable(reason: str) -> dict[str, Any]:
        return {"state": "UNAVAILABLE", "reason": reason}

    if basis is None:
        lodo: dict[str, Any] = unavailable("no collected_at and no declared position order")
        trend: dict[str, Any] = unavailable("no collected_at and no declared position order")
    elif uniform_k is None:
        lodo = unavailable("ragged k across cells; rank aggregation undefined")
        trend = unavailable("ragged k across cells; rank aggregation undefined")
    else:
        k = uniform_k
        if basis == "collected_at":
            ranked = [_time_ranks(c) for c in cells]
            rank_of = [r for r, _ in ranked]
            n_time_ties = sum(t for _, t in ranked)
        else:
            rank_of = [tuple(range(k)) for _ in cells]
            n_time_ties = 0
        lodo = _lodo_check(cells, rank_of, k, proxy)
        trend = _trend_check(cells, rank_of, k, proxy, n_time_ties)

    subchecks = {"version_constancy": version_check, "lodo": lodo, "trend": trend}
    states = [s["state"] for s in subchecks.values()]
    overall = "FAIL" if "FAIL" in states else "UNAVAILABLE" if "UNAVAILABLE" in states else "PASS"
    return {
        "state": overall,
        "basis": basis,
        "time_ordering_vacuous": time_ordering_vacuous,
        "proxy_disclaimer": (
            (
                "every cell's timestamps are identical: the time ordering carries no "
                "information; clean results report UNAVAILABLE, not PASS"
                if time_ordering_vacuous
                else PROXY_DISCLAIMER
            )
            if proxy
            else None
        ),
        "subchecks": subchecks,
    }


def _lodo_check(
    cells: list[Cell], rank_of: list[tuple[int, ...]], k: int, proxy: bool
) -> dict[str, Any]:
    mixed_cells = [
        (c, r) for c, r in zip(cells, rank_of, strict=True) if 0 < c.passes < c.k
    ]
    n_mixed = len(mixed_cells)
    if n_mixed == 0:
        state = "UNAVAILABLE" if proxy else "PASS"
        return {
            "state": state,
            "vacuous": True,
            "clean": True,
            "n_mixed": 0,
            "carried_by_rank": None,
            "max_carried": None,
            "max_share": None,
            "threshold": LODO_THRESHOLD,
        }
    only_cells = [c for c, _ in mixed_cells]
    only_ranks = [r for _, r in mixed_cells]
    carried = [
        n_mixed - _mixed_after_removal(only_cells, only_ranks, r) for r in range(k)
    ]
    max_carried = max(carried)
    majority = max_carried > LODO_THRESHOLD * n_mixed
    if majority and n_mixed < LODO_MIN_MIXED:
        # a majority over so few mixed cells is not discriminative (one mixed
        # cell always concentrates); refuse to rule rather than fire trivially
        state = "UNAVAILABLE"
        clean = False
    elif majority:
        state = "FAIL"
        clean = False
    else:
        state = "UNAVAILABLE" if proxy else "PASS"
        clean = True
    return {
        "state": state,
        "vacuous": False,
        "clean": clean,
        "n_mixed": n_mixed,
        "n_mixed_floor": LODO_MIN_MIXED,
        "carried_by_rank": carried,
        "max_carried": max_carried,
        "max_share": fmt_float(max_carried / n_mixed),
        "threshold": LODO_THRESHOLD,
    }


def _trend_check(
    cells: list[Cell],
    rank_of: list[tuple[int, ...]],
    k: int,
    proxy: bool,
    n_time_ties: int,
) -> dict[str, Any]:
    if k < 4:
        return {
            "state": "UNAVAILABLE",
            "reason": f"trend check needs k >= 4 (at k={k} the rank support is too "
            "coarse for the 0.8 threshold)",
            "n_time_ties": n_time_ties,
        }
    part = [0] * k
    for cell, ranks in zip(cells, rank_of, strict=True):
        s = cell.passes
        if not 0 < s < cell.k:
            continue
        for pos in range(cell.k):
            r = ranks[pos]
            part[r] += (cell.k - s) if cell.verdicts[pos] == 1 else s
    rho = spearman_midrank([float(r) for r in range(k)], [float(p) for p in part])
    if rho is None:
        state = "UNAVAILABLE" if proxy else "PASS"
        return {
            "state": state,
            "rho": None,
            "zero_variance": True,
            "clean": True,
            "part_by_rank": part,
            "threshold": TREND_THRESHOLD,
            "exchangeable_fpr": None,
            "n_time_ties": n_time_ties,
        }
    fail = abs(rho) > TREND_THRESHOLD
    state = "FAIL" if fail else ("UNAVAILABLE" if proxy else "PASS")
    fpr = exchangeable_fpr(k)
    return {
        "state": state,
        "rho": fmt_float(rho),
        "zero_variance": False,
        "clean": not fail,
        "part_by_rank": part,
        "threshold": TREND_THRESHOLD,
        "exchangeable_fpr": fmt_float(fpr) if fpr is not None else None,
        "n_time_ties": n_time_ties,
    }
