"""Shrink-only ratchet: full-``Shell`` consumers among the Q1 boundary modules.

Campaign Q1 (§13) migrates a service-locator boundary — a component that took
the whole ``Shell`` and reached whatever subsystem it liked — to a narrow
protocol whenever its actual needs fit one. Some boundaries genuinely still need
the full ``Shell`` (they FORWARD it to something that needs the whole shell, or
they reach the trap/signal/executor machinery no protocol models). This ratchet
freezes THAT set: every function/method in a boundary module whose parameter is
the full ``Shell`` is recorded here WITH a one-line justification, and the
recorded set may only SHRINK.

- A NEW full-``Shell`` consumer in a scanned module (not in ``ALLOWLIST``) fails
  ``test_no_unrecorded_full_shell_consumers`` — narrow it to a protocol or
  justify it here (a reviewed edit).
- A recorded consumer that no longer takes ``Shell`` (migrated to a protocol)
  fails ``test_ratchet_only_shrinks`` — remove its stale entry; the set shrank.

**Module scope — source of truth.** ``CREATED_MODULES`` is the set of files the
campaign ADDED, defined by (and verified against, when the tag is present, by
``test_created_modules_match_enumeration``):

    git log --diff-filter=A --pretty=format: --name-only v0.724.0..75ab5625 -- psh/

``TOUCHED_PREEXISTING`` adds the pre-campaign files the campaign MIGRATED or that
carry a recorded consumer, so the ratchet actually SEES them (an allowlist entry
in an unscanned file, or a future offender there, would otherwise be invisible).

**Detector.** A parameter is a full-``Shell`` consumer when its annotation
mentions ``Shell`` as an identifier — bare (``shell: Shell``), a string
forward-ref (``'Shell'``), OR wrapped/nested (``Optional['Shell']``,
``'Shell | None'``, ``Callable[['Shell'], int]``) — OR the parameter is
UNANNOTATED and named exactly ``shell`` (a smuggled reach with no type). It never
matches ``ShellState`` (a distinct identifier — already a narrowing).
``ShellState`` parameters are deliberately NOT counted (``process_launcher`` /
``input_sources`` take it; it is a state container, not a service locator).

The ``test_detector_*`` self-tests prove the detector flags the bare, wrapped,
and unannotated shapes and ignores ``ShellState`` / protocol params, so the
ratchet cannot rot into a no-op.
"""

import ast
import pathlib
import re
import subprocess
import warnings

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]


# Campaign Q3 (WP5): the git self-check below verifies CREATED_MODULES against
# the actual campaign-added set. When git or the base tag is unavailable it must
# WARN (naming the protection lost) before skipping — never skip silently, or
# list drift goes undetected in shallow/tarball checkouts. This mirrors the
# uniform F9 hardening in test_mypy_untyped_defs_coverage.py. Green-repo
# behavior (git + tag present) is unchanged: the assertion runs.
_SELFCHECK_UNVERIFIED = (
    "SELF-CHECK SKIPPED: cannot verify {name} against the git enumeration "
    "(git log --diff-filter=A v0.724.0..75ab5625 -- psh/): {reason}. The "
    "hardcoded list is TRUSTED UNVERIFIED here — drift between it and the "
    "actual campaign-created set will go UNDETECTED until this test runs in a "
    "full checkout with the base tag present."
)


def _warn_selfcheck_unverified(list_name, reason):
    warnings.warn(
        _SELFCHECK_UNVERIFIED.format(name=list_name, reason=reason),
        stacklevel=2,
    )


# Files the campaign ADDED (git --diff-filter=A v0.724.0..75ab5625 -- psh/).
CREATED_MODULES = [
    "psh/ast_nodes/syntax_templates.py",
    "psh/core/process_lease.py",
    "psh/core/variable_lookup.py",
    "psh/executor/command_resolution.py",
    "psh/executor/foreground_session.py",
    "psh/expansion/subscript.py",
    "psh/interactive/history_result.py",
    "psh/invocation.py",
    "psh/io_redirect/input_cursor.py",
    "psh/io_redirect/redirect_program.py",
    "psh/parser/parse_inputs.py",
    "psh/parser/parse_outcome.py",
    "psh/parser/recursive_descent/support/syntax_templates.py",
    "psh/parser/session.py",
    "psh/parser/unclosed_expansion.py",
    "psh/scripting/program_source.py",
]

