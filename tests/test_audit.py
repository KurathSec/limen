"""Gap-survival audit (LMN-AUD-*): instability, band, ruling precedence, witness."""

from fractions import Fraction

import pytest
from conftest import archive_from_grid

from limen.audit import (
    _half_splits,
    _partition,
    _rule,
    audit_selection_null,
    audit_split_half,
    build_pair_data,
    decisive_items,
    gap_survival_block,
    item_instability,
    majority_verdict,
    noise_band,
    rfc_differentiation,
)
from limen.ranking import draw_scores


def _pair(grid, task="t"):
    archive = archive_from_grid(grid)
    ds = draw_scores(archive, task)
    return archive, ds, build_pair_data(archive, task, ds, *ds.models[:2])


# --- instability (LMN-AUD-001) --------------------------------------------- #


def test_item_instability_exhaustive() -> None:
    for k in range(2, 10):
        for s in range(k + 1):
            assert item_instability(s, k) == min(s, k - s) / k
    with pytest.raises(ValueError):
        item_instability(0, 1)
    with pytest.raises(ValueError):
        item_instability(5, 4)


def test_majority_tie_rule() -> None:
    assert majority_verdict(3, 4) == 1
    assert majority_verdict(1, 4) == 0
    assert majority_verdict(2, 4) is None  # no majority at even k
    assert item_instability(2, 4) == 0.5  # the maximum


def test_partition_never_compounds_correctness() -> None:
    # always-fail on both sides is STABLE (the definitional difference from RFC)
    _, _, pd = _pair({"a": {"i1": [0, 0], "i2": [1, 0]}, "b": {"i1": [0, 0], "i2": [1, 1]}})
    stable, unstable = _partition(pd, pd.items)
    assert stable == ["i1"]
    assert unstable == ["i2"]


# --- noise band (LMN-AUD-003) ----------------------------------------------- #


def test_half_splits_dedup_even_and_odd() -> None:
    even = _half_splits(4)
    assert len(even) == 3  # C(3,1): position 0 pinned
    assert all(0 in h1 for h1, _ in even)
    odd = _half_splits(5)
    assert len(odd) == 10  # C(5,2): half sizes differ, no dedup


def test_noise_band_hand_computed_k4() -> None:
    # one item, a = [1,1,0,0]: halves {0,d} vs rest; self-gaps computable by hand
    _, _, pd = _pair({"a": {"i1": [1, 1, 0, 0]}, "b": {"i1": [1, 1, 1, 1]}})
    band = noise_band(pd)
    # a's splits (0-pinned): {0,1}|{2,3} -> |1-0|=1; {0,2}|{1,3} -> |1/2-1/2|=0;
    # {0,3}|{1,2} -> 0. b constant -> all 0. pooled six values [1,0,0,0,0,0]
    assert band["max"] == 1.0
    assert band["p95"] == 1.0  # lower-interpolation p95 of 6 values = max here
    assert band["per_system_max"] == {"a": 1.0, "b": 0.0}
    assert band["degenerate_zero_band"] is False


def test_noise_band_zero_on_constant_archive() -> None:
    _, _, pd = _pair({"a": {"i1": [1, 1], "i2": [1, 1]}, "b": {"i1": [0, 0], "i2": [1, 1]}})
    band = noise_band(pd)
    assert band["degenerate_zero_band"] is True


# --- ruling precedence (LMN-AUD-006) ---------------------------------------- #


def test_rule_precedence_table() -> None:
    band = Fraction(1, 10)
    # pooled tie -> UNAVAILABLE regardless of anything else
    assert _rule(0, ["x"], 5, 10, band)[0] == "UNAVAILABLE"
    # empty stable -> UNAVAILABLE
    assert _rule(5, [], 0, 1, band)[0] == "UNAVAILABLE"
    # inversion beats the band, with the within-band flag
    ruling, _, _, within = _rule(5, ["x"], -1, 100, band)
    assert ruling == "SIGN-INVERTS" and within is True
    ruling, _, _, within = _rule(5, ["x"], -50, 100, band)
    assert ruling == "SIGN-INVERTS" and within is False
    # stable tie -> FALLS-INTO-NOISE with the flag
    ruling, _, tie, _ = _rule(5, ["x"], 0, 10, band)
    assert ruling == "FALLS-INTO-NOISE" and tie is True
    # below band -> FALLS-INTO-NOISE
    assert _rule(5, ["x"], 1, 100, band)[0] == "FALLS-INTO-NOISE"
    # at or above band -> SURVIVES (strict less-than comparison)
    assert _rule(5, ["x"], 10, 100, band)[0] == "SURVIVES"
    assert _rule(5, ["x"], 50, 100, band)[0] == "SURVIVES"


