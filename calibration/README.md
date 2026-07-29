# Calibration corpus

Frozen real repeated-draw verdict tables and their immutable golden rulings:
layer two of the instrument's oracle. CI regenerates every ruling from the
committed tables and fails on any byte difference
(`tests/test_calibration_drift.py`, `tools/update_calibration.py --check`).
No external checkout is needed in CI.

`spaghetti/` holds per-draw verdict tables graded from the Spaghetti-Architect
committed archives (4 models x k=8, temperature 0, deterministic exact-match
graders) via the read-only adapter:

- `comprehend_dev`: the four-model ladder (bench/out/ladder), 1500 items/model
- `comprehend_test`: the g3 test split (1860 items/model, split injected)
- `refactor_dev`: the g3 refactor dev split (semantic_ok verdicts)

`refactor_test` is deliberately absent: the upstream repository declares its
regrade non-reproducible, and limen refuses to grade against the wrong oracle.

These tables are statements about verdict stability of those archives as
re-analysed here. They are not claims about any table published from that
ladder elsewhere, and never about which model is better (see NOTICE).

To refresh locally: `python calibration/spaghetti/build_tables.py --repo
<checkout>` then `python tools/update_calibration.py --write`. Changed golden
bytes additionally need `--confirm-spec-bump` and a rulings-spec MAJOR bump.
History is superseded, never edited.
