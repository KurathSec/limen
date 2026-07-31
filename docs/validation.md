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

### Kill tests for the 0.2.0 audit sections

Release 0.2.0 added the gap-survival audit and the variance-component
section. Before shipping, three pre-specified kill tests ran against this
corpus; the numbers below come from the committed goldens
(`calibration/spaghetti/rulings/cal1/`, rulings spec 1.0.0), which CI
regenerates byte-for-byte.

**KT1 — the partition must not degenerate, and the ladder must survive it.**
On a well-separated temperature-0 ladder the stable-for-both partition could
have collapsed to "everything" (making the audit vacuous) or the exclusions
could have erased the gaps (making it destructive). Neither happened. The
partition keeps 1,299–1,457 of 1,500 items per pair (1,742–1,790 of 1,846 on
comprehend-test), and all 18 pair orderings rule SURVIVES. The decisive-item
margin (how many stable items, removed adversarially largest-first, it takes
to change the ruling) runs from 18 (Llama-3.3-70B vs Mistral-Small on
comprehend-test, the smallest-gap pair) to 468; the share of each pooled gap
riding on unstable items runs 4.8% to 43.4%. The selection null manufactured
zero SIGN-INVERTS rulings in 1,000 replicates on every one of the 18 pairs.
The per-system retry-free-coverage comparison (arXiv 2606.00920) agrees with
every u_i ruling here while the two criteria disagree item-wise on 51–897
stable-but-always-wrong items per pair (Jaccard overlap of the exclusion
sets 0.06–0.69): on this corpus the differentiation block shows the two
lenses reach the same verdicts for different reasons, which is exactly what
it exists to make visible.

**KT2 — rulings must hold up under strata and leave-one-language-out.**
With per-language stratification (floor 30), 89 of the 90 language-stratum
rulings are issued; on comprehend-dev all 30 rule SURVIVES, and the noise
concentrates where the gaps are thinnest: refactor-dev javascript rules
FALLS-INTO-NOISE for 3 of 6 pairs and python for 2 (plus one stratum-level
UNAVAILABLE on a pooled tie). Leave-one-language-out re-rulings hold on 89
of 90 (table, pair, held-out language) subsets. The one flip is informative,
and it is printed here rather than smoothed over: DeepSeek-V4-Flash vs
Llama-3.3-70B on refactor-dev — the pair with the largest unstable gap share
(43.4%) — falls into noise when java is held out, because its java stratum
(SURVIVES 6/6 across pairs) carries the gap. Leave-one-profile-out was not
run: with 3 profiles the subsets are two-thirds removals, which this corpus
cannot support as a stability probe.

**KT3 — the saturation rollup must report association without inventing
mechanism.** Across label keys and tables the Spearman association between
stratum saturation and unstable-gap share has no consistent sign: for the
first pair alone, language gives rho 0.3 / 0.4 / −0.7 across the three
tables, scale gives −0.60 / −0.37 / −0.95, variant gives 0.31 / −0.26 /
−0.35, and profile's ±1.0 rests on 3 strata. The rollup prints `n_strata`
beside every rho, and the scope block carries
`NO_SATURATION_MECHANISM_CLAIM`; this corpus is a demonstration of why that
code exists.

**Variance components, pre-specified outcomes.** Before computing, two
readings were fixed: a draw main-effect component indistinguishable from
zero means the instability is item-local with no draw-wide effect; a nonzero
one means some draw index systematically differs (an infrastructure or
ordering effect the drift guard should then be pointed at). The corpus
lands on the first: raw draw components of 3.0e-06, −2.0e-06 and 0.0
(bootstrap 95% intervals all containing zero, upper ends at or below
1.4e-05), with the item facet at 91–97% of the variance and the remaining
3–9% in the item-by-draw residual, which is where the 1.65–4.85% mixed cells
live. All intervals carry the low-draw-levels warning (k=8 is below the
20-level floor), as designed.

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

The report was regenerated under 0.2.0 (schema report/v2, spec 1.0.0), and
the new sections split the picture three ways. The three same-model
temperature pairs rule FALLS-INTO-NOISE with 100% of each gap riding on
unstable items, agreeing with their SIGN-UNSTABLE or near-zero-effect
rulings from the 0.1.x layer. The nine pairs involving devstral rule
SURVIVES, with removal margins of 24 to 82 items. The instructive case is
the third group: Qwen3-32B vs DeepSWE-Preview clears its MDD 16-fold
(a 15.0 pp pooled gap), yet rules FALLS-INTO-NOISE, because 98.7% of that
gap rides on unstable items — DeepSWE's advantage is real against draw
noise of the mean but rests almost entirely on items it solves only some
of the time. The two limbs answer different questions and here they
diverge; the audit does not overturn the MDD statement, and the stable-only
view remains a view, not a correction (the threshold is crude by design,
LMN-AUD-002). A reader who wants a gap that persists under
consistently-decided items must ask for it explicitly, and the gate flag
`--require-gap-survives` is that question. The variance components run against the
pre-specified readings splits by configuration: five of six put the draw
main effect at zero (intervals containing zero, item facet 55–72%, the rest
in the item-by-run residual), but devstral-2512 at temperature 0 shows a
small nonzero draw component (raw 1.33e-04, interval [2.6e-05, 6.17e-04],
0.06% of variance) — the nonzero limb of the pre-specification, small enough
to matter to nobody's leaderboard and exactly the kind of run-indexed effect
the drift guard exists to be pointed at. All intervals carry the
low-draw-levels warning at k=10.

Full method, tables and scope caveats:
[validation/on_randomness/README.md](https://github.com/KurathSec/limen/blob/main/validation/on_randomness/README.md).

A second close-models reproduction is pre-registered and blocked: the
target ("When Agents Disagree With Themselves", arXiv 2602.11619; 29.3% of
single-run evaluations misranking four models on HotpotQA) has not released
its data as of 2026-07-31. The full protocol - ingest, rulings, the exact
statistics to compare, and the falsifiable expectations - was committed
before seeing any of that data, at
[validation/when_agents_disagree/README.md](https://github.com/KurathSec/limen/blob/main/validation/when_agents_disagree/README.md).
No numbers are claimed until the data exists.
