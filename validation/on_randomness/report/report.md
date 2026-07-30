# limen ruling document

- schema: `report/v2`, rulings version: `onr1`, spec: `1.0.0`
- dataset digest: `sha256:230644603b121cb1a46aee79829db6f8fa17a4bc6b3bd6305690920c5f88d670`

This document rules on measurement stability only. It makes no statement about which model is better.

## task `swebench_verified`

500 aligned items, k=10, models: `nano-agent-Qwen_Qwen3-32B`, `nano-agent-Qwen_Qwen3-32B-temp0`, `nano-agent-agentica-org_DeepSWE-Preview`, `nano-agent-agentica-org_DeepSWE-Preview__temp0`, `nano-agent-mistral_devstral-2512`, `nano-agent-mistral_devstral-2512__temp0`

Single-draw leaderboards misranking at least one pair: **8/10**

| pair | ruling | audit | delta_pool | flips | ties | MDD | effect/MDD |
|---|---|---|---|---|---|---|---|
| `nano-agent-Qwen_Qwen3-32B` vs `nano-agent-Qwen_Qwen3-32B-temp0` | SIGN-UNSTABLE | FALLS-INTO-NOISE | +0.0002 | 5/10 | 1/10 | 0.009941 | 0.02 |
| `nano-agent-Qwen_Qwen3-32B` vs `nano-agent-agentica-org_DeepSWE-Preview` | SIGN-STABLE | FALLS-INTO-NOISE | -0.15 | 0/10 | 0/10 | 0.009046 | 16.58 |
| `nano-agent-Qwen_Qwen3-32B` vs `nano-agent-agentica-org_DeepSWE-Preview__temp0` | SIGN-STABLE | FALLS-INTO-NOISE | -0.0398 | 0/10 | 0/10 | 0.00867 | 4.59 |
| `nano-agent-Qwen_Qwen3-32B` vs `nano-agent-mistral_devstral-2512` | SIGN-STABLE | SURVIVES | -0.4716 | 0/10 | 0/10 | 0.009668 | 48.78 |
| `nano-agent-Qwen_Qwen3-32B` vs `nano-agent-mistral_devstral-2512__temp0` | SIGN-STABLE | SURVIVES | -0.4744 | 0/10 | 0/10 | 0.012901 | 36.77 |
| `nano-agent-Qwen_Qwen3-32B-temp0` vs `nano-agent-agentica-org_DeepSWE-Preview` | SIGN-STABLE | FALLS-INTO-NOISE | -0.1502 | 0/10 | 0/10 | 0.011128 | 13.50 |
| `nano-agent-Qwen_Qwen3-32B-temp0` vs `nano-agent-agentica-org_DeepSWE-Preview__temp0` | SIGN-STABLE | FALLS-INTO-NOISE | -0.04 | 0/10 | 0/10 | 0.010825 | 3.70 |
| `nano-agent-Qwen_Qwen3-32B-temp0` vs `nano-agent-mistral_devstral-2512` | SIGN-STABLE | SURVIVES | -0.4718 | 0/10 | 0/10 | 0.01164 | 40.53 |
| `nano-agent-Qwen_Qwen3-32B-temp0` vs `nano-agent-mistral_devstral-2512__temp0` | SIGN-STABLE | SURVIVES | -0.4746 | 0/10 | 0/10 | 0.014438 | 32.87 |
| `nano-agent-agentica-org_DeepSWE-Preview` vs `nano-agent-agentica-org_DeepSWE-Preview__temp0` | SIGN-STABLE | FALLS-INTO-NOISE | +0.1102 | 0/10 | 0/10 | 0.010009 | 11.01 |
| `nano-agent-agentica-org_DeepSWE-Preview` vs `nano-agent-mistral_devstral-2512` | SIGN-STABLE | SURVIVES | -0.3216 | 0/10 | 0/10 | 0.010886 | 29.54 |
| `nano-agent-agentica-org_DeepSWE-Preview` vs `nano-agent-mistral_devstral-2512__temp0` | SIGN-STABLE | SURVIVES | -0.3244 | 0/10 | 0/10 | 0.013837 | 23.44 |
| `nano-agent-agentica-org_DeepSWE-Preview__temp0` vs `nano-agent-mistral_devstral-2512` | SIGN-STABLE | SURVIVES | -0.4318 | 0/10 | 0/10 | 0.010575 | 40.83 |
| `nano-agent-agentica-org_DeepSWE-Preview__temp0` vs `nano-agent-mistral_devstral-2512__temp0` | SIGN-STABLE | SURVIVES | -0.4346 | 0/10 | 0/10 | 0.013594 | 31.97 |
| `nano-agent-mistral_devstral-2512` vs `nano-agent-mistral_devstral-2512__temp0` | SIGN-UNSTABLE | FALLS-INTO-NOISE | -0.0028 | 4/10 | 0/10 | 0.014251 | 0.20 |

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

