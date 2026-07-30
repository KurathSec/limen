"""inspect_ai .eval reader: per-epoch draws, cross-run stacking, refusals.

The fixtures under tests/data/inspect/ were produced by a real inspect_ai run
(mockllm, offline) with planted verdict patterns, so the parsing is pinned to
the actual .eval format: run 1 has 4 epochs (q1 misses epoch 3, q2 clean, q3
always wrong), run 2 has 2 epochs (q1 clean, q2 misses epoch 2, q3 wrong).
The zip entries were recompressed to deflate so every supported Python can
read them; tests/data/inspect_zstd/ keeps an untouched original whose entries
are Zstandard-compressed (inspect on Python 3.14+ writes those), which only
Python >= 3.14 can decompress.
"""

import sys
from pathlib import Path

import pytest

from limen.errors import ReaderError
from limen.readers import load
from limen.readers.base import ReaderOptions
from limen.readers.inspect import InspectReader, _verdict_from

FIXTURES = Path(__file__).parent / "data" / "inspect"
ZSTD_FIXTURES = Path(__file__).parent / "data" / "inspect_zstd"
TASK = "fixture_task"
MODEL = "mockllm/model"


def test_epochs_and_runs_stack_into_draws() -> None:
    archive = load(FIXTURES)
    assert archive.models == (MODEL,)
    assert archive.aligned_items(TASK) == ("q1", "q2", "q3")
    q1 = archive.cell(MODEL, TASK, "q1")
    assert q1.k == 6  # 4 epochs + 2 epochs across two runs
    assert q1.verdicts == (1, 1, 0, 1, 1, 1)  # run-1 epoch 3 planted miss
    q2 = archive.cell(MODEL, TASK, "q2")
    assert q2.verdicts == (1, 1, 1, 1, 1, 0)  # run-2 epoch 2 planted miss
    q3 = archive.cell(MODEL, TASK, "q3")
    assert q3.verdicts == (0, 0, 0, 0, 0, 0)


def test_real_timestamps_feed_the_drift_guard() -> None:
    archive = load(FIXTURES)
    cell = archive.cell(MODEL, TASK, "q1")
    assert cell.collected_at is not None
    assert all(ts for ts in cell.collected_at)
    assert cell.raw_sha256 is not None
    # differing completions hash differently; identical ones identically
    assert len(set(cell.raw_sha256)) == 2  # "A" and "B"


def test_single_file_reads_alone() -> None:
    single = sorted(FIXTURES.glob("*.eval"))[0]
    archive = load(single)
    assert archive.cell(MODEL, TASK, "q1").k == 4


def test_sniff_claims_eval_files_and_dirs() -> None:
    reader = InspectReader()
    assert reader.sniff(FIXTURES)
    assert reader.sniff(sorted(FIXTURES.glob("*.eval"))[0])
    assert not reader.sniff(FIXTURES / "nope.eval")


def test_model_name_override() -> None:
    archive = load(FIXTURES, options=ReaderOptions(model_name="renamed"))
    assert archive.models == ("renamed",)


def test_unknown_scorer_named_with_candidates() -> None:
    with pytest.raises(ReaderError, match="no scorer 'nope'.*exact"):
        load(FIXTURES, options=ReaderOptions(metric="nope"))


def test_non_binary_values_refused() -> None:
    assert _verdict_from("C", "s", "q", Path("x.eval")) == 1
    assert _verdict_from("I", "s", "q", Path("x.eval")) == 0
    assert _verdict_from(1.0, "s", "q", Path("x.eval")) == 1
    for bad in ("P", "N", 0.5):
        with pytest.raises(ReaderError, match="never thresholds"):
            _verdict_from(bad, "s", "q", Path("x.eval"))


def test_not_a_zip_refused(tmp_path: Path) -> None:
    fake = tmp_path / "fake.eval"
    fake.write_bytes(b"not a zip")
    with pytest.raises(ReaderError, match="no reader recognizes"):
        load(fake)
    with pytest.raises(ReaderError, match="not a valid .eval"):
        InspectReader().read(fake, ReaderOptions())


@pytest.mark.skipif(sys.version_info < (3, 14), reason="zstd zip needs Python >= 3.14")
def test_zstd_compressed_eval_reads_on_supported_python() -> None:
    archive = load(ZSTD_FIXTURES)
    assert archive.cell(MODEL, TASK, "q1").k == 2


@pytest.mark.skipif(sys.version_info >= (3, 14), reason="refusal path only below 3.14")
def test_zstd_compressed_eval_refused_with_fix_named() -> None:
    with pytest.raises(ReaderError, match="Zstandard.*3.14"):
        load(ZSTD_FIXTURES)
