# Changelog

All notable changes to this project. Every stanza states both versions:
the **package** version and the **rulings spec** version (a spec MAJOR means a
recorded meaning changed).

## [0.1.1] - 2026-07-30

Package 0.1.1 · rulings spec 0.2.0.

- inspect_ai `.eval` reader at the per-epoch layer: each epoch of each sample
  is one draw, re-runs stack as further draws, per-sample `completed_at`
  timestamps feed the drift guard. The zip is parsed with the stdlib; logs
  whose entries use Zstandard compression (written by inspect on Python
  3.14+) are read on Python >= 3.14 and refused with the fix named on older
  interpreters. Fixtures were produced by a real inspect_ai run.
- Rulings spec 0.1.0 -> 0.2.0: LMN-CORE-006 superseded by LMN-CORE-007
  (HELM and Parquet remain the stated reader absences).
- `tools/update_calibration.py` distinguishes stamp-only golden changes
  (spec_version and the envelope hash over it) from recorded-value changes:
  stamps refresh on any spec bump, values still demand a MAJOR bump and an
  explicit flag.
- Validation layer three: the instrument recovers the published single-run
  pass@1 spread of "On Randomness in Agentic Evals" (Bjarnason, Silva,
  Monperrus; Zenodo 10.5281/zenodo.18684663) exactly on data it did not
  collect, and additionally rules both same-model temperature pairs
  SIGN-UNSTABLE and measures harness nondeterminism via byte-identical
  patches (`validation/on_randomness/`).
- The gate-sensitivity sweep runs in its own workflow (tags, weekly,
  dispatch) instead of on every push.
- CITATION.cff carries the author's full record and the references the
  instrument stands on.

## [0.1.0] - 2026-07-29

Package 0.1.0 · rulings spec 0.1.0.

First release. An analyzer over repeated identical evaluation runs:

- Long verdict table IR with two readers (generic long CSV,
  lm-evaluation-harness `--log_samples`) and a read-only Spaghetti-Architect
  regrade adapter (`limen regrade`).
- Per-item flakiness `f = s(k-s)/C(k,2)` with always-pass / always-fail /
  mixed counts and the constant-verdict fraction with its explicit upper-bound
  relation to TARa@N.
- Single-draw leaderboards with per-pair SIGN-STABLE / SIGN-UNSTABLE rulings,
  integer-exact tie handling, and the zero-flip upper bound
  `1 - 0.05**(1/k)`.
- Noise floor (spread of the k single-draw scores) and minimum detectable
  difference after Kalibera & Jones, conservative df, assumptions printed.
- Stable-items-only re-ranking shipped only together with its selection-bias
  mitigations: all-complementary-splits analysis and a conditional parametric
  selection null.
- Drift guard (version constancy, leave-one-draw-out, Spearman trend) with
  strict tri-state semantics — UNAVAILABLE is never PASS — and a weaker,
  explicitly-labelled draw-position proxy mode.
- Grader-defect count: verdict flips on byte-identical raw output.
- Deterministic ruling documents (canonical bytes, content hashes, immutable
  ids, embedded scope codes) with provenance in a sidecar.
- `limen gate` with exit codes 0 (pass) / 1 (measured fail) / 2 (unevaluable),
  plus a composite GitHub Action.
- Planted-truth generator (`limen synth`), known-answer test suite, published
  gate-sensitivity table.
- Frozen calibration corpus: per-draw verdict tables from the
  Spaghetti-Architect archives (comprehend dev/test, refactor dev; 4 models,
  k=8, temperature 0) with byte-compared golden rulings. The comprehend dev
  regrade reproduces the upstream mixed-outcome count exactly (99/6000
  pooled; 31/23/20/25 per model).
- Numbered, immutable spec rulings (`limen spec list`) with coverage,
  calibration-drift and layering gates in CI.
