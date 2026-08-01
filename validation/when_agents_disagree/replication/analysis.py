#!/usr/bin/env python3
"""The pre-registered comparison against arXiv 2602.11619's statistics.

Computes, on the main-phase fuzzy verdict table:
  1. the paper's bootstrap misranking statistic: sample one run per question
     per model, rank by mean, compare with the all-runs pooled ranking;
     10,000 seeded iterations, Wilson 95% interval (paper: 29.3% [28.4,30.1])
  2. limen's native intact-draw misranking (read from the limen report)
  3. the stable/unstable accuracy split per model (u_i == 0 vs u_i > 0),
     direction compared with the paper's consistent 82-87% vs 41-65%

Usage: analysis.py --table tables/wad_replication.verdicts.csv.gz --report report/report.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from limen.readers import load  # noqa: E402

BOOT_ITERS = 10_000
SEED_TAG = "wad-replication-analysis-v1"


def wilson(p: float, n: int) -> tuple[float, float]:
    z = 1.959963984540054
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return center - half, center + half


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--table", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    archive = load(args.table)
    task = archive.tasks[0]
    models = list(archive.models)
    items = sorted(
        set.intersection(*(set(archive.items(m, task)) for m in models))
    )
    k = archive.cell(models[0], task, items[0]).k
    verdicts = {
        m: {i: archive.cell(m, task, i).verdicts for i in items} for m in models
    }

    # pooled ("multi-run ground truth") ranking, ties reported not broken
    pooled = {
        m: sum(sum(verdicts[m][i]) for i in items) / (len(items) * k)
        for m in models
    }
    truth = tuple(sorted(models, key=lambda m: (-pooled[m], m)))
    print("pooled accuracy (all runs):")
    for m in truth:
        print(f"  {pooled[m]:.4f}  {m}")

    # 1. the paper's statistic: one sampled run per question per model
    seed = int.from_bytes(hashlib.sha256(SEED_TAG.encode()).digest()[:8], "big")
    rng = random.Random(seed)
    misrank = 0
    for _ in range(BOOT_ITERS):
        means = {
            m: sum(verdicts[m][i][rng.randrange(k)] for i in items) / len(items)
            for m in models
        }
        order = tuple(sorted(models, key=lambda m: (-means[m], m)))
        if order != truth:
            misrank += 1
    p = misrank / BOOT_ITERS
    lo, hi = wilson(p, BOOT_ITERS)
    print(
        f"\npaper-statistic misranking: {p:.1%} [{lo:.1%}, {hi:.1%}] "
        f"({BOOT_ITERS} iterations; paper reports 29.3% [28.4%, 30.1%] "
        "on its own four models)"
    )

    # 2. limen's native intact-draw misranking, from the committed report
    report = json.loads(args.report.read_text())
    task_block = next(
        t for t in report["rulings"]["task"] if t["scope_key"]["task"] == task
    )
    print(
        "limen intact-draw misranking:",
        json.dumps(task_block["misrank"], sort_keys=True),
    )

    # 3. stable vs unstable accuracy per model (u == 0 means all k agree)
    print("\nstable/unstable accuracy split (paper: 82-87% vs 41-65%):")
    for m in models:
        stable = [i for i in items if sum(verdicts[m][i]) in (0, k)]
        unstable = [i for i in items if i not in set(stable)]
        acc_s = (
            sum(sum(verdicts[m][i]) for i in stable) / (len(stable) * k)
            if stable
            else float("nan")
        )
        acc_u = (
            sum(sum(verdicts[m][i]) for i in unstable) / (len(unstable) * k)
            if unstable
            else float("nan")
        )
        print(
            f"  {m}: stable {len(stable)} items at {acc_s:.3f}, "
            f"unstable {len(unstable)} items at {acc_u:.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
