"""Unit pins for the ONE POSIX special-builtin exit policy (slot 2.2).

The policy has three parts and this module exercises each on the OWNER
rather than through a shell run, so a consumer that stops calling it cannot
hide behind an end-to-end pass:

* ``core/internal_errors.py#special_builtin_usage_exit`` — exit vs fail, and
  the suppressible-class exemption;
* ``core/internal_errors.py#special_builtin_stops_at_first_bad_identifier``
  — the operand-loop half (posix mode alone decides it);
* ``executor/context.py#ExecutionContext.trap_action_boundary`` — the one
  boundary bash's suppression does not cross.

bash 5.3 widened the exit set to the operand errors and made the eval/dot
boundary transparent (CHANGES, bash-5.3-alpha, "1. Changes to Bash" item jj,
"POSIX special builtins now exit the shell in posix mode on more failure
cases"; item nnnnn).  Reproduce the boundary pair on the oracle::

    bash -c "set -o posix; eval 'set -q' || echo caught; echo survived"
    #   -> caught / survived, rc 0
    bash -c "set -o posix; trap 'set -q' DEBUG; false || echo caught"
    #   -> rc 2, `caught` never printed

Gate rows G18-G22 / FLIP-PINS slot 2.2.
"""

import pytest

from psh.core.internal_errors import (
    special_builtin_stops_at_first_bad_identifier,
    special_builtin_usage_exit,
)
from psh.executor.context import ExecutionContext


class _FakeState:
    def __init__(self, posix, script_mode=True):
        self.options = {'posix': posix}
        self.is_script_mode = script_mode


class _FakeExecutor:
    def __init__(self, context):
        self.context = context


class _FakeShell:
    """The two attributes the policy reads, and nothing else."""

    def __init__(self, *, posix, script_mode=True, context=None):
        self.state = _FakeState(posix, script_mode)
        self._current_executor = (None if context is None
                                  else _FakeExecutor(context))


def _guarded(context, depth=1):
    """Enter ``depth`` errexit-suppressing contexts (an if/while/||  guard)."""
    for _ in range(depth):
        context.errexit_suppress += 1
    return context


class TestStopsAtFirstBadIdentifier:
    """The operand-loop half: POSIX MODE decides it, nothing else.

    `command export 1bad=x 2bad=y` prints ONE diagnostic on bash 5.3.15
    even though `command` strips the exit, so the predicate must not
    consult the exit at all.
    """

    def test_posix_mode_stops(self):
        assert special_builtin_stops_at_first_bad_identifier(
            _FakeState(posix=True))

    def test_default_mode_runs_the_whole_loop(self):
        assert not special_builtin_stops_at_first_bad_identifier(
            _FakeState(posix=False))

    def test_interactive_posix_shell_still_stops(self):
        # is_script_mode gates the EXIT, never the operand loop.
        assert special_builtin_stops_at_first_bad_identifier(
            _FakeState(posix=True, script_mode=False))


class TestUsageExitOutcome:
    """exit vs plain failure, by mode and shell kind."""

    @pytest.mark.parametrize("status", [1, 2])
    def test_posix_script_shell_exits_with_the_status(self, status):
        shell = _FakeShell(posix=True)
        with pytest.raises(SystemExit) as exc:
            special_builtin_usage_exit(shell, status)
        assert exc.value.code == status

    @pytest.mark.parametrize("status", [1, 2])
    def test_default_mode_returns_the_status(self, status):
        shell = _FakeShell(posix=False)
        assert special_builtin_usage_exit(shell, status) == status

    def test_interactive_or_embedded_shell_returns_the_status(self):
        shell = _FakeShell(posix=True, script_mode=False)
        assert special_builtin_usage_exit(shell, 2) == 2

    def test_no_executor_still_exits(self):
        # A suppressible outcome with no live executor has no suppression
        # depth to read: the exit stands.
        shell = _FakeShell(posix=True, context=None)
        with pytest.raises(SystemExit):
            special_builtin_usage_exit(shell, 1, suppressible=True)


