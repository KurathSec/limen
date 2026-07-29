"""Reader protocol: every input format produces the same long verdict table."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..model import Archive, VerdictRow


@dataclass(frozen=True, slots=True)
class ReaderOptions:
    """Options a reader may consume; unknown-to-a-reader options are ignored by it."""

    min_k: int = 2
    metric: str | None = None  # lm-eval: which binary metric field is the verdict
    model_name: str | None = None  # lm-eval: override the model label


class Reader(Protocol):
    name: str

    def sniff(self, path: Path) -> bool:
        """Cheap read-only check whether this reader claims the path."""
        ...

    def read(self, path: Path, options: ReaderOptions) -> Archive:
        """Read the path into an Archive, or raise ReaderError with the fix named."""
        ...

    def rows(self, path: Path, options: ReaderOptions) -> list[VerdictRow]:
        """The raw rows before any min-k filtering — what multi-input merges need,
        so that draws of one cell split across files stack before exclusion."""
        ...
