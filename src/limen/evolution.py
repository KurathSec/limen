"""Document-diff classification: how a regenerated golden may differ (LMN-EMIT-008).

Four classes, from strictest to loosest ceremony:

- ``identical``: byte-equal after canonicalization; nothing to do.
- ``stamp_only``: only the ``spec_version`` stamp (and the hashes covering it)
  moved; refreshable on any spec movement.
- ``additive``: every committed leaf value is present and byte-equal at the
  same path in the regenerated document, and the regenerated document only
  adds; acceptable under a plain ``--write`` once the rulings spec has moved
  by at least MINOR. Adding is cheap by design so that adding is never
  smuggled in as changing.
- ``changed``: a committed value moved or vanished; a changed recorded
  meaning, demanding a spec MAJOR and an explicit flag.

Comparison rules: every ``content_hash`` key is stripped at any depth (hashes
are derived addresses over content that legitimately changed by addition);
``spec_version`` and ``limen_schema`` at the top level are exempt stamps;
dicts compare per key with regenerated-only keys recorded as additions;
arrays must be equal length and compare positionally (every array in the
schema has a documented sort order, so any reorder or length change is a
change, deliberately including appends to fixed lists like the scope codes);
scalars compare by canonical JSON bytes, so ``0`` versus ``0.0`` is a change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .canonical import canonical_json

STAMP_KEYS = ("spec_version", "limen_schema")


@dataclass(frozen=True, slots=True)
class DocumentDiff:
    classification: Literal["identical", "stamp_only", "additive", "changed"]
    added_paths: tuple[str, ...]
    violations: tuple[str, ...]


def strip_content_hashes(node: Any) -> Any:
    if isinstance(node, dict):
        return {
            key: strip_content_hashes(value)
            for key, value in node.items()
            if key != "content_hash"
        }
    if isinstance(node, list):
        return [strip_content_hashes(item) for item in node]
    return node


def _walk(
    committed: Any,
    regenerated: Any,
    path: str,
    added: list[str],
    violations: list[str],
) -> None:
    if isinstance(committed, dict) and isinstance(regenerated, dict):
        for key in committed:
            child = f"{path}.{key}" if path else key
            if key not in regenerated:
                violations.append(f"removed key at {child}")
                continue
            _walk(committed[key], regenerated[key], child, added, violations)
        for key in regenerated:
            if key not in committed:
                added.append(f"{path}.{key}" if path else key)
        return
    if isinstance(committed, list) and isinstance(regenerated, list):
        if len(committed) != len(regenerated):
            violations.append(
                f"array length changed at {path}: {len(committed)} -> {len(regenerated)}"
            )
            return
        for i, (a, b) in enumerate(zip(committed, regenerated, strict=True)):
            _walk(a, b, f"{path}[{i}]", added, violations)
        return
    if isinstance(committed, dict | list) or isinstance(regenerated, dict | list):
        violations.append(f"shape changed at {path}")
        return
    if canonical_json(committed) != canonical_json(regenerated):
        violations.append(
            f"changed value at {path}: {committed!r} -> {regenerated!r}"
        )


def compare_documents(
    committed: dict[str, Any], regenerated: dict[str, Any]
) -> DocumentDiff:
    """Classify how regenerated differs from committed (see module docstring)."""
    a = strip_content_hashes(committed)
    b = strip_content_hashes(regenerated)
    stamps_moved = any(a.get(key) != b.get(key) for key in STAMP_KEYS)
    for key in STAMP_KEYS:
        a.pop(key, None)
        b.pop(key, None)
    added: list[str] = []
    violations: list[str] = []
    _walk(a, b, "", added, violations)
    if violations:
        return DocumentDiff("changed", tuple(sorted(added)), tuple(violations))
    if added:
        return DocumentDiff("additive", tuple(sorted(added)), ())
    if stamps_moved:
        return DocumentDiff("stamp_only", (), ())
    return DocumentDiff("identical", (), ())


def spec_moved_minor_or_more(old: str, new: str) -> bool:
    """True when new is at least a MINOR ahead of old (same-major minor bump,
    or any major bump)."""
    old_major, old_minor = (int(x) for x in old.split(".")[:2])
    new_major, new_minor = (int(x) for x in new.split(".")[:2])
    if new_major > old_major:
        return True
    return new_major == old_major and new_minor > old_minor
