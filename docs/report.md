# The ruling document

`limen report` writes three files. `report.json` is the ruling document itself
and the only file the gate reads. `report.md` is a human summary of the same
numbers. `provenance.json` records who produced the document and from what
(limen version, timestamp, input paths and hashes); it sits outside the byte
comparison so that a faithful regeneration of `report.json` stays identical.

This page documents every field of `report.json`. A test
(`tests/test_docs_format.py`) checks the two directions of honesty: every path
named here exists in a real report, and every field a real report emits is
named here. If the format moves, this page has to move with it.

## Conventions

- **Counted triads.** Every rate appears as an object with `count`,
  `denominator` and `rate`. The rate is derived and rounded; the integers are
  the record. `rate` is `null` when the denominator is zero. Written below as
  `x.{count,denominator,rate}`.
- **Tri-states.** Sections that depend on optional inputs carry a `state` of
  `AVAILABLE` or `UNAVAILABLE` (drift sub-checks use `PASS`, `FAIL`,
  `UNAVAILABLE`). A missing input yields `UNAVAILABLE` with null counts. It is
  never reported as zero and never treated as a pass.
- **Nulls keep their keys.** Absent data changes values to `null`; the key
  set of a section is fixed for a schema version.
- **Determinism.** Serialization is canonical: sorted keys, two-space indent,
  ASCII, LF, floats rounded half-even to six places, seeds derived from the
  rulings version. Regenerating from the same input gives identical bytes.
- **Model-keyed maps.** Two fields key objects by model name, shown below as
  `<model>`.

## Envelope

| field | meaning |
|---|---|
| `limen_schema` | Always `report/v1` for this schema. |
| `rulings_version` | The version string you passed with `--rulings-version`; part of every ruling id. |
| `spec_version` | The rulings-spec version the producing package carried (`limen spec list`). |
| `dataset_digest` | sha256 over every input row, including rows later excluded for low k. Pins the document to its exact input. |
| `options.replicates` | Selection-null replicate count. |
| `options.max_splits` | Cap on enumerated classify/rank splits. |
| `options.assume_index_is_collection_order` | Whether drift ran in position-proxy mode. |
| `options.ragged` | `error` or `truncate`; how ragged k was handled. |
| `options.bootstrap` | Audit bootstrap replicates per gap estimand. |
| `options.stratify_by` | Label keys per-stratum audit rulings were issued for (sorted; empty when none). |
| `options.stratum_replicates` | Bootstrap and null replicates inside each stratum. |
| `options.stratum_floor` | Minimum aligned items for a stratum to receive a ruling. |
| `n.models[]`, `n.tasks[]` | Sorted model and task names. |
| `n.cells` | Number of (model, task, item) cells that survived the min-k filter. |
| `n.excluded_low_k[].{model,task,count}` | Cells excluded for having fewer than min-k draws, counted per scope. Empty list when nothing was excluded. |
| `scope.does_not_show[].{code,text}` | The fixed scope codes (NO_MODEL_QUALITY_CLAIM and companions). Every document carries them. |
| `rulings.mt[]`, `rulings.pair[]`, `rulings.task[]` | The ruling bodies, described below. |
| `content_hash` | sha256 of the canonical envelope with this field removed. Each body carries its own. |

## MT rulings: one per (model, task)

Identity: `ruling_id` (`LIMEN-<version>-MT-<nnnn>`, ordinal by sorted scope),
`kind` (`MT`), `scope_key.{task,model}`, `content_hash`.

### `flakiness`