# --- decisive witness (LMN-AUD-004) ------------------------------------------ #


def test_witness_survives_margin_changes_ruling() -> None:
    grid = {
        "a": {f"i{j}": [1, 1, 1, 1] for j in range(5)} | {"m": [1, 0, 1, 1]},
        "b": {f"i{j}": [0, 0, 0, 0] for j in range(5)} | {"m": [0, 1, 0, 0]},
    }
    _, _, pd = _pair(grid)
    stable, unstable = _partition(pd, pd.items)
    band = noise_band(pd)
    witness = decisive_items(pd, stable, unstable, "SURVIVES", band["_p95_fraction"])
    assert witness["state"] == "WITNESS"
    assert witness["direction"] == "removal_from_stable"
    assert 1 <= witness["n_items"]["count"] <= len(stable)
    # deterministic: same call, same ids
    again = decisive_items(pd, stable, unstable, "SURVIVES", band["_p95_fraction"])
    assert witness == again


def test_witness_cap_and_truncation() -> None:
    grid = {
        "a": {f"i{j:03d}": [1, 1] for j in range(40)},
        "b": {f"i{j:03d}": [0, 0] for j in range(40)},
    }
    _, _, pd = _pair(grid)
    stable, unstable = _partition(pd, pd.items)
    witness = decisive_items(pd, stable, unstable, "SURVIVES", Fraction(0))
    assert len(witness["ids"]) <= 25
    if witness["n_items"]["count"] > 25:
        assert witness["truncated"] is True


def test_witness_no_witness_when_all_inside_band() -> None:
    # gap so small that even all items don't clear a huge band
    grid = {"a": {"i1": [1, 0], "i2": [1, 1]}, "b": {"i1": [0, 1], "i2": [1, 0]}}
    _, _, pd = _pair(grid)
    stable, unstable = _partition(pd, pd.items)
    witness = decisive_items(pd, stable, unstable, "FALLS-INTO-NOISE", Fraction(9, 1))
    assert witness["state"] == "NO_WITNESS"
    assert "note" in witness


# --- RFC differentiation (LMN-AUD-007) -------------------------------------- #


def test_rfc_containment_and_sbaw() -> None:
    # i1 stable-both-always-wrong: excluded by RFC, kept by u_i
    grid = {
        "a": {"i1": [0, 0], "i2": [1, 1], "i3": [1, 0]},
        "b": {"i1": [0, 0], "i2": [1, 1], "i3": [1, 1]},
    }
    _, _, pd = _pair(grid)
    stable, _ = _partition(pd, pd.items)
    block = rfc_differentiation(pd, stable, Fraction(0))
    assert block["ui_kept"]["count"] == 2  # i1, i2
    assert block["rfc_kept"]["count"] == 1  # i2 only
    assert block["stable_but_always_wrong"]["count"] == 1
    assert block["excluded_intersection"]["count"] <= block["excluded_union"]["count"]


# --- mitigations (LMN-AUD-005) ----------------------------------------------- #


def test_split_half_below_k4_unavailable() -> None:
    _, _, pd = _pair({"a": {"i1": [1, 0, 1]}, "b": {"i1": [0, 0, 0]}})
    result = audit_split_half(pd)
    assert result["state"] == "UNAVAILABLE"


def test_selection_null_deterministic_and_frequencies_sum() -> None:
    grid = {
        "a": {f"i{j}": [1, 1, 0, 1] for j in range(4)} | {"s": [1, 1, 1, 1]},
        "b": {f"i{j}": [0, 1, 0, 0] for j in range(4)} | {"s": [0, 0, 0, 0]},
    }
    _, _, pd = _pair(grid)
    band = noise_band(pd)["_p95_fraction"]
    kwargs = dict(rulings_version="x", replicates=40)
    r1 = audit_selection_null(pd, band, **kwargs)
    r2 = audit_selection_null(pd, band, **kwargs)
    assert r1 == r2
    freq = r1["null"]["ruling_frequencies"]
    assert sum(v["count"] for v in freq.values()) == 40
    assert r1["band_held_fixed"] is True


