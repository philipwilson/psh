"""break/continue/return are ordinary builtins, not reserved words (D2).

bash lexes break/continue/return as plain words backed by (special)
builtins: they can be shadowed by functions, their redirections apply
(`break 2>/dev/null`), and they compose in pipelines and && / || lists.
psh matches by parsing them as simple commands dispatched to the builtins
in psh/builtins/loop_control.py. All expectations here are probe-verified
against bash 5.2 (tmp truth table, reappraisal #15 D2); the same cases are
pinned live in tests/behavioral/golden_cases.yaml.
"""

import subprocess
import sys

import pytest


def run_psh(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True)


class TestParsedAsSimpleCommands:
    def test_type_reports_shell_builtin(self, captured_shell):
        rc = captured_shell.run_command('type -t break continue return')
        assert rc == 0
        assert captured_shell.get_stdout() == 'builtin\nbuiltin\nbuiltin\n'

    def test_break_with_redirect_parses_and_applies(self, captured_shell):
        rc = captured_shell.run_command('break 2>/dev/null; echo rc=$?')
        assert rc == 0
        assert captured_shell.get_stdout() == 'rc=0\n'
        assert captured_shell.get_stderr() == ''

    def test_break_outside_loop_warns_status_0(self, captured_shell):
        rc = captured_shell.run_command('break; echo rc=$?')
        assert rc == 0
        assert captured_shell.get_stdout() == 'rc=0\n'
        assert 'only meaningful' in captured_shell.get_stderr()

    def test_break_composes_with_and_or(self, captured_shell):
        # Outside a loop break is a no-op with status 0, so && continues.
        rc = captured_shell.run_command('break && echo yes')
        assert rc == 0
        assert captured_shell.get_stdout() == 'yes\n'

    def test_continue_composes_with_or(self, captured_shell):
        rc = captured_shell.run_command('continue || echo no')
        assert rc == 0
        assert captured_shell.get_stdout() == ''


class TestFunctionShadowing:
    def test_break_function_shadows_builtin_in_loop(self, captured_shell):
        rc = captured_shell.run_command(
            'break(){ echo custom-break; }; '
            'for i in 1 2; do break; done; echo after-$i')
        assert rc == 0
        assert captured_shell.get_stdout() == \
            'custom-break\ncustom-break\nafter-2\n'

    def test_command_and_builtin_bypass_break_function(self, captured_shell):
        for bypass in ('command', 'builtin'):
            captured_shell.clear_output()
            rc = captured_shell.run_command(
                f'break(){{ echo custom; }}; '
                f'for i in 1 2; do {bypass} break; echo in-$i; done; echo after')
            assert rc == 0
            assert captured_shell.get_stdout() == 'after\n', bypass

    def test_return_function_shadows_builtin(self, captured_shell):
        rc = captured_shell.run_command(
            'return(){ echo custom-return; }; '
            'f(){ return; echo in-f; }; f; echo rc=$?')
        assert rc == 0
        assert captured_shell.get_stdout() == 'custom-return\nin-f\nrc=0\n'


class TestLoopSemanticsPreserved:
    def test_variable_expanding_to_break_breaks(self, captured_shell):
        rc = captured_shell.run_command(
            'c=break; for i in 1 2; do $c; echo in-$i; done; echo after')
        assert rc == 0
        assert captured_shell.get_stdout() == 'after\n'

    def test_break_in_while_condition_exits_loop(self, captured_shell):
        rc = captured_shell.run_command(
            'while break; do echo body; done; echo rc=$?')
        assert rc == 0
        assert captured_shell.get_stdout() == 'rc=0\n'
        assert captured_shell.get_stderr() == ''

    def test_break_in_until_condition_exits_loop(self, captured_shell):
        rc = captured_shell.run_command(
            'until break; do echo body; done; echo rc=$?')
        assert rc == 0
        assert captured_shell.get_stdout() == 'rc=0\n'

    def test_level_argument_still_expands(self, captured_shell):
        rc = captured_shell.run_command(
            'n=1; for i in 1 2; do break $n; echo in; done; echo after')
        assert rc == 0
        assert captured_shell.get_stdout() == 'after\n'

    @pytest.mark.parametrize("cmd,expected", [
        # break 2 exits both loops
        ('for i in a b; do for j in 1 2; do break 2; done; echo j-done; done; '
         'echo after', 'after\n'),
        # continue 2 continues the OUTER loop
        ('for i in a b; do for j in 1 2; do continue 2; echo nc; done; '
         'echo j-done-$i; done; echo after', 'after\n'),
    ])
    def test_level_matrix(self, captured_shell, cmd, expected):
        rc = captured_shell.run_command(cmd)
        assert rc == 0
        assert captured_shell.get_stdout() == expected

    def test_break_in_function_does_not_break_caller_loop(self, captured_shell):
        # Function bodies are a fresh loop scope (v0.518, preserved).
        rc = captured_shell.run_command(
            'f(){ break; echo in-f; }; '
            'for i in 1 2; do f; echo in-$i; done; echo after')
        assert rc == 0
        assert captured_shell.get_stdout() == \
            'in-f\nin-1\nin-f\nin-2\nafter\n'
        assert 'only meaningful' in captured_shell.get_stderr()


