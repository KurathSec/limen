"""docs/report.md drift gate: the format reference and the format cannot diverge.

Two directions: every field path the page names must exist in a real report,
and every field a real report emits must be named on the page. The union of
report shapes comes from the committed calibration golden plus synthetic
archives chosen to exercise the variant shapes (proxy drift, pooled ties,
unavailable sections, low-k refusals, exclusion counts).
"""

import json
import re
from pathlib import Path
from typing import Any

from conftest import archive_from_grid, rows_from_grid

from limen.model import VerdictRow, build_archive
from limen.report import ReportOptions, build_report

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "report.md"
GOLDEN = ROOT / "calibration" / "spaghetti" / "rulings" / "cal1" / "comprehend_dev.report.json"

MODEL_KEYED_PARENTS = {"alignment_excluded", "per_model_constant"}


def _paths(node: Any, prefix: str = "", parent_key: str = "") -> set[str]:
    out: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            shown = "<model>" if parent_key in MODEL_KEYED_PARENTS else key
            out |= _paths(value, f"{prefix}.{shown}" if prefix else shown, key)
    elif isinstance(node, list):
        if node and isinstance(node[0], dict | list):
            for item in node:
                out |= _paths(item, prefix + "[]", parent_key)
        else:
            out.add(prefix + "[]")
    else:
        out.add(prefix)
    return out


def _report_union() -> set[str]:
    union: set[str] = set()
    if GOLDEN.is_file():
        union |= _paths(json.loads(GOLDEN.read_text(encoding="utf-8")))
    # full-featured: timestamps, versions, hashes, a version change, k=8
    full = archive_from_grid(
        {
            "a": {f"i{j}": [1, 0, 1, 1, 1, 1, 0, 1] if j < 2 else [1] * 8 for j in range(6)},
            "b": {f"i{j}": [0, 1, 0, 0, 1, 0, 1, 0] if j < 2 else [0] * 8 for j in range(6)},
        },
        with_timestamps=True,
        with_hashes=True,
        version_by_draw={6: "v2", 7: "v2"},
    )
    union |= _paths(build_report(full, rulings_version="doc", options=ReportOptions(replicates=8)))
    # pooled tie at k=2: null agreement fields, split-half refusal, low-k paths
    tie = archive_from_grid(
        {"a": {"i1": [1, 0], "i2": [0, 1]}, "b": {"i1": [0, 1], "i2": [1, 0]}}
    )
    union |= _paths(build_report(tie, rulings_version="doc", options=ReportOptions(replicates=8)))
    # bare archive with an excluded low-k row: exclusion entries, unavailable sections
    rows = rows_from_grid(
        {"a": {"i1": [1, 0, 1], "i2": [1, 1, 0]}, "b": {"i1": [0, 1, 1], "i2": [1, 0, 0]}}
    ) + [VerdictRow(model="a", task="t", item_id="stray", draw_id="0", verdict=1)]
    bare = build_archive(rows)
    union |= _paths(build_report(bare, rulings_version="doc", options=ReportOptions(replicates=8)))
    return union


_BRACE = re.compile(r"^(.*)\{([^{}]+)\}(.*)$")
_ROOTS = (
    "limen_schema", "rulings_version", "spec_version", "dataset_digest",
    "content_hash", "options.", "n.", "scope.", "rulings.",
)


def _doc_paths() -> set[str]:
    out: set[str] = set()
    for token in re.findall(r"`([^`]+)`", DOC.read_text(encoding="utf-8")):
        candidates = [token]
        while any("{" in c for c in candidates):
            expanded = []
            for cand in candidates:
                m = _BRACE.match(cand)
                if m:
                    expanded += [m.group(1) + part + m.group(3) for part in m.group(2).split(",")]
                else:
                    expanded.append(cand)
            candidates = expanded
        for cand in candidates:
            if cand.startswith(_ROOTS) or cand in ("limen_schema", "rulings_version",
                                                   "spec_version", "dataset_digest",
                                                   "content_hash"):
                out.add(cand)
    return out


def _contextualize(doc_paths: set[str]) -> set[str]:
    """Doc tables abbreviate deep paths; expand section-relative mentions."""
    expanded = set(doc_paths)
    prefixes = {
        "flakiness.": "rulings.mt[].",
        "noise_floor.": "rulings.mt[].",
        "drift.": "rulings.mt[].",
        "grader_defect.": "rulings.mt[].",
        "subchecks.": "rulings.mt[].drift.",
        "pooled.": "rulings.pair[].",
        "sign_stability.": "rulings.pair[].",
        "noise.": "rulings.pair[].",
        "drift_ref.": "rulings.pair[].",
        "pooled_flakiness.": "rulings.task[].",
        "misrank.": "rulings.task[].",
        "stable_only.": "rulings.task[].",
        "per_model_constant.": "rulings.task[].stable_only.",
        "naive.": "rulings.task[].stable_only.",
        "mitigations.": "rulings.task[].stable_only.",
        "split_half.": "rulings.task[].stable_only.mitigations.",
        "sign_survival[]": "rulings.task[].stable_only.mitigations.split_half.",
        "tau_over_splits.": "rulings.task[].stable_only.mitigations.split_half.",
        "stable_set_size_over_splits.": "rulings.task[].stable_only.mitigations.split_half.",
        "canonical_split.": "rulings.task[].stable_only.mitigations.split_half.",
        "observed.": "rulings.task[].stable_only.mitigations.selection_null.",
        "null.": "rulings.task[].stable_only.mitigations.selection_null.",
    }
    for path in doc_paths:
        for short, prefix in prefixes.items():
            if path.startswith(short):
                expanded.add(prefix + path)
    return expanded


def test_every_documented_path_exists_in_a_real_report() -> None:
    union = _report_union()
    documented = _contextualize(_doc_paths())
    identity_extras = {
        "ruling_id", "kind", "content_hash",
        "scope_key.task", "scope_key.model", "scope_key.model_a", "scope_key.model_b",
    }
    missing = []
    for path in sorted(_doc_paths()):
        full_candidates = [p for p in documented if p.endswith(path)]
        if not any(
            u == c or u.startswith(c + ".") or u.startswith(c + "[]")
            for c in full_candidates
            for u in union
        ) and path not in identity_extras and not any(
            path in u for u in union
        ):
            missing.append(path)
    assert not missing, f"docs/report.md names fields no real report emits: {missing}"


def test_every_emitted_path_is_documented() -> None:
    union = _report_union()
    documented = _contextualize(_doc_paths())
    identity_re = re.compile(
        r"(ruling_id|kind|content_hash|scope_key\.(task|model(_a|_b)?)|"
        r"model_a|model_b)$"
    )
    undocumented = []
    for path in sorted(union):
        if identity_re.search(path):
            continue  # identity fields are described in prose per section
        covered = any(
            path == d or path.startswith(d) or d.startswith(path)
            for d in documented
        )
        if not covered:
            undocumented.append(path)
    assert not undocumented, (
        "report fields missing from docs/report.md: " + ", ".join(undocumented[:20])
    )