# Pre-campaign files the campaign MIGRATED or that carry a recorded consumer —
# scanned so the ratchet can see them (each annotated with why).
TOUCHED_PREEXISTING = [
    "psh/executor/process_launcher.py",   # campaign added AsyncJobPolicy; takes ShellState
    "psh/executor/child_policy.py",       # holds the 3 full-Shell subshell runners (allowlisted)
    "psh/scripting/input_sources.py",     # pre-campaign (v0.285); campaign-touched; takes ShellState
    "psh/builtins/input_reader.py",       # holds migrated make_reader (Shell -> IOContext)
]

TOUCHED_MODULES = CREATED_MODULES + TOUCHED_PREEXISTING


# The frozen set of boundary-module defs that legitimately still take the full
# ``Shell`` — (dotted-module, qualified-symbol) -> justification. MAY ONLY
# SHRINK. Each forwards the shell to a whole-shell need or reaches a subsystem no
# protocol (VariableAccess/ExpansionContext/IOContext/JobRuntime/LocaleContext)
# models.
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
    ("psh.scripting.program_source", "execute_sourced_file"):
        "THE sourced-file executor (source/. + rc load): owns state.source_depth, "
        "the positional-params swap/restore, FunctionReturn handling, the RETURN "
        "trap, and drives the input source through the executor — a whole-shell "
        "transaction, not a protocol-shaped slice",
}


def _module_dotted(rel_path: str) -> str:
    return rel_path[:-3].replace("/", ".")


def _string_mentions_shell(s: str) -> bool:
    """True if a forward-ref string annotation names ``Shell`` as an identifier
    (``'Shell'``, ``"Optional[Shell]"``, ``'Shell | None'``) — never
    ``ShellState``."""
    try:
        sub = ast.parse(s, mode="eval")
    except SyntaxError:
        # Unparseable string: word-boundary match. `\bShell\b` does NOT match
        # inside `ShellState` (the following `S` is a word char).
        return re.search(r"\bShell\b", s) is not None
    # Delegate back so a doubly-nested forward-ref (Callable[['Shell'], int] —
    # 'Shell' is a string INSIDE the string) is unwrapped too.
    return _ann_mentions_shell(sub)


def _ann_mentions_shell(node) -> bool:
    """True if an annotation mentions ``Shell`` as an identifier anywhere —
    bare, string forward-ref, or wrapped (Optional/Union/Callable/…)."""
    if node is None:
        return False
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and n.id == "Shell":
            return True
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            if _string_mentions_shell(n.value):
                return True
    return False


def full_shell_consumers(src: str, module: str) -> set:
    """Return {(module, qualname)} for every def with a parameter that is the
    full ``Shell`` (annotation mentions ``Shell``, or unannotated + named
    ``shell``)."""
    tree = ast.parse(src)
    found: set = set()

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
                hit = any(
                    _ann_mentions_shell(p.annotation)
                    or (p.annotation is None and p.arg == "shell")
                    for p in params
                )
                if hit:
                    found.add(".".join(prefix + [child.name]))
                visit(child, prefix + [child.name])

    visit(tree, [])
    return {(module, sym) for sym in found}


def _live_consumers() -> set:
    consumers: set = set()
    for rel in TOUCHED_MODULES:
        path = ROOT / rel
        assert path.exists(), f"scanned module missing: {rel}"
        consumers |= full_shell_consumers(path.read_text(), _module_dotted(rel))
    return consumers


# --- The ratchet ------------------------------------------------------------

def test_scanned_modules_all_exist():
    for rel in TOUCHED_MODULES:
        assert (ROOT / rel).exists(), f"scanned module missing: {rel}"


