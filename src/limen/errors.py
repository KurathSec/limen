"""Exception taxonomy.

Every refusal limen issues is one of these, and every message names the fix.
"""

from __future__ import annotations


class LimenError(Exception):
    """Base class for every error limen raises deliberately."""


class TableError(LimenError):
    """The long verdict table violates an invariant (duplicate key, non-binary verdict,
    partially present optional fields, nothing left after k filtering)."""


class ReaderError(LimenError):
    """An input file could not be read into a verdict table (unknown format, sniff
    ambiguity, missing column, repeats too small)."""


class AdapterError(LimenError):
    """The Spaghetti-Architect adapter refused or failed (missing checkout, poisoned
    environment, non-binary regrade, unsupported task)."""


class SpecError(LimenError):
    """A spec ruling was cited that does not exist or is superseded."""


class ReportError(LimenError):
    """A ruling document could not be assembled or fails its own schema."""


class GateError(LimenError):
    """The gate could not evaluate a report (unreadable, wrong schema, missing pair)."""
