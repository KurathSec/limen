"""Reader registry: enumerated, not globbed.

limen reads the generic long CSV, lm-evaluation-harness ``--log_samples``
trees, and inspect_ai ``.eval`` logs at the per-epoch layer. Deliberately
absent, stated rather than silent (spec ruling LMN-CORE-007): HELM and
Parquet. Each is one new module and one tuple entry when it earns its cost.
"""

from __future__ import annotations

from pathlib import Path

from ..errors import ReaderError
from ..model import Archive, VerdictRow
from .base import Reader, ReaderOptions
from .inspect import InspectReader
from .lmeval import LmEvalReader
from .longcsv import LongCsvReader

READERS: tuple[Reader, ...] = (LongCsvReader(), LmEvalReader(), InspectReader())


def _resolve(path: Path, format: str | None) -> Reader:
    if format is not None:
        for reader in READERS:
            if reader.name == format:
                return reader
        raise ReaderError(
            f"unknown format {format!r}; available: {[r.name for r in READERS]}"
        )
    claims = [r for r in READERS if r.sniff(path)]
    if len(claims) == 1:
        return claims[0]
    if not claims:
        raise ReaderError(
            f"{path}: no reader recognizes this input; long-csv wants a .csv/.csv.gz with "
            "columns model,task,item_id,draw_id,verdict; lm-eval wants samples_*.jsonl "
            "from --log_samples; inspect wants .eval zip logs; pass --format to override"
        )
    raise ReaderError(
        f"{path}: ambiguous input, claimed by {[r.name for r in claims]}; pass --format"
    )


def load(
    path: Path | str,
    *,
    format: str | None = None,
    options: ReaderOptions | None = None,
) -> Archive:
    """Load an input into an Archive, sniffing the format unless one is named."""
    p = Path(path)
    if not p.exists():
        raise ReaderError(f"{p}: no such file or directory")
    return _resolve(p, format).read(p, options or ReaderOptions())


def load_rows(
    path: Path | str,
    *,
    format: str | None = None,
    options: ReaderOptions | None = None,
) -> list[VerdictRow]:
    """Raw rows before min-k filtering — the merge-safe entry for multi-input
    reports: draws of one cell split across inputs must stack BEFORE exclusion."""
    p = Path(path)
    if not p.exists():
        raise ReaderError(f"{p}: no such file or directory")
    return _resolve(p, format).rows(p, options or ReaderOptions())
