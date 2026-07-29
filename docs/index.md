# limen

**The same-configuration noise floor of an evaluation, and whether a published
ranking clears it.**

The quantities limen computes already have names in five older fields, and
this page uses them so you can find this tool from any of them. The
constant-verdict fraction upper-bounds **TARa@N** (Atil et al.,
arXiv:2408.04667; TARa counts parsed-answer agreement, which verdict constancy
can only bound from above). The rank-flip rate is what information-retrieval
evaluation calls the **swap rate**. Psychometrics calls the per-item question
**decision consistency**. Quality engineering has measured it for seventy
years as **attribute agreement analysis**, the pass/fail branch of gage R&R.
Genomics' **IDR** (irreproducible discovery rate) is the
exclude-unstable-items-then-re-rank step. The literature exists, several times
over. What did not exist was something a practitioner can install that turns a
directory of repeated identical runs into those numbers. That instrument is
the whole contribution here.

## What limen answers

You ran the same evaluation k times (same models, same items, same
temperature) and you hold the logs. limen answers three questions with every
denominator shown:

1. **How flaky is the measurement?** Per-item verdict flakiness
   (`f = s(k−s)/C(k,2)`, the fraction of draw pairs that disagree),
   always-pass / always-fail / mixed counts, and the constant-verdict fraction
   (an upper bound on TARa@N, stated as such).
2. **How big must a difference be to mean anything at this k?** The spread of
   the k single-draw scores and a minimum detectable difference after Kalibera
   & Jones (ISMM 2013), with its assumptions printed.
3. **Does your ranking survive your own repeats?** For each model pair, the
   share of single-draw leaderboards whose sign disagrees with the pooled
   sign: a per-pair **SIGN-STABLE** / **SIGN-UNSTABLE** ruling, plus a CI
   gate that fails a claim smaller than its own measured noise.

## What limen never answers

Which model is better. A sign flip is a verdict on the measurement: "this
comparison is not supported by its own data", never "the other model wins".
Every ruling document embeds this and eight further scope limits as
machine-readable codes; see [Honesty](honesty.md).

## Quickstart

```sh
pip install limen-eval
limen synth --out demo --models 3 --items 500 --draws 8 --flaky-fraction 0.05 --gap 0.02
limen report demo/archive.verdicts.csv.gz --out demo-report
limen gate demo-report/report.json --require-sign-stable --min-effect-vs-noise 1.0
```

See [Quickstart](quickstart.md) for reading your own logs (generic long CSV or
lm-evaluation-harness `--log_samples`), [Validation](validation.md) for how the
instrument is checked against planted truth and a frozen real-data calibration
corpus, and [Spec rulings](spec/rulings.md) for the numbered, immutable
measurement definitions.
