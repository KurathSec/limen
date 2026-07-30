"""The gate: pass/fail policy over a ruling document, for CI.

The gate audits a report against itself (LMN-GTE-002): the claimed improvement
for a pair is the report's own pooled delta, and ``--pair task:A>B`` asserts a
direction that must match the report's pooled sign. Exit codes preserve the
three-way distinction (LMN-GTE-001): 0 pass, 1 measured fail, 2 unevaluable —
both non-zero, so UNAVAILABLE can never slip through as success, and a measured
failure outranks a missing section. Every FAIL reprints NO_MODEL_QUALITY_CLAIM
(LMN-GTE-003): a failed pair never means the other model wins.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .errors import GateError
from .spec import require

ACCEPTED_SCHEMAS = ("report/v1", "report/v2")


@dataclass(frozen=True, slots=True)
class GateOptions:
    require_sign_stable: bool = False
    min_effect_vs_noise: float | None = None
    pairs: tuple[str, ...] = ()
    tasks: tuple[str, ...] = ()
    require_drift_pass: bool = False
    max_grader_defect_share: float | None = None
    require_gap_survives: bool = False
    max_unstable_gap_share: float | None = None


@dataclass(frozen=True, slots=True)
class PairVerdict:
    task: str
    model_a: str
    model_b: str
    checks: tuple[tuple[str, str, str], ...]  # (check, state, detail); state PASS/FAIL/UNEVALUABLE
    verdict: str  # PASS | FAIL | UNEVALUABLE


@dataclass(frozen=True)
class GateResult:
    exit_code: int
    lines: tuple[str, ...]
    pair_verdicts: tuple[PairVerdict, ...]
    failures: tuple[str, ...] = field(default_factory=tuple)


def _parse_pair_spec(spec: str) -> tuple[str, str, str]:
    """'task:A>B' -> (task, better, worse)."""
    if ":" not in spec or ">" not in spec.split(":", 1)[1]:
        raise GateError(
            f"--pair {spec!r}: expected the form task:modelA>modelB "
            "(the > asserts the claimed direction)"
        )
    task, rest = spec.split(":", 1)
    better, worse = rest.split(">", 1)
    if not task or not better or not worse:
        raise GateError(f"--pair {spec!r}: empty task or model name")
    return task, better, worse


def _fmt_counted(c: dict[str, Any] | None) -> str:
    if c is None:
        return "null"
    return f"{c['count']}/{c['denominator']}"


def evaluate_gate(report: dict[str, Any], opts: GateOptions) -> GateResult:
    """Evaluate the gate policy. Malformed reports raise GateError (exit 2 at the
    CLI), never a bare KeyError masquerading as a measured verdict."""
    try:
        return _evaluate(report, opts)
    except GateError:
        raise
    except (KeyError, TypeError, IndexError, StopIteration) as exc:
        raise GateError(
            f"report is missing or malforms a required section ({exc!r}); "
            "not a faithful limen report/v1 document — regenerate it with limen report"
        ) from exc


def _evaluate(report: dict[str, Any], opts: GateOptions) -> GateResult:
    require("LMN-GTE-001")
    # LMN-GTE-004: report/v2 is additive over v1 and the gate never reads the
    # added variance_components section (LMN-VAR-004), so both schemas are
    # evaluable; an unknown or newer schema is unevaluable, never a silent pass
    if report.get("limen_schema") not in ACCEPTED_SCHEMAS:
        raise GateError(
            f"unknown limen schema {report.get('limen_schema')!r}; this gate "
            f"accepts {list(ACCEPTED_SCHEMAS)}"
        )
    pair_rulings: list[dict[str, Any]] = list(report["rulings"]["pair"])
    mt_index: dict[tuple[str, str], dict[str, Any]] = {
        (b["scope_key"]["task"], b["scope_key"]["model"]): b
        for b in report["rulings"]["mt"]
    }
    quality_notes = [
        item["text"]
        for item in report["scope"]["does_not_show"]
        if item["code"] == "NO_MODEL_QUALITY_CLAIM"
    ]
    if not quality_notes:
        raise GateError("report carries no NO_MODEL_QUALITY_CLAIM scope code")
    quality_note = quality_notes[0]

    if opts.tasks:
        pair_rulings = [b for b in pair_rulings if b["scope_key"]["task"] in opts.tasks]

    asserted: dict[tuple[str, str, str], int] = {}
    unmatched_specs: list[str] = []
    if opts.pairs:
        selected: list[dict[str, Any]] = []
        selected_keys: set[tuple[str, str, str]] = set()
        for spec in opts.pairs:
            task, better, worse = _parse_pair_spec(spec)
            match = None
            for body in pair_rulings:
                sk = body["scope_key"]
                if sk["task"] == task and {sk["model_a"], sk["model_b"]} == {better, worse}:
                    match = body
                    break
            if match is None:
                unmatched_specs.append(spec)
                continue
            sk = match["scope_key"]
            key = (task, sk["model_a"], sk["model_b"])
            direction = 1 if better == sk["model_a"] else -1
            if key in asserted and asserted[key] != direction:
                raise GateError(
                    f"--pair specs assert both directions for {task}: "
                    f"{sk['model_a']} vs {sk['model_b']}; a claim has one direction"
                )
            asserted[key] = direction
            if key not in selected_keys:
                selected_keys.add(key)
                selected.append(match)
        pair_rulings = selected

    lines: list[str] = []
    failures: list[str] = []
    verdicts: list[PairVerdict] = []
    any_unevaluable = bool(unmatched_specs)
    for spec in unmatched_specs:
        lines.append(f"UNEVALUABLE: --pair {spec} matches no pair ruling in the report")

    for body in pair_rulings:
        sk = body["scope_key"]
        task, a, b = sk["task"], sk["model_a"], sk["model_b"]
        pooled = body["pooled"]
        stability = body["sign_stability"]
        noise = body["noise"]
        mdd = noise["mdd"]
        checks: list[tuple[str, str, str]] = []

        asserted_direction = asserted.get((task, a, b))
        if asserted_direction is not None and pooled["pooled_sign"] != asserted_direction:
            checks.append(
                (
                    "claimed-direction",
                    "FAIL",
                    "claim_contradicts_pooled_data: asserted direction disagrees with "
                    f"the report's pooled sign {pooled['pooled_sign']}",
                )
            )
        elif asserted_direction is not None:
            checks.append(("claimed-direction", "PASS", "matches pooled sign"))

        if opts.require_sign_stable:
            if stability["ruling"] == "SIGN-STABLE":
                checks.append(
                    (
                        "sign-stable",
                        "PASS",
                        f"flips {_fmt_counted(stability['n_flip'])}, "
                        f"ties {_fmt_counted(stability['n_tie'])}, "
                        f"flip_prob_upper95 {stability['flip_prob_upper95']}",
                    )
                )
            else:
                reason = (
                    "pooled tie: no directional claim is supported"
                    if stability.get("pooled_tie")
                    else f"flips {_fmt_counted(stability['n_flip'])} of the single-draw leaderboards"
                )
                checks.append(("sign-stable", "FAIL", reason))

        if opts.min_effect_vs_noise is not None:
            threshold = opts.min_effect_vs_noise
            delta = abs(pooled["delta_pool"])
            if pooled["pooled_tie"]:
                checks.append(
                    ("effect-vs-noise", "FAIL", "pooled delta is zero; no effect exists")
                )
            elif body["confounded_by_version_change"]:
                checks.append(
                    (
                        "effect-vs-noise",
                        "FAIL",
                        "drift_confound: model_version changed mid-window; attribution "
                        "of the delta to the draw facet is refused",
                    )
                )
            elif mdd["value"] == 0.0:
                reason = (
                    "zero observed spread at this k bounds nothing; the check cannot "
                    "be evaluated and zero spread is not evidence of zero noise"
                    if mdd["degenerate_zero_spread"]
                    else "the serialized MDD rounds to zero at this resolution; the "
                    "ratio is not evaluable"
                )
                checks.append(("effect-vs-noise", "UNEVALUABLE", reason))
            else:
                ratio = delta / mdd["value"]
                state = "PASS" if ratio >= threshold else "FAIL"
                checks.append(
                    (
                        "effect-vs-noise",
                        state,
                        f"|delta| {delta} / MDD {mdd['value']} = {ratio:.2f} "
                        f"(threshold {threshold})",
                    )
                )

        if opts.require_drift_pass:
            drift_states = {
                m: body["drift_ref"][key] for m, key in ((a, "model_a"), (b, "model_b"))
            }
            if "FAIL" in drift_states.values():
                checks.append(("drift", "FAIL", f"drift guard failed: {drift_states}"))
            elif "UNAVAILABLE" in drift_states.values():
                checks.append(
                    (
                        "drift",
                        "UNEVALUABLE",
                        f"drift guard could not run: {drift_states} (UNAVAILABLE is not PASS)",
                    )
                )
            else:
                checks.append(("drift", "PASS", f"{drift_states}"))

        if opts.max_grader_defect_share is not None:
            detail: list[str] = []
            any_fail = False
            any_unavailable = False
            for model in (a, b):
                gd = mt_index[(task, model)]["grader_defect"]
                if gd["state"] == "UNAVAILABLE":
                    any_unavailable = True
                    detail.append(f"{model}: UNAVAILABLE (no raw text)")
                    continue
                pairs_counted = gd["defect_pairs"]
                share = pairs_counted["rate"] if pairs_counted["denominator"] else 0.0
                detail.append(f"{model}: {_fmt_counted(pairs_counted)} discordant pairs")
                if share is not None and share > opts.max_grader_defect_share:
                    any_fail = True
            # a measured failure outranks a missing section (same precedence as exits)
            state = "FAIL" if any_fail else "UNEVALUABLE" if any_unavailable else "PASS"
            checks.append(("grader-defects", state, "; ".join(detail)))

        if opts.require_gap_survives:
            audit = body.get("gap_survival")
            if audit is None:
                checks.append(
                    (
                        "gap-survives",
                        "UNEVALUABLE",
                        "no gap_survival section in this report (report/v1); "
                        "regenerate it with limen >= 0.2.0",
                    )
                )
            else:
                audit_ruling = audit["ruling"]["ruling"]
                band = audit["noise_band"]["p95"]
                if audit_ruling == "SURVIVES":
                    margin = (
                        audit["decisive_items"]["n_items"]["count"]
                        if audit["decisive_items"]
                        else None
                    )
                    checks.append(
                        (
                            "gap-survives",
                            "PASS",
                            f"stable delta {audit['gaps']['stable_both']['delta']}, "
                            f"band p95 {band}, survival margin {margin} items",
                        )
                    )
                elif audit_ruling == "UNAVAILABLE":
                    checks.append(
                        (
                            "gap-survives",
                            "UNEVALUABLE",
                            f"audit unavailable: {audit['ruling']['reason']}",
                        )
                    )
                else:
                    witness = audit["decisive_items"]
                    detail_text = (
                        f"{audit_ruling}: stable delta "
                        f"{audit['gaps']['stable_both']['delta']}, band p95 {band}"
                    )
                    if witness and witness.get("state") == "WITNESS":
                        detail_text += (
                            f"; {witness['n_items']['count']} re-included items "
                            "would flip the ruling"
                        )
                    checks.append(("gap-survives", "FAIL", detail_text))

        if opts.max_unstable_gap_share is not None:
            audit = body.get("gap_survival")
            share = audit["share_unstable"]["share"] if audit else None
            if audit is None:
                checks.append(
                    (
                        "unstable-gap-share",
                        "UNEVALUABLE",
                        "no gap_survival section in this report (report/v1); "
                        "regenerate it with limen >= 0.2.0",
                    )
                )
            elif share is None:
                checks.append(
                    (
                        "unstable-gap-share",
                        "UNEVALUABLE",
                        "share undefined (pooled tie)",
                    )
                )
            else:
                over = abs(share) > opts.max_unstable_gap_share
                opposing = audit["share_unstable"]["opposing_partition_signs"]
                checks.append(
                    (
                        "unstable-gap-share",
                        "FAIL" if over else "PASS",
                        f"|share| {abs(share)} vs threshold "
                        f"{opts.max_unstable_gap_share}"
                        + ("; partition signs oppose" if opposing else ""),
                    )
                )

        states = [state for _, state, _ in checks]
        verdict = (
            "FAIL" if "FAIL" in states else "UNEVALUABLE" if "UNEVALUABLE" in states else "PASS"
        )
        verdicts.append(
            PairVerdict(task=task, model_a=a, model_b=b, checks=tuple(checks), verdict=verdict)
        )
        if verdict == "FAIL":
            failures.append(f"{task}: {a} vs {b}")
        if verdict == "UNEVALUABLE":
            any_unevaluable = True

        lines.append(f"PAIR {task}: {a} vs {b}   [ruling: {stability['ruling']}]")
        lines.append(
            f"  pooled: a {_fmt_counted(pooled['pass_a'])} ({pooled['pass_a']['rate']})  "
            f"b {_fmt_counted(pooled['pass_b'])} ({pooled['pass_b']['rate']})  "
            f"delta {pooled['delta_pool']:+}  sign {pooled['pooled_sign']:+d}"
        )
        lines.append(
            f"  draws: agree {_fmt_counted(stability['n_agree'])}  "
            f"flip {_fmt_counted(stability['n_flip'])}  tie {_fmt_counted(stability['n_tie'])}"
        )
        lines.append(
            f"  noise: sd_a {noise['sd_a']}  sd_b {noise['sd_b']}  "
            f"MDD {mdd['value']} (t {mdd['t']}, df {mdd['df']}, alpha {mdd['alpha']})"
        )
        for check, state, detail_text in checks:
            lines.append(f"  check {check}: {state}  ({detail_text})")
        lines.append(f"  VERDICT: {verdict}")
        if verdict == "FAIL":
            lines.append(f"  note: {quality_note}")
        lines.append("")

    if not pair_rulings:
        # An empty selection can NEVER pass: a gate that checked nothing has not
        # gated anything (a --task typo must not turn CI green).
        any_unevaluable = True
        lines.append(
            "UNEVALUABLE: no pair rulings selected"
            + (
                f" (filters: tasks={list(opts.tasks)}, pairs={list(opts.pairs)})"
                if opts.tasks or opts.pairs
                else " (the report contains no within-task model pair)"
            )
        )

    n_checked = len(verdicts)
    n_failed = len(failures)
    n_unevaluable = sum(1 for v in verdicts if v.verdict == "UNEVALUABLE") + len(
        unmatched_specs
    )
    exit_code = 1 if n_failed else 2 if any_unevaluable else 0
    overall = "FAIL" if n_failed else "UNEVALUABLE" if any_unevaluable else "PASS"
    lines.append(
        f"OVERALL: {overall} ({n_failed} of {n_checked} pairs failed; "
        f"{n_unevaluable} unevaluable)   exit {exit_code}"
    )
    return GateResult(
        exit_code=exit_code,
        lines=tuple(lines),
        pair_verdicts=tuple(verdicts),
        failures=tuple(failures),
    )