def test_band_is_arrangement_sensitive_but_partition_is_not() -> None:
    """The LMN-AUD-005 rationale: the band alone sees CROSS-ITEM draw alignment.
    Two mixed items with aligned flips give a wide band; the same per-cell pass
    counts anti-aligned give a zero band, while partition and gaps are identical."""
    aligned = {
        "a": {"i1": [1, 1, 0, 0], "i2": [1, 1, 0, 0]},
        "b": {"i1": [0, 0, 0, 0], "i2": [0, 0, 0, 0]},
    }
    anti = {
        "a": {"i1": [1, 1, 0, 0], "i2": [0, 0, 1, 1]},  # same s per cell
        "b": {"i1": [0, 0, 0, 0], "i2": [0, 0, 0, 0]},
    }
    _, _, pd = _pair(aligned)
    _, _, pd2 = _pair(anti)
    assert _partition(pd, pd.items) == _partition(pd2, pd2.items)
    from limen.audit import _gap_totals

    assert _gap_totals(pd, list(pd.items)) == _gap_totals(pd2, list(pd2.items))
    assert noise_band(pd)["max"] == 1.0  # aligned flips: the band sees them
    assert noise_band(pd2)["max"] == 0.0  # anti-aligned: perfectly self-cancelling


# --- strata (LMN-AUD-008) ----------------------------------------------------- #


def test_strata_floor_and_available() -> None:
    from limen.model import VerdictRow, build_archive

    rows = []
    for j in range(35):
        for model, verdicts in (("a", [1, 1, 0, 1]), ("b", [0, 0, 0, 0])):
            for d, v in enumerate(verdicts):
                rows.append(
                    VerdictRow(
                        model=model, task="t", item_id=f"big{j:02d}", draw_id=str(d),
                        verdict=v, labels=(("lang", "py"),),
                    )
                )
    for j in range(3):
        for model in ("a", "b"):
            for d in range(4):
                rows.append(
                    VerdictRow(
                        model=model, task="t", item_id=f"small{j}", draw_id=str(d),
                        verdict=1 if model == "a" else 0, labels=(("lang", "go"),),
                    )
                )
    archive = build_archive(rows)
    ds = draw_scores(archive, "t")
    block = gap_survival_block(
        archive, "t", ds, "a", "b",
        rulings_version="x", bootstrap=10, replicates=10,
        stratify_by=("lang",), stratum_replicates=10, stratum_floor=30,
    )
    strata = block["strata"]
    assert strata["state"] == "AVAILABLE"
    by_lang = strata["by"][0]
    values = {entry["value"]: entry for entry in by_lang["strata"]}
    assert values["go"]["state"] == "UNAVAILABLE"
    assert values["go"]["reason"] == "below_stratum_floor"
    assert values["py"]["state"] == "AVAILABLE"
    assert values["py"]["audit"]["ruling"]["ruling"] in (
        "SURVIVES", "SIGN-INVERTS", "FALLS-INTO-NOISE", "UNAVAILABLE",
    )
    rollup = block["unstable_share_vs_saturation"]
    assert rollup and rollup[0]["label"] == "lang"


def test_strata_unavailable_without_request_or_labels() -> None:
    grid = {"a": {"i1": [1, 0], "i2": [1, 1]}, "b": {"i1": [0, 1], "i2": [0, 0]}}
    archive, ds, _ = _pair(grid)
    block = gap_survival_block(
        archive, "t", ds, "a", "b", rulings_version="x", bootstrap=5, replicates=5
    )
    assert block["strata"]["state"] == "UNAVAILABLE"
    assert block["strata"]["reason"] == "no label columns in the input"


# --- the block always carries its mitigations -------------------------------- #


def test_block_always_carries_both_mitigations_and_differentiation() -> None:
    grid = {"a": {"i1": [1, 1, 1, 1], "i2": [1, 0, 1, 1]}, "b": {"i1": [0, 0, 0, 0], "i2": [0, 1, 0, 0]}}
    archive, ds, _ = _pair(grid)
    block = gap_survival_block(
        archive, "t", ds, "a", "b", rulings_version="x", bootstrap=5, replicates=5
    )
    assert "split_half" in block["mitigations"]
    assert "selection_null" in block["mitigations"]
    assert "rfc_differentiation" in block
    assert "verdict on the measurement" in block["note"]
    assert "_p95_fraction" not in block["noise_band"]  # internal value stripped


# --- band enumeration is exact and never thinned (LMN-AUD-003) -------------- #


