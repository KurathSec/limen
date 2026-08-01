# Conceptual replication: the close-models regime, first-party data

The parent pre-registration ([../README.md](../README.md)) targets the
unreleased artifact of arXiv 2602.11619. This directory is its fallback
limb, chosen when the data remained unreleased: a **conceptual replication**
of the paper's design on models we can run ourselves. It replicates the
regime (close models, repeated identical runs, agentic multi-hop QA), not
the paper's models or scaffold, and it never claims to reproduce their
numbers. The comparison target is qualitative: does the misranking
phenomenon appear, and how does limen rule on it.

## Design, fixed before any run was collected

Everything in this section was committed before the first API call of the
main phase; the pilot exists only to measure cost and execute the
pre-registered model pick.

- **Substrate**: HotpotQA dev, distractor setting (public, CC BY-SA 4.0),
  the item's own provided paragraphs as the whole corpus (7,345 of 7,405
  items carry exactly ten; 60 carry fewer, used as shipped). The dataset's
  `level` field is `hard` for the entire dev-distractor split, so the
  informative stratification key is `type` (bridge 5,918 / comparison
  1,487); `level` is still recorded, and the paper's own easy/medium/hard
  split was post-hoc on outcomes, which limen deliberately does not
  stratify on (selection on the measured quantity).
- **Item selection**: deterministic — items sorted by `_id`,
  `random.Random(sha256("wad-replication-v1")[:8])` samples 220; the first
  20 are the pilot set, the next 200 the main set, disjoint by
  construction (`collect.py --self-test` pins this).
- **Agent**: ReAct with the paper's three tools. Search ranks the ten
  titles by query-token overlap (ties by paragraph order); Retrieve
  returns the titled paragraph (case-insensitive exact match, containment
  fallback); Finish terminates. One Thought/Action pair per turn, at most
  8 turns; a run that never calls Finish is recorded `no_finish` and
  graded 0. Malformed replies get a format reminder and consume a turn.
  The last well-formed action in a reply wins; `<think>` blocks are
  stripped before parsing, and Qwen3-32B gets its documented `/no_think`
  soft switch (recorded deviation: we want the non-reasoning regime the
  other models are in).
- **Decoding**: temperature 0.7 (the paper's), max 384 tokens per call.
- **Runs**: 10 identical runs per (model, item), the paper's k.
- **Models**: six candidates on one endpoint (DeepInfra):
  Qwen2.5-72B-Instruct, Qwen3-32B, gemma-3-27b-it,
  Llama-3.3-70B-Instruct-Turbo, phi-4, Mistral-Small-24B-Instruct-2501.
  The main phase uses the 4-subset of pilot pooled accuracies (fuzzy rule)
  minimizing max minus min, ties broken by lower summed price then
  lexicographic id (`closeness_pick`, pinned by self-test). The pilot and
  main item sets are disjoint, so the pick cannot leak into the measured
  items.
- **Grading** (deterministic code paths, `ingest.py --self-test`):
  headline `fuzzy` = the paper's stated rule (normalized containment
  either way, case-insensitive); robustness variants `em` (official
  SQuAD/HotpotQA normalization, exact) and `f1_05` (token F1 >= 0.5) as
  separate tables.
- **Completeness**: an item missing any (model, draw) cell after retries is
  excluded and counted, never padded or partially graded.
- **Budget**: hard in-code cap (pilot $3, total $30) on accumulated
  actual-usage cost; the collector aborts resumable at the cap.

## Pre-registered analysis (unchanged from the parent protocol)

`limen report` on the fuzzy table (bootstrap 1000, stratified by `level`
and `type`), then:

1. limen's native misranking-draws statistic and the paper's bootstrap
   statistic (one run per question per model, 10,000 iterations) computed
   by `analysis.py`; the paper reports 29.3% [28.4, 30.1] for its models —
   ours is expected in the same regime IF the pick achieves comparable
   closeness, and reported as-measured either way.
2. Gap-survival rulings: pairs inside the replicate noise regime are
   expected FALLS-INTO-NOISE / SIGN-UNSTABLE; well-separated pairs (if the
   pick leaves any) SURVIVES with margins.
