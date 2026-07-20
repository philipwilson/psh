"""Shrink-only ratchet: full-``Shell`` consumers among the Q1 touched modules.

Campaign Q1 (§13) migrates a service-locator boundary — a component that took
the whole ``Shell`` and reached whatever subsystem it liked — to a narrow
protocol whenever its actual needs fit one. Some boundaries genuinely still need
the full ``Shell`` (they FORWARD it to something that needs the whole shell, or
they reach the trap/signal/executor machinery no protocol models). This ratchet
freezes THAT set: every function/method in a campaign-created ("touched") module
whose parameter is annotated as the full ``Shell`` is recorded here WITH a
one-line justification, and the recorded set may only SHRINK.

- A NEW full-``Shell`` consumer in a touched module (not in ``ALLOWLIST``) fails
  ``test_no_unrecorded_full_shell_consumers`` — you must either narrow it to a
  protocol or justify it here (a reviewed edit).
- A recorded consumer that no longer takes ``Shell`` (migrated to a protocol)
  fails ``test_ratchet_only_shrinks`` — remove its stale entry; the set shrank.

``ShellState`` parameters are deliberately NOT counted: taking ``ShellState`` is
already a narrowing away from ``Shell`` (``process_launcher`` /
``input_sources`` do this), and it is a value/state container, not a
service-locator into every subsystem. The ratchet's subject is the full
``Shell`` reach specifically.

The ``test_detector_*`` self-tests prove the AST detector flags a synthetic
``Shell``-typed parameter and ignores a protocol-typed one, so the ratchet
cannot rot into a no-op.
"""

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]


# The campaign-created modules (the Q1 "touched" inventory). Each is checked for
# functions/methods that still take the full ``Shell``.
TOUCHED_MODULES = [
    "psh/executor/foreground_session.py",
    "psh/executor/process_launcher.py",
    "psh/executor/command_resolution.py",
    "psh/executor/child_policy.py",
    "psh/expansion/subscript.py",
    "psh/core/variable_lookup.py",
    "psh/io_redirect/redirect_program.py",
    "psh/io_redirect/input_cursor.py",
    "psh/parser/session.py",
    "psh/parser/parse_inputs.py",
    "psh/parser/parse_outcome.py",
    "psh/interactive/history_result.py",
    "psh/scripting/input_sources.py",
    "psh/ast_nodes/syntax_templates.py",
]


# The frozen set of touched-module boundaries that legitimately still take the
# full ``Shell`` — (dotted-module, qualified-symbol) -> justification. MAY ONLY
# SHRINK. Each entry must forward the shell to a whole-shell need or reach a
# subsystem no protocol (VariableAccess/ExpansionContext/IOContext/JobRuntime/
# LocaleContext) models.
ALLOWLIST = {
    ("psh.executor.command_resolution", "resolve_command"):
        "forwards `shell` to ExecutionStrategy.can_execute(name, shell), which "
        "reads the function/builtin registries — a whole-shell dispatch need, "
        "not a protocol-shaped slice (it only reads shell.state.options itself)",
    ("psh.executor.child_policy", "run_background_shell_child"):
        "backgrounded compound-child runner: re-arms trap handlers via "
        "trap_manager + interactive_manager.signal_manager and runs the child "
        "body — whole-shell machinery, no protocol fit",
    ("psh.executor.child_policy", "run_child_body"):
        "shared child-Shell body runner: drives trap_manager, errexit/loop "
        "seeds and _current_executor — whole-shell machinery, no protocol fit",
    ("psh.executor.child_policy", "run_child_shell"):
        "substitution-child runner built on run_child_body: forks a child "
        "Shell (Shell.for_subshell) and reaches trap/signal/executor/streams",
    ("psh.expansion.subscript", "SubscriptEvaluator.__init__"):
        "forwards `shell` to evaluate_arithmetic(expr, shell) for indexed "
        "subscript evaluation; also consumes ExpansionContext + state "
        "diagnostics, but the arithmetic forward forces the full Shell",
}


def _module_dotted(rel_path: str) -> str:
    return rel_path[:-3].replace("/", ".")


def full_shell_consumers(src: str, module: str) -> set:
    """Return the qualified names of defs in ``src`` with a parameter annotated
    as the full ``Shell`` (bare ``Shell`` or the string forward-ref
    ``'Shell'`` — NOT ``ShellState`` and not any protocol name)."""
    tree = ast.parse(src)
    found: set = set()

    def is_shell_annotation(node) -> bool:
        if node is None:
            return False
        if isinstance(node, ast.Name):
            return node.id == "Shell"
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value.strip() == "Shell"
        return False

    def visit(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, prefix + [child.name])
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                a = child.args
                params = (list(a.posonlyargs) + list(a.args)
                          + list(a.kwonlyargs))
                if a.vararg:
                    params.append(a.vararg)
                if a.kwarg:
                    params.append(a.kwarg)
                if any(is_shell_annotation(p.annotation) for p in params):
                    found.add(".".join(prefix + [child.name]))
                # a nested function could also take Shell; keep descending
                visit(child, prefix + [child.name])

    visit(tree, [])
    return {(module, sym) for sym in found}


def _live_consumers() -> set:
    consumers: set = set()
    for rel in TOUCHED_MODULES:
        path = ROOT / rel
        assert path.exists(), f"touched module missing: {rel}"
        consumers |= full_shell_consumers(path.read_text(), _module_dotted(rel))
    return consumers


# --- The ratchet ------------------------------------------------------------

def test_touched_modules_all_exist():
    for rel in TOUCHED_MODULES:
        assert (ROOT / rel).exists(), f"touched module missing: {rel}"


def test_no_unrecorded_full_shell_consumers():
    live = _live_consumers()
    new = live - set(ALLOWLIST)
    assert not new, (
        "New full-`Shell` consumer(s) in a touched module. Narrow the "
        "parameter to a psh.protocols protocol whose surface covers its needs, "
        "or (if it genuinely needs the whole shell) add it to ALLOWLIST with a "
        f"justification: {sorted(new)}"
    )


def test_ratchet_only_shrinks():
    live = _live_consumers()
    stale = set(ALLOWLIST) - live
    assert not stale, (
        "ALLOWLIST entries that no longer take `Shell` (migrated away). The "
        "ratchet only shrinks — delete these stale entries: " f"{sorted(stale)}"
    )


def test_every_allowlist_entry_has_justification():
    for key, reason in ALLOWLIST.items():
        assert isinstance(reason, str) and len(reason.strip()) >= 20, (
            f"allowlist entry {key} needs a real justification")


def test_iocontext_migration_removed_input_cursor():
    """The Q1 IOContext migration narrowed InputCursorRegistry.cursor_for_fd
    from `Shell` to IOContext — it must NOT appear as a full-Shell consumer."""
    live = _live_consumers()
    assert ("psh.io_redirect.input_cursor",
            "InputCursorRegistry.cursor_for_fd") not in live


# --- Detector self-tests ----------------------------------------------------

def test_detector_flags_synthetic_offender():
    src = (
        "class Foo:\n"
        "    def bar(self, shell: 'Shell', fd: int) -> None: ...\n"
    )
    found = full_shell_consumers(src, "psh.fake")
    assert ("psh.fake", "Foo.bar") in found


def test_detector_ignores_protocol_and_state_params():
    src = (
        "class Foo:\n"
        "    def a(self, io: 'IOContext') -> None: ...\n"
        "    def b(self, state: 'ShellState') -> None: ...\n"
        "    def c(self, x: int) -> None: ...\n"
    )
    assert full_shell_consumers(src, "psh.fake") == set()