| field | meaning |
|---|---|
| `n_items` | Items this model has for the task (may exceed the aligned count). |
| `k_uniform` | The uniform k across this model's cells, or `null` if ragged. |
| `always_pass.{count,denominator,rate}` | Items passing on every draw. |
| `always_fail.{count,denominator,rate}` | Items failing on every draw. |
| `mixed.{count,denominator,rate}` | Items whose draws disagree. |
| `constant_verdict_fraction` | `(always_pass + always_fail) / n_items` at uniform k, else `null`. |
| `constant_verdict_n` | The k the fraction was computed at, else `null`. |
| `tara_upper_bound_note` | Fixed text: this fraction upper-bounds TARa@N (Atil et al.); parsed-answer agreement can be lower on always-fail items. |
| `mean_flakiness` | Mean of `f = s(k-s)/C(k,2)` over all items, zeros included. |
| `mean_flakiness_mixed_only` | Mean of f over mixed items only; `null` when none are mixed. |
| `pooled_pair_discordance.{count,denominator,rate}` | Discordant draw pairs over all draw pairs. Equals mean flakiness at uniform k and differs under ragged k. |
| `f_max`, `f_p50`, `f_p90`, `f_p99` | The f distribution: maximum and lower-interpolation quantiles. |

### `instability`

The repaudit companion of the flakiness block: `u_i = min(s, k-s)/k`, the
fraction of draws disagreeing with the item's own majority verdict, never
compounded with correctness. `n_unstable` equals the flakiness block's mixed
count by construction.

| field | meaning |
|---|---|
| `mean_u`, `u_p50`, `u_p90`, `u_p99`, `u_max` | The u distribution over this model's items. |
| `n_unstable.{count,denominator,rate}` | Items with u above zero. |
| `n_majority_tie.{count,denominator,rate}` | Even-k items at s = k/2: no majority verdict exists and u = 0.5. |

### `variance_components`

The subordinate two-facet items x draws decomposition (exact EMS method of
moments). The gate never reads this section; the CLI summary never prints it;
`report.md` renders it only after the scope block. `state` is `UNAVAILABLE`
(with `reason`) at ragged k or below two items, and the `bucket_note` and
`never_headline_note` travel with it either way.

| field | meaning |
|---|---|
| `state`, `reason` | Availability; the reason names the refusal. |
| `design` | Fixed text naming the crossed design and its crossing key. |
| `n_items`, `k` | The matrix behind the decomposition. |
| `grand_mean.{count,denominator,rate}` | Total passes over n*k. |
| `mean_squares.{item,draw,residual,df_item,df_draw,df_residual}` | The exact ANOVA mean squares and their degrees of freedom. |
| `components.item.{estimate,raw,truncated,ci95,boot_share_truncated}` | The item component: truncated-at-zero estimate beside the raw moment value, a seeded item-bootstrap percentile interval (`ci95.{lo,hi}`), and the share of bootstrap replicates that truncated. |
| `components.draw.{estimate,raw,truncated,ci95,boot_share_truncated}` | The draw component, same shape. Zero in expectation when draws are exchangeable. |
| `components.residual.{estimate,raw,truncated,ci95,boot_share_truncated}` | The item x draw interaction confounded with error; never negative. |
| `shares.{item,draw,residual}` | Of total variance; `null` when the total is zero. |
| `icc_item`, `icc_draw` | Intraclass correlations. |
| `design_effect.{deff,n_eff,definition}` | Kish design effect and effective sample size, with the definition printed. |
| `planning.{model_implied_single_draw_score_sd,pooled_sd_at_observed_k,draw_facet_share_of_pooled_variance,k_to_halve_draw_contribution,k_where_item_facet_dominates,note,citation}` | Kalibera-Jones-style sizing: the draw-facet contribution scales exactly as 1/k. |
| `interval.{method,replicates,seed_procedure,assumptions}` | How the intervals were produced, with the assumption list printed verbatim. |
| `low_draw_levels`, `draw_levels_floor`, `low_k_note` | The fixed warning fires below 20 draw levels. |
| `bucket_note`, `never_headline_note` | The section's own limits; always present. |
| `degenerate_all_constant` | True when the archive carries zero variance. |

### `noise_floor`

The spread of this model's k single-draw scores over the aligned item set.
`null` when the task has fewer than two models.

| field | meaning |
|---|---|
| `k`, `n_items_aligned` | Draws and aligned items behind the scores. |
| `score_min`, `score_max`, `score_range`, `score_mean`, `score_sd` | Spread statistics, sd with ddof=1. |
| `score_resolution` | `1/n`: one flipped verdict moves one draw's score by exactly this. Spread below it is quantization. |