the draw facet has fewer than 20 levels: the draw and residual components rest on df_draw = k-1 and are wide by construction; this section is a subordinate diagnostic and never a headline (LMN-VAR-003) Applies to: `nano-agent-Qwen_Qwen3-32B`/`swebench_verified` (k=10), `nano-agent-Qwen_Qwen3-32B-temp0`/`swebench_verified` (k=10), `nano-agent-agentica-org_DeepSWE-Preview`/`swebench_verified` (k=10), `nano-agent-agentica-org_DeepSWE-Preview__temp0`/`swebench_verified` (k=10), `nano-agent-mistral_devstral-2512`/`swebench_verified` (k=10), `nano-agent-mistral_devstral-2512__temp0`/`swebench_verified` (k=10).

| model, task | component | estimate | ci95 | raw |
|---|---|---|---|---|
| `nano-agent-Qwen_Qwen3-32B`, `swebench_verified` | item | 0.081605 | [0.066275, 0.096361] | 0.081605 |
| `nano-agent-Qwen_Qwen3-32B`, `swebench_verified` | draw | 0.0 | [0.0, 0.000241] | -5.6e-05 |
| `nano-agent-Qwen_Qwen3-32B`, `swebench_verified` | residual | 0.055589 | [0.047601, 0.063572] | 0.055589 |
| `nano-agent-Qwen_Qwen3-32B-temp0`, `swebench_verified` | item | 0.083416 | [0.067842, 0.098956] | 0.083416 |
| `nano-agent-Qwen_Qwen3-32B-temp0`, `swebench_verified` | draw | 3e-05 | [0.0, 0.00038] | 3e-05 |
| `nano-agent-Qwen_Qwen3-32B-temp0`, `swebench_verified` | residual | 0.05357 | [0.045645, 0.062271] | 0.05357 |
| `nano-agent-agentica-org_DeepSWE-Preview`, `swebench_verified` | item | 0.118176 | [0.10706, 0.128683] | 0.118176 |
| `nano-agent-agentica-org_DeepSWE-Preview`, `swebench_verified` | draw | 0.0 | [0.0, 0.000442] | -9.1e-05 |
| `nano-agent-agentica-org_DeepSWE-Preview`, `swebench_verified` | residual | 0.097491 | [0.08828, 0.106924] | 0.097491 |
| `nano-agent-agentica-org_DeepSWE-Preview__temp0`, `swebench_verified` | item | 0.091138 | [0.0776, 0.10528] | 0.091138 |
| `nano-agent-agentica-org_DeepSWE-Preview__temp0`, `swebench_verified` | draw | 0.0 | [0.0, 0.000316] | -5.1e-05 |
| `nano-agent-agentica-org_DeepSWE-Preview__temp0`, `swebench_verified` | residual | 0.071251 | [0.062576, 0.080499] | 0.071251 |
| `nano-agent-mistral_devstral-2512`, `swebench_verified` | item | 0.166346 | [0.154375, 0.177323] | 0.166346 |
| `nano-agent-mistral_devstral-2512`, `swebench_verified` | draw | 0.0 | [0.0, 0.000341] | -4e-06 |
| `nano-agent-mistral_devstral-2512`, `swebench_verified` | residual | 0.065671 | [0.057877, 0.073564] | 0.065671 |
| `nano-agent-mistral_devstral-2512__temp0`, `swebench_verified` | item | 0.162787 | [0.150064, 0.174001] | 0.162787 |
| `nano-agent-mistral_devstral-2512__temp0`, `swebench_verified` | draw | 0.000133 | [2.6e-05, 0.000617] | 0.000133 |
| `nano-agent-mistral_devstral-2512__temp0`, `swebench_verified` | residual | 0.068334 | [0.059277, 0.076268] | 0.068334 |
