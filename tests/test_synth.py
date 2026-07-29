"""Planted-truth generator: determinism and config validation."""

import pytest

from limen.readers.longcsv import write_archive
from limen.synth import PlantedConfig, expected_flakiness, expected_mixed_prob, generate


def test_same_seed_byte_identical(tmp_path) -> None:
    cfg = PlantedConfig(
        n_items=50, k=4, models=("a", "b"), mu=(0.7, 0.6), flaky_fraction=0.2
    )
    a1, t1 = generate(cfg, seed=9)
    a2, t2 = generate(cfg, seed=9)
    assert a1.dataset_digest() == a2.dataset_digest()
    write_archive(a1, tmp_path / "x1.csv.gz")
    write_archive(a2, tmp_path / "x2.csv.gz")
    assert (tmp_path / "x1.csv.gz").read_bytes() == (tmp_path / "x2.csv.gz").read_bytes()
    assert t1.as_dict() == t2.as_dict()


def test_different_seed_differs() -> None:
    cfg = PlantedConfig(
        n_items=50, k=4, models=("a", "b"), mu=(0.7, 0.6), flaky_fraction=0.2
    )
    a1, _ = generate(cfg, seed=1)
    a2, _ = generate(cfg, seed=2)
    assert a1.dataset_digest() != a2.dataset_digest()


def test_infeasible_config_rejected() -> None:
    with pytest.raises(ValueError, match="infeasible"):
        PlantedConfig(
            n_items=40, k=4, models=("a", "b"), mu=(0.9, 0.5), flaky_fraction=0.5
        ).validate()


def test_mu_must_be_non_increasing() -> None:
    with pytest.raises(ValueError, match="non-increasing"):
        PlantedConfig(n_items=10, k=2, models=("a", "b"), mu=(0.5, 0.6)).validate()


def test_deterministic_structure_is_rng_free() -> None:
    # zero flaky fraction -> archive independent of seed
    cfg = PlantedConfig(n_items=30, k=3, models=("a", "b"), mu=(0.6, 0.5))
    a1, _ = generate(cfg, seed=1)
    a2, _ = generate(cfg, seed=999)
    assert a1.dataset_digest() == a2.dataset_digest()


def test_closed_forms() -> None:
    assert expected_flakiness(0.5) == 0.5
    assert expected_mixed_prob(0.5, 8) == pytest.approx(1 - 2 * 0.5**8)


def test_planted_defects_and_versions() -> None:
    cfg = PlantedConfig(
        n_items=20,
        k=4,
        models=("a",),
        mu=(0.5,),
        flaky_fraction=0.25,
        defect_items=2,
        version_change_at_draw=2,
    )
    archive, truth = generate(cfg, seed=0)
    cell = archive.cell("a", "synthetic", "item-000000")
    assert cell.verdicts[0] == 1 and cell.verdicts[1] == 0
    assert cell.raw_sha256[0] == cell.raw_sha256[1]
    assert cell.model_version == ("v1", "v1", "v2", "v2")
    assert truth.expected["planted_defect_pairs_per_model"] == 2