### `drift`

| field | meaning |
|---|---|
| `{state,basis,time_ordering_vacuous,proxy_disclaimer}` | Overall state (FAIL wins over UNAVAILABLE wins over PASS), the ordering basis, the vacuous-timestamps flag (clean results then report UNAVAILABLE), and the fixed proxy disclaimer, else `null`. |
| `subchecks.version_constancy.{state,versions,n_cells_missing}` | Byte equality of `model_version` across all draws. Two distinct values anywhere is FAIL; missing fields are UNAVAILABLE. `versions` lists the distinct values seen. |
| `subchecks.lodo.{state,reason,vacuous,clean,n_mixed,n_mixed_floor,carried_by_rank,max_carried,max_share,threshold}` | Leave-one-draw-out: `carried_by_rank[]` counts how many items stop being mixed when that rank is removed. FAIL when one rank carries more than `threshold` of the flips and `n_mixed` is at least `n_mixed_floor`. Below the floor the majority rule cannot discriminate and the state is UNAVAILABLE. |
| `subchecks.trend.{state,reason,rho,zero_variance,clean,part_by_rank,threshold,exchangeable_fpr,n_time_ties}` | Spearman trend of flip participation against collection order. FAIL when abs(rho) exceeds `threshold`. `exchangeable_fpr` is the exact false-positive rate of that threshold under a random ordering at this k. |

### `grader_defect`

| field | meaning |
|---|---|
| `state` | `AVAILABLE` when every cell carries raw hashes, else `UNAVAILABLE` with null counts. |
| `n_cells_with_text`, `n_cells` | Coverage of raw hashes. |
| `defect_pairs.{count,denominator,rate}` | Draw pairs with identical raw bytes and differing verdicts, over all discordant pairs. |
| `defect_items.{count,denominator,rate}` | Cells containing at least one defect pair, over mixed cells. |
| `mean_flakiness_raw` | Mean flakiness before any adjustment. |
| `mean_flakiness_excluding_detected_defects` | Mean flakiness with detected defect pairs subtracted. This subtracts only what byte identity can see; it does not prove the remainder is the model's. |
| `note` | Fixed text: the check detects grader nondeterminism, never grader wrongness. |

## PAIR rulings: one per within-task model pair

Identity: `ruling_id` (`LIMEN-<version>-PAIR-<nnnn>`), `kind` (`PAIR`),
`scope_key.{task,model_a,model_b}` with `model_a < model_b` lexicographically,
`content_hash`. `model_a` and `model_b` also appear at the top level of the
body. Direction is carried by the sign of the delta, never by pair order.

| field | meaning |
|---|---|
| `n.{items_aligned,k,draws_total}` | The comparison substrate. |
| `pooled.pass_a.{count,denominator,rate}`, `pooled.pass_b.{count,denominator,rate}` | Total passes over all draws of the aligned items. |
| `pooled.delta_pool` | `(pass_a - pass_b) / draws_total`. The claimed improvement, as the gate defines it. |
| `pooled.pooled_sign` | -1, 0 or +1, computed on integer pass counts. |
| `pooled.pooled_tie` | True when the pooled counts are exactly equal. |
| `sign_stability.ruling` | `SIGN-STABLE` or `SIGN-UNSTABLE`. Stable requires a nonzero pooled sign and zero flips. A pooled tie rules SIGN-UNSTABLE. |
| `sign_stability.pooled_tie` | Repeats the tie flag beside the ruling. |
| `sign_stability.n_agree.{count,denominator,rate}` | Draws agreeing with the pooled sign. `null` under a pooled tie: agreement with a nonexistent direction is undefined. |
| `sign_stability.n_flip.{count,denominator,rate}` | Draws reversing the pooled sign. `null` under a pooled tie. |
| `sign_stability.n_tie.{count,denominator,rate}` | Draws where the two models' pass counts are exactly equal. Ties are their own count and never break stability on their own. |
| `sign_stability.rank_flip_rate` | `n_flip / k`, ties kept in the denominator. |
| `sign_stability.flip_rate_excl_ties` | `n_flip / (n_flip + n_agree)`; `null` when that denominator is zero. |
| `sign_stability.flip_prob_upper95` | `1 - 0.05**(1/k)` when zero flips were observed: the one-sided 95% bound on the per-draw flip probability. `null` otherwise. |
| `noise.sd_a`, `noise.sd_b`, `noise.range_a`, `noise.range_b` | Single-draw score spread per side. |
| `noise.mdd.{value,t,df,alpha,low_k,degenerate_zero_spread,score_resolution,assumptions,citation}` | The minimum detectable difference at the observed k, with its t quantile, conservative df, fixed assumption list and citation. `low_k` flags k below 4. `degenerate_zero_spread` flags zero observed spread on both sides, which bounds nothing. |
| `confounded_by_version_change` | True when either model's version-constancy sub-check failed. The gate refuses effect attribution for such pairs. |
| `drift_ref.{model_a,model_b}` | The two models' overall drift states, repeated here for the gate. |

