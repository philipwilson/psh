"""
Tests for DEBUG/ERR traps and deferred signal traps (v0.263.0).

Regression guards: execute_debug_trap/execute_err_trap existed and were
documented in `trap` help but had ZERO call sites — the traps were stored
and silently never fired. Signal traps also used to execute inside the
Python signal handler, able to re-enter the parser/executor mid-command.
Verified against bash 5.2.
"""

import subprocess
import sys


def run_psh(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True)


class TestDebugTrap:
    def test_fires_before_each_command(self):
        result = run_psh('trap "echo DBG" DEBUG; echo one; echo two')
        assert result.stdout == 'DBG\none\nDBG\ntwo\n'

    def test_action_does_not_recurse(self):
        result = run_psh('trap "echo DBG" DEBUG; echo one')
        assert result.stdout.count('DBG') == 1

    def test_reset_stops_firing(self):
        """DEBUG fires before the reset command itself, then stops (bash)."""
        result = run_psh('trap "echo DBG" DEBUG; trap - DEBUG; echo one')
        assert result.stdout == 'DBG\none\n'


class TestErrTrap:
    def test_fires_on_failure(self):
        result = run_psh('trap "echo ERR-RAN" ERR; false; true')
        assert result.stdout == 'ERR-RAN\n'

    def test_exempt_in_if_condition(self):
        result = run_psh('trap "echo E" ERR; if false; then :; fi; echo ok')
        assert result.stdout == 'ok\n'

    def test_exempt_in_or_list(self):
        result = run_psh('trap "echo E" ERR; false || true; echo ok')
        assert result.stdout == 'ok\n'

    def test_exempt_under_negation(self):
        result = run_psh('trap "echo E" ERR; ! false; ! true; echo ok')
        assert result.stdout == 'ok\n'

    def test_fires_before_errexit_abort(self):
        result = run_psh('trap "echo X" ERR; set -e; false; echo no')
        assert result.stdout == 'X\n'
        assert result.returncode == 1

    def test_dollar_q_inside_action(self):
        result = run_psh("trap 'echo code=$?' ERR; f(){ return 7; }; f; true")
        assert result.stdout == 'code=7\n'


class TestDeferredSignalTraps:
    def test_trap_runs_at_command_boundary(self):
        """The action runs after the signalling command, before the next."""
        result = run_psh('trap "echo caught" INT; kill -INT $$; echo after')
        assert result.stdout == 'caught\nafter\n'

    def test_trap_can_set_variables(self):
        """Actions run in normal execution context, not handler context."""
        result = run_psh(
            'trap "hit=yes" INT; kill -INT $$; echo "hit=$hit"')
        assert result.stdout == 'hit=yes\n'
