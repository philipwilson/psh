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


class TestTrapInvalidSignalParity:
    """trap's SET path and its -p path both location-prefix identically.

    Regression pin for the F1 bounce: the set-trap invalid-signal diagnostic
    (trap_manager.py) bypassed Builtin.error, so it stayed bare while the -p
    sibling was prefixed — a same-builtin inconsistency.
    """

    def test_set_path_is_prefixed(self, captured_shell):
        captured_shell.run_command('trap "echo hi" NOPE')
        assert captured_shell.get_stderr().splitlines()[0] == \
            'psh: line 1: trap: NOPE: invalid signal specification'

    def test_ignore_set_path_is_prefixed(self, captured_shell):
        captured_shell.run_command('trap "" NOPE')
        assert captured_shell.get_stderr().splitlines()[0] == \
            'psh: line 1: trap: NOPE: invalid signal specification'

    def test_set_and_p_paths_are_identical(self, captured_shell):
        captured_shell.run_command('trap "echo hi" NOPE')
        set_line = captured_shell.get_stderr().splitlines()[0]
        captured_shell.clear_output()
        captured_shell.run_command('trap -p NOPE')
        p_line = captured_shell.get_stderr().splitlines()[0]
        assert set_line == p_line == \
            'psh: line 1: trap: NOPE: invalid signal specification'


class TestBareRowResweepFinds:
    """Prefix-class sites found by the F2 bounce's all-bare-rows re-probe.

    Each bash-prefixes a runtime diagnostic that psh emitted bare; each is the
    same class as F2 (a `warning:`/expansion diagnostic bash location-prefixes).
    """

    def test_nameref_cycle_warning_is_prefixed(self, captured_shell):
        captured_shell.run_command('declare -n a=b; declare -n b=a; echo $a')
        assert captured_shell.get_stderr().splitlines()[0] == \
            'psh: line 1: warning: a: circular name reference'

    def test_nameref_cycle_warning_tracks_line(self, captured_shell):
        captured_shell.run_command('echo x\ndeclare -n a=b\ndeclare -n b=a\necho $a')
        assert 'psh: line 4: warning: a: circular name reference' in \
            captured_shell.get_stderr()

    def test_cmdsub_null_byte_warning_is_prefixed(self):
        r = _psh_c('x=$(printf "a\\0b"); echo done')
        assert r.stderr.splitlines()[0] == \
            'psh: line 1: warning: command substitution: ignored null byte in input'

    def test_shellopts_env_import_bad_option_is_prefixed(self):
        # bash uses its startup sentinel `line 0` (argv0, no command run yet).
        import os
        env = dict(os.environ, SHELLOPTS='nosuchopt_zz')
        r = subprocess.run([sys.executable, '-m', 'psh', '-c', 'true'],
                           capture_output=True, text=True, env=env)
        assert r.stderr.splitlines()[0] == \
            'psh: line 0: nosuchopt_zz: invalid option name'

    def test_set_u_in_script_mode_prefixed_with_script_name(self, tmp_path):
        script = tmp_path / 'su.sh'
        script.write_text('set -u\necho $undef_zz\n')
        r = subprocess.run([sys.executable, '-m', 'psh', str(script)],
                           capture_output=True, text=True)
        assert r.stderr.splitlines()[0] == \
            f'{script}: line 2: undef_zz: unbound variable'


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
