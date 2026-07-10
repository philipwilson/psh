"""Systemic runtime-error location prefix (task #21 [#35]).

bash prefixes every runtime error with ``<$0>: [line N: ]`` — the shell's
invocation name (``$0``) plus, when NON-interactive, the source line of the
failing command: ``bash: line 1: trap: -x: invalid option``. psh used to emit
the bare message. These pins lock the prefix across the mode × error-class
matrix. psh's ``$0`` analogue is ``script_name`` ("psh" for ``-c``/stdin, the
script path in script mode). Follow-up *usage* lines are NOT prefixed.

Representative cells only — the exhaustive truth table lives in the wave ledger.
Each cell was demonstrated RED on base d6ed461c (bare message, no prefix).
"""

import subprocess
import sys


def _psh_c(script, cwd=None):
    """Run ``psh -c script`` in a subprocess; return the CompletedProcess."""
    return subprocess.run(
        [sys.executable, '-m', 'psh', '-c', script],
        capture_output=True, text=True, cwd=cwd)


class TestBuiltinErrorPrefix:
    """Builtin runtime errors: `psh: line N: <builtin>: <msg>` (non-interactive)."""

    def test_bad_option_is_location_prefixed(self, captured_shell):
        captured_shell.run_command('trap -x')
        lines = captured_shell.get_stderr().splitlines()
        assert lines[0] == 'psh: line 1: trap: -x: invalid option'

    def test_usage_line_is_NOT_prefixed(self, captured_shell):
        # The dual-line shape: the runtime error is prefixed, the usage line
        # that follows carries only the builtin name (bash builtin_usage).
        captured_shell.run_command('trap -x')
        lines = captured_shell.get_stderr().splitlines()
        assert lines[0] == 'psh: line 1: trap: -x: invalid option'
        assert lines[1] == 'trap: usage: trap [-lp] [[arg] signal_spec ...]'

    def test_bad_operand_is_prefixed(self, captured_shell):
        captured_shell.run_command('cd /nonexistent_zz_99')
        assert captured_shell.get_stderr().splitlines()[0] == \
            'psh: line 1: cd: /nonexistent_zz_99: No such file or directory'

    def test_runtime_error_is_prefixed(self, captured_shell):
        captured_shell.run_command('local x')
        assert captured_shell.get_stderr().splitlines()[0] == \
            'psh: line 1: local: can only be used in a function'

    def test_line_number_tracks_the_failing_command(self, captured_shell):
        captured_shell.run_command('echo a\necho b\ntrap -x')
        assert captured_shell.get_stderr().splitlines()[0] == \
            'psh: line 3: trap: -x: invalid option'

    def test_pure_usage_error_is_unprefixed(self, captured_shell):
        # printf with no args goes straight to builtin_usage — no prefix at all.
        captured_shell.run_command('printf')
        assert captured_shell.get_stderr().splitlines()[0] == \
            'printf: usage: printf [-v var] format [arguments]'


class TestReturnDoubleError:
    """`return <nonnum>` outside a function: TWO prefixed lines (bash)."""

    def test_return_nonnumeric_outside_function(self, captured_shell):
        rc = captured_shell.run_command('return abc')
        assert rc == 2
        assert captured_shell.get_stderr().splitlines() == [
            'psh: line 1: return: abc: numeric argument required',
            "psh: line 1: return: can only `return' from a function or sourced script",
        ]

    def test_return_numeric_outside_function_single_line(self, captured_shell):
        rc = captured_shell.run_command('return 5')
        assert rc == 2
        assert captured_shell.get_stderr().splitlines() == [
            "psh: line 1: return: can only `return' from a function or sourced script",
        ]


class TestReportErrorNoBuiltinName:
    """Assignment/readonly failures: prefixed but WITHOUT a builtin name."""

    def test_export_readonly_has_no_builtin_name(self, captured_shell):
        captured_shell.run_command('readonly r=1; export r=2')
        assert captured_shell.get_stderr().splitlines()[0] == \
            'psh: line 1: r: readonly variable'

    def test_cd_readonly_pwd_has_no_builtin_name(self, captured_shell):
        # cd reporting a readonly OLDPWD/PWD names the variable, no `cd:`.
        captured_shell.run_command('readonly PWD; cd /tmp')
        err = captured_shell.get_stderr()
        assert 'psh: line 1: PWD: readonly variable' in err


class TestGetoptsSpecialForm:
    """getopts uses `<$0>: msg` — no `line N:`, no `getopts:` name (bash quirk)."""

    def test_illegal_option(self, captured_shell):
        captured_shell.run_command('set -- -q; getopts "ab" opt')
        assert captured_shell.get_stderr().splitlines()[0] == \
            'psh: illegal option -- q'

    def test_missing_required_argument(self, captured_shell):
        captured_shell.run_command('set -- -a; getopts "a:b" opt')
        assert captured_shell.get_stderr().splitlines()[0] == \
            'psh: option requires an argument -- a'


class TestInteractiveDropsLineNumber:
    """Interactive shells prefix with `<$0>: ` but omit `line N:` (bash -i)."""

    def test_interactive_no_line_number(self, captured_shell):
        captured_shell.state.options['interactive'] = True
        try:
            captured_shell.run_command('cd /nonexistent_zz_99')
        finally:
            captured_shell.state.options['interactive'] = False
        assert captured_shell.get_stderr().splitlines()[0] == \
            'psh: cd: /nonexistent_zz_99: No such file or directory'


class TestTierCExpansionAndExec:
    """Non-builtin runtime errors share the prefix (Tier C)."""

    def test_command_not_found_is_prefixed(self):
        r = _psh_c('nosuchcmd_zz_123')
        assert r.returncode == 127
        assert r.stderr.splitlines()[0] == \
            'psh: line 1: nosuchcmd_zz_123: command not found'

    def test_set_u_unbound_is_prefixed(self):
        r = _psh_c('set -u; echo $undef_zz_123')
        assert 'psh: line 1: undef_zz_123: unbound variable' in r.stderr

    def test_colon_question_is_prefixed(self, captured_shell):
        captured_shell.run_command('unset x; echo ${x:?custom message}')
        assert captured_shell.get_stderr().splitlines()[0] == \
            'psh: line 1: x: custom message'

    def test_arithmetic_readonly_is_prefixed(self, captured_shell):
        captured_shell.run_command('readonly r=1; (( r=2 ))')
        assert captured_shell.get_stderr().splitlines()[0] == \
            'psh: line 1: r: readonly variable'

    def test_bad_substitution_is_prefixed(self, captured_shell):
        captured_shell.run_command('echo ${!x*bad}')
        assert captured_shell.get_stderr().splitlines()[0] == \
            'psh: line 1: ${!x*bad}: bad substitution'


class TestScriptModeUsesScriptName:
    """In script mode `<$0>` is the script path and `line N` tracks the file."""

    def test_script_name_and_line(self, tmp_path):
        script = tmp_path / 'errs.sh'
        script.write_text('echo first\ntrap -x\ncd /nonexistent_zz_99\n')
        r = subprocess.run([sys.executable, '-m', 'psh', str(script)],
                           capture_output=True, text=True)
        lines = r.stderr.splitlines()
        assert f'{script}: line 2: trap: -x: invalid option' in lines
        assert f'{script}: line 3: cd: /nonexistent_zz_99: No such file or directory' in lines
