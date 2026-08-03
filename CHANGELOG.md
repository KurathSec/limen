# Changelog

All notable changes to this project. Every stanza states both versions:
the **package** version and the **rulings spec** version (a spec MAJOR means a
recorded meaning changed).

## [0.2.1] - 2026-08-03

Package 0.2.1 · rulings spec 1.0.0 (unchanged) · schema report/v2. No code
changes; the installed package behaves identically to 0.2.0.

- **When-Agents-Disagree study** (`validation/when_agents_disagree/`): the
  pre-registered reproduction protocol for arXiv 2602.11619 (blocked on its
  data release) and the executed fallback limb, a first-party conceptual
  replication: 8,000 ReAct episodes on HotpotQA distractor (four open
  models picked by a pre-registered pilot closeness rule, 200 items, k=10),
  with the collector, grader, analysis script, three labeled verdict
  tables, and the byte-reproducible report/v2 ruling document committed.
  The scored expectations report one miss and one split as measured, and
  the phi-4 refusals are graded by the report's own selection null.
- Validation prose corrected against the committed artifacts: corpus-wide
  variance figures (residual 0.9-25.2% across all twelve calibration
  scopes, one draw interval excluding zero), two pair-count labels in the
  On-Randomness summary, the KT3 rollup variable name, the KT1 margin
  attribution, and the replication cost total.
- README carries the Zenodo DOI and documentation badges.

## [0.2.0] - 2026-07-30

Package 0.2.0 · rulings spec 1.0.0 · schema report/v2.

- **Gap-survival audit** (the repaudit sections, LMN-AUD-001..008): per-item
  instability u = min(s, k-s)/k against the item's own majority verdict,
  never compounded with correctness; the stable-for-both partition at the
  versioned threshold u0; the pairwise gap recomputed three ways with
  two-stage paired bootstrap intervals; an enumerated replicate noise band;
  SURVIVES / SIGN-INVERTS / FALLS-INTO-NOISE rulings with a capped
  deterministic decisive-item witness; the mandated differentiation against
  retry-free coverage (arXiv 2606.00920); both selection mitigations in
  every block; per-stratum rulings over item labels with a floor, plus the
  saturation rollup. Gate flags `--require-gap-survives` and
  `--max-unstable-gap-share`.
- **Variance components** (LMN-VAR-001..006): the exact EMS two-facet
  items x draws decomposition with truncation-aware raw values, seeded
  item-bootstrap intervals, design effect and Kalibera-Jones planning
  numbers — shipped strictly subordinated: the gate never reads the section
  (deletion-invariance tested), the CLI summary never prints it, and the
  wide-interval warning fires below 20 draw levels.
- **Per-item labels** (LMN-CORE-008): `label_<name>` CSV columns, item-
  consistent and all-or-nothing; the Spaghetti adapter emits language,
  variant, profile, scale and tier; unlabeled tables keep their digests.
- **Additive schema evolution** (LMN-EMIT-008): `limen.evolution` classifies
  golden diffs (identical / stamp-only / additive / changed); additive
  refreshes need only a spec MINOR, changed values still demand MAJOR plus
  the explicit flag.
- Schema report/v1 -> report/v2 (LMN-EMIT-007 supersedes 006); the gate
  accepts both (LMN-GTE-004), and every v1 field value is byte-identical in
  v2 (regression-pinned against frozen v1 fixtures). Two new scope codes:
  STABILITY_THRESHOLD_IS_CRUDE, NO_SATURATION_MECHANISM_CLAIM.
- Calibration tables carry labels (verdict-identical migration, checked);
  goldens regenerated under spec 1.0.0 with per-language strata.

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