def test_created_modules_match_enumeration():
    """CREATED_MODULES is exactly the campaign-added set. Verified against git
    when the base tag is present; when git or the tag is absent the self-check
    WARNS loudly (Q3 WP5) before skipping, never silently (shallow checkout)."""
    try:
        out = subprocess.run(
            ["git", "log", "--diff-filter=A", "--pretty=format:",
             "--name-only", "v0.724.0..75ab5625", "--", "psh/"],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as e:
        _warn_selfcheck_unverified(
            "CREATED_MODULES", f"git unavailable ({type(e).__name__})")
        pytest.skip("git unavailable")
    if out.returncode != 0:
        _warn_selfcheck_unverified(
            "CREATED_MODULES", "base tag/range v0.724.0..75ab5625 not present")
        pytest.skip("base tag/range unavailable in this checkout")
    enumerated = {ln.strip() for ln in out.stdout.splitlines()
                  if ln.strip().endswith(".py")}
    assert enumerated == set(CREATED_MODULES), (
        "CREATED_MODULES drifted from the git enumeration "
        "(v0.724.0..75ab5625 --diff-filter=A -- psh/). Update the list.\n"
        f"  only in git: {sorted(enumerated - set(CREATED_MODULES))}\n"
        f"  only in list: {sorted(set(CREATED_MODULES) - enumerated)}"
    )


def test_selfcheck_warns_loudly_when_git_unavailable():
    """Q3 WP5: the git self-check WARNS (naming the lost protection) rather than
    skipping silently — so CREATED_MODULES drift is signalled even in a checkout
    without git/the base tag. Uniform with the F9 twin."""
    with pytest.warns(UserWarning, match="TRUSTED UNVERIFIED"):
        _warn_selfcheck_unverified("CREATED_MODULES", "git unavailable (OSError)")


def test_no_unrecorded_full_shell_consumers():
    live = _live_consumers()
    new = live - set(ALLOWLIST)
    assert not new, (
        "New full-`Shell` consumer(s) in a boundary module. Narrow the "
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
    and make_reader from `Shell` to IOContext — neither may appear as a
    full-Shell consumer."""
    live = _live_consumers()
    assert ("psh.io_redirect.input_cursor",
            "InputCursorRegistry.cursor_for_fd") not in live
    assert ("psh.builtins.input_reader", "make_reader") not in live


# --- Detector self-tests ----------------------------------------------------

def test_detector_flags_bare_shell():
    src = ("class Foo:\n"
           "    def bar(self, shell: 'Shell', fd: int) -> None: ...\n")
    assert ("psh.fake", "Foo.bar") in full_shell_consumers(src, "psh.fake")


def test_detector_flags_wrapped_shell():
    # Optional['Shell'], 'Shell | None', Callable[['Shell'], int] — all evade a
    # bare-name-only detector; all must fire here.
    src = (
        "from typing import Callable, Optional\n"
        "class Foo:\n"
        "    def a(self, shell: Optional['Shell']) -> None: ...\n"
        "    def b(self, shell: 'Shell | None') -> None: ...\n"
        "    def c(self, cb: \"Callable[['Shell'], int]\") -> None: ...\n"
    )
    found = full_shell_consumers(src, "psh.fake")
    assert {("psh.fake", "Foo.a"), ("psh.fake", "Foo.b"),
            ("psh.fake", "Foo.c")} <= found


def test_detector_flags_unannotated_shell():
    src = ("class Foo:\n"
           "    def sneaky(self, shell) -> None: ...\n")
    assert ("psh.fake", "Foo.sneaky") in full_shell_consumers(src, "psh.fake")


def test_detector_ignores_state_and_protocol_and_other_names():
    src = (
        "from typing import Optional\n"
        "class Foo:\n"
        "    def a(self, io_ctx: 'IOContext') -> None: ...\n"
        "    def b(self, state: 'ShellState') -> None: ...\n"
        "    def c(self, state: Optional['ShellState']) -> None: ...\n"
        "    def d(self, x: int) -> None: ...\n"
        "    def e(self, other) -> None: ...\n"   # unannotated but NOT named 'shell'
    )
    assert full_shell_consumers(src, "psh.fake") == set()
