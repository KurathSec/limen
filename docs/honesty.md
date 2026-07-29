# Honesty

What this instrument does not show. Pre-committed here so none of it can be
quietly claimed later. The first nine ship as machine-readable scope codes in
**every** ruling document limen emits.

1. **It does not show a new finding.** The effect limen measures (single-draw
   leaderboards misranking, verdicts flipping between identical runs) has been
   published several times over. The contribution is a package, not a
   phenomenon, and the docs cite the prior names (TARa@N, swap rate, decision
   consistency, attribute agreement analysis, IDR) rather than renaming them.
2. **It does not show which model is better** (`NO_MODEL_QUALITY_CLAIM`). A
   sign flip is a verdict on the measurement. The correct conclusion is "this
   comparison is not supported by its own data", never "the other one wins".
3. **It does not decompose the named nuisance factors**
   (`NO_FACTOR_ATTRIBUTION`). "Draw" is a bucket containing everything that
   varies between two identical calls: seed, hardware, batch neighbours,
   serving stack. limen measures the bucket's size. It cannot attribute the
   contents.
4. **It does not show provider drift is absent**
   (`NO_DRIFT_ABSENCE_CLAIM`). The drift guard reports UNAVAILABLE when
   `collected_at` or `model_version` are missing, and UNAVAILABLE is not PASS.
   In position-proxy mode a clean result still reports UNAVAILABLE.
5. **It does not show the stable-items-only ranking is the true ranking**
   (`STABLE_SUBSET_IS_A_VIEW`). Excluding unstable items conditions on a
   selected subset enriched for easy items. The stable-only ordering is one
   view, not a correction. It is never emitted without its selection-bias
   mitigations (disjoint draw splits and a selection null).
6. **It does not show that unstable items are bad items**
   (`UNSTABLE_ITEMS_NOT_DEFECTIVE`). Instability is a joint property of item,
   model, serving stack, grader and protocol.
7. **It does not certify that k=1 is sufficient** (`NO_K1_CERTIFICATE`). limen
   reports a measured spread and a minimum detectable difference at the k you
   ran. It issues no certificate, for any k, on any benchmark or provider.
8. **It does not generalise beyond deterministic exact-match grading**
   (`EXACT_MATCH_GRADING_ONLY`). Nothing here says anything about
   judge-scored, rubric-scored or preference-scored tasks. Pointing limen at a
   judge-scored task is out of scope by design.
9. **Constancy is not correctness** (`CONSTANCY_IS_NOT_CORRECTNESS`). A
   constant-but-wrong verdict is invisible to every number here. The
   grader-defect count catches grader *nondeterminism*, not grader
   *wrongness*. (`NO_PRIVILEGED_DRAW` is the ninth embedded code: no draw is
   the correct one.)
10. **It does not claim to be cheaper than current practice.** No cost
    comparison is made anywhere.
11. **It does not show that public evaluation logs contain the required
    input.** limen needs k >= 2 committed draws; how often those exist in the
    wild is an unmeasured, separate question.
12. **It does not report variance components.** The item/model/draw
    decomposition is deliberately absent from schema `report/v1`
    (LMN-EMIT-006): 8 draw levels give a wide interval, and shipping a wide
    interval as a headline teaches people to trust the wrong thing. Adding it
    is a schema bump for a future release, not a field.

## Boundaries with neighbouring work

**The calibration corpus** is graded from the Spaghetti-Architect four-model
ladder archives. Results over it are statements about the verdict stability of
those committed archives as re-analysed here: instruments over the same
population as that project's own reporting. They are not claims about, or
corrections to, any table published from that ladder elsewhere, and never
statements about which of the four models is better.

**Judge-scored evaluation** is excluded (item 8), both on principle (the
graders validating limen are deterministic code paths) and to stay clear of
neighbouring work on judge faithfulness that owns that question.

**The refactor regrade path executes model-generated code**: Python `exec`
plus compile-and-run subprocesses for four other languages, the same path the
upstream benchmark itself uses. `limen regrade` says so in its help text; run
it only where you would run the benchmark.

**One instrument, two report sections.** The per-item stability rate limen
computes is also the first limb of a gap-survival audit (does a pairwise gap
survive removing irreproducible items). If that limb is ever built, it belongs
in this package as another report section, not in a sibling tool. The seam is
named in `limen.adapters`.
