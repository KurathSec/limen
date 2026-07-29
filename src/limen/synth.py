"""Planted-truth generator: synthetic archives whose right answers are chosen.

Layer one of the instrument's oracle (dossier: "The oracle, two layers"). Every
estimator in limen has a known-answer test against archives built here, where
the per-item flip probability, the true model ordering, and the true gaps are
set by construction. The truth record's expectations are computed from what the
archive actually contains — the effective flaky fraction ``round(phi*n)/n``,
not the requested phi, and the per-draw q vector when a shift is planted — so
the known-answer bounds are exact at every configuration, including small n.

Determinism (LMN-EMIT-003): the deterministic structure (which items are flaky,
which items each model passes) uses no RNG at all; only the flaky draws consume
randomness, from one ``random.Random(seed)`` in a documented stream order
(models in config order, items ascending, draws 0..k-1). Same config + seed
gives byte-identical archives on any CPython >= 3.12.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from random import Random
from typing import Any

from .model import Archive, VerdictRow, build_archive
from .stats import normal_cdf


@dataclass(frozen=True, slots=True)
class PlantedConfig:
    """The chosen truth. ``mu`` are target true scores, non-increasing."""

    n_items: int
    k: int
    models: tuple[str, ...]
    mu: tuple[float, ...]
    task: str = "synthetic"
    flaky_fraction: float = 0.0
    q: float = 0.5
    q_per_model: tuple[float, ...] | None = None
    version_change_at_draw: int | None = None
    q_shift_at_draw: tuple[int, float] | None = None
    defect_items: int = 0
    with_timestamps: bool = True
    with_raw_hashes: bool = True
    with_versions: bool = True

    def q_for(self, model_index: int) -> float:
        if self.q_per_model is not None:
            return self.q_per_model[model_index]
        return self.q

    def validate(self) -> None:
        if self.n_items < 1 or self.k < 2:
            raise ValueError("need n_items >= 1 and k >= 2")
        if len(self.models) != len(self.mu) or len(self.models) < 1:
            raise ValueError("models and mu must be non-empty and aligned")
        if len(set(self.models)) != len(self.models):
            raise ValueError("model names must be unique")
        if any(b > a for a, b in zip(self.mu, self.mu[1:], strict=False)):
            raise ValueError("mu must be non-increasing (true ordering by construction)")
        if not 0.0 <= self.flaky_fraction <= 1.0:
            raise ValueError("flaky_fraction must be in [0, 1]")
        if self.q_per_model is not None and len(self.q_per_model) != len(self.models):
            raise ValueError("q_per_model must align with models")
        for i in range(len(self.models)):
            if not 0.0 <= self.q_for(i) <= 1.0:
                raise ValueError("q must be in [0, 1]")
        n_flaky = self.n_flaky
        for i, m in enumerate(self.models):
            c = self.deterministic_passes(i)
            if not 0 <= c <= self.n_items - n_flaky:
                raise ValueError(
                    f"infeasible config for {m}: mu={self.mu[i]} with "
                    f"flaky_fraction={self.flaky_fraction}, q={self.q_for(i)} needs "
                    f"{c} deterministic passes out of {self.n_items - n_flaky}"
                )
        if self.defect_items > n_flaky:
            raise ValueError("defect_items cannot exceed the number of flaky items")
        if self.defect_items > 0 and self.k < 2:
            raise ValueError("defect planting needs k >= 2")

    @property
    def n_flaky(self) -> int:
        return round(self.flaky_fraction * self.n_items)

    def deterministic_passes(self, model_index: int) -> int:
        """c_m: deterministic pass-set size hitting the target true score."""
        return round(self.n_items * self.mu[model_index] - self.n_flaky * self.q_for(model_index))

    def true_score(self, model_index: int) -> float:
        """Expected pooled score of the archive as generated: deterministic passes
        plus the flaky mass at the mean per-draw success probability (accounts for
        q_shift_at_draw; equals the base-q form when no shift is planted)."""
        mean_q = sum(
            _q_effective(self, model_index, d) for d in range(self.k)
        ) / self.k
        return (
            self.deterministic_passes(model_index) + self.n_flaky * mean_q
        ) / self.n_items


@dataclass(frozen=True)
class PlantedTruth:
    """Everything the generator chose, plus closed-form expectations for the tests."""

    config: PlantedConfig
    seed: int
    true_ordering: tuple[str, ...]
    true_scores: dict[str, float]
    expected: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        cfg = self.config
        return {
            "config": {
                "n_items": cfg.n_items,
                "k": cfg.k,
                "models": list(cfg.models),
                "mu": list(cfg.mu),
                "task": cfg.task,
                "flaky_fraction": cfg.flaky_fraction,
                "q": cfg.q,
                "q_per_model": list(cfg.q_per_model) if cfg.q_per_model else None,
                "version_change_at_draw": cfg.version_change_at_draw,
                "q_shift_at_draw": list(cfg.q_shift_at_draw) if cfg.q_shift_at_draw else None,
                "defect_items": cfg.defect_items,
            },
            "seed": self.seed,
            "true_ordering": list(self.true_ordering),
            "true_scores": self.true_scores,
            "expected": self.expected,
        }


def expected_flakiness(q: float) -> float:
    """E[f] for a flaky item with per-draw pass probability q: 2q(1-q), any k."""
    return 2.0 * q * (1.0 - q)


def expected_mixed_prob(q: float, k: int) -> float:
    """P(an item with pass prob q is mixed over k draws) = 1 - q^k - (1-q)^k."""
    return 1.0 - q**k - (1.0 - q) ** k


def expected_flip_prob(gap: float, sigma_a: float, sigma_b: float) -> float:
    """Normal approximation to P(a single-draw leaderboard reverses a true gap)."""
    sigma = (sigma_a**2 + sigma_b**2) ** 0.5
    if sigma == 0.0:
        return 0.0
    return normal_cdf(-gap / sigma)


def _q_effective(cfg: PlantedConfig, model_index: int, draw: int) -> float:
    q = cfg.q_for(model_index)
    if cfg.q_shift_at_draw is not None and draw >= cfg.q_shift_at_draw[0]:
        q = min(1.0, max(0.0, q + cfg.q_shift_at_draw[1]))
    return q


def generate(config: PlantedConfig, seed: int) -> tuple[Archive, PlantedTruth]:
    """Build the archive and its truth record. Deterministic given (config, seed)."""
    config.validate()
    rng = Random(seed)
    n_flaky = config.n_flaky
    items = [f"item-{i:06d}" for i in range(config.n_items)]
    flaky = items[:n_flaky]
    deterministic = items[n_flaky:]

    flaky_set = set(flaky)
    rows: list[VerdictRow] = []
    for mi, model in enumerate(config.models):
        pass_set = set(deterministic[: config.deterministic_passes(mi)])
        for item_index, item in enumerate(items):
            is_flaky = item in flaky_set
            planted_defect = is_flaky and item_index < config.defect_items
            for d in range(config.k):
                if is_flaky:
                    verdict = 1 if rng.random() < _q_effective(config, mi, d) else 0
                else:
                    verdict = 1 if item in pass_set else 0
                if planted_defect and d == 0:
                    verdict = 1
                if planted_defect and d == 1:
                    verdict = 0
                if planted_defect and d in (0, 1):
                    raw = f"sha256:planted-defect:{model}:{item}"
                else:
                    raw = "sha256:" + hashlib.sha256(
                        f"{model}|{item}|{d}".encode()
                    ).hexdigest()
                version: str | None = None
                if config.with_versions:
                    version = "v1"
                    if (
                        config.version_change_at_draw is not None
                        and d >= config.version_change_at_draw
                    ):
                        version = "v2"
                rows.append(
                    VerdictRow(
                        model=model,
                        task=config.task,
                        item_id=item,
                        draw_id=str(d),
                        verdict=verdict,
                        collected_at=(
                            f"2026-01-01T00:{d // 60:02d}:{d % 60:02d}Z"
                            if config.with_timestamps
                            else None
                        ),
                        model_version=version,
                        raw_sha256=raw if config.with_raw_hashes else None,
                    )
                )

    archive = build_archive(rows, meta={"reader": "synth", "seed": str(seed)})
    truth = _truth(config, seed)
    return archive, truth


def _truth(cfg: PlantedConfig, seed: int) -> PlantedTruth:
    """Closed-form expectations computed from what the archive actually contains:
    the EFFECTIVE flaky fraction n_flaky/n_items (rounding matters at small n), and
    the per-draw q vector (q_shift_at_draw makes draws non-identically distributed;
    the pairwise-disagreement expectation below handles that exactly)."""
    eff = cfg.n_flaky / cfg.n_items
    shifted = cfg.q_shift_at_draw is not None

    def q_vector(model_index: int) -> list[float]:
        return [_q_effective(cfg, model_index, d) for d in range(cfg.k)]

    def mean_pair_disagreement(qs: list[float]) -> float:
        # E[f] for one flaky item = mean over draw pairs of P(disagree) with
        # per-draw probabilities; collapses to 2q(1-q) when all q_i equal.
        k = len(qs)
        total = 0.0
        for i in range(k):
            for j in range(i + 1, k):
                total += qs[i] * (1 - qs[j]) + qs[j] * (1 - qs[i])
        return total / (k * (k - 1) / 2)

    def mixed_prob(qs: list[float]) -> float:
        all_pass = 1.0
        all_fail = 1.0
        for q in qs:
            all_pass *= q
            all_fail *= 1 - q
        return 1.0 - all_pass - all_fail

    sigmas: dict[str, float | None] = {
        model: (
            None
            if shifted  # draws not identically distributed; single sigma undefined
            else (eff * cfg.q_for(i) * (1.0 - cfg.q_for(i)) / cfg.n_items) ** 0.5
        )
        for i, model in enumerate(cfg.models)
    }
    pairs = {}
    for i in range(len(cfg.models)):
        for j in range(i + 1, len(cfg.models)):
            a, b = cfg.models[i], cfg.models[j]
            gap = cfg.true_score(i) - cfg.true_score(j)
            sig_a, sig_b = sigmas[a], sigmas[b]
            pairs[f"{a}|{b}"] = {
                "true_gap": gap,
                "expected_flip_prob": (
                    expected_flip_prob(gap, sig_a, sig_b)
                    if sig_a is not None and sig_b is not None
                    else None
                ),
            }
    expected = {
        "effective_flaky_fraction": eff,
        "mean_flakiness_per_model": {
            model: eff * mean_pair_disagreement(q_vector(i))
            for i, model in enumerate(cfg.models)
        },
        "mixed_prob_per_model": {
            model: eff * mixed_prob(q_vector(i)) for i, model in enumerate(cfg.models)
        },
        "single_draw_score_sigma": sigmas,
        "pairs": pairs,
        "planted_defect_pairs_per_model": cfg.defect_items,
    }
    return PlantedTruth(
        config=cfg,
        seed=seed,
        true_ordering=tuple(cfg.models),
        true_scores={m: cfg.true_score(i) for i, m in enumerate(cfg.models)},
        expected=expected,
    )
