# limen

**The same-configuration noise floor of an evaluation, and whether a
published ranking clears it.**

limen turns a directory of repeated identical evaluation runs into the three
numbers that decide whether a comparison is real: the fraction of items whose
pass/fail verdict is not constant across identical repeats, the noise floor a
claimed improvement has to clear at the k you actually ran, and how often a
leaderboard computed from a single run disagrees in sign with the leaderboard
computed from all of them. These are emitted as per-pair **SIGN-STABLE** /
**SIGN-UNSTABLE** rulings with every denominator shown, plus a CI gate that
fails a benchmark report claiming a gain smaller than that report's own
measured draw noise.

What it does not do, and this is the whole boundary of the instrument: **it
makes no statement about which model is better.** A sign flip means "this
comparison is not supported by its own measurement", never "the other one
wins".

The quantities are not new, and the docs say so up front: the constant-verdict
fraction upper-bounds **TARa@N** (Atil et al.), the rank-flip rate is IR's **swap rate**,
psychometrics calls the per-item question **decision consistency**, quality
engineering has had it for seventy years as **attribute agreement analysis**,
and genomics' **IDR** is the exclude-then-re-rank step. The literature exists.
An installable instrument did not. That is the whole claim.

## Install

```sh
pip install limen
```

Zero runtime dependencies, Python >= 3.12.

## 90 seconds

```sh
# a synthetic archive whose right answers are chosen (the instrument's oracle)
limen synth --out demo --models 3 --items 500 --draws 8 --flaky-fraction 0.05 --gap 0.02

# repeated-run logs -> a versioned ruling document
limen report demo/archive.verdicts.csv.gz --out demo-report

# fail CI when a claim does not clear its own noise
limen gate demo-report/report.json --require-sign-stable --min-effect-vs-noise 1.0
```

`limen report` reads:

- a generic long-format CSV (`model, task, item_id, draw_id, verdict`, plus
  optional `score, collected_at, model_version, raw_sha256`),
- lm-evaluation-harness `--log_samples` output trees (run the harness at least
  twice, or with repeats: limen needs k >= 2 draws per item).

## The ruling document

One deterministic JSON document per archive: per-(model, task) flakiness with
always-pass / always-fail / mixed counts, the spread of the k single-draw
scores with a minimum detectable difference at the observed k (after Kalibera
& Jones), per-pair sign-stability rulings with drawn ties counted separately,
a stable-items-only re-ranking that ships only together with its selection-bias
mitigations, a drift guard whose missing-field state is UNAVAILABLE and never
PASS, and a grader-defect count (verdict flips on byte-identical output are the
grader's flakiness, not the model's). Regeneration from the same input is
byte-identical. Rulings are versioned and immutable.

## GitHub Action

```yaml
- uses: KurathSec/limen@main
  with:
    report: limen-report/report.json
    require-sign-stable: "true"
    min-effect-vs-noise: "1.0"
```

## Status

Alpha. The measurement definitions are frozen behind a versioned rulings spec
(`limen spec list`); changing any recorded meaning is a spec version bump, not
a patch. See `docs/honesty.md` for the full list of things this instrument
deliberately does not claim.

## License

MIT.
