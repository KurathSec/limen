"""Byte-stability primitives (LMN-EMIT-001)."""

import math

import pytest

from limen.canonical import canonical_json, content_hash, counted, derive_seed, fmt_float


def test_fmt_float_rounds_and_normalizes_negative_zero() -> None:
    assert fmt_float(0.1234567) == 0.123457
    assert str(fmt_float(-0.0)) == "0.0"
    assert fmt_float(1.0) == 1.0


def test_fmt_float_refuses_non_finite() -> None:
    for bad in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError):
            fmt_float(bad)


def test_canonical_json_sorted_lf_trailing_newline() -> None:
    text = canonical_json({"b": 1, "a": [2, 1]})
    assert text.endswith("\n")
    assert text.index('"a"') < text.index('"b"')
    assert "\r" not in text
    assert canonical_json({"b": 1, "a": [2, 1]}) == text  # idempotent


def test_content_hash_excludes_itself() -> None:
    body = {"x": 1}
    h = content_hash(body)
    assert content_hash({"x": 1, "content_hash": h}) == h


def test_counted_never_bare() -> None:
    c = counted(3, 8)
    assert c == {"count": 3, "denominator": 8, "rate": 0.375}
    assert counted(0, 0)["rate"] is None


def test_derive_seed_deterministic_and_labelled() -> None:
    assert derive_seed("v1", "t", "proc", 0) == derive_seed("v1", "t", "proc", 0)
    assert derive_seed("v1", "t", "proc", 0) != derive_seed("v1", "t", "proc", 1)
    assert derive_seed("v1", "t", "proc", 0) != derive_seed("v2", "t", "proc", 0)
