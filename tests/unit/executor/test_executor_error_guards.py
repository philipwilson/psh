"""Executor error-boundary behavior (study triage #13).

The executor's broad ``except Exception`` guards keep the shell alive on a
command/builtin/function error, but should:
  - report a readonly-variable assignment via the specific ReadonlyVariableError
    path (not a blanket catch), and
  - surface a traceback under --debug-exec when an unexpected (likely internal)
    error is caught, instead of hiding it behind the generic message.
"""

import pytest

from psh.builtins.base import Builtin
from psh.builtins.registry import registry


class TestReadonlyAssignment:
    def test_standalone_readonly_reassignment_errors(self, captured_shell):
        captured_shell.run_command('readonly RO=1; RO=2')
        assert "readonly variable" in captured_shell.get_stderr()

    def test_command_prefix_readonly_assignment_errors(self, captured_shell):
        rc = captured_shell.run_command('readonly RO=1; RO=2 echo hi')
        assert rc == 1
        assert "readonly variable" in captured_shell.get_stderr()
        # The command should not have run.
        assert captured_shell.get_stdout() == ""


class _BoomBuiltin(Builtin):
    """A builtin that raises an unexpected (non-shell) error."""

    @property
    def name(self) -> str:
        return "boom"

    def execute(self, args, shell) -> int:
        raise RuntimeError("kaboom")


@pytest.fixture
def boom_builtin():
    registry.register(_BoomBuiltin)
    try:
        yield
    finally:
        registry._builtins.pop("boom", None)


class TestUnexpectedErrorGuard:
    def test_builtin_defect_reported_without_crashing(self, captured_shell, boom_builtin):
        rc = captured_shell.run_command('boom')
        assert rc == 1
        assert "boom" in captured_shell.get_stderr()
        # Default (no debug-exec): no traceback leaks to the user.
        assert "Traceback" not in captured_shell.get_stderr()

    def test_builtin_defect_surfaces_traceback_under_debug_exec(self, captured_shell, boom_builtin):
        captured_shell.state.options['debug-exec'] = True
        try:
            captured_shell.run_command('boom')
        finally:
            captured_shell.state.options['debug-exec'] = False
        err = captured_shell.get_stderr()
        assert "Traceback" in err
        assert "RuntimeError" in err
