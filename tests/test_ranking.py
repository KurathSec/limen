"""Sign stability, ties, pooled ties, and the stable-only mitigations (LMN-RNK-*)."""

import pytest
from conftest import archive_from_grid

from limen.errors import TableError
from limen.ranking import (
    _stable_stats,
    collect_verdicts,
    draw_scores,
    misrank_summary,
    pair_stability,
    selection_null,
    split_half_analysis,
    stable_only_block,
)
from limen.stats import sign


def _flip_archive():
    # pooled: a 3/6 vs b 2/6 (a ahead); draw 0 agrees (+3), draw 1 flips (-2)
    return archive_from_grid(
        {
            "a": {"i1": [1, 0], "i2": [1, 0], "i3": [1, 0]},
            "b": {"i1": [0, 1], "i2": [0, 1], "i3": [0, 0]},
        }
    )


def test_sign_unstable_flip_counted() -> None:
    ds = draw_scores(_flip_archive(), "t")
    block = pair_stability(ds, "a", "b")
    st = block["sign_stability"]
    assert st["ruling"] == "SIGN-UNSTABLE"
    assert st["n_agree"]["count"] == 1
    assert st["n_flip"]["count"] == 1
    assert st["n_tie"]["count"] == 0
    assert st["rank_flip_rate"] == 0.5
    assert st["flip_prob_upper95"] is None
    assert block["pooled"]["pooled_sign"] == 1


def test_pooled_tie_is_unstable_with_nulls() -> None:
    archive = archive_from_grid(
        {"a": {"i1": [1, 0], "i2": [0, 1]}, "b": {"i1": [0, 1], "i2": [1, 0]}}
    )
    block = pair_stability(draw_scores(archive, "t"), "a", "b")
    st = block["sign_stability"]
    assert block["pooled"]["pooled_tie"] is True
    assert st["ruling"] == "SIGN-UNSTABLE"
    assert st["n_agree"] is None and st["n_flip"] is None
    assert st["n_tie"]["denominator"] == 2


def test_tie_draw_does_not_break_stability() -> None:
    # draw 0 ties (1 vs 1), draw 1: a ahead -> SIGN-STABLE with the tie glaring
    archive = archive_from_grid(
        {"a": {"i1": [1, 1], "i2": [0, 1]}, "b": {"i1": [0, 0], "i2": [1, 0]}}
    )
    st = pair_stability(draw_scores(archive, "t"), "a", "b")["sign_stability"]
    assert st["ruling"] == "SIGN-STABLE"
    assert st["n_tie"]["count"] == 1
    assert st["n_agree"]["count"] == 1
    assert st["flip_prob_upper95"] == pytest.approx(1 - 0.05 ** 0.5, abs=1e-6)


def test_signs_are_integer_based() -> None:
    # 3/9 vs 1/3: float subtraction of means would not be exactly zero here if
    # computed naively; equal pass counts on equal denominators must tie exactly.
    archive = archive_from_grid(
        {"a": {"i1": [1, 1], "i2": [0, 0], "i3": [0, 1]}, "b": {"i1": [0, 1], "i2": [1, 0], "i3": [0, 1]}}
    )
    ds = draw_scores(archive, "t")
    assert sign(ds.pooled_pass["a"] - ds.pooled_pass["b"]) == 0
    assert pair_stability(ds, "a", "b")["pooled"]["pooled_tie"] is True


def test_misrank_summary() -> None:
    ds = draw_scores(_flip_archive(), "t")
    assert misrank_summary(ds)["draws_misranking_any_pair"] == {
        "count": 1,
        "denominator": 2,
        "rate": 0.5,
    }


def test_ragged_k_refused_unless_truncate() -> None:
    archive = archive_from_grid({"a": {"i1": [1, 0], "i2": [1, 0, 1]}, "b": {"i1": [0, 1], "i2": [1, 1]}})
    with pytest.raises(TableError, match="ragged"):
        draw_scores(archive, "t")
    ds = draw_scores(archive, "t", ragged="truncate")
    assert ds.k == 2
    assert ds.n_cells_truncated == 1


