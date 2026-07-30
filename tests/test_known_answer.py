"""Known-answer tests: estimators recover the generator's planted values.

Statistical tests aggregate over multiple seeds and assert against the
closed-form expectations with generous-but-meaningful bounds; golden tests pin
exact values at one seed.
"""

import pytest
from conftest import archive_from_grid

from limen.flakiness import model_task_flakiness
from limen.graderdefect import grader_defects
from limen.ranking import (
    _stable_stats,
    collect_verdicts,
    draw_scores,
    selection_null,
    single_draw_score_list,
)
from limen.stats import sample_sd, sign
from limen.synth import PlantedConfig, expected_flip_prob, generate

SEEDS = range(10)


def _archives(cfg: PlantedConfig, seeds=SEEDS):
    return [generate(cfg, seed=s) for s in seeds]


CFG = PlantedConfig(
    n_items=400,
    k=8,
    models=("a", "b"),
    mu=(0.65, 0.64),
    flaky_fraction=0.25,
    q=0.5,
)


def test_flakiness_recovers_planted_rate() -> None:
    means = []
    taras = []
    for archive, _truth in _archives(CFG):
        block = model_task_flakiness(archive, "a", "synthetic")
        means.append(block["mean_flakiness"])
        taras.append(block["constant_verdict_fraction"])
    expected_mean = 0.25 * 0.5  # phi * 2q(1-q)
    expected_tara = 1 - 0.25 * (1 - 2 * 0.5**8)
    assert sum(means) / len(means) == pytest.approx(expected_mean, abs=0.01)
    assert sum(taras) / len(taras) == pytest.approx(expected_tara, abs=0.015)


def test_single_draw_flip_rate_matches_normal_approximation() -> None:
    # true gap 0.01; sigma_delta = sqrt(2 * phi q(1-q) / n)
    sigma = (0.25 * 0.25 / 400) ** 0.5
    p_expected = expected_flip_prob(0.01, sigma, sigma)
    flips = draws = 0
    for archive, _truth in _archives(CFG, seeds=range(25)):
        ds = draw_scores(archive, "synthetic")
        for d in range(ds.k):
            s_d = sign(ds.pass_counts["a"][d] - ds.pass_counts["b"][d])
            draws += 1
            if s_d == -1:  # against the TRUE direction (a > b by construction)
                flips += 1
    assert flips / draws == pytest.approx(p_expected, abs=0.09)


def test_single_draw_score_variance_matches_planted_sigma() -> None:
    sigma2 = 0.25 * 0.25 / 400
    variances = []
    for archive, _ in _archives(CFG):
        ds = draw_scores(archive, "synthetic")
        variances.append(sample_sd(single_draw_score_list(ds, "a")) ** 2)
    assert sum(variances) / len(variances) == pytest.approx(sigma2, rel=0.5)


def test_planted_grader_defects_exact() -> None:
    cfg = PlantedConfig(
        n_items=100,
        k=8,
        models=("a", "b"),
        mu=(0.6, 0.55),
        flaky_fraction=0.2,
        defect_items=4,
    )
    archive, truth = generate(cfg, seed=3)
    for model in ("a", "b"):
        result = grader_defects(archive, model, "synthetic")
        assert result["defect_pairs"]["count"] >= 4  # planted pairs (Bernoulli draws may add same-hash? no: hashes unique)
        # exactly the planted pairs: every non-planted draw hash is unique
        assert result["defect_pairs"]["count"] == 4
        assert result["defect_items"]["count"] == 4


def test_selection_null_pvalues_healthy_under_null() -> None:
    """Null-structured archives (i.i.d. Bernoulli flaky draws): the selection-null
    p-values must not systematically reject."""
    cfg = PlantedConfig(
        n_items=120, k=6, models=("a", "b"), mu=(0.6, 0.6), flaky_fraction=0.3
    )
    p_values = []
    for seed in range(8):
        archive, _ = generate(cfg, seed=seed)
        ds = draw_scores(archive, "synthetic")
        verdicts = collect_verdicts(archive, "synthetic", ds.models, ds.items, ds.k)
        result = selection_null(
            verdicts,
            ds.models,
            ds.items,
            ds.k,
            rulings_version=f"ka{seed}",
            task="synthetic",
            replicates=100,
        )
        p_values.append(result["null"]["t_gap"]["p_value_one_sided_large"])
    assert sum(1 for p in p_values if p < 0.05) <= 2
    assert max(p_values) > 0.2


def test_selection_null_detects_draw_coherent_structure() -> None:
    """Draw-coherent flips (which i.i.d. per-cell resampling cannot produce) push
    observed T_flip outside the null band."""
    grid = {"a": {}, "b": {}}
    # 10 coherent items for a: stable on the classify half, coherent drop on the
    # rank half; b constant everywhere, competitive on the rank half.
    for j in range(10):
        grid["a"][f"c{j}"] = [1, 1, 1, 1, 1, 1, 0, 0]
        grid["b"][f"c{j}"] = [0, 0, 0, 0, 0, 0, 0, 0]
    for j in range(13):
        grid["a"][f"p{j}"] = [0, 0, 0, 0, 0, 0, 0, 0]
        grid["b"][f"p{j}"] = [1, 1, 1, 1, 1, 1, 1, 1]
    for j in range(10):
        grid["a"][f"q{j}"] = [1, 1, 1, 1, 1, 1, 1, 1]
        grid["b"][f"q{j}"] = [0, 0, 0, 0, 0, 0, 0, 0]
    archive = archive_from_grid(grid)
    ds = draw_scores(archive, "t")
    verdicts = collect_verdicts(archive, "t", ds.models, ds.items, ds.k)
    observed = _stable_stats(verdicts, ds.models, ds.items, ds.k)
    assert observed[1] is not None and observed[1] >= 2  # rank-half flips observed
    result = selection_null(
        verdicts,
        ds.models,
        ds.items,
        ds.k,
        rulings_version="power",
        task="t",
        replicates=200,
    )
    flip_null = result["null"]["t_flip"]
    assert flip_null is not None
    assert result["observed"]["t_flip"] >= flip_null["p97_5"]
    assert flip_null["p_value_one_sided_large"] < 0.1
