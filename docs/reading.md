# Reading a ruling

The document tells you whether a comparison survives its own repeats. This
page is about what each answer licenses you to write, and what to run next
when the answer is unwelcome.

## SIGN-STABLE

You may write: "the ordering of A and B was stable across all k of our
identical runs, and the pooled gap of X clears the measured minimum detectable
difference of Y."

Check two numbers before celebrating.

First, `flip_prob_upper95`. Zero flips in eight draws only bounds the per-draw
flip probability below 0.312. If your gap is small and the ruling matters, the
honest sentence includes that bound. More draws shrink it: it is 0.145 at
k=20, 0.058 at k=50.

Second, the ratio of `delta_pool` to `mdd.value`. The gate's default threshold
of 1.0 is the floor for meaning anything. A ratio near 1 means your claim and
your noise are the same size, and one more run could put you on the other side
of it. The calibration corpus runs at ratios of 8 to 200; a ratio like that is
what "comfortably clear" looks like.

## SIGN-UNSTABLE

You may write: "our own repeats do not support a direction for this pair."
You may never write that the other model is ahead. The flip is a verdict on
the measurement. Every gate failure reprints this and the document carries it
as `NO_MODEL_QUALITY_CLAIM`.

What to do next depends on why it flipped.

- `pooled_tie` is true: the pooled counts are exactly equal. There is no
  direction to defend. Report the tie.
- Flips with a small `delta_pool` to `mdd.value` ratio: the gap is inside the
  noise floor. Either the models are close on this task or your k is too
  small to resolve them. Raising k narrows the MDD by roughly the square root
  of the increase; the [sensitivity table](spec/sensitivity.md) shows what
  each (k, flakiness) level can resolve.
- Flips with a large ratio: something is off beyond sampling noise. Check the
  drift guard and the grader-defect count before trusting either direction.

## Choosing k, and more draws versus more items

The MDD at the observed k is `t * sqrt((sd_a^2 + sd_b^2) / k)`. More draws
divide the draw noise; more items shrink the per-draw sds themselves (roughly
with the square root of n) and also improve `score_resolution`, the smallest
movement one flipped verdict can cause. If your MDD is dominated by a handful
of flaky items, more items dilute them; if scores swing between whole runs,
more draws average them. The spread statistics in each MT ruling's
`noise_floor` tell you which regime you are in. At k=2 or 3 the document flags
`low_k`: the t quantile at one or two degrees of freedom is so large that
almost nothing clears it, and that is the correct answer at that k.

## Drift states

`PASS` means the checks that could run found nothing, on the ordering
information you supplied. It is a statement about those checks and that
window.

`UNAVAILABLE` means limen could not evaluate drift, most often because
`collected_at` or `model_version` were absent from the input. The gate treats
a required UNAVAILABLE as exit 2. If your draws carry no timestamps but you
know their order, `--assume-index-is-collection-order` runs the order-based
checks in proxy mode; a found effect still fails, and a clean result stays
UNAVAILABLE because the timestamps are still missing.

`FAIL` on version constancy poisons attribution: the pair rulings involved are
stamped `confounded_by_version_change`, and the effect-vs-noise check refuses
them. Movement between draws that straddle a version change belongs to the
version change until shown otherwise.

## The stable-items-only view

Read the mitigations before the ranking. The naive stable-only numbers answer
"what would the leaderboard look like without the flaky items", and the same
draws that selected those items also rank the models, so the naive view is
biased toward looking tidy.

- `split_half.sign_survival`: survival counted where selection and ranking
  used disjoint draws. High survival across all splits (the calibration corpus
  shows 70/70) is the trustworthy version of "the ordering does not depend on
  the flaky items".
- `selection_null`: if the observed t_gap sits inside the null band, the
  tidiness of the stable-only view is what selection alone produces, and it
  supports no further claim. Only values outside the band suggest the mixed
  items carry model-differential signal.

Either way the stable-only ranking remains one view of the data. Excluded
items are enriched for hard and near-threshold cases; dropping them answers a
different question, and `UNSTABLE_ITEMS_NOT_DEFECTIVE` applies to the items
themselves.

## The gap-survival ruling

SURVIVES says the pair's ordering does not depend on the items the systems
cannot reproduce against themselves: the stable-for-both gap keeps the
all-items sign and clears the replicate noise band, with the survival margin
(how many stable items it would take to change that) printed. SIGN-INVERTS
says the published direction is carried entirely by irreproducible items; the
witness lists the unstable items whose re-inclusion would restore it. It
never means the other model wins. FALLS-INTO-NOISE says the stable gap is
smaller than the band the system shows against itself. Check the selection
null before reading any erosion as structure: naive exclusion shrinks gaps
even under a null, and the `ruling_frequencies` show how often selection
alone produces each ruling on an archive with these rates. The
`rfc_differentiation` block says whether the same conclusion follows from
retry-free coverage; the two criteria differ exactly on stable-but-always-
wrong items.

## Variance components, read as planning numbers

The decomposition answers one practical question: where would another unit of
compute help? A large item share means more items; a large draw or residual
share means more draws (the draw-facet contribution scales exactly as 1/k, so
`k_to_halve_draw_contribution` is always 2k). Read the components only beside
their intervals, remember the low-k warning (below 20 draw levels the draw
and residual components are wide by construction), and never quote them as
headline findings: the gate does not read this section, and "draw" remains a
bucket that attributes nothing inside itself.

## Grader defects

A nonzero `defect_pairs` count means some of your measured flakiness is the
grader's: identical bytes received different verdicts. Fix the grader before
interpreting flakiness, and quote `mean_flakiness_excluding_detected_defects`
beside the raw number. Zero defects with `state: AVAILABLE` is a real
measurement of the grader's determinism on identical inputs. It says nothing
about grader correctness, and `UNAVAILABLE` (no raw hashes in the input) says
nothing at all.

## Gate exit codes in CI

Exit 0 means every requested check passed on every selected pair. Exit 1
means a check measurably failed. Exit 2 means a check could not be evaluated:
a required section was UNAVAILABLE, a `--pair` or `--task` filter matched
nothing, or the report is malformed. Both nonzero codes are red. Treat exit 2
as "fix the measurement or the invocation", never as a soft pass, and be
suspicious of any pipeline that special-cases it back to green.
