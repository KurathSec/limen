"""The limen command line: report / gate / synth / regrade / spec / env."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ._version import __version__
from .canonical import canonical_json, sha256_file, write_text_deterministic
from .errors import LimenError, TableError
from .gate import GateOptions, evaluate_gate
from .model import VerdictRow, build_archive
from .readers import load_rows
from .readers.base import ReaderOptions
from .report import ReportOptions, build_report
from .spec import all_decisions, require, spec_version


def _cmd_report(args: argparse.Namespace) -> int:
    options = ReaderOptions(min_k=args.min_k, metric=args.metric, model_name=args.model_name)
    # merge at ROW level, before any min-k exclusion: draws of one cell split
    # across inputs must stack first, and the exclusion counts survive intact
    rows: list[VerdictRow] = []
    meta: dict[str, str] = {}
    for i, input_path in enumerate(args.inputs):
        rows.extend(load_rows(input_path, format=args.format, options=options))
        meta.update({f"source_{i}": str(input_path)})
    try:
        merged = build_archive(rows, meta=meta, min_k=args.min_k)
    except TableError as exc:
        if "duplicate" in str(exc) and len(args.inputs) > 1:
            raise TableError(
                f"{exc}; if these inputs are re-runs of the same lm-eval configuration, "
                "pass their common parent directory as ONE input so repeats stack into "
                "draws instead of colliding"
            ) from exc
        raise
    report = build_report(
        merged,
        rulings_version=args.rulings_version,
        options=ReportOptions(
            replicates=args.replicates,
            max_splits=args.max_splits,
            assume_index_is_collection_order=args.assume_index_is_collection_order,
            ragged=args.ragged,
        ),
    )
    out = Path(args.out)
    write_text_deterministic(out / "report.json", canonical_json(report))
    provenance = {
        "limen_version": __version__,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "inputs": [
            {
                "path": str(p),
                "sha256": sha256_file(Path(p)) if Path(p).is_file() else None,
            }
            for p in args.inputs
        ],
        "rulings_version": args.rulings_version,
        "argv": sys.argv[1:],
    }
    write_text_deterministic(out / "provenance.json", canonical_json(provenance))
    write_text_deterministic(out / "report.md", _render_markdown(report))
    if args.json:
        sys.stdout.write(canonical_json(report))
    else:
        print(f"wrote {out / 'report.json'} (+ provenance.json, report.md)")
        _print_summary(report)
    return 0


def _print_summary(report: dict[str, Any]) -> None:
    for task_body in report["rulings"]["task"]:
        task = task_body["scope_key"]["task"]
        n = task_body["n"]
        mis = task_body["misrank"]["draws_misranking_any_pair"]
        print(
            f"task {task}: {n['items_aligned']} aligned items x k={n['k']} x "
            f"{len(n['models'])} models; {mis['count']}/{mis['denominator']} single-draw "
            "leaderboards misrank at least one pair"
        )
    for body in report["rulings"]["pair"]:
        sk = body["scope_key"]
        st = body["sign_stability"]
        print(
            f"  {sk['task']}: {sk['model_a']} vs {sk['model_b']}: {st['ruling']}"
            f" (delta {body['pooled']['delta_pool']:+}, MDD {body['noise']['mdd']['value']})"
        )


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# limen ruling document",
        "",
        f"- schema: `{report['limen_schema']}`, rulings version: "
        f"`{report['rulings_version']}`, spec: `{report['spec_version']}`",
        f"- dataset digest: `{report['dataset_digest']}`",
        "",
        "This document rules on measurement stability only. It makes no statement "
        "about which model is better.",
        "",
    ]
    for task_body in report["rulings"]["task"]:
        task = task_body["scope_key"]["task"]
        n = task_body["n"]
        mis = task_body["misrank"]["draws_misranking_any_pair"]
        lines += [
            f"## task `{task}`",
            "",
            f"{n['items_aligned']} aligned items, k={n['k']}, models: "
            + ", ".join(f"`{m}`" for m in n["models"]),
            "",
            f"Single-draw leaderboards misranking at least one pair: "
            f"**{mis['count']}/{mis['denominator']}**",
            "",
            "| pair | ruling | delta_pool | flips | ties | MDD | effect/MDD |",
            "|---|---|---|---|---|---|---|",
        ]
        for body in report["rulings"]["pair"]:
            if body["scope_key"]["task"] != task:
                continue
            sk = body["scope_key"]
            st = body["sign_stability"]
            mdd = body["noise"]["mdd"]["value"]
            delta = body["pooled"]["delta_pool"]
            ratio = f"{abs(delta) / mdd:.2f}" if mdd else "null"
            flips = "null" if st["n_flip"] is None else f"{st['n_flip']['count']}/{st['n_flip']['denominator']}"
            ties = "null" if st["n_tie"] is None else f"{st['n_tie']['count']}/{st['n_tie']['denominator']}"
            lines.append(
                f"| `{sk['model_a']}` vs `{sk['model_b']}` | {st['ruling']} | "
                f"{delta:+} | {flips} | {ties} | {mdd} | {ratio} |"
            )
        lines.append("")
    lines += ["## scope", ""]
    for item in report["scope"]["does_not_show"]:
        lines.append(f"- **{item['code']}**: {item['text']}")
    lines.append("")
    return "\n".join(lines)


def _cmd_gate(args: argparse.Namespace) -> int:
    require("LMN-GTE-002")
    try:
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"limen gate: cannot read report: {exc}", file=sys.stderr)
        return 2
    result = evaluate_gate(
        report,
        GateOptions(
            require_sign_stable=args.require_sign_stable,
            min_effect_vs_noise=args.min_effect_vs_noise,
            pairs=tuple(args.pair or ()),
            tasks=tuple(args.task or ()),
            require_drift_pass=args.require_drift_pass,
            max_grader_defect_share=args.max_grader_defect_share,
        ),
    )
    for line in result.lines:
        print(line)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        for failure in result.failures:
            print(f"::error title=limen gate::pair failed: {failure}")
    return result.exit_code


def _cmd_synth(args: argparse.Namespace) -> int:
    from .readers.longcsv import write_archive
    from .synth import PlantedConfig, generate

    models = tuple(f"model-{chr(ord('a') + i)}" for i in range(args.models))
    mu = tuple(args.top_mu - i * args.gap for i in range(args.models))
    config = PlantedConfig(
        n_items=args.items,
        k=args.draws,
        models=models,
        mu=mu,
        flaky_fraction=args.flaky_fraction,
        q=args.q,
        defect_items=args.defect_items,
        version_change_at_draw=args.version_change_at_draw,
    )
    archive, truth = generate(config, seed=args.seed)
    out = Path(args.out)
    write_archive(archive, out / "archive.verdicts.csv.gz")
    write_text_deterministic(out / "truth.json", canonical_json(truth.as_dict()))
    print(f"wrote {out / 'archive.verdicts.csv.gz'} and truth.json")
    return 0


def _cmd_regrade(args: argparse.Namespace) -> int:
    from .adapters.spaghetti import build_tables

    paths = build_tables(
        repo_path=args.repo,
        out_dir=Path(args.out),
        tasks=tuple(args.task),
        max_workers=args.workers,
    )
    for p in paths:
        print(f"wrote {p}")
    return 0


def _cmd_spec(args: argparse.Namespace) -> int:
    if args.action == "list":
        print(f"rulings spec version {spec_version()}")
        for decision in all_decisions():
            print(f"  {decision.id}  [{decision.status}]  {decision.title}")
        return 0
    decision = require(args.id)
    print(f"{decision.id} [{decision.status}] {decision.title}")
    print(decision.text)
    return 0


def _cmd_env(_args: argparse.Namespace) -> int:
    import platform

    print(f"limen {__version__}")
    print(f"rulings spec {spec_version()}")
    print(f"python {platform.python_version()} on {platform.platform()}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="limen",
        description=(
            "The same-configuration noise floor of an evaluation: verdict flakiness, "
            "sign-stability rulings, and a CI gate over repeated identical runs. "
            "It makes no statement about which model is better."
        ),
    )
    parser.add_argument("--version", action="version", version=f"limen {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("report", help="analyze repeated-run logs into a ruling document")
    p.add_argument("inputs", nargs="+", help="input file(s)/dir(s): long CSV or lm-eval logs")
    p.add_argument("--format", choices=["long-csv", "lm-eval"], default=None)
    p.add_argument("--out", default="limen-report", help="output directory")
    p.add_argument("--json", action="store_true", help="also print report.json to stdout")
    p.add_argument("--metric", default=None, help="lm-eval: binary metric field to use")
    p.add_argument("--model-name", default=None, help="lm-eval: override the model label")
    p.add_argument("--min-k", type=int, default=2)
    p.add_argument("--rulings-version", default="adhoc")
    p.add_argument("--replicates", type=int, default=1000, help="selection-null replicates")
    p.add_argument("--max-splits", type=int, default=256)
    p.add_argument(
        "--assume-index-is-collection-order",
        action="store_true",
        help="drift guard position-proxy mode: declares draw order = collection order "
        "(clean results still report UNAVAILABLE, never PASS)",
    )
    p.add_argument("--ragged", choices=["error", "truncate"], default="error")
    p.set_defaults(func=_cmd_report)

    p = sub.add_parser("gate", help="pass/fail a ruling document for CI")
    p.add_argument("report", help="path to report.json")
    p.add_argument("--require-sign-stable", action="store_true")
    p.add_argument("--min-effect-vs-noise", type=float, default=None, metavar="RATIO")
    p.add_argument(
        "--pair",
        action="append",
        metavar="task:A>B",
        help="restrict to a claimed pair; > asserts the claimed direction (repeatable)",
    )
    p.add_argument("--task", action="append", help="restrict to a task (repeatable)")
    p.add_argument("--require-drift-pass", action="store_true")
    p.add_argument("--max-grader-defect-share", type=float, default=None)
    p.set_defaults(func=_cmd_gate)

    p = sub.add_parser("synth", help="generate a planted-truth synthetic archive")
    p.add_argument("--out", required=True)
    p.add_argument("--models", type=int, default=2)
    p.add_argument("--items", type=int, default=500)
    p.add_argument("--draws", type=int, default=8)
    p.add_argument("--flaky-fraction", type=float, default=0.05)
    p.add_argument("--q", type=float, default=0.5)
    p.add_argument("--gap", type=float, default=0.02, help="true adjacent-pair score gap")
    p.add_argument("--top-mu", type=float, default=0.8)
    p.add_argument("--defect-items", type=int, default=0)
    p.add_argument("--version-change-at-draw", type=int, default=None)
    p.add_argument("--seed", type=int, default=0)
    p.set_defaults(func=_cmd_synth)

    p = sub.add_parser(
        "regrade",
        help="build verdict tables from a Spaghetti-Architect checkout (read-only)",
    )
    p.add_argument("--repo", default=None, help="checkout path (default $LIMEN_SPAGHETTI_REPO)")
    p.add_argument(
        "--task",
        action="append",
        required=True,
        choices=["comprehend_dev", "comprehend_test", "refactor_dev"],
        help="repeatable; refactor_test is refused (upstream declares it non-reproducible)",
    )
    p.add_argument("--out", required=True)
    p.add_argument("--workers", type=int, default=8)
    p.set_defaults(func=_cmd_regrade)

    p = sub.add_parser("spec", help="list or show the numbered spec rulings")
    spec_sub = p.add_subparsers(dest="action", required=True)
    spec_sub.add_parser("list").set_defaults(func=_cmd_spec, action="list")
    show = spec_sub.add_parser("show")
    show.add_argument("id")
    show.set_defaults(func=_cmd_spec, action="show")

    p = sub.add_parser("env", help="print versions and platform")
    p.set_defaults(func=_cmd_env)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (LimenError, ValueError) as exc:
        print(f"limen: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
