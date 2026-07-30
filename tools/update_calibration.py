#!/usr/bin/env python3
"""The only supported way to move the committed calibration rulings.

Regenerates every golden report from the committed verdict tables and
classifies the difference via limen.evolution (LMN-EMIT-008):

  identical    nothing to do
  stamp_only   only the spec_version stamp (and the hashes covering it)
               moved; refreshed under --write on any spec movement
  additive     the regenerated document only ADDS fields; every committed
               leaf is present and byte-equal; accepted under plain --write
               once the rulings spec moved by at least MINOR
  changed      a committed value moved or vanished; a changed recorded
               meaning, demanding a spec MAJOR and --confirm-spec-bump

Modes:

  --check                exit 1 if any golden would change or is missing (CI)
  --write                write missing goldens; apply stamp_only and eligible
                         additive refreshes
  --write --confirm-spec-bump
                         additionally overwrite CHANGED goldens; refused
                         unless the rulings spec MAJOR moved
  --root PATH            repo root (default: this file's repo); lets tests
                         run the tool against a temporary calibration tree
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src"))

from limen.canonical import canonical_json, sha256_file  # noqa: E402
from limen.evolution import compare_documents, spec_moved_minor_or_more  # noqa: E402
from limen.readers import load  # noqa: E402
from limen.report import ReportOptions, build_report  # noqa: E402
from limen.spec import spec_version  # noqa: E402

RULINGS_VERSION = "cal1"
OPTIONS = ReportOptions(
    replicates=1000,
    max_splits=256,
    assume_index_is_collection_order=True,
    bootstrap=1000,
    stratify_by=("language",),
    stratum_replicates=200,
    stratum_floor=30,
)


def _major(version: str) -> str:
    return version.split(".", 1)[0]


def _sections(paths: tuple[str, ...]) -> str:
    """Dedup added paths to their top-level sections for a readable summary."""
    tops = sorted({p.split("[")[0].split(".")[0] + "…" if "." in p or "[" in p else p for p in paths})
    return ", ".join(tops[:8]) + ("…" if len(tops) > 8 else "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument("--confirm-spec-bump", action="store_true")
    parser.add_argument("--root", type=Path, default=_REPO)
    args = parser.parse_args()

    calibration = args.root / "calibration" / "spaghetti"
    tables = sorted(calibration.glob("tables/*.verdicts.csv.gz"))
    rulings_dir = calibration / "rulings" / RULINGS_VERSION
    # a golden whose table is gone verifies nothing; it must fail the gate,
    # never be skipped (deleting it is a deliberate act, not this tool's)
    expected_goldens = {
        t.name.replace(".verdicts.csv.gz", ".report.json") for t in tables
    }
    orphans = sorted(
        p.name
        for p in rulings_dir.glob("*.report.json")
        if p.name not in expected_goldens
    )
    if not tables and not orphans:
        print("no calibration tables found; nothing to do")
        return 0
    pending_new: list[str] = []
    pending_refresh: list[str] = []  # stamp_only or eligible additive, not yet written
    pending_changed: list[str] = []
    ok = 0
    for table in tables:
        golden = rulings_dir / table.name.replace(".verdicts.csv.gz", ".report.json")
        print(f"regenerating from {table.name} ...", flush=True)
        archive = load(table)
        regenerated = build_report(
            archive, rulings_version=RULINGS_VERSION, options=OPTIONS
        )
        text = canonical_json(regenerated)
        if not golden.is_file():
            pending_new.append(golden.name)
            if args.write:
                golden.parent.mkdir(parents=True, exist_ok=True)
                golden.write_text(text, encoding="utf-8", newline="")
                print(f"  wrote NEW golden {golden.name}")
            continue
        committed_text = golden.read_text(encoding="utf-8")
        if committed_text == text:
            ok += 1
            continue
        committed = json.loads(committed_text)
        committed_spec = committed.get("spec_version", "0.0.0")
        diff = compare_documents(committed, regenerated)

        if diff.classification == "stamp_only":
            if args.write:
                golden.write_text(text, encoding="utf-8", newline="")
                print(f"  refreshed spec stamp on {golden.name} ({spec_version()})")
                ok += 1
            else:
                pending_refresh.append(golden.name)
                print(f"  {golden.name}: stamp-only change pending (run --write)")
            continue

        if diff.classification == "additive":
            if not spec_moved_minor_or_more(committed_spec, spec_version()):
                pending_changed.append(golden.name)
                print(
                    f"  REFUSED: {golden.name} gains {len(diff.added_paths)} paths but "
                    f"the rulings spec did not move by at least MINOR "
                    f"({committed_spec} -> {spec_version()}); bump the spec first "
                    "(LMN-EMIT-008)"
                )
                continue
            if args.write:
                golden.write_text(text, encoding="utf-8", newline="")
                print(
                    f"  ADDITIVE refresh of {golden.name}: "
                    f"{len(diff.added_paths)} paths added, 0 values changed, "
                    f"spec {committed_spec} -> {spec_version()} "
                    f"(sections: {_sections(diff.added_paths)})"
                )
                ok += 1
            else:
                pending_refresh.append(golden.name)
                print(
                    f"  {golden.name}: additive change pending "
                    f"({len(diff.added_paths)} added paths; run --write)"
                )
            continue

        # changed: the heavy ceremony
        pending_changed.append(golden.name)
        for violation in diff.violations[:5]:
            print(f"    {violation}")
        if args.write:
            if not args.confirm_spec_bump:
                print(
                    f"  REFUSED: {golden.name} changed recorded values; needs "
                    "--confirm-spec-bump (and a spec MAJOR bump)"
                )
                continue
            if int(_major(spec_version())) <= int(_major(committed_spec)):
                print(
                    f"  REFUSED: --confirm-spec-bump given but the live spec MAJOR is "
                    f"not beyond the committed golden's "
                    f"({committed_spec} -> {spec_version()})"
                )
                continue
            golden.write_text(text, encoding="utf-8", newline="")
            print(f"  overwrote {golden.name} under spec {spec_version()}")
            pending_changed.pop()
            ok += 1

    for name in orphans:
        print(
            f"  ORPHANED golden {name}: no matching verdict table, so nothing "
            "verifies it; restore the table or delete the golden deliberately"
        )
    pending_changed.extend(orphans)

    manifest_path = calibration / "MANIFEST.json"
    # never re-pin table hashes on a run that refused anything: a refusing run
    # must leave the tamper-evidence exactly as it found it
    if args.write and not pending_changed and manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for table in tables:
            manifest.setdefault("tables", {}).setdefault(table.name, {})["sha256"] = (
                sha256_file(table)
            )
        manifest_path.write_text(canonical_json(manifest), encoding="utf-8", newline="")

    print(
        f"goldens: {ok} up to date, {len(pending_new)} new, "
        f"{len(pending_refresh)} refresh-pending, {len(pending_changed)} changed"
    )
    if args.check and (pending_new or pending_refresh or pending_changed):
        print("CHECK FAILED: goldens out of date", file=sys.stderr)
        return 1
    if args.write and pending_changed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
