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
    # single aligned item: variance_components UNAVAILABLE with reason
    solo = archive_from_grid({"a": {"solo": [1, 0]}, "b": {"solo": [0, 1]}})
    union |= _paths(build_report(solo, rulings_version="doc", options=ReportOptions(replicates=4)))
    # labeled archive with stratification: labels summary, strata, saturation rollup
    labeled_rows = []
    for j in range(4):
        for model, verdicts in (("a", [1, 0, 1, 1]), ("b", [0, 1, 0, 0])):
            for d, v in enumerate(verdicts):
                labeled_rows.append(
                    VerdictRow(
                        model=model, task="t", item_id=f"i{j}", draw_id=str(d),
                        verdict=v if j < 2 else (1 if model == "a" else 0),
                        labels=(("lang", "py" if j % 2 == 0 else "go"),),
                    )
                )
    labeled = build_archive(labeled_rows)
    union |= _paths(
        build_report(
            labeled,
            rulings_version="doc",
            options=ReportOptions(replicates=6, stratify_by=("lang",), stratum_floor=2),
        )
    )
    # near-tied pair with aligned flips: FALLS-INTO-NOISE and a NO_WITNESS block
    noisy = archive_from_grid(
        {
            "a": {"i1": [1, 0], "i2": [1, 0], "i3": [1, 1]},
            "b": {"i1": [0, 0], "i2": [0, 0], "i3": [1, 1]},
        }
    )
    union |= _paths(build_report(noisy, rulings_version="doc", options=ReportOptions(replicates=4)))
    return union


_BRACE = re.compile(r"^(.*)\{([^{}]+)\}(.*)$")
_ROOTS = (
    "limen_schema", "rulings_version", "spec_version", "dataset_digest",
    "content_hash", "options.", "n.", "scope.", "rulings.",
)
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_<>.,{}\[\]-]+$")
_H2_PREFIX = {
    "Envelope": "",
    "MT rulings": "rulings.mt[].",
    "PAIR rulings": "rulings.pair[].",
    "TASK rulings": "rulings.task[].",
}


def _expand_braces(token: str) -> list[str]:
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
    return candidates


def _doc_paths() -> set[str]:
    """Collect field paths with heading-aware context: '### `flakiness`' under
    '## MT rulings' prefixes that section's bare tokens with
    'rulings.mt[].flakiness.'."""
    out: set[str] = set()
    h2: str | None = None
    h3: str | None = None
    h4: str | None = None
    for line in DOC.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            title = line[3:].strip()
            h2 = next((p for name, p in _H2_PREFIX.items() if title.startswith(name)), None)
            h3 = h4 = None
            continue
        if line.startswith("### "):
            m = re.match(r"### `([A-Za-z0-9_.]+)`", line)
            h3 = (h2 + m.group(1) + ".") if (m and h2 is not None) else None
            h4 = None
            continue
        if line.startswith("#### "):
            m = re.match(r"#### `([A-Za-z0-9_.]+)`", line)
            h4 = (h3 + m.group(1) + ".") if (m and h3 is not None) else None
            continue
        prefix = h4 if h4 is not None else h3 if h3 is not None else h2
        # only the FIRST column of a table row names field paths; description
        # cells and prose backticks are commentary, not the contract
        if line.startswith("| "):
            first_cell = line.split(" | ")[0][2:]
        else:
            first_cell = ""
        for token in re.findall(r"`([^`]+)`", first_cell):
            if not _TOKEN_RE.match(token):
                continue
            for cand in _expand_braces(token):
                in_section = prefix is not None and prefix != ""
                if in_section and not cand.startswith("rulings."):
                    if re.match(r"^[A-Za-z0-9_<>-]", cand) and not cand.endswith("."):
                        out.add(prefix + cand)
                elif cand.startswith(_ROOTS) or cand in (
                    "limen_schema", "rulings_version", "spec_version",
                    "dataset_digest", "content_hash",
                ):
                    out.add(cand)
    return out


def test_every_documented_path_exists_in_a_real_report() -> None:
    union = _report_union()
    missing = []
    for path in sorted(_doc_paths()):
        if not any(
            u == path or u.startswith(path + ".") or u.startswith(path + "[]")
            or path in u
            for u in union
        ):
            missing.append(path)
    assert not missing, f"docs/report.md names fields no real report emits: {missing}"


#: bare container mentions in the envelope table must not blanket-cover every
#: leaf underneath them, or the completeness direction loses its teeth
_NON_COVERING = {"rulings.mt[]", "rulings.pair[]", "rulings.task[]", "rulings."}


def test_every_emitted_path_is_documented() -> None:
    union = _report_union()
    documented = _doc_paths() - _NON_COVERING
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
