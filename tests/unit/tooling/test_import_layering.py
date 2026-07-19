"""Meta-guard: the psh import graph obeys its layering rules (P4, reappraisal #19).

Historically the layering of ``psh`` was folklore: "utils is a leaf", "core is
near-leaf", "there are no runtime import cycles" — true by habit, enforced by
nothing. P4 converted that folklore into this guard. It AST-builds the
MODULE-LEVEL import graph (no imports executed) and asserts three invariants:

(a) **No package-level runtime cycles.** Collapsing modules to their depth-2
    package (``psh.executor``, ``psh.expansion`, ...), the runtime import graph
    has zero cycles. "Runtime" means module-level imports that actually execute
    at import time — imports under ``if TYPE_CHECKING:`` and imports inside a
    function body are excluded (they are not import-time edges). The allowlist
    is EMPTY: P4 items 1-2 removed the two real cycles
    (``builtins<->executor`` via the job vocabulary, ``core->utils->lexer`` via
    ``TokenFormatter``).

(b) **Leaf rules.** ``psh.utils`` imports NOTHING from ``psh`` at module level
    (a true leaf). ``psh.core`` is near-leaf: its only module-level ``psh``
    imports are into the packages in ``CORE_MODULE_IMPORT_ALLOWLIST``
    (``ast_nodes``/``utils``/``version`` — value types, escape helpers, and the
    version string). Adding a ``core -> executor`` (etc.) module-level import
    would re-entangle the state layer with the machinery above it.

(c) **Function-level import ratchet.** Deferred (function-body) ``psh`` imports
    are the escape hatch for the genuinely-forced cycles (see the
    ``# cycle-break:`` comments). Each is a small readability cost, so their
    per-file count is capped at the post-P4 value and may only go DOWN. Lowering
    a cap is free; raising one (a new lazy import) forces an explicit, reviewed
    edit here — where the reviewer asks "is this really cycle-forced, or should
    it be hoisted?"

The counting/graph logic is guarded by its own ``test_guard_*`` self-tests
below (synthetic offender sources must be flagged), so the guard cannot rot into
a no-op.
"""

import ast
import pathlib
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[3]
PSH = ROOT / "psh"

# --- Layering rules (the documented invariants) -----------------------------

# Package-level runtime cycles that are tolerated. EMPTY by design after P4.
PACKAGE_CYCLE_ALLOWLIST: set = set()

# The ONLY psh packages psh.core may import at module level (near-leaf rule).
CORE_MODULE_IMPORT_ALLOWLIST = {"psh.ast_nodes", "psh.utils", "psh.version"}


# --- AST import-graph builder (no psh imports executed) ---------------------

def _is_psh(name):
    return name is not None and (name == "psh" or name.startswith("psh."))


def _is_type_checking_test(test):
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return True
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def _resolve_relative(cur_mod, node, is_package):
    """Resolve a relative ``from . import x`` to an absolute ``psh.*`` module."""
    parts = cur_mod.split(".")
    # a package __init__ anchors level-1 at itself; a plain module at its parent
    pkg_parts = list(parts) if is_package else parts[:-1]
    up = node.level - 1
    if up > 0:
        pkg_parts = pkg_parts[:-up] if up <= len(pkg_parts) else []
    target = ".".join(pkg_parts)
    if node.module:
        target = target + "." + node.module if target else node.module
    return target


def analyze_source(src, module, is_package):
    """Return (runtime_module_imports, func_import_count) for one module's source.

    ``runtime_module_imports`` is the set of ``psh.*`` targets imported at MODULE
    level, excluding ``if TYPE_CHECKING:`` blocks (not runtime).
    ``func_import_count`` counts deferred ``psh.*`` imports inside function bodies.
    """
    tree = ast.parse(src)
    runtime = set()
    func_count = 0

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

        def _record(self, targets):
            nonlocal func_count
            for t in targets:
                if not _is_psh(t):
                    continue
                if self.depth > 0:
                    func_count += 1
                elif self.tc == 0:
                    runtime.add(t)

        def visit_Import(self, node):
            self._record([a.name for a in node.names])

        def visit_ImportFrom(self, node):
            if node.level and node.level > 0:
                tgt = _resolve_relative(module, node, is_package)
            else:
                tgt = node.module
            self._record([tgt])

    V().visit(tree)
    return runtime, func_count


