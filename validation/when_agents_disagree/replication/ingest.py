#!/usr/bin/env python3
"""Grade raw replication runs into limen verdict tables.

Three deterministic grading rules, all fixed before data collection:
  fuzzy  - the paper's stated rule: normalized answer contains gold or vice
           versa, case-insensitive (headline table)
  em     - exact match under official SQuAD/HotpotQA normalization
  f1_05  - token F1 >= 0.5 under the same normalization

Items missing any (model, draw) cell are excluded and counted, never padded.

Usage:
  ingest.py --phase pilot            # accuracy summary + closeness pick
  ingest.py --phase main --models m1,m2,m3,m4 --out tables/
  ingest.py --self-test
"""

from __future__ import annotations

import argparse
import gzip
import itertools
import json
import re
import string
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
RUNS = REPO / "scratch" / "wad_replication" / "runs"

DRAWS = 10
_ARTICLES = re.compile(r"\b(a|an|the)\b")
_WS = re.compile(r"\s+")
PRICES_TOTAL = {  # input+output USD/M, tie-break only (see collect.py PRICES)
    "Qwen/Qwen2.5-72B-Instruct": 0.76,
    "Qwen/Qwen3-32B": 0.36,
    "google/gemma-3-27b-it": 0.24,
    "meta-llama/Llama-3.3-70B-Instruct-Turbo": 0.42,
    "microsoft/phi-4": 0.21,
    "mistralai/Mistral-Small-24B-Instruct-2501": 0.13,
}


def norm_simple(text: str) -> str:
    """The paper's rule needs only case-insensitivity; whitespace collapsed so
    span boundaries do not depend on formatting."""
    return _WS.sub(" ", text.casefold()).strip()


def norm_official(text: str) -> str:
    """SQuAD/HotpotQA answer normalization: lower, strip punctuation and
    articles, collapse whitespace."""
    text = text.casefold()
    text = "".join(ch for ch in text if ch not in set(string.punctuation))
    text = _ARTICLES.sub(" ", text)
    return _WS.sub(" ", text).strip()


def grade_fuzzy(pred: str, gold: str) -> int:
    p, g = norm_simple(pred), norm_simple(gold)
    if not p or not g:
        return 0
    return int(g in p or p in g)


def grade_em(pred: str, gold: str) -> int:
    p, g = norm_official(pred), norm_official(gold)
    return int(bool(g) and p == g)


def grade_f1_05(pred: str, gold: str) -> int:
    p, g = norm_official(pred).split(), norm_official(gold).split()
    if not p or not g:
        return 0
    common = Counter(p) & Counter(g)
    overlap = sum(common.values())
    if overlap == 0:
        return 0
    precision = overlap / len(p)
    recall = overlap / len(g)
    f1 = 2 * precision * recall / (precision + recall)
    return int(f1 >= 0.5)


GRADERS = {"fuzzy": grade_fuzzy, "em": grade_em, "f1_05": grade_f1_05}


def load_runs(phase: str, models: list[str]) -> dict:
    """{(model, item_id, draw): record}; a later record for the same key wins
    (a resumed run may re-record a previously stubbed cell)."""
    recs: dict = {}
    for model in models:
        path = RUNS / phase / f"{model.replace('/', '__')}.jsonl.gz"
        if not path.is_file():
            raise SystemExit(f"missing {path}")
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                recs[(r["model"], r["item_id"], r["draw"])] = r
    return recs


def complete_items(recs: dict, models: list[str]) -> tuple[list[str], int]:
    """Item ids with a non-stub record for every (model, draw); count dropped."""
    by_item: dict[str, int] = defaultdict(int)
    for (model, item_id, _draw), r in recs.items():
        if model in models and r["status"] in ("finished", "no_finish"):
            by_item[item_id] += 1
    want = len(models) * DRAWS
    complete = sorted(i for i, n in by_item.items() if n == want)
    return complete, len(by_item) - len(complete)


