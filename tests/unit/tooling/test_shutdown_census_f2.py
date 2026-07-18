"""Census ratchet: ``Shell.shutdown`` is THE top-level cleanup path (F2).

Top-level cleanup — firing the EXIT trap and saving history on the way out
of a shell — used to be duplicated per route (exit builtin, REPL EOF, and
nothing at all for some paths).  ``Shell.shutdown(reason)`` unified it; this
census pins every remaining production call site of ``execute_exit_trap``
and ``save_to_file`` to an explicit, justified allowlist so no route can
quietly grow a bypass.  The allowlists are ratchets: they may only shrink
(a stale entry fails), and a synthetic offender proves the scanner fires.
"""
import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PSH_DIR = REPO_ROOT / "psh"

#: Production call sites of ``execute_exit_trap`` (method calls; the
#: definition itself is not a call).  Every entry has a justification:
EXIT_TRAP_CALLS_ALLOWED = {
    # THE top-level path: exit builtin, REPL EOF, and __main__'s final
    # funnel all route here.
    "psh/shell.py",
    # execute_as_main: the EXIT trap must fire while the run's state is
    # still in place and a trap-body `exit N` must override the status —
    # timing shutdown() cannot reproduce after the fact.  Idempotent with
    # the shutdown() firing (at-most-once inside TrapManager).
    "psh/scripting/source_processor.py",
    # Untrapped fatal-signal death: fires the trap, then re-raises the
    # signal so the wait status stays 128+N — not a normal shutdown.
    "psh/interactive/signal_manager.py",
    # Forked children (subshell / child-shell bodies): per-child EXIT
    # semantics inside the fork, never top-level cleanup; children must
    # NOT save history or release the parent's leases.
    "psh/executor/child_policy.py",
    # The idempotent implementation itself (execute_exit_trap calls
    # execute_trap; kept for completeness of the method-name scan).
    "psh/core/trap_manager.py",
}

#: Production call sites of history ``save_to_file``.
SAVE_HISTORY_CALLS_ALLOWED = {
    # shutdown()'s history-saving routes (exit builtin, REPL EOF).
    "psh/shell.py",
    # The public InteractiveManager.save_history() convenience wrapper
    # (embedder API; no production caller routes through it).
    "psh/interactive/base.py",
    # The HistoryManager implementation file (internal helpers).
    "psh/interactive/history_manager.py",
}


def _method_calls(source: str, filename: str, method: str) -> list:
    hits = []
    tree = ast.parse(source, filename=filename)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == method):
            hits.append(node.lineno)
    return hits


def _scan(method: str, allowed: set) -> list:
    offenders = []
    for path in sorted(PSH_DIR.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in allowed:
            continue
        for lineno in _method_calls(path.read_text(), rel, method):
            offenders.append(f"{rel}:{lineno}: .{method}()")
    return offenders


def test_exit_trap_fires_only_from_allowlisted_sites():
    offenders = _scan("execute_exit_trap", EXIT_TRAP_CALLS_ALLOWED)
    assert not offenders, (
        "execute_exit_trap called from a NEW site — top-level cleanup must "
        "route through Shell.shutdown(reason) (campaign F2 census):\n"
        + "\n".join(offenders))


def test_history_save_only_from_allowlisted_sites():
    offenders = _scan("save_to_file", SAVE_HISTORY_CALLS_ALLOWED)
    assert not offenders, (
        "history save_to_file called from a NEW site — persistence on the "
        "way out belongs to Shell.shutdown(reason) (campaign F2 census):\n"
        + "\n".join(offenders))


def test_exit_builtin_and_repl_route_through_shutdown():
    """The two explicit routes must call shutdown, not the primitives."""
    exit_src = (PSH_DIR / "builtins" / "core.py").read_text()
    repl_src = (PSH_DIR / "interactive" / "repl_loop.py").read_text()
    assert "shutdown('exit-builtin')" in exit_src
    assert "shutdown('repl-eof')" in repl_src
    main_src = (PSH_DIR / "__main__.py").read_text()
    assert "shutdown('main-exit')" in main_src


def test_allowlisted_files_exist():
    for rel in EXIT_TRAP_CALLS_ALLOWED | SAVE_HISTORY_CALLS_ALLOWED:
        assert (REPO_ROOT / rel).is_file(), f"stale allowlist entry: {rel}"


def test_scanner_fires_on_synthetic_offender():
    source = "shell.trap_manager.execute_exit_trap()\n"
    assert _method_calls(source, "offender.py", "execute_exit_trap")
    source = "self.history_manager.save_to_file()\n"
    assert _method_calls(source, "offender.py", "save_to_file")
    clean = "# shell.trap_manager.execute_exit_trap()\nx = 'save_to_file()'\n"
    assert not _method_calls(clean, "clean.py", "execute_exit_trap")
    assert not _method_calls(clean, "clean.py", "save_to_file")