class TestSuppressibleClass:
    """The guard exemption applies to the suppressible class only."""

    def test_guard_suppresses_a_suppressible_outcome(self):
        shell = _FakeShell(posix=True,
                           context=_guarded(ExecutionContext()))
        assert special_builtin_usage_exit(shell, 1, suppressible=True) == 1

    def test_guard_does_not_suppress_the_hard_class(self):
        shell = _FakeShell(posix=True,
                           context=_guarded(ExecutionContext()))
        with pytest.raises(SystemExit) as exc:
            special_builtin_usage_exit(shell, 1, suppressible=False)
        assert exc.value.code == 1

    def test_unguarded_suppressible_outcome_exits(self):
        shell = _FakeShell(posix=True, context=ExecutionContext())
        with pytest.raises(SystemExit):
            special_builtin_usage_exit(shell, 2, suppressible=True)

    def test_nested_guards_still_suppress(self):
        shell = _FakeShell(posix=True,
                           context=_guarded(ExecutionContext(), depth=3))
        assert special_builtin_usage_exit(shell, 2, suppressible=True) == 2


class TestEvalDotBoundaryIsTransparent:
    """bash 5.3: no nesting raises the floor except a trap action.

    The 5.2 shape raised the floor for EVERY nested run, which is what made
    `eval 'set -q' || echo caught` exit; nothing in the context does that
    any more, so an outer guard reaches through an eval/dot boundary.
    """

    def test_context_starts_with_a_zero_floor(self):
        assert ExecutionContext().special_exit_floor == 0

    def test_outer_guard_reaches_through_a_nested_run(self):
        # An eval/dot nesting no longer touches the floor, so the guard
        # entered OUTSIDE it is still visible.
        context = _guarded(ExecutionContext())
        assert context.special_exit_suppressed
        shell = _FakeShell(posix=True, context=context)
        assert special_builtin_usage_exit(shell, 2, suppressible=True) == 2


class TestTrapActionBoundary:
    """The one boundary the suppression does not cross."""

    def test_outer_guard_is_fenced_off(self):
        context = _guarded(ExecutionContext())
        with context.trap_action_boundary():
            assert not context.special_exit_suppressed
            shell = _FakeShell(posix=True, context=context)
            with pytest.raises(SystemExit) as exc:
                special_builtin_usage_exit(shell, 2, suppressible=True)
            assert exc.value.code == 2

    def test_guard_inside_the_action_suppresses_again(self):
        context = _guarded(ExecutionContext())
        with context.trap_action_boundary():
            context.errexit_suppress += 1          # a guard in the action
            assert context.special_exit_suppressed
            shell = _FakeShell(posix=True, context=context)
            assert special_builtin_usage_exit(shell, 2,
                                              suppressible=True) == 2

    def test_boundary_restores_the_previous_floor(self):
        context = _guarded(ExecutionContext())
        with context.trap_action_boundary():
            pass
        assert context.special_exit_floor == 0
        assert context.special_exit_suppressed

    def test_boundary_restores_the_floor_after_an_exception(self):
        context = _guarded(ExecutionContext())
        with pytest.raises(RuntimeError):
            with context.trap_action_boundary():
                raise RuntimeError("action blew up")
        assert context.special_exit_floor == 0

    def test_nested_boundaries_stack(self):
        # A signal trap firing DURING an EXIT action nests two boundaries;
        # unwinding the inner one must restore the outer floor, not zero.
        context = _guarded(ExecutionContext())
        with context.trap_action_boundary():
            context.errexit_suppress += 1
            with context.trap_action_boundary():
                assert not context.special_exit_suppressed
            assert context.special_exit_suppressed
            assert context.special_exit_floor == 1

    def test_hard_class_exits_inside_the_boundary_too(self):
        context = _guarded(ExecutionContext())
        with context.trap_action_boundary():
            shell = _FakeShell(posix=True, context=context)
            with pytest.raises(SystemExit):
                special_builtin_usage_exit(shell, 1, suppressible=False)

    def test_default_mode_never_exits_inside_the_boundary(self):
        context = _guarded(ExecutionContext())
        with context.trap_action_boundary():
            shell = _FakeShell(posix=False, context=context)
            assert special_builtin_usage_exit(shell, 2,
                                              suppressible=True) == 2
