"""The golden gate: committed calibration tables regenerate their committed rulings
byte-for-byte, with no Spaghetti-Architect checkout needed.

Teeth against self-disarming: the committed reports must exist for every
committed table, must already be canonical bytes, must carry the live spec
version, and the regenerated document must match exactly.
"""

import json
from pathlib import Path

import pytest

from limen.canonical import canonical_json
from limen.readers import load
from limen.report import ReportOptions, build_report
from limen.spec import spec_version

CALIBRATION = Path(__file__).resolve().parent.parent / "calibration" / "spaghetti"
TABLES = sorted(CALIBRATION.glob("tables/*.verdicts.csv.gz"))
RULINGS_VERSION = "cal1"
REPORT_OPTIONS = ReportOptions(
    replicates=1000, max_splits=256, assume_index_is_collection_order=True
)

pytestmark = pytest.mark.skipif(
    not TABLES, reason="calibration corpus not yet committed"
)


def _golden_path(table: Path) -> Path:
    name = table.name.replace(".verdicts.csv.gz", ".report.json")
    return CALIBRATION / "rulings" / RULINGS_VERSION / name


@pytest.mark.parametrize("table", TABLES, ids=lambda p: p.stem.split(".")[0])
def test_golden_ruling_regenerates_byte_identically(table: Path) -> None:
    golden = _golden_path(table)
    assert golden.is_file(), (
        f"{golden} missing: every committed table needs its committed ruling "
        "(generate with tools/update_calibration.py)"
    )
    committed_text = golden.read_text(encoding="utf-8")
    committed = json.loads(committed_text)
    assert canonical_json(committed) == committed_text, "committed golden is not canonical bytes"
    assert committed["spec_version"] == spec_version(), (
        "spec version moved without regenerating the calibration rulings"
    )
    archive = load(table)
    regenerated = build_report(
        archive, rulings_version=RULINGS_VERSION, options=REPORT_OPTIONS
    )
    assert canonical_json(regenerated) == committed_text, (
        f"regeneration of {table.name} diverged from the committed golden; a changed "
        "meaning requires a rulings-spec bump via tools/update_calibration.py"
    )


def test_manifest_pins_every_table() -> None:
    manifest_path = CALIBRATION / "MANIFEST.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    from limen.canonical import sha256_file

    for table in TABLES:
        entry = manifest["tables"].get(table.name)
        assert entry is not None, f"{table.name} missing from MANIFEST.json"
        assert entry["sha256"] == sha256_file(table), (
            f"{table.name} does not match its manifest hash; regenerate the corpus "
            "deliberately, never edit it in place"
        )