### `gap_survival`

The repaudit section: does the pair's ordering survive removing the items the
systems cannot reproduce against themselves? Never emitted without both
selection mitigations. All signs are integer pass-count signs; all band
comparisons are exact rationals.

| field | meaning |
|---|---|
| `note` | Fixed text: a ruling is a verdict on the measurement. |
| `threshold.{version,rule,note}` | The declared partition threshold (`u0`: u = 0 for both systems), with the IDR benchmark named. |
| `instability.u_tie_rule` | Fixed text for the even-k no-majority case. |
| `instability.a.{mean_u,max_u}`, `instability.b.{mean_u,max_u}` | Pair-scoped instability summaries per side. |
| `partition.{stable_both,unstable_either,unstable_a_only,unstable_b_only,unstable_both}` | The partition, every cell a counted triad. |
| `gaps.all.{state,n_items,pass_a,pass_b,delta,sign,ci95}` | The all-items gap; `delta` equals the PAIR body's `pooled.delta_pool` byte-for-byte. `ci95.{lo,hi,replicates}` is the two-stage paired bootstrap interval. |
| `gaps.stable_both.{state,n_items,pass_a,pass_b,delta,sign,ci95}` | The gap over items stable for both systems; `UNAVAILABLE` with nulls when the partition is empty. |
| `gaps.unstable_either.{state,n_items,pass_a,pass_b,delta,sign,ci95}` | The gap over the unstable remainder. |
| `share_unstable.{carried_draw_delta,total_draw_delta,share,opposing_partition_signs}` | The signed share of the gap carried by unstable items, with the raw integers printed; the share exceeds 1 or drops below 0 exactly when the partition gaps oppose, and the flag says so. |
| `bootstrap.{method,replicates,seed_procedure,note}` | The CI recipe; CIs are conditional on the observed partition. |
| `noise_band.{statistic,p95,max,per_system_max,n_splits,half_sizes,enumeration_cap,low_k,item_set,degenerate_zero_band,note}` | The enumerated replicate band: p95 of \|self-gap\| over ALL complementary half-splits, both systems pooled (`per_system_max.{a,b}` printed). No RNG and no thinning; above `enumeration_cap` splits (k of 23 or more) the block instead carries `{state,reason,n_splits,enumeration_cap,half_sizes,item_set,note}` with state UNAVAILABLE, and the ruling, selection null and coverage comparison go UNAVAILABLE with it. `item_set` is `all_aligned` at the pair level and `stratum` inside a stratum block. |
| `ruling.{ruling,reason,stable_tie,also_within_noise_band,band_statistic_used}` | SURVIVES / SIGN-INVERTS / FALLS-INTO-NOISE / UNAVAILABLE under the fixed precedence; an inversion inside the band stays SIGN-INVERTS with the flag printed. |
| `decisive_items.{state,direction,n_items,terminal_ruling,ids,cap,truncated,note}` | The auditable witness: the greedy removal margin (SURVIVES) or re-inclusion set (otherwise), capped at 25 printed ids; `NO_WITNESS` when even full re-inclusion cannot rule SURVIVES. |
| `rfc_differentiation.{citation,coverage_a,coverage_b,rfc_kept,ui_kept,excluded_intersection,excluded_union,jaccard_excluded,stable_but_always_wrong,ruling_under_rfc,rulings_differ}` | The mandated comparison against retry-free coverage. RFC is per-system, so `ruling_under_rfc.{ruling,reason,delta,sign}` rules on the coverage difference `coverage_a - coverage_b`; a joint-kept gap would be identically zero by construction and is not used. |
| `mitigations.split_half.{state,reason,n_splits,thinned,classify_draws,survived,inverted,indeterminate,share_unstable_over_splits,stable_both_size_over_splits,canonical_split}` | Disjoint classify/audit halves; `canonical_split.{classify_positions,audit_positions,n_stable,stable_sign,all_sign}` reported alone; `share_unstable_over_splits.{mean,min,max}` and `stable_both_size_over_splits.{mean,min,max}` across splits. |
| `mitigations.selection_null.{state,reason,replicates,replicates_effective,replicates_pooled_tie,band_held_fixed,seed_procedure,low_k,observed,null,interpretation}` | The selection null: `observed.{t_shrink,t_share,ruling}`; `null.t_shrink.{mean,p2_5,p97_5,p_value_one_sided_small,p_value_one_sided_large}`; `null.t_share.{mean,p2_5,p97_5,percentile_of_observed}`; `null.ruling_frequencies.{SURVIVES,SIGN-INVERTS,FALLS-INTO-NOISE,UNAVAILABLE}` as counted triads — the selection-only base rates. |
| `strata.{state,reason,by}` | Per-stratum rulings when requested: `by[].{label,n_items_unlabelled,strata}`; each stratum entry is `{value,state,n_items,...}` with either `reason`/`floor` (below the floor) or a full nested `audit` block (same shape as this section, minus differentiation and strata). |
| `unstable_share_vs_saturation[].{label,n_strata,spearman_rho,points}` | The saturation rollup per label key; `points[].{value,n_items,saturation,unstable_share}`. Association only; no mechanism claimed. |

