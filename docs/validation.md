# Validation

The instrument is validated in two layers, per its design: planted truth
(synthetic archives whose right answers are chosen) and a frozen calibration
corpus of real repeated-draw logs whose rulings are byte-compared in CI.

## Layer one: planted truth

Every estimator has known-answer tests against the generator
(`tests/test_known_answer.py`): the flakiness U-statistic recovers the planted
`2q(1-q)` rate, the single-draw flip rate matches the normal approximation at
the planted gap, planted grader defects are counted exactly, and the drift
guard fires on planted version changes, single-draw corruption, and monotone
drift. The selection null is itself calibrated: on null-structured archives its
p-values do not systematically reject, and planted draw-coherent structure
(which i.i.d. per-cell resampling cannot produce) lands outside the null band.
A test also pins the trap the design warns about: within-cell permutation
changes nothing (every statistic is a function of per-cell pass counts), which
is exactly why the null resamples verdicts (LMN-RNK-006).

The gate's operating point is measured directly: see
[Gate sensitivity](spec/sensitivity.md) for the full sweep. Headline: at
n=1500, k=8, ~2% flaky items, the gate resolves a 0.5 pp true gap at >= 80%
pass rate with a measured false-pass rate <= 2% at true gap zero. At k=2 it is
conservative, needing ~5 pp.

## Layer two: the calibration corpus

Per-draw verdict tables graded read-only from the Spaghetti-Architect
committed archives (4 models, k=8 draws, temperature 0, deterministic
exact-match graders, one OpenAI-compatible endpoint), frozen under
`calibration/spaghetti/` with golden rulings that CI regenerates byte-for-byte
from the committed tables.

**Cross-check against independent prior analysis.** The comprehend-dev regrade
reproduces the number the research programme computed with its own independent
script exactly: 99/6000 cells mixed (1.65%), per-model 31/23/20/25. The
refactor-dev regrade (a limb no prior script had regenerated) lands at
291/6000 (4.85%), independently consistent with the upstream repository's own
4.9% docstring assertion.

### What the instrument rules on this corpus

| split | aligned items | mixed cells | misranking draws | pair rulings |
|---|---|---|---|---|
| comprehend_dev | 1500 | 99/6000 (1.65%) | 0/8 | 6/6 SIGN-STABLE |
| comprehend_test | 1846 | 163/7426 (2.19%) | 0/8 | 6/6 SIGN-STABLE |
| refactor_dev | 1500 | 291/6000 (4.85%) | 0/8 | 6/6 SIGN-STABLE |

Every one of the 18 within-task pair orderings is SIGN-STABLE across all 8
single-draw leaderboards, with zero drawn ties. Not one of the 24 single-draw
leaderboards misranks any pair. The smallest pooled gap anywhere
(Llama-3.3-70B vs Mistral-Small on comprehend_test, +1.52 pp) still clears its
minimum detectable difference eight-fold; the median pair clears it ~50-fold.
Because zero flips at k=8 bounds the per-draw flip probability only below
0.312 (one-sided 95%), every SIGN-STABLE ruling prints that bound beside
itself.

**This is a clean null, and it was predicted.** The four models are a
deliberately spread capability ladder: a model's score cannot move between two
draws by more than its mixed-cell share, so with pooled gaps of 1.5–28.6 pp
against mixed shares of 0.7–7.8%, sign flips were arithmetically nearly
impossible on this substrate. The corpus therefore validates the instrument's
plumbing on real data and demonstrates the ruling a well-separated ladder
*should* get. It does not exhibit the misranking phenomenon, which is already
published elsewhere (single-run evaluations misranking close models ~29% of
the time on other benchmarks). An archive of *close* models is where the
SIGN-UNSTABLE limb earns its keep. The planted-truth layer covers that regime
by construction.

Further readings from the corpus, all with their scope caveats machine-embedded:

- **Stable-items-only view**: the stable-only orderings match the headline
  orderings; per-pair sign survival is 70/70 across every disjoint
  classify/rank split on all three tables, and the selection null shows the
  stable-only gaps *shrink* slightly relative to what selection alone predicts
  (t_gap at the null's far low side). There is no tidiness artifact to
  misread, and the stable-only ranking remains a view, not a correction.
- **Drift guard**: UNAVAILABLE on all twelve (model, task) scopes. The
  archives carry no `collected_at` and no per-draw `model_version`, so limen
  refuses to certify drift absence. The position-proxy sub-checks (the
  `raw_outputs` index is collection order within each item) found no positional
  effect, which by design reports UNAVAILABLE, never PASS.
- **Grader defects**: the check runs (raw hashes are stored) and finds 0
  byte-identical verdict flips in 6,143 discordant draw pairs across the three
  tables, consistent with the graders being deterministic code paths.
- 14 upstream stub records (failed fetches, no stored completions) were
  skipped and counted, never silently graded; see
  `calibration/spaghetti/MANIFEST.json`.

### Boundary

These results are statements about the verdict stability of those committed
archives as re-analysed here: instruments over the same population as the
upstream project's own reporting. They are not claims about any table
published from that ladder elsewhere, and never statements about which of the
four models is better ([Honesty](honesty.md)).

## Layer three: reproducing a published number on third-party data

The strongest thing a measurement instrument can prove about itself is that
it recovers a published statistic on data it did not collect. limen was run
over the released artifact of Bjarnason, Silva and Monperrus, *On Randomness
in Agentic Evals* (Zenodo, doi 10.5281/zenodo.18684663, CC-BY-4.0): six
configurations on SWE-Bench-Verified, 500 instances, ten identical runs each.

The paper reports single-run pass@1 varying by 2.2 to 6.0 percentage points
depending on which run is selected, with standard deviations above 1.5 pp at
temperature 0. limen's per-configuration noise floors span ranges of exactly
2.20 to 6.00 pp, with sd reaching 1.64 pp at temperature 0. On the same data
the instrument adds what the paper did not report: 8 of 10 single-run
leaderboards misrank at least one pair; both same-model temperature pairs
rule SIGN-UNSTABLE while all 13 cross-model pairs clear their MDD 3.7x to
49x; 37.1% of cells are mixed across identical runs (against 1.65% on the
calibration corpus); and for one configuration, 20.4% of discordant run-pairs
had byte-identical submitted patches, which is measured harness
nondeterminism, separated from model nondeterminism by the grader-defect
check.

Full method, tables and scope caveats:
[validation/on_randomness/README.md](https://github.com/KurathSec/limen/blob/main/validation/on_randomness/README.md).
