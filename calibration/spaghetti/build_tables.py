#!/usr/bin/env python3
"""One-time LOCAL generation of the calibration verdict tables. Never run in CI.

Runs the read-only Spaghetti-Architect adapter over a local checkout and writes
the verdict tables plus MANIFEST.json (provenance: upstream archive hashes,
table hashes, checkout commit). CI never needs the checkout: it regenerates
rulings from the committed tables only.

Usage:
    python calibration/spaghetti/build_tables.py --repo /path/to/Spaghetti-Architect
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from limen.adapters.spaghetti import TASKS, build_tables, is_stub, resolve_repo  # noqa: E402
from limen.canonical import canonical_json, sha256_file  # noqa: E402


def _stub_count(path: Path) -> int:
    import gzip
    import json

    with gzip.open(path, "rt", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip() and is_stub(json.loads(line)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=None)
    parser.add_argument("--task", action="append", choices=sorted(TASKS), default=None)
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()

    repo = resolve_repo(args.repo)
    tasks = tuple(args.task) if args.task else tuple(TASKS)
    paths = build_tables(repo, HERE / "tables", tasks=tasks, max_workers=args.workers)

    commit = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip() or None
    sources = {
        p.name: {"sha256": sha256_file(p), "stub_records_skipped": _stub_count(p)}
        for task in tasks
        for p in sorted(repo.glob(TASKS[task][0]))
    }
    manifest_path = HERE / "MANIFEST.json"
    manifest = (
        __import__("json").loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.is_file()
        else {}
    )
    manifest.setdefault("source", {})
    manifest["source"].update(
        {
            "checkout_commit": commit,
            "archives": {**manifest["source"].get("archives", {}), **sources},
            "generated_at": datetime.now(tz=UTC).isoformat(),
        }
    )
    manifest.setdefault("tables", {})
    for p in paths:
        manifest["tables"][p.name] = {"sha256": sha256_file(p)}
    manifest_path.write_text(canonical_json(manifest), encoding="utf-8", newline="")
    for p in paths:
        print(f"wrote {p}")
    print(f"wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
