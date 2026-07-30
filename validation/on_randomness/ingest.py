#!/usr/bin/env python3
"""Ingest the "On Randomness in Agentic Evals" trajectories into a verdict table.

Source: Bjarnason, Silva and Monperrus, "On Randomness in Agentic Evals -
Trajectories", Zenodo, doi 10.5281/zenodo.18684663 (CC-BY-4.0). The archive
holds, per configuration directory ({scaffold-model}[__temp0]) and per run
(run_0..run_9), a SWE-bench harness report JSON (resolved_ids over the
500-instance SWE-Bench-Verified universe) and a preds.jsonl with each
instance's submitted model_patch.

Mapping into limen's long verdict table:

- task     = "swebench_verified"
- model    = the configuration directory name, verbatim (scaffold, model and
  temperature variant together; the write-up says so explicitly)
- item_id  = the SWE-bench instance id
- draw_id  = the run index
- verdict  = 1 if the instance is in that run's resolved_ids, else 0
- raw_sha256 = sha256 of the run's submitted model_patch for the instance
  (empty string when the patch is empty, a sentinel when absent), so limen's
  grader-defect check can count byte-identical patches whose resolution
  differs between runs: measured evaluation-harness nondeterminism.

No collected_at exists in the reports, so the drift guard reports UNAVAILABLE,
which is the honest state for this archive.

Usage:
    python validation/on_randomness/ingest.py --archive-dir <extracted-tree> \
        --out validation/on_randomness/tables
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from limen.model import VerdictRow, build_archive  # noqa: E402
from limen.readers.longcsv import write_archive  # noqa: E402

TASK = "swebench_verified"
ABSENT_SENTINEL = "<no-prediction-submitted>"


def _find_report(run_dir: Path) -> dict[str, object] | None:
    for path in sorted(run_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(data, dict) and "resolved_ids" in data and "submitted_ids" in data:
            return data
    return None


def _patch_hashes(run_dir: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    preds = run_dir / "preds.jsonl"
    if not preds.is_file():
        return hashes
    with open(preds, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            instance = rec.get("instance_id")
            if instance is None:
                continue
            patch = rec.get("model_patch") or ""
            hashes[str(instance)] = (
                "sha256:" + hashlib.sha256(str(patch).encode("utf-8")).hexdigest()
            )
    return hashes


def ingest(archive_dir: Path, out_dir: Path) -> Path:
    rows: list[VerdictRow] = []
    configs = sorted(
        p for p in archive_dir.iterdir() if p.is_dir() and any(p.glob("run_*"))
    )
    if not configs:
        raise SystemExit(f"{archive_dir}: no configuration directories with run_* found")
    absent_hash = "sha256:" + hashlib.sha256(ABSENT_SENTINEL.encode()).hexdigest()
    for config in configs:
        for run_dir in sorted(config.glob("run_*")):
            run = run_dir.name.split("_", 1)[1]
            report = _find_report(run_dir)
            if report is None:
                print(f"WARN {run_dir}: no harness report json; run skipped", file=sys.stderr)
                continue
            resolved = set(map(str, report["resolved_ids"]))  # type: ignore[index]
            submitted = sorted(map(str, report["submitted_ids"]))  # type: ignore[index]
            hashes = _patch_hashes(run_dir)
            for instance in submitted:
                rows.append(
                    VerdictRow(
                        model=config.name,
                        task=TASK,
                        item_id=instance,
                        draw_id=run,
                        verdict=1 if instance in resolved else 0,
                        raw_sha256=hashes.get(instance, absent_hash),
                    )
                )
        print(f"{config.name}: ingested", file=sys.stderr)
    archive = build_archive(
        rows, meta={"reader": "on-randomness-ingest", "source": archive_dir.name}
    )
    out_path = out_dir / "on_randomness.verdicts.csv.gz"
    write_archive(archive, out_path)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    out = ingest(args.archive_dir, args.out)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