def _module_name(path):
    rel = path.relative_to(ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _iter_modules():
    for path in sorted(PSH.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path, _module_name(path), path.name == "__init__.py"


def build_graph():
    """Return (module_runtime_edges, func_counts) over the live psh tree."""
    edges = {}
    func_counts = {}
    for path, module, is_pkg in _iter_modules():
        runtime, fcount = analyze_source(path.read_text(), module, is_pkg)
        edges[module] = runtime
        func_counts[module] = fcount
    return edges, func_counts


def _top_package(mod, depth=2):
    return ".".join(mod.split(".")[:depth])


def package_edges(module_edges):
    """Collapse module edges to depth-2 package edges (drop intra-package)."""
    pkg = defaultdict(set)
    for src, dsts in module_edges.items():
        ps = _top_package(src)
        for d in dsts:
            pd = _top_package(d)
            if pd != ps:
                pkg[ps].add(pd)
    return pkg


def find_cycles(pkg_edges):
    """Tarjan SCCs; return the list of cyclic package groups (frozensets)."""
    index, low, onstack, stack, counter, sccs = {}, {}, {}, [], [0], []

    def strong(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        onstack[v] = True
        for w in pkg_edges.get(v, ()):
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif onstack.get(w):
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                onstack[w] = False
                comp.append(w)
                if w == v:
                    break
            sccs.append(comp)

    nodes = set(pkg_edges) | {d for ds in pkg_edges.values() for d in ds}
    for v in nodes:
        if v not in index:
            strong(v)
    cycles = []
    for comp in sccs:
        if len(comp) > 1:
            cycles.append(frozenset(comp))
        elif comp[0] in pkg_edges.get(comp[0], set()):
            cycles.append(frozenset(comp))
    return cycles


# --- Function-level import ratchet baseline (post-P4; direction: DOWN only) --
#
# Per-module cap on deferred (function-body) psh imports. A module absent here
# must have ZERO. To ADD a lazy import you must justify it as cycle-forced (add
# a `# cycle-break:` comment) AND bump its cap here — a visible, reviewed edit.
# To hoist one, LOWER its cap. Regenerate with:
#     python tests/unit/tooling/test_import_layering.py
FUNC_IMPORT_CAPS = {
    'psh.__main__': 3,
    'psh.builtins.command_builtin': 6,
    'psh.builtins.core': 2,
    'psh.builtins.declaration_engine': 2,
    'psh.builtins.declare_format': 1,
    'psh.builtins.env_command': 1,
    'psh.builtins.environment': 5,
    'psh.builtins.function_support': 7,
    'psh.builtins.hash_builtin': 1,
    'psh.builtins.let_builtin': 1,
    'psh.builtins.parse_tree': 4,
    'psh.builtins.print_builtin': 1,
    'psh.builtins.shell_state': 4,
    'psh.builtins.source_command': 2,
    'psh.builtins.type_builtin': 3,
    'psh.core.assignment_utils': 2,
    'psh.core.locale_service': 5,
    'psh.core.scope': 2,
    'psh.core.state': 3,
    'psh.core.trap_manager': 1,
    'psh.core.variable_store': 2,
    'psh.core.variables': 1,
    'psh.executor.child_policy': 1,
    'psh.executor.control_flow': 6,
    'psh.executor.core': 8,
    'psh.executor.pipeline': 4,
    'psh.executor.process_launcher': 1,
    'psh.executor.strategies': 3,
    'psh.executor.subshell': 6,
    'psh.expansion.command_sub': 2,
    'psh.expansion.extglob': 4,
    'psh.expansion.glob': 4,
    'psh.expansion.manager': 5,
    'psh.expansion.operands': 3,
    'psh.expansion.operators': 1,
    'psh.expansion.parameter_expansion': 12,
    'psh.expansion.pattern': 2,
    # cycle-break: the W2 subscript authority re-lexes raw subscript text via
    # the parser word-builder (parser.word_builder imports expansion at module
    # level, so the reverse edge must stay function-level). arrays.py's old
    # deferred arithmetic import (cap 1) retired with _eval_array_index's body.
    'psh.expansion.subscript': 1,
    'psh.expansion.word_expander': 2,
    'psh.interactive.base': 4,
    'psh.interactive.multiline_handler': 1,
    'psh.interactive.prompt': 2,
    'psh.interactive.rc_loader': 1,
    'psh.io_redirect.file_redirect': 2,
    'psh.io_redirect.process_sub': 4,
    'psh.lexer': 2,
    'psh.lexer.cmdsub_scanner': 2,
    'psh.lexer.expansion_parser': 1,
    'psh.lexer.heredoc_collector': 1,
    'psh.lexer.heredoc_lexer': 1,
    'psh.lexer.modular_lexer': 6,
    'psh.lexer.pure_helpers': 3,
    'psh.lexer.recognizers.process_sub': 1,
    'psh.lexer.recognizers.word_scanners': 4,
    'psh.parser': 2,
    'psh.parser.array_flat_text': 1,
    # cycle-break (campaign S4): parse_outcome catches ParseError, defined in
    # recursive_descent.helpers; importing it eagerly re-enters this module via
    # recursive_descent/__init__ -> recursive_descent.parser -> parse_outcome.
    'psh.parser.parse_outcome': 1,
    'psh.parser.recursive_descent.parsers.arrays': 1,
    'psh.parser.recursive_descent.support.nested_parse': 2,
    'psh.parser.recursive_descent.support.utils': 1,
    'psh.parser.recursive_descent.support.word_builder': 1,
    'psh.scripting.base': 3,
    'psh.scripting.command_accumulator': 2,
    'psh.scripting.input_preprocessing': 1,
    'psh.scripting.input_sources': 1,
    'psh.scripting.lex_parse': 1,
    'psh.scripting.source_processor': 6,
    'psh.scripting.visitor_modes': 9,
    'psh.shell': 5,
    'psh.utils.ast_debug': 6,
    # 3rd deferred import (S2): the ANSI-C escape decoder for $'...' heredoc
    # delimiters — utils.heredoc_detection is module-level-imported by lexer
    # modules, so importing psh.lexer back at module level is a real cycle.
    'psh.utils.heredoc_detection': 3,
    'psh.visitor.enhanced_validator_visitor': 1,
}


# --- The invariants ---------------------------------------------------------

def test_no_package_level_runtime_cycles():
    edges, _ = build_graph()
    cycles = [c for c in find_cycles(package_edges(edges))
              if c not in PACKAGE_CYCLE_ALLOWLIST]
    assert not cycles, (
        "New package-level runtime import cycle(s) detected — a module-level "
        "import created a back-edge between packages. Make one direction a "
        "deferred (function-body) import with a `# cycle-break:` comment, or "
        "move the shared symbol to a lower layer:\n  "
        + "\n  ".join(" <-> ".join(sorted(c)) for c in cycles)
    )


def test_utils_is_a_runtime_leaf():
    edges, _ = build_graph()
    offenders = {m: sorted(d for d in dsts if not d.startswith("psh.utils"))
                 for m, dsts in edges.items()
                 if m.startswith("psh.utils")
                 and any(not d.startswith("psh.utils") for d in dsts)}
    assert not offenders, (
        "psh.utils must import NOTHING from psh at module level (it is the leaf "
        "layer). Move the dependency out, or make the import deferred:\n  "
        + "\n  ".join(f"{m} -> {d}" for m, d in offenders.items())
    )


def test_core_is_near_leaf():
    edges, _ = build_graph()
    offenders = {}
    for m, dsts in edges.items():
        if not m.startswith("psh.core"):
            continue
        bad = sorted(d for d in dsts
                     if not d.startswith("psh.core")
                     and _top_package(d) not in CORE_MODULE_IMPORT_ALLOWLIST)
        if bad:
            offenders[m] = bad
    assert not offenders, (
        "psh.core may only import these psh packages at module level: "
        f"{sorted(CORE_MODULE_IMPORT_ALLOWLIST)}. A new core->machinery edge "
        "re-entangles the state layer with what runs above it — defer it or "
        "invert the dependency:\n  "
        + "\n  ".join(f"{m} -> {d}" for m, d in offenders.items())
    )


def test_function_level_import_ratchet():
    _, func_counts = build_graph()
    violations = []
    for module, count in sorted(func_counts.items()):
        cap = FUNC_IMPORT_CAPS.get(module, 0)
        if count > cap:
            violations.append(f"{module}: {count} deferred psh import(s) > cap {cap}")
    assert not violations, (
        "Function-level (deferred) psh imports exceeded their ratchet cap. If "
        "the import is genuinely cycle-forced, add a `# cycle-break:` comment "
        "and raise its cap in FUNC_IMPORT_CAPS; otherwise HOIST it to module "
        "level. The ratchet only moves down:\n  " + "\n  ".join(violations)
    )


# --- Guard-the-guard: synthetic offenders must be flagged -------------------

def test_guard_detects_synthetic_package_cycle():
    # psh.aaa.m imports psh.bbb; psh.bbb.m imports psh.aaa -> a package cycle.
    edges = {
        "psh.aaa.m": {"psh.bbb.thing"},
        "psh.bbb.m": {"psh.aaa.thing"},
    }
    cycles = find_cycles(package_edges(edges))
    assert any({"psh.aaa", "psh.bbb"} == set(c) for c in cycles), (
        "cycle detector failed to flag a synthetic 2-package cycle")


def test_guard_detects_utils_leaf_violation():
    runtime, _ = analyze_source(
        "from ..executor.job_control import JobState\n", "psh.utils.bad", False)
    assert "psh.executor.job_control" in runtime, (
        "module-level import classifier missed a utils->psh edge")


def test_guard_ignores_type_checking_and_defers_function_imports():
    src = (
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from ..shell import Shell\n"        # type-only: NOT runtime
        "def f():\n"
        "    from ..core import ExpansionError\n"  # deferred: counts as func import
    )
    runtime, func_count = analyze_source(src, "psh.executor.x", False)
    assert runtime == set(), "TYPE_CHECKING import leaked into runtime edges"
    assert func_count == 1, "function-body psh import was not counted"


def test_guard_detects_ratchet_violation():
    # A module with two deferred imports must exceed a cap of 1.
    src = (
        "def f():\n"
        "    from ..core import A\n"
        "def g():\n"
        "    from ..core import B\n"
    )
    _, func_count = analyze_source(src, "psh.executor.x", False)
    assert func_count == 2 and func_count > 1, (
        "ratchet counter failed to count deferred imports")


if __name__ == "__main__":
    # Regenerate the FUNC_IMPORT_CAPS baseline from the live tree.
    _, counts = build_graph()
    nonzero = {m: c for m, c in sorted(counts.items()) if c > 0}
    print("FUNC_IMPORT_CAPS = {")
    for m, c in nonzero.items():
        print(f"    {m!r}: {c},")
    print("}")
    print(f"# total deferred psh imports: {sum(nonzero.values())} across {len(nonzero)} modules")
