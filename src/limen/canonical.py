"""Canonical serialization: the byte-stability contract.

Every committed ruling document is produced through this module, and regeneration
must be byte-identical (spec ruling LMN-EMIT-001). The rules:

- floats pass ``fmt_float`` (round to 6 places, ``-0.0`` normalized to ``0.0``);
  NaN and infinities raise — upstream code must have turned them into null-with-state;
- ``json.dumps(sort_keys=True, indent=2, ensure_ascii=True)`` plus a trailing newline;
- gzip written with ``mtime=0`` so archives are byte-stable too;
- content hashes are sha256 over the canonical bytes with the ``content_hash`` field
  removed, so a document can carry its own address.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
from pathlib import Path
from typing import Any


def fmt_float(x: float) -> float:
    """Normalize a float for serialization: round half-even to 6 places, kill -0.0."""
    if math.isnan(x) or math.isinf(x):
        raise ValueError("non-finite float reached serialization; upstream must emit null")
    return round(x, 6) + 0.0


def counted(count: int, denominator: int) -> dict[str, Any]:
    """A count that can never appear without its denominator (spec ruling LMN-EMIT-002)."""
    return {
        "count": count,
        "denominator": denominator,
        "rate": fmt_float(count / denominator) if denominator else None,
    }


def canonical_json(body: Any) -> str:
    """The canonical text form: sorted keys, 2-space indent, ASCII, trailing newline."""
    return json.dumps(body, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def content_hash(body: dict[str, Any]) -> str:
    """sha256 of the canonical bytes with the content_hash field removed."""
    stripped = {k: v for k, v in body.items() if k != "content_hash"}
    digest = hashlib.sha256(canonical_json(stripped).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def derive_seed(*parts: str | int) -> int:
    """Deterministic seed from labelled parts (spec ruling LMN-EMIT-003).

    No stochastic procedure in limen may seed itself from the clock; every seed is
    derived from the rulings version, the scope, the procedure name, and an index.
    """
    text = "|".join(str(p) for p in parts)
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")


def write_text_deterministic(path: Path, text: str) -> None:
    """Write UTF-8 text with LF endings exactly as given."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def write_gzip_deterministic(path: Path, data: bytes) -> None:
    """Write a gzip member with mtime=0 and no embedded filename, so identical
    data gives identical bytes regardless of where or when it is written.

    Scope of the guarantee: bytes are stable per zlib build. A different zlib
    (e.g. zlib-ng) may compress identical data differently, which is why the
    byte-compared calibration artifacts are the JSON ruling documents, while
    committed .gz tables are pinned by hash in a manifest and never regenerated
    in CI."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as gz:
            gz.write(data)
