# Quickstart

## Install

```sh
pip install limen-eval
```

Python >= 3.12, zero runtime dependencies. The distribution is named
`limen-eval`; the import and the CLI are `limen`.

## The 90-second loop

```sh
# 1. a synthetic archive whose right answers are chosen by construction
limen synth --out demo --models 3 --items 500 --draws 8 --flaky-fraction 0.05 --gap 0.02

# 2. logs -> a versioned ruling document (report.json + report.md + provenance.json)
limen report demo/archive.verdicts.csv.gz --out demo-report --rulings-version demo

# 3. gate it: exit 0 pass, 1 measured fail, 2 unevaluable
limen gate demo-report/report.json --require-sign-stable --min-effect-vs-noise 1.0
```

## Reading your own logs

**Generic long CSV** (`.csv` or `.csv.gz`), one row per draw:

```csv
model,task,item_id,draw_id,verdict,score,collected_at,model_version,raw_sha256
gpt-x,gsm8k,q1,0,1,,2026-05-01T10:00:00Z,gpt-x-0521,sha256:ab12...
gpt-x,gsm8k,q1,1,0,,2026-05-01T11:00:00Z,gpt-x-0521,sha256:9f00...
```

`verdict` must be literally `0` or `1`. limen never derives a verdict from a
score (LMN-CORE-001): choosing a threshold is the evaluation's decision, not
the auditor's. The last four columns are optional, but what they unlock is
real. `collected_at` and `model_version` feed the drift guard (absent means
its state is UNAVAILABLE, which is never PASS). `raw_sha256` (a hash of
the raw completion) enables the grader-defect count.

**lm-evaluation-harness** `--log_samples` output:

```sh
lm_eval --model ... --tasks gsm8k --log_samples --output_path runs/  # run this >= 2 times
limen report runs/ --out my-report
```

Each sample line is one draw. Re-runs of the identical configuration stack
into draws per item. One run alone is refused: limen needs k >= 2 draws.

**inspect_ai** `.eval` logs, at the per-epoch layer:

```sh
inspect eval mytask.py --model <model> --epochs 8   # epochs are the draws
limen report logs/ --out my-report
```

Each epoch of each sample is one draw; re-runs stack as further draws. limen
reads the `.eval` zip directly (no inspect_ai dependency) and uses the
per-sample `completed_at` timestamps for the drift guard. Score values must be
binary (`C`/`I` or 0/1); with several scorers, `--metric` names the verdict.

**Spaghetti-Architect checkouts** (repeated-draw archives with committed
graders): `limen regrade --repo <checkout> --task comprehend_dev --out tables/`
builds long-CSV verdict tables through the checkout's own public regrade API,
read-only. The refactor path executes model-generated code, the same path the
benchmark itself uses. Run it only where you would run the benchmark.

Multiple inputs merge: `limen report a.csv.gz b.csv.gz --out r`.

## In CI

```yaml
- uses: KurathSec/limen@main
  with:
    report: limen-report/report.json
    require-sign-stable: "true"
    min-effect-vs-noise: "1.0"
    pairs: "gsm8k:challenger>baseline"   # optional: assert the claimed direction
```

Exit code 1 means a check measurably failed. Exit code 2 means the report
cannot support a requested check (an UNAVAILABLE section is red, not quietly
green). On failure the log reprints the boundary: a failed pair never means
the other model wins.

## Library

```python
import limen

archive = limen.load("runs/")
report = limen.build_report(archive, rulings_version="v1")
result = limen.evaluate_gate(report, limen.GateOptions(require_sign_stable=True))
print(result.exit_code)
```
