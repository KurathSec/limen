#!/usr/bin/env python3
"""The only supported way to move the committed calibration rulings.

Regenerates every golden report from the committed verdict tables and compares
bytes. Modes:

  --check                exit 1 if any golden would change or is missing (CI)
  --write                write missing goldens (new tables are always allowed)
  --write --confirm-spec-bump
                         overwrite CHANGED goldens; refused unless the rulings
                         spec MAJOR version moved since the committed goldens

A changed byte in an existing golden is a changed recorded meaning: it needs a
spec bump and an explicit flag, never a silent refresh. Deleting or emptying a
baseline is refused outright.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from limen.canonical import canonical_json, sha256_file  # noqa: E402
from limen.readers import load  # noqa: E402
from limen.report import ReportOptions, build_report  # noqa: E402
from limen.spec import spec_version  # noqa: E402

CALIBRATION = ROOT / "calibration" / "spaghetti"
RULINGS_VERSION = "cal1"
OPTIONS = ReportOptions(
    replicates=1000, max_splits=256, assume_index_is_collection_order=True
)


def _major(version: str) -> str:
    return version.split(".", 1)[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument("--confirm-spec-bump", action="store_true")
    args = parser.parse_args()

    tables = sorted(CALIBRATION.glob("tables/*.verdicts.csv.gz"))
    if not tables:
        print("no calibration tables found; nothing to do")
        return 0

    rulings_dir = CALIBRATION / "rulings" / RULINGS_VERSION
    pending_new: list[str] = []
    pending_changed: list[str] = []
    ok = 0
    for table in tables:
        golden = rulings_dir / table.name.replace(".verdicts.csv.gz", ".report.json")
        print(f"regenerating from {table.name} ...", flush=True)
        archive = load(table)
        text = canonical_json(
            build_report(archive, rulings_version=RULINGS_VERSION, options=OPTIONS)
        )
        if not golden.is_file():
            pending_new.append(golden.name)
            if args.write:
                golden.parent.mkdir(parents=True, exist_ok=True)
                golden.write_text(text, encoding="utf-8", newline="")
                print(f"  wrote NEW golden {golden.name}")
            continue
        committed = golden.read_text(encoding="utf-8")
        if committed == text:
            ok += 1
            continue
        pending_changed.append(golden.name)
        if args.write:
            committed_spec = json.loads(committed).get("spec_version", "0.0.0")
            if not args.confirm_spec_bump:
                print(
                    f"  REFUSED: {golden.name} bytes changed; a changed recorded "
                    "meaning needs --confirm-spec-bump (and a spec MAJOR bump)"
                )
                continue
            if _major(committed_spec) == _major(spec_version()):
                print(
                    f"  REFUSED: --confirm-spec-bump given but spec MAJOR did not move "
                    f"({committed_spec} -> {spec_version()})"
                )
                continue
            golden.write_text(text, encoding="utf-8", newline="")
            print(f"  overwrote {golden.name} under spec {spec_version()}")

    # refresh manifest table hashes when writing
    manifest_path = CALIBRATION / "MANIFEST.json"
    if args.write and manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for table in tables:
            manifest.setdefault("tables", {}).setdefault(table.name, {})["sha256"] = (
                sha256_file(table)
            )
        manifest_path.write_text(canonical_json(manifest), encoding="utf-8", newline="")

    print(
        f"goldens: {ok} unchanged, {len(pending_new)} new, {len(pending_changed)} changed"
    )
    if args.check and (pending_new or pending_changed):
        print("CHECK FAILED: goldens out of date", file=sys.stderr)
        return 1
    if args.write and pending_changed and not args.confirm_spec_bump:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
