# Reproduction study: "On Randomness in Agentic Evals"

limen's strongest credential is recovering a published number on data it did
not collect. This study runs the instrument over the released artifact of
Bjarnason, Silva and Monperrus, *On Randomness in Agentic Evals -
Trajectories* (Zenodo, doi
[10.5281/zenodo.18684663](https://doi.org/10.5281/zenodo.18684663),
CC-BY-4.0), and compares limen's noise-floor block against the statistics the
paper published.

## The data

Six configurations on the nano-agent scaffold over SWE-Bench-Verified
(500 instances), ten identical runs each: three models (DeepSWE-Preview,
Devstral-2512, Qwen3-32B), each at its default sampling settings and at
temperature 0. Per run, the artifact carries the SWE-bench harness report
(`resolved_ids`) and every submitted `model_patch`. `ingest.py` maps this
into limen's long verdict table: one cell per (configuration, instance),
k = 10 draws, verdict = resolved, `raw_sha256` = hash of the submitted patch.
A spot check pins the ingest to the source: DeepSWE-Preview run_8 resolves
159/500 in both the report JSON and the table.

Note one deliberate labelling choice: limen's "model" column holds the full
configuration name (scaffold, model, temperature variant). Pair rulings
therefore compare configurations. Rulings involving two different underlying
models say nothing about the models themselves (NO_MODEL_QUALITY_CLAIM), and
the same-model pairs compare sampling settings.

## The reproduction

Published (quoted from the occupancy record the study was planned against):
single-run pass@1 varying by **2.2 to 6.0 percentage points** depending on
which run is selected, with standard deviations **above 1.5 pp at
temperature 0**.

limen's per-configuration noise floor (`noise_floor` in the MT rulings,
min/max/range/sd of the 10 single-run scores):

| configuration | min | max | range | sd |
|---|---|---|---|---|
| Qwen3-32B | 15.00% | 17.20% | 2.20 pp | 0.75 pp |
| Qwen3-32B, temp 0 | 14.40% | 18.00% | 3.60 pp | 1.17 pp |
| DeepSWE-Preview | 28.80% | 32.40% | 3.60 pp | 1.02 pp |
| DeepSWE-Preview, temp 0 | 18.20% | 21.40% | 3.20 pp | 0.96 pp |
| Devstral-2512 | 61.80% | 65.00% | 3.20 pp | 1.13 pp |
| Devstral-2512, temp 0 | 60.60% | 66.60% | 6.00 pp | 1.64 pp |

The per-configuration ranges span 2.20 to 6.00 pp: the published bracket's
endpoints, recovered exactly. The temperature-0 standard deviations reach
1.64 pp, matching the "above 1.5 pp at temperature 0" claim (on the Devstral
configuration; the other temp-0 configurations sit at 0.96 and 1.17 pp).

## What limen adds that the paper did not report

- **Sign-stability rulings.** 8 of the 10 single-run leaderboards misrank at
  least one configuration pair. Both same-model temperature pairs rule
  SIGN-UNSTABLE: Qwen3-32B default vs temp 0 differs by +0.02 pp pooled and
  flips direction in 5 of 10 runs; Devstral default vs temp 0 differs by
  -0.28 pp and flips in 4 of 10. A single-run comparison of either pair is a
  coin toss wearing a leaderboard. The other 13 pairs (12 cross-model plus
  the DeepSWE temperature pair) rule SIGN-STABLE,
  clearing their minimum detectable difference 3.7x to 49x.
- **Verdict flakiness.** 1,113 of 3,000 cells (37.1%) are mixed across the
  10 identical runs; per configuration between 144/500 and 258/500. At
  temperature 0 the mixed counts are 144-190 per 500: greedy decoding does
  not buy determinism here. For comparison, limen's own calibration corpus
  (single-turn code comprehension, temperature 0, deterministic exact-match
  grading) shows 1.65%.
- **Measured harness nondeterminism.** The grader-defect check counts
  discordant run-pairs whose submitted patch bytes are identical: for
  DeepSWE-Preview default, 896 of 4,383 discordant pairs (20.4%). The model
  submitted the same patch; the evaluation resolved it differently. The
  other configurations show 0 to 21 such pairs. This number separates
  evaluation-side flakiness from model-side flakiness, per configuration,
  and is exactly the limb the check exists for.
- **The stable-items-only trap, avoided.** Only 95/500 instances are stable
  across all 60 runs. The selection null puts the observed stable-only
  tidiness at p = 0.96: entirely explained by selection. Reporting the
  stable-only ordering as a cleaned-up leaderboard would be the artifact
  limen's mitigations exist to catch.
- **Drift**: UNAVAILABLE. The artifact carries no per-run timestamps or
  serving-version records, so limen refuses to certify drift absence rather
  than assuming it.

## Reproducing this study

```sh
# ~7.7 GB download from Zenodo, then:
tar xzf randomness-agentic-evals.tar.gz -C extracted \
    --wildcards '*/run_*/*.json' '*/run_*/preds.jsonl'
python validation/on_randomness/ingest.py --archive-dir extracted \
    --out validation/on_randomness/tables
limen report validation/on_randomness/tables/on_randomness.verdicts.csv.gz \
    --out validation/on_randomness/report --rulings-version onr1 --replicates 1000
```

The committed `tables/` and `report/` are the outputs of exactly that
sequence; the report regenerates byte-identically from the table. These are
study artifacts (attribution above), not CI-gated goldens.

## Scope

Everything in `docs/honesty.md` applies. In particular: no statement about
which model or setting is better; verdicts here are SWE-bench harness
resolutions, whose own environment sensitivity is part of what is being
measured; and the drift guard's UNAVAILABLE is not a clean bill of health.