class TestArgumentErrors:
    """The bash-matched argument diagnostics moved into the builtins.

    Hard argument errors abort a NON-INTERACTIVE shell (break/continue/
    return are POSIX special builtins), so these run psh -c in a
    subprocess where script-mode abort applies.
    """

    def test_break_non_numeric_aborts_script(self):
        r = run_psh('for i in 1 2; do break abc; done; echo rc=$?')
        assert r.returncode == 128
        assert r.stdout == ''
        assert 'numeric argument required' in r.stderr

    def test_break_too_many_arguments(self):
        r = run_psh('for i in 1 2; do break 1 2; done; echo rc=$?')
        assert r.returncode == 1
        assert r.stdout == ''
        assert 'too many arguments' in r.stderr

    def test_break_zero_out_of_range_exits_loops_status_1(self):
        r = run_psh('for i in 1 2; do break 0; done; echo rc=$?')
        assert r.returncode == 0
        assert r.stdout == 'rc=1\n'
        assert 'loop count out of range' in r.stderr

    def test_return_too_many_arguments_aborts(self):
        r = run_psh('f(){ return 1 2; echo in; }; f; echo rc=$?')
        assert r.returncode == 1
        assert r.stdout == ''
        assert 'too many arguments' in r.stderr


class TestBackgroundedControlFlowNoLeak:
    """A break/continue/return backgrounded with & must not leak an internal
    error. It runs in a forked child, so the control-flow signal cannot cross
    the process boundary — the child just ends (bash is silent). Regression
    for the D2 empty "psh: error:" leak: the LoopBreak/LoopContinue/
    FunctionReturn escaping the launcher child was caught by the generic
    `except Exception` and printed "psh: error: " with no message.

    Subprocess-based (& + wait): the background job lives in the child psh,
    so these are xdist-safe and assert the child's real stderr.
    """

    def test_break_backgrounded_in_loop_is_silent(self):
        r = run_psh('for i in 1 2; do break & wait; echo in-$i; done; echo after')
        assert r.returncode == 0
        assert r.stdout == 'in-1\nin-2\nafter\n'
        assert 'psh: error:' not in r.stderr
        assert r.stderr == ''

    def test_continue_backgrounded_in_loop_is_silent(self):
        r = run_psh('for i in 1 2; do continue & wait; echo in-$i; done; echo after')
        assert r.returncode == 0
        assert r.stdout == 'in-1\nin-2\nafter\n'
        assert 'psh: error:' not in r.stderr
        assert r.stderr == ''

    def test_return_backgrounded_in_function_is_silent(self):
        r = run_psh('f(){ return & wait; echo in-fn; }; f; echo after')
        assert r.returncode == 0
        assert r.stdout == 'in-fn\nafter\n'
        assert 'psh: error:' not in r.stderr
        assert r.stderr == ''

    def test_brace_group_break_backgrounded_no_empty_error(self):
        # bash prints its "only meaningful in a loop" warning for the brace-
        # group form; psh stays silent (consistent with `{ break; } | cat`).
        # The hard requirement either way: NO empty "psh: error:" leak.
        r = run_psh('for i in 1 2; do { break; } & wait; echo in-$i; done; echo after')
        assert r.returncode == 0
        assert r.stdout == 'in-1\nin-2\nafter\n'
        assert 'psh: error:' not in r.stderr

    def test_backgrounded_return_status_reaches_child(self):
        # bash: the child exits with the return's status (silent).
        r = run_psh('f(){ return 5 & p=$!; wait $p; echo rc=$?; }; f')
        assert r.returncode == 0
        assert r.stdout == 'rc=5\n'
        assert 'psh: error:' not in r.stderr

    def test_break_backgrounded_outside_loop_still_warns(self):
        # Guard the other direction: with no enclosing loop the builtin (in
        # the child) prints bash's warning and exits 0 — unchanged by the fix.
        r = run_psh('break & wait; echo after')
        assert r.returncode == 0
        assert r.stdout == 'after\n'
        assert 'only meaningful' in r.stderr
        assert 'psh: error:' not in r.stderr
