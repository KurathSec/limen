"""limen: the same-configuration noise floor of an evaluation.

An analyzer over repeated identical evaluation runs: per-item verdict
flakiness, model-pair sign-stability rulings, the noise floor a claimed
improvement has to clear, and a CI gate. It issues no model calls and makes no
statement about which model is better — that boundary is the instrument.

This package never imports the Spaghetti-Architect adapter at import time; the
core stays free of foreign code (enforced by tests/test_layering.py).
"""

from ._version import __version__
from .gate import GateOptions, GateResult, evaluate_gate
from .model import Archive, Cell, VerdictRow, build_archive
from .readers import load
from .readers.base import ReaderOptions
from .report import ReportOptions, build_report
from .synth import PlantedConfig, PlantedTruth, generate

__all__ = [
    "Archive",
    "Cell",
    "GateOptions",
    "GateResult",
    "PlantedConfig",
    "PlantedTruth",
    "ReaderOptions",
    "ReportOptions",
    "VerdictRow",
    "__version__",
    "build_archive",
    "build_report",
    "evaluate_gate",
    "generate",
    "load",
]
