"""The same-configuration noise floor and the minimum detectable difference.

The noise floor is the spread of the k single-draw scores — the honest,
model-free statement of how much the number you would have published moves
between identical runs. The MDD follows Kalibera & Jones, *Rigorous
benchmarking in reasonable time* (ISMM 2013), specialized to one level of
repetition, with the conservative df choice and every assumption printed
(spec ruling LMN-NSE-001). It is cited, not reinvented.
"""

from __future__ import annotations

from typing import Any

from .canonical import fmt_float
from .stats import mean, sample_sd, t_quantile_975

MDD_CITATION = "Kalibera & Jones, Rigorous benchmarking in reasonable time, ISMM 2013"

MDD_ASSUMPTIONS: tuple[str, ...] = (
    "each single-draw score is treated as approximately normal (mean over n items; CLT)",
    "the k draws are treated as i.i.d.; the drift guard polices exactly this assumption",
    "draws are not treated as paired across models; two-sample unpooled-variance form",
    "df = k-1, the conservative choice (Welch df would be larger and the MDD smaller)",
    "speaks to draw noise on this fixed item set only, not to item-sampling variability",
)


def draw_spread(scores: list[float]) -> dict[str, Any]:
    """min/max/range/mean/sd of the k single-draw scores (ddof=1)."""
    if len(scores) < 2:
        raise ValueError("noise floor needs k >= 2 single-draw scores")
    return {
        "k": len(scores),
        "score_min": fmt_float(min(scores)),
        "score_max": fmt_float(max(scores)),
        "score_range": fmt_float(max(scores) - min(scores)),
        "score_mean": fmt_float(mean(scores)),
        "score_sd": fmt_float(sample_sd(scores)),
    }


def mdd_pair(sd_a: float, sd_b: float, k: int, n_items: int) -> dict[str, Any]:
    """MDD = t_{0.975, k-1} * sqrt((sd_a^2 + sd_b^2) / k), assumptions attached."""
    if k < 2:
        raise ValueError("MDD needs k >= 2")
    df = k - 1
    t = t_quantile_975(df)
    value = t * ((sd_a**2 + sd_b**2) / k) ** 0.5
    return {
        "value": fmt_float(value),
        "t": t,
        "df": df,
        "alpha": 0.05,
        "low_k": k < 4,
        "degenerate_zero_spread": sd_a == 0.0 and sd_b == 0.0,
        "score_resolution": fmt_float(1.0 / n_items),
        "assumptions": list(MDD_ASSUMPTIONS),
        "citation": MDD_CITATION,
    }