def test_split_half_unavailable_below_k4() -> None:
    archive = archive_from_grid({"a": {"i1": [1, 0, 1]}, "b": {"i1": [0, 0, 1]}})
    ds = draw_scores(archive, "t")
    verdicts = collect_verdicts(archive, "t", ds.models, ds.items, ds.k)
    result = split_half_analysis(verdicts, ds.models, ds.items, ds.k, {("a", "b"): 1})
    assert result["state"] == "UNAVAILABLE"
    assert ">= 2 classification draws" in result["reason"]


def test_split_half_enumerates_all_complementary_splits() -> None:
    grid = {
        "a": {f"i{j}": [1, 1, 0, 1] for j in range(4)},
        "b": {f"i{j}": [0, 1, 0, 0] for j in range(4)},
    }
    archive = archive_from_grid(grid)
    ds = draw_scores(archive, "t")
    verdicts = collect_verdicts(archive, "t", ds.models, ds.items, ds.k)
    result = split_half_analysis(verdicts, ds.models, ds.items, ds.k, {("a", "b"): 1})
    assert result["state"] == "AVAILABLE"
    assert result["n_splits"] == 6  # C(4,2)
    assert result["canonical_split"]["classify_positions"] == [0, 1]


def test_selection_null_is_not_a_permutation_null() -> None:
    """The trap (LMN-RNK-006): permuting draw labels within cells changes NOTHING,
    so a permutation 'null' would be vacuous. Assert the invariance explicitly."""
    archive = archive_from_grid(
        {
            "a": {"i1": [1, 0, 1, 1], "i2": [1, 1, 1, 1], "i3": [0, 0, 1, 0]},
            "b": {"i1": [0, 1, 1, 0], "i2": [1, 0, 1, 1], "i3": [0, 0, 0, 0]},
        }
    )
    ds = draw_scores(archive, "t")
    verdicts = collect_verdicts(archive, "t", ds.models, ds.items, ds.k)
    baseline = _stable_stats(verdicts, ds.models, ds.items, ds.k)
    # permute each cell's draws (reverse; a nontrivial permutation)
    permuted = {key: tuple(reversed(vs)) for key, vs in verdicts.items()}
    stats_gap_flip_tau = _stable_stats(permuted, ds.models, ds.items, ds.k)
    assert stats_gap_flip_tau[0] == baseline[0]  # t_gap invariant
    assert stats_gap_flip_tau[3] == baseline[3]  # stable-set size invariant
    # (t_flip depends on per-draw arrangement and is exactly why the null must
    # resample verdicts rather than permute labels — checked in test_known_answer)


def test_selection_null_deterministic_given_version() -> None:
    archive = archive_from_grid(
        {
            "a": {"i1": [1, 0, 1, 1], "i2": [1, 1, 1, 1]},
            "b": {"i1": [0, 1, 1, 0], "i2": [1, 0, 1, 1]},
        }
    )
    ds = draw_scores(archive, "t")
    verdicts = collect_verdicts(archive, "t", ds.models, ds.items, ds.k)
    kwargs = dict(rulings_version="x", task="t", replicates=25)
    r1 = selection_null(verdicts, ds.models, ds.items, ds.k, **kwargs)
    r2 = selection_null(verdicts, ds.models, ds.items, ds.k, **kwargs)
    assert r1 == r2  # fully deterministic given (rulings_version, task, replicates)


def test_stable_only_block_always_carries_mitigations() -> None:
    archive = archive_from_grid(
        {
            "a": {"i1": [1, 0, 1, 1], "i2": [1, 1, 1, 1], "i3": [0, 0, 0, 0]},
            "b": {"i1": [0, 1, 1, 0], "i2": [1, 1, 0, 1], "i3": [0, 0, 0, 0]},
        }
    )
    ds = draw_scores(archive, "t")
    block = stable_only_block(archive, "t", ds, rulings_version="x", replicates=10)
    assert "split_half" in block["mitigations"]
    assert "selection_null" in block["mitigations"]
    assert block["naive"]["n_stable"]["count"] == 1  # only i3 constant for both
    assert "not a corrected or true ranking" in block["note"]