def write_table(
    recs: dict, models: list[str], items: list[str], rule: str, out: Path
) -> None:
    grader = GRADERS[rule]
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8", newline="") as fh:
        fh.write("model,task,item_id,draw_id,verdict,label_level,label_type\n")
        for model in models:
            for item_id in items:
                for d in range(DRAWS):
                    r = recs[(model, item_id, d)]
                    verdict = (
                        grader(r.get("final_answer", ""), r["gold"])
                        if r["status"] == "finished"
                        else 0
                    )
                    fh.write(
                        f"{model.replace('/', '-')},hotpotqa_distractor,"
                        f"{item_id},{d},{verdict},{r['level']},{r['type']}\n"
                    )


def pooled_accuracy(recs: dict, models: list[str], items: list[str]) -> dict:
    acc = {}
    for model in models:
        good = sum(
            grade_fuzzy(
                recs[(model, i, d)].get("final_answer", ""),
                recs[(model, i, d)]["gold"],
            )
            for i in items
            for d in range(DRAWS)
            if recs[(model, i, d)]["status"] == "finished"
        )
        acc[model] = good / (len(items) * DRAWS)
    return acc


def closeness_pick(acc: dict) -> tuple[list[str], float]:
    """Pre-registered rule: the 4-subset minimizing accuracy spread (max-min),
    ties by lower summed price, then lexicographic ids."""
    best = None
    for combo in itertools.combinations(sorted(acc), 4):
        spread = max(acc[m] for m in combo) - min(acc[m] for m in combo)
        price = sum(PRICES_TOTAL[m] for m in combo)
        key = (round(spread, 9), round(price, 6), combo)
        if best is None or key < best:
            best = key
    return list(best[2]), best[0]


def self_test() -> None:
    assert grade_fuzzy("The Springfield  city", "springfield") == 1
    assert grade_fuzzy("spring", "Springfield") == 1  # containment either way
    assert grade_fuzzy("shelbyville", "Springfield") == 0
    assert grade_fuzzy("", "x") == 0 and grade_fuzzy("x", "") == 0
    assert grade_em("The Beatles!", "beatles") == 1
    assert grade_em("beatles band", "beatles") == 0
    assert grade_f1_05("John Smith", "John Smith Jr") == 1  # F1 = 0.8
    assert grade_f1_05("John", "John Smith Jr") == 1  # F1 exactly 0.5, >= passes
    assert grade_f1_05("apple", "orange fruit") == 0
    acc = {"a": 0.60, "b": 0.62, "c": 0.61, "d": 0.90, "e": 0.58, "f": 0.63}
    prices = {m: 0.5 for m in acc}
    global PRICES_TOTAL
    saved = PRICES_TOTAL
    PRICES_TOTAL = prices
    try:
        picked, spread = closeness_pick(acc)
        assert picked == ["a", "b", "c", "f"], picked
        assert abs(spread - 0.03) < 1e-9
    finally:
        PRICES_TOTAL = saved
    print("self-test OK")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase", choices=["pilot", "main"])
    ap.add_argument("--models", type=str, default="")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.phase:
        ap.error("--phase required (or --self-test)")
    if args.models:
        models = [m.strip() for m in args.models.split(",")]
    else:
        from collect import PILOT_MODELS

        models = PILOT_MODELS
    recs = load_runs(args.phase, models)
    items, dropped = complete_items(recs, models)
    print(f"{len(items)} complete items, {dropped} dropped for missing cells")
    statuses = Counter(r["status"] for r in recs.values())
    print("statuses:", dict(statuses))
    acc = pooled_accuracy(recs, models, items)
    for m in sorted(acc, key=acc.get, reverse=True):
        print(f"  {acc[m]:.3f}  {m}")
    if args.phase == "pilot":
        picked, spread = closeness_pick(acc)
        print(f"closeness pick (spread {spread:.3f}):")
        for m in picked:
            print(f"  {m}")
    if args.out:
        for rule in GRADERS:
            name = "wad_replication" if rule == "fuzzy" else f"wad_replication_{rule}"
            write_table(recs, models, items, rule, args.out / f"{name}.verdicts.csv.gz")
            print(f"wrote {args.out / name}.verdicts.csv.gz")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    raise SystemExit(main())