## TASK rulings: one per task

Identity: `ruling_id` (`LIMEN-<version>-TASK-<nnnn>`), `kind` (`TASK`),
`scope_key.task`, `content_hash`.

| field | meaning |
|---|---|
| `n.{items_aligned,k,cells_truncated}`, `n.models[]` | The aligned substrate; `cells_truncated` counts cells shortened under `--ragged truncate`. |
| `pooled_flakiness.cell_pooled_mixed.{count,denominator,rate}` | Mixed cells over all (item x model) cells. |
| `pooled_flakiness.item_union_mixed.{count,denominator,rate}` | Aligned items mixed for at least one model. |
| `pooled_flakiness.n_items_aligned` | The aligned denominator. |
| `pooled_flakiness.alignment_excluded.<model>` | Per model, how many of its items fell outside the aligned intersection. |
| `misrank.draws_misranking_any_pair.{count,denominator,rate}` | Single-draw leaderboards that reverse at least one pair's pooled sign. |
| `variance_components.{state,reason,substrate,per_model,model_facet,low_draw_levels,draw_levels_floor,low_k_note,bucket_note,never_headline_note}` | The task-level decomposition over the aligned substrate: `substrate.{items_aligned,k}`; `per_model[].{model,grand_mean,components,shares,icc_item,icc_draw,design_effect}` (same component shape as the MT section); `model_facet.{kind,n_models,between_model_variance,between_model_sd,note}` is descriptive, never a component. |
| `differentiation.{n_pairs,pairs_rulings_differ,jaccard_min,jaccard_max,stable_but_always_wrong_max,interpretation}` | The task rollup of the per-pair RFC differentiation. |
| `labels.keys[].{key,n_items_labelled,values}` | Label coverage: `values[].{value,n_items}` per key; `null` when the input carries no labels. |

### `stable_only`

The stable-items-only view. The naive numbers are never emitted without the
two mitigations below (LMN-RNK-005).

