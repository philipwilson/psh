"""Guard: ``psh.protocols`` imports NOTHING from ``psh`` at runtime (Q1, §13).

The five service protocols (``psh/protocols/__init__.py``) exist to invert a
dependency: a consumer depends on a narrow protocol instead of the whole
``Shell``. That inversion is only real if the direction is ONE-WAY —
implementations may import a protocol, but a protocol may NEVER import an
implementation. If ``psh.protocols`` imported, say, ``psh.core.state`` at import
time, it would drag the state layer up into every consumer and re-entangle
exactly what the protocols separate.

This guard AST-builds each protocol module's MODULE-LEVEL import set (imports
that actually execute at import time — ``if TYPE_CHECKING:`` blocks and
function-body imports are excluded, they are not runtime edges) and asserts it
contains NO ``psh.*`` target. Producer/value types the protocols name in
annotations are imported under ``TYPE_CHECKING`` only (PEP 563 strings), which is
allowed. It is a sibling of the r19 import-layering guard
(``test_import_layering.py``); the counting logic is re-derived here so the two
guards stay independent. The ``test_guard_*`` self-tests prove the detector
flags a runtime implementation import and ignores a TYPE_CHECKING one, so the
guard cannot rot into a no-op.
"""

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
PROTOCOLS_DIR = ROOT / "psh" / "protocols"


def _is_type_checking_test(test):
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return True
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def runtime_psh_imports(src: str, module: str) -> set:
    """Return the set of ``psh.*`` modules imported at MODULE level and at
    RUNTIME (outside ``if TYPE_CHECKING:`` and outside any function body)."""
    tree = ast.parse(src)
    found: set = set()

    # ``module`` is a dotted name like "psh.protocols"; a package __init__
    # anchors relative imports at itself.
    pkg_parts = module.split(".")

    def resolve_relative(node) -> str:
        parts = list(pkg_parts)
        up = node.level - 1
        if up > 0:
            parts = parts[:-up] if up <= len(parts) else []
        target = ".".join(parts)
        if node.module:
            target = f"{target}.{node.module}" if target else node.module
        return target

    class V(ast.NodeVisitor):
        def __init__(self):
            self.depth = 0   # >0 inside a function body (deferred import)
            self.tc = 0      # >0 inside `if TYPE_CHECKING:` (not runtime)

        def visit_FunctionDef(self, node):
            self.depth += 1
            self.generic_visit(node)
            self.depth -= 1

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_If(self, node):
            if _is_type_checking_test(node.test):
                self.tc += 1
                for s in node.body:
                    self.visit(s)
                self.tc -= 1
                for s in node.orelse:
                    self.visit(s)
            else:
                self.generic_visit(node)

        def _record(self, name):
            if name and (name == "psh" or name.startswith("psh.")):
                if self.depth == 0 and self.tc == 0:
                    found.add(name)

        def visit_Import(self, node):
            for a in node.names:
                self._record(a.name)

        def visit_ImportFrom(self, node):
            if node.level and node.level > 0:
                self._record(resolve_relative(node))
            else:
                self._record(node.module)

    V().visit(tree)
    return found


def _protocol_module_name(path: pathlib.Path) -> str:
    rel = path.relative_to(ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _protocol_files():
    return sorted(p for p in PROTOCOLS_DIR.rglob("*.py")
                  if "__pycache__" not in p.parts)


# --- The invariant ----------------------------------------------------------

def test_protocols_package_exists():
    assert PROTOCOLS_DIR.is_dir(), "psh/protocols/ package missing"
    assert _protocol_files(), "no protocol modules found under psh/protocols/"


def test_protocol_modules_have_no_runtime_impl_imports():
    offenders = {}
    for path in _protocol_files():
        module = _protocol_module_name(path)
        imports = runtime_psh_imports(path.read_text(), module)
        if imports:
            offenders[module] = sorted(imports)
    assert not offenders, (
        "A protocol module imports an implementation at RUNTIME — protocols "
        "must depend on NOTHING in psh (implementations may import protocols, "
        "never the reverse). Move the import under `if TYPE_CHECKING:` (it is "
        f"only needed in an annotation): {offenders}"
    )


def test_protocols_package_exports_five():
    import psh.protocols as p

    assert set(p.__all__) == {
        "VariableAccess", "ExpansionContext", "IOContext",
        "JobRuntime", "LocaleContext",
    }
    for name in p.__all__:
        assert hasattr(p, name), f"psh.protocols does not export {name}"


# --- Detector self-tests (so the guard cannot silently pass) ----------------

_SYNTH_RUNTIME_IMPORT = (
    "from __future__ import annotations\n"
    "from typing import Protocol\n"
    "from ..core.state import ShellState\n"   # RUNTIME impl import — illegal
    "class Bad(Protocol):\n"
    "    def f(self, s: ShellState) -> None: ...\n"
)

_SYNTH_TYPE_CHECKING_IMPORT = (
    "from __future__ import annotations\n"
    "from typing import TYPE_CHECKING, Protocol\n"
    "if TYPE_CHECKING:\n"
    "    from ..core.state import ShellState\n"   # annotation only — legal
    "class Ok(Protocol):\n"
    "    def f(self, s: 'ShellState') -> None: ...\n"
)


def test_guard_flags_runtime_impl_import():
    imports = runtime_psh_imports(_SYNTH_RUNTIME_IMPORT, "psh.protocols")
    assert "psh.core.state" in imports


def test_guard_ignores_type_checking_import():
    imports = runtime_psh_imports(_SYNTH_TYPE_CHECKING_IMPORT, "psh.protocols")
    assert imports == set()