def test_noise_band_k12_matches_bruteforce_over_all_splits() -> None:
    # k=12 sits above the old thinning threshold; the emitted p95 and max must
    # equal the statistics over ALL C(11,5) = 462 deduplicated splits
    verdicts_a = {
        "i1": [1, 0, 1, 1, 0, 0, 1, 0, 1, 1, 0, 1],
        "i2": [0, 0, 0, 1, 1, 0, 0, 0, 1, 0, 0, 0],
        "i3": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
        "i4": [0, 1, 0, 0, 1, 1, 0, 1, 0, 0, 1, 0],
        "i5": [1, 1, 0, 1, 0, 1, 1, 1, 0, 1, 1, 0],
    }
    verdicts_b = {
        "i1": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        "i2": [1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0],
        "i3": [0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0],
        "i4": [1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0],
        "i5": [0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1],
    }
    _, _, pd = _pair({"a": verdicts_a, "b": verdicts_b})
    band = noise_band(pd)

    splits = _half_splits(12)
    assert len(splits) == 462
    n = len(pd.items)
    reference: list[Fraction] = []
    for verdicts in (pd.verdicts_a, pd.verdicts_b):
        for h1, h2 in splits:
            p1 = sum(sum(verdicts[i][d] for d in h1) for i in pd.items)
            p2 = sum(sum(verdicts[i][d] for d in h2) for i in pd.items)
            reference.append(abs(Fraction(p1, len(h1) * n) - Fraction(p2, len(h2) * n)))
    ordered = sorted(reference)
    import math as _math

    expected_p95 = ordered[max(0, _math.ceil(0.95 * len(ordered)) - 1)]
    from limen.canonical import fmt_float

    assert band["_p95_fraction"] == expected_p95
    assert band["max"] == fmt_float(float(ordered[-1]))
    assert band["n_splits"] == {"count": 924, "denominator": 924, "rate": 1.0}
    assert "thinned" not in band
    assert band["enumeration_cap"] == 400_000


def test_noise_band_refuses_above_enumeration_cap() -> None:
    from limen.audit import n_half_splits

    assert n_half_splits(22) <= 400_000 < n_half_splits(23)
    k = 23
    _, _, pd = _pair(
        {"a": {"i1": [1] * k, "i2": [0] * k}, "b": {"i1": [0] * k, "i2": [0] * k}}
    )
    band = noise_band(pd)
    assert band["state"] == "UNAVAILABLE"
    assert "enumeration refused" in band["reason"]
    assert "never sampled" in band["reason"]
    assert band["_p95_fraction"] is None


def test_gap_survival_rules_unavailable_when_band_refuses() -> None:
    k = 23
    grid = {
        "a": {"i1": [1] * k, "i2": [1] * k, "i3": [0] * k},
        "b": {"i1": [0] * k, "i2": [0] * k, "i3": [0] * k},
    }
    archive = archive_from_grid(grid)
    ds = draw_scores(archive, "t")
    block = gap_survival_block(
        archive, "t", ds, "a", "b", rulings_version="x", bootstrap=2, replicates=2
    )
    assert block["noise_band"]["state"] == "UNAVAILABLE"
    assert block["ruling"]["ruling"] == "UNAVAILABLE"
    assert "enumeration refused" in block["ruling"]["reason"]
    assert block["decisive_items"] is None
    assert block["mitigations"]["selection_null"]["state"] == "UNAVAILABLE"
    assert block["rfc_differentiation"]["state"] == "UNAVAILABLE"


def test_stratum_band_declares_its_item_set() -> None:
    from limen.model import VerdictRow, build_archive

    rows = []
    for j in range(31):
        for model, verdicts in (("a", [1, 1, 1, 1]), ("b", [0, 0, 0, 0])):
            for d, v in enumerate(verdicts):
                rows.append(
                    VerdictRow(
                        model=model, task="t", item_id=f"it{j:02d}", draw_id=str(d),
                        verdict=v, labels=(("lang", "py"),),
                    )
                )
    archive = build_archive(rows)
    ds = draw_scores(archive, "t")
    block = gap_survival_block(
        archive, "t", ds, "a", "b",
        rulings_version="x", bootstrap=5, replicates=5,
        stratify_by=("lang",), stratum_replicates=5, stratum_floor=30,
    )
    assert block["noise_band"]["item_set"] == "all_aligned"
    stratum = block["strata"]["by"][0]["strata"][0]
    assert stratum["audit"]["noise_band"]["item_set"] == "stratum"
