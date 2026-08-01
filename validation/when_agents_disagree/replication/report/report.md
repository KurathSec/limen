# limen ruling document

- schema: `report/v2`, rulings version: `wad1`, spec: `1.0.0`
- dataset digest: `sha256:10fa7d07c50d16ef78432e42f2b0c5d3a4b8f8dde4dc134391a7198d4629ccd0`

This document rules on measurement stability only. It makes no statement about which model is better.

## task `hotpotqa_distractor`

200 aligned items, k=10, models: `Qwen-Qwen2.5-72B-Instruct`, `google-gemma-3-27b-it`, `meta-llama-Llama-3.3-70B-Instruct-Turbo`, `microsoft-phi-4`

Single-draw leaderboards misranking at least one pair: **6/10**

| pair | ruling | audit | delta_pool | flips | ties | MDD | effect/MDD |
|---|---|---|---|---|---|---|---|
| `Qwen-Qwen2.5-72B-Instruct` vs `google-gemma-3-27b-it` | SIGN-UNSTABLE | SURVIVES | -0.0085 | 3/10 | 0/10 | 0.01832 | 0.46 |
| `Qwen-Qwen2.5-72B-Instruct` vs `meta-llama-Llama-3.3-70B-Instruct-Turbo` | SIGN-UNSTABLE | FALLS-INTO-NOISE | -0.008 | 2/10 | 1/10 | 0.022508 | 0.36 |
| `Qwen-Qwen2.5-72B-Instruct` vs `microsoft-phi-4` | SIGN-STABLE | FALLS-INTO-NOISE | +0.13 | 0/10 | 0/10 | 0.025066 | 5.19 |
| `google-gemma-3-27b-it` vs `meta-llama-Llama-3.3-70B-Instruct-Turbo` | SIGN-UNSTABLE | FALLS-INTO-NOISE | +0.0005 | 5/10 | 0/10 | 0.022257 | 0.02 |
| `google-gemma-3-27b-it` vs `microsoft-phi-4` | SIGN-STABLE | SURVIVES | +0.1385 | 0/10 | 0/10 | 0.024841 | 5.58 |
| `meta-llama-Llama-3.3-70B-Instruct-Turbo` vs `microsoft-phi-4` | SIGN-STABLE | FALLS-INTO-NOISE | +0.138 | 0/10 | 0/10 | 0.028073 | 4.92 |

## scope

- **NO_MODEL_QUALITY_CLAIM**: A sign ruling is a verdict on the measurement, never on the models; a flip means 'this comparison is not supported by its own data', never 'the other model wins'.
- **NO_PRIVILEGED_DRAW**: No draw is the correct one; all k are equally legitimate executions of the declared configuration, and there is no true score behind them to prefer.
- **NO_FACTOR_ATTRIBUTION**: 'Draw' is a bucket holding everything that varies between two identical calls; no seed / hardware / order / version decomposition is claimed.
- **NO_DRIFT_ABSENCE_CLAIM**: A drift PASS means the checks that could run found nothing; UNAVAILABLE is not PASS, and absence of evidence of drift is not evidence of its absence.
- **STABLE_SUBSET_IS_A_VIEW**: The stable-items-only ranking conditions on a selected subset enriched for easy items; it is one view, not a corrected or true ranking.
- **UNSTABLE_ITEMS_NOT_DEFECTIVE**: Instability is a joint property of item, model, serving stack, grader and protocol; an item unstable for one model and stable for another is not defective.
- **NO_K1_CERTIFICATE**: The spread and MDD are reported at the observed k; no sufficiency certificate is issued for k=1 or any other k, on any benchmark or provider.
- **EXACT_MATCH_GRADING_ONLY**: Validity is scoped to deterministic exact-match grading; nothing here says anything about judge-scored, rubric-scored or preference-scored tasks.
- **CONSTANCY_IS_NOT_CORRECTNESS**: Flakiness and TARa measure repeatability only; a constant-but-wrong verdict is invisible to this instrument.
- **STABILITY_THRESHOLD_IS_CRUDE**: The v1 stable/unstable threshold (u_i == 0 for both systems) is deliberately crude; the principled benchmark is an IDR-style threshold, and every ruling is stamped with the threshold version it used.
- **NO_SATURATION_MECHANISM_CLAIM**: The unstable-share-versus-saturation correlation is an association across strata of one archive; no causal mechanism and no generalization beyond it is claimed.

## variance components (subordinate diagnostic)

subordinate diagnostic: the gate never reads this section (LMN-VAR-004), and no top-line summary prints it

'draw' is a bucket holding everything that varies between two identical calls; the components size the bucket and attribute nothing inside it (NO_FACTOR_ATTRIBUTION)

the draw facet has fewer than 20 levels: the draw and residual components rest on df_draw = k-1 and are wide by construction; this section is a subordinate diagnostic and never a headline (LMN-VAR-003) Applies to: `Qwen-Qwen2.5-72B-Instruct`/`hotpotqa_distractor` (k=10), `google-gemma-3-27b-it`/`hotpotqa_distractor` (k=10), `meta-llama-Llama-3.3-70B-Instruct-Turbo`/`hotpotqa_distractor` (k=10), `microsoft-phi-4`/`hotpotqa_distractor` (k=10).

| model, task | component | estimate | ci95 | raw |
|---|---|---|---|---|
| `Qwen-Qwen2.5-72B-Instruct`, `hotpotqa_distractor` | item | 0.182499 | [0.162934, 0.198031] | 0.182499 |
| `Qwen-Qwen2.5-72B-Instruct`, `hotpotqa_distractor` | draw | 6.3e-05 | [0.0, 0.000928] | 6.3e-05 |
| `Qwen-Qwen2.5-72B-Instruct`, `hotpotqa_distractor` | residual | 0.055159 | [0.043021, 0.067155] | 0.055159 |
| `google-gemma-3-27b-it`, `hotpotqa_distractor` | item | 0.18018 | [0.160325, 0.196611] | 0.18018 |
| `google-gemma-3-27b-it`, `hotpotqa_distractor` | draw | 4e-05 | [0.0, 0.000882] | 4e-05 |
| `google-gemma-3-27b-it`, `hotpotqa_distractor` | residual | 0.05546 | [0.043222, 0.067701] | 0.05546 |
| `meta-llama-Llama-3.3-70B-Instruct-Turbo`, `hotpotqa_distractor` | item | 0.155156 | [0.133926, 0.171717] | 0.155156 |
| `meta-llama-Llama-3.3-70B-Instruct-Turbo`, `hotpotqa_distractor` | draw | 0.00025 | [0.0, 0.001553] | 0.00025 |
| `meta-llama-Llama-3.3-70B-Instruct-Turbo`, `hotpotqa_distractor` | residual | 0.080306 | [0.066124, 0.094717] | 0.080306 |
| `microsoft-phi-4`, `hotpotqa_distractor` | item | 0.128506 | [0.113377, 0.142515] | 0.128506 |
| `microsoft-phi-4`, `hotpotqa_distractor` | draw | 0.00028 | [0.0, 0.002066] | 0.00028 |
| `microsoft-phi-4`, `hotpotqa_distractor` | residual | 0.12172 | [0.106861, 0.135498] | 0.12172 |
