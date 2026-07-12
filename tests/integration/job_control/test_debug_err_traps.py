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


class TestTrapInheritanceIntoFunctions:
    """Reappraisal #14 H2: ERR/DEBUG must NOT be inherited into function
    bodies unless errtrace/functrace is set (bash). Previously psh fired them
    at every nesting level. Verified against bash 5.2."""

    # Single-quoted trap action so $((c+1)) is deferred to fire-time (counts
    # the actual fires); double-quoted would expand once at definition.
    def test_err_not_inherited_into_function_by_default(self):
        # Only the top-level `f`-returns-nonzero fires; the inner `false` does
        # not (no errtrace). bash: fired=1 (psh used to give fired=2).
        result = run_psh("c=0; trap 'c=$((c+1))' ERR; f(){ false; }; f; echo \"fired=$c\"")
        assert result.stdout == 'fired=1\n'

    def test_err_inherited_with_errtrace(self):
        result = run_psh("set -E; c=0; trap 'c=$((c+1))' ERR; f(){ false; }; f; echo \"fired=$c\"")
        assert result.stdout == 'fired=2\n'

    def test_err_inherited_with_set_o_errtrace(self):
        result = run_psh("set -o errtrace; c=0; trap 'c=$((c+1))' ERR; f(){ false; }; f; echo \"fired=$c\"")
        assert result.stdout == 'fired=2\n'

    def test_err_function_false_then_true_does_not_fire(self):
        # f returns 0 (true is last), and the inner false is not inherited.
        result = run_psh("c=0; trap 'c=$((c+1))' ERR; f(){ false; true; }; f; echo \"fired=$c\"")
        assert result.stdout == 'fired=0\n'

    def test_err_nested_function_calls_default(self):
        cmd = "c=0; trap 'c=$((c+1))' ERR; g(){ false; }; f(){ g; }; f; echo \"fired=$c\""
        result = run_psh(cmd)
        bash = subprocess.run(['bash', '-c', cmd], capture_output=True, text=True)
        assert result.stdout == bash.stdout

    def test_err_brace_group_transparent_fires_once(self):
        result = run_psh("c=0; trap 'c=$((c+1))' ERR; { { false; }; }; echo \"fired=$c\"")
        assert result.stdout == 'fired=1\n'

    def test_debug_not_inherited_into_function_by_default(self):
        # DEBUG fires before `echo top` and before the `f` call, but NOT before
        # the body's `echo a`/`echo b` (no functrace).
        result = run_psh('trap "echo D" DEBUG; f(){ echo a; echo b; }; echo top; f')
        assert result.stdout == 'D\ntop\nD\na\nb\n'

    def test_debug_count_with_function_call_default(self):
        result = run_psh('trap "echo D" DEBUG; f(){ :; }; echo a; f; echo b')
        assert result.stdout == 'D\na\nD\nD\nb\n'

    def test_debug_inherited_with_functrace(self):
        # With -T, DEBUG fires for body commands too (at least once before the
        # body command — count differs from bash internals but inheritance is on).
        result = run_psh('set -T; trap "echo D" DEBUG; f(){ echo a; }; f')
        assert 'a' in result.stdout
        assert result.stdout.count('D') >= 1

    def test_errtrace_functrace_in_dollar_dash(self):
        result = run_psh('set -E -T; case "$-" in *E*T*) echo yes;; *) echo no;; esac')
        assert result.stdout == 'yes\n'

    def test_set_plus_e_uppercase_unsets_errtrace(self):
        result = run_psh('set -E; set +E; case "$-" in *E*) echo on;; *) echo off;; esac')
        assert result.stdout == 'off\n'


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


