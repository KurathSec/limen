"""Reader contract: long CSV round-trip and refusals; lm-eval grouping and refusals."""

import gzip
import json
from pathlib import Path

import pytest
from conftest import archive_from_grid

from limen.errors import ReaderError
from limen.readers import load
from limen.readers.base import ReaderOptions
from limen.readers.longcsv import write_archive


def test_longcsv_roundtrip(tmp_path: Path) -> None:
    archive = archive_from_grid(
        {"a": {"i1": [1, 0]}, "b": {"i1": [0, 1]}}, with_hashes=True, with_timestamps=True
    )
    path = tmp_path / "x.verdicts.csv.gz"
    write_archive(archive, path)
    loaded = load(path)
    assert loaded.dataset_digest() == archive.dataset_digest()


def test_longcsv_writer_deterministic(tmp_path: Path) -> None:
    archive = archive_from_grid({"a": {"i1": [1, 0]}})
    p1, p2 = tmp_path / "a.csv.gz", tmp_path / "b.csv.gz"
    write_archive(archive, p1)
    write_archive(archive, p2)
    assert p1.read_bytes() == p2.read_bytes()


def test_longcsv_missing_column(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("model,task,item_id,draw_id\na,t,i,0\n")
    with pytest.raises(ReaderError, match="missing required column"):
        load(path, format="long-csv")


def test_longcsv_unknown_column(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("model,task,item_id,draw_id,verdict,extra\na,t,i,0,1,x\n")
    with pytest.raises(ReaderError, match="unknown column"):
        load(path, format="long-csv")


def test_longcsv_never_thresholds(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("model,task,item_id,draw_id,verdict\na,t,i,0,0.7\n")
    with pytest.raises(ReaderError, match="never derives a verdict"):
        load(path, format="long-csv")


def test_unknown_input_lists_what_readers_want(tmp_path: Path) -> None:
    path = tmp_path / "mystery.txt"
    path.write_text("hello")
    with pytest.raises(ReaderError, match="no reader recognizes"):
        load(path)


def test_unknown_format_flag(tmp_path: Path) -> None:
    path = tmp_path / "x.csv"
    path.write_text("model,task,item_id,draw_id,verdict\na,t,i,0,1\na,t,i,1,0\n")
    with pytest.raises(ReaderError, match="unknown format"):
        load(path, format="parquet")


def _write_lmeval_tree(root: Path, model: str, task: str, runs: int, docs: int) -> None:
    model_dir = root / model
    model_dir.mkdir(parents=True, exist_ok=True)
    for run in range(runs):
        lines = []
        for doc in range(docs):
            lines.append(
                json.dumps(
                    {
                        "doc_id": doc,
                        "doc": {"q": "?"},
                        "target": "x",
                        "resps": [[f"resp-{doc}-{run}"]],
                        "filtered_resps": [f"resp-{doc}-{run}"],
                        "exact_match": 1.0 if (doc + run) % 2 == 0 else 0.0,
                    }
                )
            )
        (model_dir / f"samples_{task}_2026-01-0{run + 1}T00-00-00.000000.jsonl").write_text(
            "\n".join(lines) + "\n"
        )


def test_lmeval_two_runs_become_two_draws(tmp_path: Path) -> None:
    _write_lmeval_tree(tmp_path, "modelA", "gsm8k", runs=2, docs=3)
    archive = load(tmp_path)
    assert archive.models == ("modelA",)
    cell = archive.cell("modelA", "gsm8k", "doc0")
    assert cell.k == 2
    assert cell.collected_at is not None  # run timestamps carried
    assert cell.raw_sha256 is not None


def test_lmeval_single_run_refused_with_fix_named(tmp_path: Path) -> None:
    _write_lmeval_tree(tmp_path, "modelA", "gsm8k", runs=1, docs=3)
    with pytest.raises(Exception, match="k >= 2"):
        load(tmp_path)


def test_lmeval_multiple_binary_metrics_demand_choice(tmp_path: Path) -> None:
    model_dir = tmp_path / "m"
    model_dir.mkdir()
    line = json.dumps({"doc_id": 0, "exact_match": 1.0, "acc": 0.0, "resps": [["r"]]})
    for run in (1, 2):
        (model_dir / f"samples_t_2026-01-0{run}T00-00-00.000000.jsonl").write_text(line + "\n")
    with pytest.raises(ReaderError, match="multiple binary metric fields"):
        load(tmp_path)
    archive = load(tmp_path, options=ReaderOptions(metric="acc"))
    assert archive.cell("m", "t", "doc0").verdicts == (0, 0)


def test_lmeval_metric_resolved_per_task(tmp_path: Path) -> None:
    """Two tasks with different binary metric names must both read; --metric
    applies to the tasks that carry it, the rest auto-pick per task."""
    model_dir = tmp_path / "m"
    model_dir.mkdir()
    for run in (1, 2):
        (model_dir / f"samples_taskem_2026-01-0{run}T00-00-00.000000.jsonl").write_text(
            json.dumps({"doc_id": 0, "exact_match": 1.0, "resps": [["r"]]}) + "\n"
        )
        (model_dir / f"samples_taskacc_2026-01-0{run}T00-00-00.000000.jsonl").write_text(
            json.dumps({"doc_id": 0, "acc": 0.0, "resps": [["r"]]}) + "\n"
        )
    archive = load(tmp_path)
    assert archive.cell("m", "taskem", "doc0").verdicts == (1, 1)
    assert archive.cell("m", "taskacc", "doc0").verdicts == (0, 0)


def test_lmeval_requested_metric_missing_from_task_names_candidates(tmp_path: Path) -> None:
    model_dir = tmp_path / "m"
    model_dir.mkdir()
    for run in (1, 2):
        (model_dir / f"samples_t_2026-01-0{run}T00-00-00.000000.jsonl").write_text(
            json.dumps({"doc_id": 0, "acc": 1.0, "resps": [["r"]]}) + "\n"
        )
    with pytest.raises(ReaderError, match="no field 'exact_match'.*acc"):
        load(tmp_path, options=ReaderOptions(metric="exact_match"))


def test_lmeval_gz_csv_sniff_priority(tmp_path: Path) -> None:
    # a csv.gz with the right header must go to long-csv even inside a dir walk
    archive = archive_from_grid({"a": {"i1": [1, 0]}})
    path = tmp_path / "t.verdicts.csv.gz"
    write_archive(archive, path)
    with gzip.open(path, "rt") as f:
        assert f.readline().startswith("model,")
    assert load(path).models == ("a",)
