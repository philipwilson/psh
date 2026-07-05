"""Tests for the unified statement-sequence executor (`_execute_sequence`).

`visit_Program` (the program root) and `visit_StatementList` (a nested body)
both delegate to `ExecutorVisitor._execute_sequence`, which selects its
control-flow policy from a `SequenceContext`. These tests pin the three
divergences between the ROOT and NESTED contexts (KeyboardInterrupt handling,
out-of-loop break/continue announce-vs-silent and continue-vs-stop) plus the
shared FunctionReturn propagation and `set -e` semantics.
"""
import subprocess
import sys
from pathlib import Path

import pytest

from psh.core import LoopBreak, LoopContinue
from psh.core.exceptions import FunctionReturn
from psh.executor.core import NESTED_SEQUENCE, ROOT_SEQUENCE, ExecutorVisitor
from psh.shell import Shell

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class _Stmt:
    """A stand-in statement whose ``visit`` runs ``fn(visited_list)``."""
    line = None

    def __init__(self, fn):
        self.fn = fn


def _raise(exc):
    def _fn(_visited):
        raise exc
    return _fn


def _record(tag):
    def _fn(visited):
        visited.append(tag)
        return 0
    return _fn


def _run_sequence(stmts, context, *, loop_depth=0):
    """Execute *stmts* through _execute_sequence, returning (rc, visited)."""
    ev = ExecutorVisitor(Shell())
    ev.context.loop_depth = loop_depth
    visited = []
    ev.visit = lambda node: node.fn(visited)  # type: ignore[method-assign]
    rc = ev._execute_sequence(stmts, context=context)
    return rc, visited


class TestKeyboardInterrupt:
    """ROOT catches ^C (130, continue); NESTED lets it propagate."""

    def test_root_catches_and_returns_130(self):
        rc, visited = _run_sequence(
            [_Stmt(_raise(KeyboardInterrupt()))], ROOT_SEQUENCE)
        assert rc == 130
        assert visited == []

    def test_root_continues_after_interrupt(self):
        rc, visited = _run_sequence(
            [_Stmt(_raise(KeyboardInterrupt())), _Stmt(_record("after"))],
            ROOT_SEQUENCE)
        assert visited == ["after"]  # loop continued past ^C
        assert rc == 0  # the trailing statement's status

    def test_nested_propagates(self):
        with pytest.raises(KeyboardInterrupt):
            _run_sequence([_Stmt(_raise(KeyboardInterrupt()))], NESTED_SEQUENCE)


class TestFunctionReturnPropagates:
    """FunctionReturn propagates from both contexts (the loop catches neither)."""

    def test_root_propagates(self):
        with pytest.raises(FunctionReturn):
            _run_sequence([_Stmt(_raise(FunctionReturn(3)))], ROOT_SEQUENCE)

    def test_nested_propagates(self):
        with pytest.raises(FunctionReturn):
            _run_sequence([_Stmt(_raise(FunctionReturn(3)))], NESTED_SEQUENCE)


class TestOutOfLoopBreakContinue:
    """ROOT announces + continues; NESTED is silent + stops. Both re-raise
    when loop_depth > 0 (an enclosing loop frame owns it)."""

    def test_root_announces_break_and_continues(self, capsys):
        rc, visited = _run_sequence(
            [_Stmt(_raise(LoopBreak())), _Stmt(_record("after"))], ROOT_SEQUENCE)
        assert visited == ["after"]
        assert rc == 0
        assert "break: only meaningful" in capsys.readouterr().err

    def test_root_announces_continue(self, capsys):
        _run_sequence([_Stmt(_raise(LoopContinue()))], ROOT_SEQUENCE)
        assert "continue: only meaningful" in capsys.readouterr().err

    def test_nested_is_silent_and_stops(self, capsys):
        rc, visited = _run_sequence(
            [_Stmt(_raise(LoopBreak())), _Stmt(_record("after"))], NESTED_SEQUENCE)
        assert visited == []  # stopped: the trailing statement did not run
        assert rc == 1
        assert capsys.readouterr().err == ""

    @pytest.mark.parametrize("context", [ROOT_SEQUENCE, NESTED_SEQUENCE])
    def test_reraises_when_in_loop(self, context):
        with pytest.raises(LoopBreak):
            _run_sequence([_Stmt(_raise(LoopBreak()))], context, loop_depth=1)


def _psh_c(script):
    return subprocess.run(
        [sys.executable, "-m", "psh", "-c", script],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30)


def _psh_script(tmp_path, body):
    path = tmp_path / "s.sh"
    path.write_text(body)
    return subprocess.run(
        [sys.executable, "-m", "psh", str(path)],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30)


class TestErrexitContext:
    """`set -e`: a triggering failure stops the sequence in -c mode and exits
    the process in script mode — both surface as status 1 with no continuation.
    """

    def test_dash_c_mode_stops(self):
        r = _psh_c("set -e; false; echo UNREACHED")
        assert r.returncode == 1
        assert "UNREACHED" not in r.stdout

    def test_script_mode_exits(self, tmp_path):
        r = _psh_script(tmp_path, "set -e\nfalse\necho UNREACHED\n")
        assert r.returncode == 1
        assert "UNREACHED" not in r.stdout

    def test_dash_c_nested_condition_is_exempt(self):
        # A failure in an if-condition is errexit-exempt (POSIX), so execution
        # continues -- same in both contexts.
        r = _psh_c("set -e; if false; then :; fi; echo REACHED")
        assert r.returncode == 0
        assert "REACHED" in r.stdout


class TestTopLevelBreakContinueEndToEnd:
    """The reachable top-level break/continue path (the builtin reports at
    loop_depth == 0, and execution continues to the next statement)."""

    def test_break_reports_and_continues(self):
        r = _psh_c("break; echo after")
        assert r.returncode == 0
        assert r.stdout == "after\n"
        assert "only meaningful" in r.stderr

    def test_eval_break_inside_loop_breaks_loop(self):
        r = _psh_c("for i in 1 2 3; do eval break; echo $i; done; echo done")
        assert r.returncode == 0
        assert r.stdout == "done\n"
