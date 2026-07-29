# Architecture

When this file and the code disagree, the code is right; when a number and its
spec ruling disagree, the ruling is right (`src/limen/spec/rulings/*.toml`,
rendered at `docs/spec/rulings.md`).

## 1. One IR, one direction of flow

Everything flows through the **long verdict table**: one row per
`(model, task, item_id, draw_id)` with a binary verdict, compiled into cells
(all draws of one item for one model, canonical draw order). Readers produce
it, analyzers consume it, the report serializes rulings from it, and the gate
consumes only the report:

```
readers/ (long-csv, lm-eval)      adapters/spaghetti (regrade -> long-csv)
        \                          /
         model.py  (VerdictRow -> Cell -> Archive)
            |
   flakiness.py  ranking.py  noise.py  drift.py  graderdefect.py
            \        |         |        |        /
                 report.py  (canonical body; provenance sidecar)
                     |
                  gate.py  (exit 0 / 1 / 2)
```

`synth.py` sits beside the readers: it manufactures archives whose right
answers are chosen, so every analyzer has a known-answer harness
(tests/test_known_answer.py) and the gate has a measured sensitivity table
(tools/render_sensitivity.py).

## 2. The three mechanical gates

- **Calibration drift** (tests/test_calibration_drift.py,
  tools/update_calibration.py): committed real-data verdict tables regenerate
  their committed golden rulings byte-for-byte. Changing a golden requires a
  rulings-spec MAJOR bump and an explicit flag; deletion is refused. CI needs
  no foreign checkout.
- **Spec coverage** (tests/test_spec.py): every active numbered ruling is
  cited from code, tests or docs, and every cited id resolves.
- **Layering** (tests/test_layering.py + ruff TID253): only
  `adapters/spaghetti.py` may import the foreign checkout's modules, only
  inside functions; `import limen` touches no foreign module; the adapter
  contains no write calls.

## 3. Byte-stability contract

`canonical.py` is the single serialization authority: sorted keys, 2-space
indent, ASCII, trailing LF; floats round-half-even to 6 places with `-0.0`
normalized; gzip members carry mtime 0 and no filename; every seed derives
from `sha256(rulings_version | scope | procedure | index)`. Ruling bodies
carry no timestamp, package version, or path — provenance is a sidecar the
byte comparison never sees.

## 4. Statistical spine

- Flakiness `f = s(k-s)/C(k,2)` — the pairwise-disagreement U-statistic,
  unbiased for `2q(1-q)` at any k.
- Every leaderboard sign is computed on integer pass-count differences.
- The MDD follows Kalibera & Jones (ISMM 2013), one repetition level,
  conservative df, hardcoded t-table (no scipy).
- The stable-items-only view is only ever emitted with both selection-bias
  mitigations: all-complementary-splits classify/rank analysis, and a
  conditional parametric selection null (per-cell Bernoulli resampling —
  within-cell permutation is provably vacuous here, which is a numbered
  ruling, LMN-RNK-006).
- Tri-state discipline: drift and grader-defect sections are
  PASS / FAIL / UNAVAILABLE, and UNAVAILABLE is never PASS, including in the
  gate's exit codes (0 / 1 / 2).

## 5. Two versions

The package version (`src/limen/_version.py`) and the rulings-spec version
(`src/limen/spec/rulings/index.toml`) move independently; every CHANGELOG
stanza states both. A spec MAJOR means a recorded meaning changed.
