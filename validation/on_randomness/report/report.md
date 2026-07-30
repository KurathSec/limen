# limen ruling document

- schema: `report/v1`, rulings version: `onr1`, spec: `0.2.0`
- dataset digest: `sha256:230644603b121cb1a46aee79829db6f8fa17a4bc6b3bd6305690920c5f88d670`

This document rules on measurement stability only. It makes no statement about which model is better.

## task `swebench_verified`

500 aligned items, k=10, models: `nano-agent-Qwen_Qwen3-32B`, `nano-agent-Qwen_Qwen3-32B-temp0`, `nano-agent-agentica-org_DeepSWE-Preview`, `nano-agent-agentica-org_DeepSWE-Preview__temp0`, `nano-agent-mistral_devstral-2512`, `nano-agent-mistral_devstral-2512__temp0`

Single-draw leaderboards misranking at least one pair: **8/10**

| pair | ruling | delta_pool | flips | ties | MDD | effect/MDD |
|---|---|---|---|---|---|---|
| `nano-agent-Qwen_Qwen3-32B` vs `nano-agent-Qwen_Qwen3-32B-temp0` | SIGN-UNSTABLE | +0.0002 | 5/10 | 1/10 | 0.009941 | 0.02 |
| `nano-agent-Qwen_Qwen3-32B` vs `nano-agent-agentica-org_DeepSWE-Preview` | SIGN-STABLE | -0.15 | 0/10 | 0/10 | 0.009046 | 16.58 |
| `nano-agent-Qwen_Qwen3-32B` vs `nano-agent-agentica-org_DeepSWE-Preview__temp0` | SIGN-STABLE | -0.0398 | 0/10 | 0/10 | 0.00867 | 4.59 |
| `nano-agent-Qwen_Qwen3-32B` vs `nano-agent-mistral_devstral-2512` | SIGN-STABLE | -0.4716 | 0/10 | 0/10 | 0.009668 | 48.78 |
| `nano-agent-Qwen_Qwen3-32B` vs `nano-agent-mistral_devstral-2512__temp0` | SIGN-STABLE | -0.4744 | 0/10 | 0/10 | 0.012901 | 36.77 |
| `nano-agent-Qwen_Qwen3-32B-temp0` vs `nano-agent-agentica-org_DeepSWE-Preview` | SIGN-STABLE | -0.1502 | 0/10 | 0/10 | 0.011128 | 13.50 |
| `nano-agent-Qwen_Qwen3-32B-temp0` vs `nano-agent-agentica-org_DeepSWE-Preview__temp0` | SIGN-STABLE | -0.04 | 0/10 | 0/10 | 0.010825 | 3.70 |
| `nano-agent-Qwen_Qwen3-32B-temp0` vs `nano-agent-mistral_devstral-2512` | SIGN-STABLE | -0.4718 | 0/10 | 0/10 | 0.01164 | 40.53 |
| `nano-agent-Qwen_Qwen3-32B-temp0` vs `nano-agent-mistral_devstral-2512__temp0` | SIGN-STABLE | -0.4746 | 0/10 | 0/10 | 0.014438 | 32.87 |
| `nano-agent-agentica-org_DeepSWE-Preview` vs `nano-agent-agentica-org_DeepSWE-Preview__temp0` | SIGN-STABLE | +0.1102 | 0/10 | 0/10 | 0.010009 | 11.01 |
| `nano-agent-agentica-org_DeepSWE-Preview` vs `nano-agent-mistral_devstral-2512` | SIGN-STABLE | -0.3216 | 0/10 | 0/10 | 0.010886 | 29.54 |
| `nano-agent-agentica-org_DeepSWE-Preview` vs `nano-agent-mistral_devstral-2512__temp0` | SIGN-STABLE | -0.3244 | 0/10 | 0/10 | 0.013837 | 23.44 |
| `nano-agent-agentica-org_DeepSWE-Preview__temp0` vs `nano-agent-mistral_devstral-2512` | SIGN-STABLE | -0.4318 | 0/10 | 0/10 | 0.010575 | 40.83 |
| `nano-agent-agentica-org_DeepSWE-Preview__temp0` vs `nano-agent-mistral_devstral-2512__temp0` | SIGN-STABLE | -0.4346 | 0/10 | 0/10 | 0.013594 | 31.97 |
| `nano-agent-mistral_devstral-2512` vs `nano-agent-mistral_devstral-2512__temp0` | SIGN-UNSTABLE | -0.0028 | 4/10 | 0/10 | 0.014251 | 0.20 |

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
