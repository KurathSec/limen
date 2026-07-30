"""Known-answer tests for the 0.2.0 sections: EMS expectations, instability,
planted inversions. Statistical tests average RAW estimator values over seeds
(E[max(X,0)] > 0 even when E[X] = 0, which is the machine reason the schema
prints raw beside estimate)."""

import pytest

from limen.audit import gap_survival_block, item_instability
from limen.ranking import draw_scores
from limen.synth import (
    PlantedConfig,
    expected_mean_instability,
    expected_variance_components,
    generate,
)
from limen.varcomp import mean_squares, raw_components, two_facet_sums


def _raw_components_for(archive, model: str) -> tuple[float, float, float]:
    items = archive.items(model, "synthetic")
    rows = [archive.cell(model, "synthetic", i).verdicts for i in items]
    n, k, total, ssi, ssd = two_facet_sums(list(rows))
    raw = raw_components(mean_squares(n, k, total, ssi, ssd), n, k)
    return float(raw[0]), float(raw[1]), float(raw[2])


NULL_CFG = PlantedConfig(
    n_items=400, k=8, models=("a",), mu=(0.6,), flaky_fraction=0.25, q=0.5
)


def test_null_draw_component_is_zero_in_expectation() -> None:
    """i.i.d. draws are exchangeable: E[raw s2_draw] = 0 exactly."""
    expected = expected_variance_components(NULL_CFG, 0)
    assert expected["draw"] == 0.0
    raws = [
        _raw_components_for(generate(NULL_CFG, seed=s)[0], "a") for s in range(20)
    ]
    mean_draw = sum(r[1] for r in raws) / len(raws)
    mean_item = sum(r[0] for r in raws) / len(raws)
    mean_res = sum(r[2] for r in raws) / len(raws)
    assert mean_draw == pytest.approx(0.0, abs=1e-4)
    assert mean_item == pytest.approx(expected["item"], abs=5e-3)
    assert mean_res == pytest.approx(expected["residual"], abs=5e-3)


def test_planted_shift_draw_component_matches_finite_n_form() -> None:
    cfg = PlantedConfig(
        n_items=400, k=8, models=("a",), mu=(0.6,), flaky_fraction=0.25,
        q=0.5, q_shift_at_draw=(4, 0.3),
    )
    expected = expected_variance_components(cfg, 0)
    assert expected["draw"] > 0
    raws = [_raw_components_for(generate(cfg, seed=s)[0], "a") for s in range(20)]
    mean_draw = sum(r[1] for r in raws) / len(raws)
    mean_res = sum(r[2] for r in raws) / len(raws)
    assert mean_draw == pytest.approx(expected["draw"], abs=6e-4)
    assert mean_res == pytest.approx(expected["residual"], abs=5e-3)


def test_golden_components_at_one_seed() -> None:
    """Byte-level regression pin: these exact raw values at seed 99, forever."""
    archive, _ = generate(NULL_CFG, seed=99)
    item, draw, residual = _raw_components_for(archive, "a")
    assert item == pytest.approx(0.1780063999283924, abs=1e-15)
    assert draw == pytest.approx(2.08109559613319e-05, abs=1e-18)
    assert residual == pytest.approx(0.06167561761546724, abs=1e-15)


def test_expected_mean_instability_recovered() -> None:
    cfg = PlantedConfig(
        n_items=300, k=8, models=("a", "b"), mu=(0.6, 0.55), flaky_fraction=0.2
    )
    expected = expected_mean_instability(cfg, 0)
    observed = []
    for seed in range(15):
        archive, _ = generate(cfg, seed=seed)
        items = archive.items("a", "synthetic")
        us = [
            item_instability(archive.cell("a", "synthetic", i).passes, 8)
            for i in items
        ]
        observed.append(sum(us) / len(us))
    assert sum(observed) / len(observed) == pytest.approx(expected, abs=0.01)


def test_planted_inversion_rules_sign_inverts() -> None:
    """Deterministic passes favor b; the flaky mass favors a: the all-items gap
    and the stable-for-both gap have opposite signs by construction."""
    cfg = PlantedConfig(
        n_items=100, k=8, models=("a", "b"), mu=(0.56, 0.34),
        flaky_fraction=0.4, q_per_model=(0.9, 0.1),
    )
    # construction check: c_a = 56 - 36 = 20 < c_b = 34 - 4 = 30
    assert cfg.deterministic_passes(0) == 20
    assert cfg.deterministic_passes(1) == 30
    inversions = 0
    for seed in range(6):
        archive, _ = generate(cfg, seed=seed)
        ds = draw_scores(archive, "synthetic")
        block = gap_survival_block(
            archive, "synthetic", ds, "a", "b",
            rulings_version=f"inv{seed}", bootstrap=20, replicates=20,
        )
        assert block["gaps"]["all"]["sign"] == 1  # a ahead overall
        if block["ruling"]["ruling"] == "SIGN-INVERTS":
            inversions += 1
            witness = block["decisive_items"]
            assert witness["direction"] == "reinclusion_from_unstable"
    assert inversions >= 5  # w.h.p. every seed; allow one band edge case


def test_selection_null_base_rates_healthy() -> None:
    """On a genuinely i.i.d.-generated archive with a clear gap, the selection
    null should rarely manufacture inversions."""
    cfg = PlantedConfig(
        n_items=200, k=8, models=("a", "b"), mu=(0.65, 0.55), flaky_fraction=0.2
    )
    archive, _ = generate(cfg, seed=11)
    ds = draw_scores(archive, "synthetic")
    block = gap_survival_block(
        archive, "synthetic", ds, "a", "b",
        rulings_version="base", bootstrap=20, replicates=200,
    )
    freq = block["mitigations"]["selection_null"]["null"]["ruling_frequencies"]
    assert freq["SIGN-INVERTS"]["count"] <= 4  # <= 2% manufactured inversions
    assert sum(v["count"] for v in freq.values()) == 200
