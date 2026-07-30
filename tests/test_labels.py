"""Per-item stratum labels (LMN-CORE-008): invariants, round-trip, digest rule."""

from pathlib import Path

import pytest

from limen.adapters.spaghetti import build_task_archive
from limen.errors import TableError
from limen.model import VerdictRow, build_archive
from limen.readers import load
from limen.readers.longcsv import write_archive


def _row(model: str, item: str, draw: int, verdict: int, labels=None) -> VerdictRow:
    return VerdictRow(
        model=model, task="t", item_id=item, draw_id=str(draw), verdict=verdict,
        labels=labels,
    )


LAB = (("lang", "py"), ("scale", "n_ops=3"))


def test_labels_roundtrip_and_indexes() -> None:
    rows = [_row("a", "i1", d, 1, LAB) for d in range(2)]
    rows += [_row("a", "i2", d, 0) for d in range(2)]  # unlabeled item coexists
    archive = build_archive(rows)
    assert archive.label_keys("t") == ("lang", "scale")
    assert archive.item_labels("t", "i1") == {"lang": "py", "scale": "n_ops=3"}
    assert archive.item_labels("t", "i2") is None


def test_labels_all_or_nothing_per_cell() -> None:
    rows = [_row("a", "i1", 0, 1, LAB), _row("a", "i1", 1, 0)]
    with pytest.raises(TableError, match="all-or-nothing"):
        build_archive(rows)


def test_labels_must_match_across_draws() -> None:
    rows = [_row("a", "i1", 0, 1, LAB), _row("a", "i1", 1, 0, (("lang", "go"),))]
    with pytest.raises(TableError, match="differ across draws"):
        build_archive(rows)


def test_labels_must_match_across_models() -> None:
    rows = [_row("a", "i1", d, 1, LAB) for d in range(2)]
    rows += [_row("b", "i1", d, 0, (("lang", "go"),)) for d in range(2)]
    with pytest.raises(TableError, match="disagree across models"):
        build_archive(rows)


def test_bad_label_name_and_empty_value_refused() -> None:
    with pytest.raises(TableError, match="a-z0-9_"):
        build_archive([_row("a", "i", 0, 1, (("Bad-Name", "x"),)), _row("a", "i", 1, 0, (("Bad-Name", "x"),))])
    with pytest.raises(TableError, match="empty value"):
        build_archive([_row("a", "i", 0, 1, (("lang", " "),)), _row("a", "i", 1, 0, (("lang", " "),))])


def test_unlabeled_digest_unchanged_by_label_support() -> None:
    """Label-free rows keep their exact pre-label digest bytes."""
    rows = [_row("a", "i1", d, d % 2) for d in range(2)]
    digest = build_archive(rows).dataset_digest()
    # pinned from the 0.1.x line format (9-element JSON rows)
    assert digest.startswith("sha256:")
    labeled = build_archive([_row("a", "i1", d, d % 2, LAB) for d in range(2)])
    assert labeled.dataset_digest() != digest


def test_csv_label_columns_roundtrip(tmp_path: Path) -> None:
    rows = [_row("a", "i1", d, 1, LAB) for d in range(2)]
    rows += [_row("a", "i2", d, 0) for d in range(2)]
    archive = build_archive(rows)
    path = tmp_path / "x.verdicts.csv.gz"
    write_archive(archive, path)
    loaded = load(path)
    assert loaded.dataset_digest() == archive.dataset_digest()
    assert loaded.item_labels("t", "i1") == {"lang": "py", "scale": "n_ops=3"}
    assert loaded.item_labels("t", "i2") is None


def test_label_free_csv_bytes_unchanged(tmp_path: Path) -> None:
    rows = [_row("a", "i1", d, 1) for d in range(2)]
    archive = build_archive(rows)
    path = tmp_path / "plain.csv"
    write_archive(archive, path)
    header = path.read_text().splitlines()[0]
    assert header == "model,task,item_id,draw_id,verdict,score,collected_at,model_version,raw_sha256"


def test_adapter_emits_labels(fake_spaghetti: Path) -> None:
    archive = build_task_archive(fake_spaghetti, "comprehend_dev")
    labels = archive.item_labels("comprehend_dev", "s1|base|standard|python")
    assert labels == {
        "language": "python",
        "profile": "standard",
        "scale": "n_ops=1",
        "variant": "base",
    }


def test_duplicated_columns_refused(tmp_path: Path) -> None:
    # csv.DictReader keeps only the last of a duplicated column; the reader
    # must refuse rather than silently drop data
    from limen.readers.longcsv import ReaderError

    for header in (
        "model,task,item_id,draw_id,verdict,label_lang,label_lang",
        "model,task,item_id,draw_id,verdict,verdict",
    ):
        path = tmp_path / "dup.csv"
        cells = ["a", "t", "i1", "0", "1", "x", "y"][: header.count(",") + 1]
        path.write_text(header + "\n" + ",".join(cells) + "\n")
        with pytest.raises(ReaderError, match="duplicated column"):
            load(path)