class TestTrapInheritanceIntoSubshellChildren:
    """The ONE inherited-traps rule (appraisal H9): ERR stays live in a
    subshell-style child under `set -E`, DEBUG under `set -T` — for BOTH a
    forked child shell (clone_for_child: `( )`, `$( )`, `<( )`) AND a
    backgrounded compound that reuses the parent Shell (enter_subshell_trap_
    environment: `{ ...; } &`, `f &`). Those two paths used to disagree on the
    DEBUG-under-functrace exemption. All expectations verified against bash 5.2.
    """

    def test_debug_functrace_inherited_into_bg_brace(self):
        # THE H9 fix: a DEBUG trap under set -T fires inside a backgrounded
        # brace group (3 DBG). Was 2 before — the DEBUG exemption was missing
        # from enter_subshell_trap_environment.
        result = run_psh('set -T; trap "echo DBG" DEBUG; { true; } & wait; echo done')
        assert result.stdout == 'DBG\nDBG\nDBG\ndone\n'

    def test_debug_no_functrace_not_inherited_into_bg_brace(self):
        # Both branches of the symmetric fix: WITHOUT set -T the DEBUG trap does
        # NOT fire inside the child (2 DBG, both from the parent).
        result = run_psh('trap "echo DBG" DEBUG; { true; } & wait; echo done')
        assert result.stdout == 'DBG\nDBG\ndone\n'

    def test_debug_functrace_inherited_into_bg_function(self):
        result = run_psh('set -T; trap "echo DBG" DEBUG; f(){ true; }; f & wait; echo done')
        assert result.stdout == 'DBG\nDBG\nDBG\nDBG\nDBG\ndone\n'

    def test_debug_functrace_inherited_into_subshell(self):
        # The clone_for_child path (fresh child shell) — already correct.
        result = run_psh('set -T; trap "echo DBG" DEBUG; ( true ); echo done')
        assert result.stdout == 'DBG\nDBG\ndone\n'

    def test_err_errtrace_inherited_into_bg_brace(self):
        result = run_psh('set -E; trap "echo ET" ERR; { false; } & wait; echo done')
        assert result.stdout == 'ET\ndone\n'

    def test_err_no_errtrace_not_inherited_into_bg_brace(self):
        result = run_psh('trap "echo ET" ERR; { false; } & wait; echo done')
        assert result.stdout == 'done\n'


class TestComputeInheritedTraps:
    """Direct unit coverage of the single exemption rule."""

    def _compute(self, *, errtrace=False, functrace=False, handlers):
        from psh.core.trap_manager import TrapManager
        opts = {'errtrace': errtrace, 'functrace': functrace}
        return TrapManager.compute_inherited_traps(opts, handlers)

    def test_err_exempt_under_errtrace_debug_reset(self):
        # ERR stays live (not listed-only) under errtrace; DEBUG resets.
        got = self._compute(errtrace=True, functrace=False,
                            handlers={'ERR': 'e', 'DEBUG': 'd', 'INT': 'i'})
        assert got == {'DEBUG', 'INT'}

    def test_debug_exempt_under_functrace_err_reset(self):
        # DEBUG stays live under functrace; ERR resets — the branch that used to
        # differ between the two call sites.
        got = self._compute(errtrace=False, functrace=True,
                            handlers={'ERR': 'e', 'DEBUG': 'd', 'INT': 'i'})
        assert got == {'ERR', 'INT'}

    def test_both_options_exempt_both(self):
        got = self._compute(errtrace=True, functrace=True,
                            handlers={'ERR': 'e', 'DEBUG': 'd', 'INT': 'i'})
        assert got == {'INT'}

    def test_neither_option_all_reset(self):
        got = self._compute(errtrace=False, functrace=False,
                            handlers={'ERR': 'e', 'DEBUG': 'd', 'INT': 'i'})
        assert got == {'ERR', 'DEBUG', 'INT'}

    def test_ignored_traps_never_listed_only(self):
        # An ignored ('') trap stays in effect (not in the listed-only set).
        got = self._compute(errtrace=False, functrace=False,
                            handlers={'INT': '', 'TERM': 't'})
        assert got == {'TERM'}
