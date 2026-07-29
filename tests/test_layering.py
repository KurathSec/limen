"""The architectural gate: only the adapter may touch the foreign checkout."""

import ast
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "limen"
FOREIGN = {"bench"}
ALLOWED_FOREIGN_IMPORTER = SRC / "adapters" / "spaghetti.py"


def _imports(tree: ast.AST) -> list[tuple[str, bool]]:
    """(top-level module name, is_module_level) for every import in the tree."""
    found: list[tuple[str, bool]] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.depth = 0

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self.depth += 1
            self.generic_visit(node)
            self.depth -= 1

        visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

        def visit_Import(self, node: ast.Import) -> None:
            for alias in node.names:
                found.append((alias.name.split(".")[0], self.depth == 0))

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            if node.level == 0 and node.module:
                found.append((node.module.split(".")[0], self.depth == 0))

    Visitor().visit(tree)
    return found


def test_only_the_adapter_imports_the_checkout() -> None:
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for name, module_level in _imports(tree):
            if name in FOREIGN:
                assert path == ALLOWED_FOREIGN_IMPORTER, (
                    f"{path} imports foreign module {name!r}; only the adapter may"
                )
                assert not module_level, (
                    f"{path} imports {name!r} at module level; must be lazy"
                )


def test_import_limen_touches_no_foreign_module() -> None:
    code = (
        "import sys\n"
        "import limen\n"
        "bad = [n for n in sys.modules if n == 'bench' or n.startswith('bench.')]\n"
        "assert not bad, bad\n"
        "print('clean')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert "clean" in result.stdout


def test_adapter_has_no_write_calls_into_checkout() -> None:
    """The adapter is read-only: no open(..., 'w'), no shutil/os mutation calls."""
    tree = ast.parse(ALLOWED_FOREIGN_IMPORTER.read_text(encoding="utf-8"))
    banned_attrs = {"unlink", "rmtree", "rmdir", "makedirs", "write_text", "write_bytes"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in banned_attrs:
                raise AssertionError(f"adapter calls {func.attr}() — must stay read-only")
            if isinstance(func, ast.Name) and func.id == "open":
                modes = [
                    a.value
                    for a in node.args[1:2]
                    if isinstance(a, ast.Constant) and isinstance(a.value, str)
                ]
                assert not any("w" in m or "a" in m for m in modes), "adapter opens for write"