| field | meaning |
|---|---|
| `note` | Fixed text: this ranking conditions on a selected subset and is one view of the data. |
| `per_model_constant.<model>.{count,denominator,rate}` | Items constant across all k draws for that model alone. |
| `naive.n_stable.{count,denominator,rate}` | Items constant for every model. |
| `naive.ranking_all_items[].{model,passes.count,passes.denominator,passes.rate}` | The headline ranking, descending. |
| `naive.ranking_stable_only[].{model,passes.count,passes.denominator,passes.rate}` | The ranking over stable items only; `null` when the stable set is empty. |
| `naive.tau_stable_vs_all.{tau_b,tau_a,concordant,discordant,ties_x,ties_y,undefined}` | Kendall tau between the two rankings, with the raw pair counts, which at four models say more than the coefficient. |
| `naive.pair_sign_survives[].{model_a,model_b,survives}` | Whether each pair's stable-only sign matches its headline sign; `null` when either sign is zero. |

#### `mitigations.split_half`

State `UNAVAILABLE` with a `reason` below k=4, where no disjoint split with two
classification draws exists. Otherwise:

| field | meaning |
|---|---|
| `state`, `reason` | Availability; the reason names the refusal. |
| `n_splits`, `thinned`, `classify_draws` | How many complementary classify/rank splits ran, whether the enumeration was deterministically thinned, and the classify-half size. |
| `sign_survival[].{model_a,model_b}` | The pair each row scores. |
| `sign_survival[].survived.{count,denominator,rate}` | Splits where the stable-only rank-half sign matched the headline pooled sign. |
| `sign_survival[].indeterminate.{count,denominator,rate}` | Splits where either sign was zero or the split-stable set was empty. |
| `tau_over_splits.{mean,min,max,n_undefined}` | Kendall tau between rank-half stable-only and rank-half all-items rankings, across splits. |
| `stable_set_size_over_splits.{mean,min,max}` | Size of the classify-half stable set across splits. Larger than the full-k stable set by construction. |
| `canonical_split.{classify_positions,rank_positions}` | The first-half/second-half split, reported alone for inspection. |
| `canonical_split.n_stable.{count,denominator,rate}` | Its classify-stable set size. |
| `canonical_split.tau.{tau_b,tau_a,concordant,discordant,ties_x,ties_y,undefined}` | Its rank-half tau. |

#### `mitigations.selection_null`

| field | meaning |
|---|---|
| `state` | `AVAILABLE`, or `UNAVAILABLE` when the observed stable set is empty or no replicate produced one. |
| `replicates`, `replicates_effective`, `replicates_empty_stable_set` | Requested replicates, those that produced a stable set, and those that did not. |
| `seed_procedure` | The fixed seed-derivation recipe, printed so the run is reproducible from the document alone. |
| `low_k` | Flags k below 4, where the per-cell rates behind the null are coarse. |
| `observed.{t_gap,t_flip,t_tau,n_stable}` | The statistics of the real archive under the naive pipeline. |
| `t_flip_definition` | Fixed text defining t_flip on the canonical split; it is `null` below k=4. |
| `null.t_gap.{mean,p2_5,p97_5,p_value_one_sided_large}` | Null band for gap inflation; a small p says the stable-only gaps widened more than selection alone explains. |
| `null.t_flip.{mean,p2_5,p97_5,p_value_one_sided_large,p_value_one_sided_small}` | Null band for rank-half flips among classify-stable items. `null` when t_flip is undefined. |
| `null.t_tau.{mean,p2_5,p97_5,percentile_of_observed}` | Null band for the stable-vs-all tau, reported as a percentile without a one-sided claim. |
| `interpretation` | The fixed reading rule: tidiness inside the null band is explained by selection alone. |

## What is deliberately absent

Ruling bodies carry no timestamp, no package version and no absolute paths
(LMN-EMIT-004). Schema `report/v1` had no variance-components section; adding
it in `report/v2` was a schema bump, exactly as the deferral prescribed
(LMN-EMIT-007), and the section exists only under its guardrails: the gate
never reads it, and it renders after the scope block. Removing or altering any
recorded value is a spec MAJOR, never a quiet edit (LMN-EMIT-008).