3. Stable-partition accuracy split direction vs the paper's
   consistent > inconsistent.
4. Draw main-effect variance component ~ 0 (item-local instability), k=10
   below the 20-level interval floor acknowledged.

## Results (2026-08-01, as measured, misses included)

Collection: pilot $0.43 (1,200 episodes, 0 stubs), main $3.08 (8,000
episodes, 0 stubs, all 200 items complete; 934 runs never called Finish
and are graded 0 per protocol). The pilot pick selected Qwen2.5-72B,
gemma-3-27b, Llama-3.3-70B and phi-4 (pilot spread 5.0pp). On the main
set the top three landed within 0.9pp of one another (62.35 / 62.30 /
61.50%) with phi-4 at 48.50% — a tighter cluster than the paper's own
(81.5–72.2%).

**Misranking.** Under the paper's exact statistic (one sampled run per
question per model, 10,000 seeded iterations) 77.3% [76.4, 78.1] of
single-run evaluations misrank the pooled ordering, against the paper's
29.3% [28.4, 30.1] on its models. The direction follows the regime: our
cluster is much tighter than theirs, and closer models misrank more. On
intact draws, 6 of 10 single-draw leaderboards misrank at least one pair.
The three top-cluster pairs all rule SIGN-UNSTABLE; the three ~13.8pp
phi-4 pairs all rule SIGN-STABLE and clear their MDD 5.2 to 5.6-fold.

**Pre-registered expectations, scored.**

1. *Closest pairs rule SIGN-UNSTABLE and/or FALLS-INTO-NOISE* — held.
   All three top-cluster pairs are SIGN-UNSTABLE; two also rule
   FALLS-INTO-NOISE. The third (Qwen vs gemma) rules audit-SURVIVES with
   a removal margin of exactly 1 item: on this substrate every audit
   verdict is edge-balanced, and the witness quantifies it.
2. *Well-separated pairs rule SURVIVES* — **missed**, and the miss is the
   finding. Two of the three ~13.8pp pairs rule FALLS-INTO-NOISE with 92
   to 96% of the pooled gap riding on unstable items (the stable-for-both
   partitions shrink to 56–64 of 200 items because phi-4 is unstable on
   128); the third survives by 1 item. This replicates, on a second task
   family and substrate, the SWE-bench divergence: a gap that clears its
   MDD several-fold while resting almost wholly on inconsistently-decided
   items.
3. *Stable-partition accuracy exceeds unstable, as the paper's
   consistent > inconsistent* — **split**: it holds for Qwen (64.5 vs
   54.2%) and gemma (66.9 vs 51.2%), is flat for Llama (61.8 vs 62.9%),
   and inverts for phi-4 (37.5 vs 54.7%), whose stable set is dominated
   by always-fail items. This is the pre-declared boundary made visible:
   u_i never compounds with correctness (an always-wrong item is stable),
   while the paper's consistency is defined on action paths. The two
   partitions measure different things exactly where a weak model fails
   reliably.
4. *Draw main-effect component ~ 0* — held, 4 of 4 models (largest raw
   2.8e-4, every interval containing zero; instability is item-local).
   The item-by-draw residual runs 23–49% of variance against 3–9% on the
   temperature-0 code corpus: agentic QA at temperature 0.7 is an order
   flakier per item, which is why the audit lives at its edges here.

Per-question-type strata (floor 30): for the headline pair, bridge (170
items) rules SURVIVES while comparison (30 items) rules FALLS-INTO-NOISE.
Mean per-item instability u runs 0.071 (Qwen) to 0.160 (phi-4).

The numbers above come from `report/report.json` (schema report/v2, spec
1.0.0), regenerable byte-for-byte from the committed tables with the
envelope's options; `analysis.py` prints the misranking and split
statistics from the same table.

## What is committed vs local

Raw trajectories, the dataset copy and run state live under
`scratch/wad_replication/` (gitignored). Committed: this protocol, the
collector, grader and analysis (`collect.py`, `ingest.py`, `analysis.py`,
self-tested), the three verdict tables under `tables/`, and the ruling
document under `report/`.
