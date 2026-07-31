# Pre-registered reproduction: When Agents Disagree With Themselves

Target: **"When Agents Disagree With Themselves: Behavioral Consistency as
an Uncertainty Signal for LLM Agents"**, Aman Mehta (Snowflake AI
Research), arXiv [2602.11619](https://arxiv.org/abs/2602.11619) (v2,
2026-07-15, CC-BY-4.0), accepted to the ICML 2026 Workshop on Statistical
Frameworks for Uncertainty in Agentic Systems.

## Status: blocked on data release

As of **2026-07-31** the paper's artifact is not public. The v2 text says
"code and data will be released upon publication"; no repository or archive
record is linked from the paper, and none was found on the author's public
GitHub. A data request to the author has been prepared separately.

This document is a **pre-registration**: everything below was written and
committed before anyone on this project saw a single run of that dataset.
The commit date of this file is the timestamp. Nothing here is a claim
about the data; every expectation is falsifiable and will be reported
as-measured, including the misses.

## The published design and numbers

- HotpotQA, distractor setting: ReAct agent with Search / Retrieve /
  Finish tools, temperature 0.7, four models (Claude Sonnet 4.5, GPT-5,
  Llama 3.1 70B, Gemini 3 Pro), 200 questions x 10 identical runs =
  8,000 runs. Pooled accuracies 81.5 / 79.6 / 73.7 / 72.2 (%).
- SWE-bench: 50 tasks across 5 repositories, 5 runs per model-task pair,
  all four models = 1,000 runs, temperature 0.5.
- Grading: fuzzy string match (answer contains gold or vice versa,
  case-insensitive), with exact match and token F1 >= 0.5 as robustness
  variants.
- Headline statistics: 29.3% [28.4, 30.1] of single-run evaluations
  misrank the models (10,000 bootstrap iterations, sampling one run per
  question per model, ranked against the multi-run ordering); consistent
  tasks (<= 2 unique action sequences per 10 runs) reach 82-87% accuracy
  against 41-65% for inconsistent tasks (>= 4).

## Pre-registered protocol

Fixed now; to be executed unchanged when the data exists.

1. **Ingest.** Per-run per-item correctness into a limen verdict table:
   HotpotQA at k=10, n=200, 4 models; SWE-bench separately at k=5, n=50.
   If final answer strings ship rather than correctness, grade with the
   paper's fuzzy rule reimplemented as a deterministic code path, and emit
   exact-match and F1>=0.5 variants as separate tables. HotpotQA native
   `level` and `type` fields (from the public validation set, keyed by
   question id) become `label_` columns.
2. **Rule.** `limen report` (schema report/v2, rulings spec 1.0.0,
   bootstrap 1000, stratified by the available labels) and `limen gate`.
3. **Compare.** Two statistics against the paper:
   - limen's native misranking-draws statistic (intact single draws), and
   - the paper's exact bootstrap statistic (one run sampled per question
     per model, 10,000 iterations), reimplemented in this directory's
     `analysis.py` at reproduction time, expected to land in
     29.3% [28.4, 30.1];
   - pooled per-model accuracies against 81.5 / 79.6 / 73.7 / 72.2.
4. **Expectations** (each falsifiable, all reported as-measured):
   - The two closest pairs (Claude vs GPT-5, ~1.9pp; Llama vs Gemini,
     ~1.5pp) rule SIGN-UNSTABLE and/or gap-survival FALLS-INTO-NOISE.
   - The well-separated top-vs-bottom pairs rule SURVIVES with a decisive
     item margin printed.
   - The stable-partition accuracy ordering agrees in direction with the
     paper's consistent > inconsistent split.
   - The draw main-effect variance component is indistinguishable from
     zero (instability is item-local), with the k=10 low-draw-levels
     interval warning acknowledged in advance.

## Boundary

The paper's consistency is defined on **action sequences**; limen's u_i is
defined on **verdicts**. The partitions are related but not identical, and
the comparison between them is a differentiation (like the retry-free
coverage block in every gap-survival ruling), never an identity claim.
Until the data is released, this directory makes no claim of any kind
about that dataset.
