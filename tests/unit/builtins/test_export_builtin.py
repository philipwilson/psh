"""
Tests for the `export` builtin's option parsing and validation.

Regression guards (verified against bash 5.2):
- `export -p` used to create an environment variable literally named `-p`.
- `export 1bad=x` used to succeed with rc 0 (bash: invalid identifier, rc 1).
- `export -n` silently corrupted instead of removing the export attribute.
"""

import os


class TestExportValidation:
    def test_invalid_identifier_rejected(self, captured_shell):
        result = captured_shell.run_command('export 1bad=x')
        assert result == 1
        assert 'not a valid identifier' in captured_shell.get_stderr()

    def test_invalid_identifier_does_not_stop_processing(self, captured_shell):
        """bash reports the bad name but still exports the good one."""
        result = captured_shell.run_command('export 1bad=x good=y')
        assert result == 1
        assert captured_shell.state.get_variable('good') == 'y'
        assert captured_shell.state.env.get('good') == 'y'

    def test_underscore_name_ok(self, captured_shell):
        result = captured_shell.run_command('export _ok=1')
        assert result == 0
        assert captured_shell.state.env.get('_ok') == '1'

    def test_invalid_option_exit_2(self, captured_shell):
        result = captured_shell.run_command('export -q')
        assert result == 2


class TestExportOptions:
    def test_dash_p_does_not_create_variable(self, captured_shell):
        """Regression: -p literally became an env var named '-p'."""
        result = captured_shell.run_command('export -p')
        assert result == 0
        assert '-p' not in captured_shell.state.env
        assert 'declare -x' in captured_shell.get_stdout()

    def test_dash_p_with_name_prints_only_that_export(self, captured_shell):
        captured_shell.run_command('export E1=v1')
        captured_shell.clear_output()
        result = captured_shell.run_command('export -p E1')
        assert result == 0
        assert captured_shell.get_stdout() == 'declare -x E1="v1"\n'

    def test_dash_n_removes_export_keeps_variable(self, captured_shell):
        captured_shell.run_command('export E2=v2')
        result = captured_shell.run_command('export -n E2')
        assert result == 0
        assert 'E2' not in captured_shell.state.env
        # Policy (v0.312): os.environ is read-once at startup and never
        # written, so the export never touched the runner's environment.
        assert 'E2' not in os.environ
        assert captured_shell.state.get_variable('E2') == 'v2'

    def test_dash_n_with_assignment(self, captured_shell):
        """export -n NAME=value assigns the value without exporting."""
        result = captured_shell.run_command('export -n E3=v3')
        assert result == 0
        assert 'E3' not in captured_shell.state.env
        assert captured_shell.state.get_variable('E3') == 'v3'

    def test_double_dash_ends_options(self, captured_shell):
        result = captured_shell.run_command('export -- X=1')
        assert result == 0
        assert captured_shell.state.env.get('X') == '1'


class TestExportBasics:
    def test_assignment_exports(self, captured_shell):
        result = captured_shell.run_command('export EXPORT_TEST_FOO=bar')
        assert result == 0
        assert captured_shell.state.env.get('EXPORT_TEST_FOO') == 'bar'
        captured_shell.run_command('unset EXPORT_TEST_FOO')

    def test_existing_variable_export(self, captured_shell):
        # Unique name + unset: shells in this process share fixtures and
        # children inherit state.env, so generic names like V can leak
        # into later tests' shells. (os.environ itself is never written
        # as of v0.312.)
        captured_shell.run_command('EXPORT_TEST_V=val')
        result = captured_shell.run_command('export EXPORT_TEST_V')
        assert result == 0
        assert captured_shell.state.env.get('EXPORT_TEST_V') == 'val'
        captured_shell.run_command('unset EXPORT_TEST_V')

    def test_no_args_prints_exports(self, captured_shell):
        captured_shell.run_command('export PRINTME=1')
        captured_shell.clear_output()
        result = captured_shell.run_command('export')
        assert result == 0
        assert 'declare -x PRINTME="1"' in captured_shell.get_stdout()


class TestExportOptionReflectionSpecials:
    """`export -p` lists SHELLOPTS/BASHOPTS ONLY when they are exported —
    bash 5.2 (r19-P8, P8-probes/02 + /03).

    These option-reflection specials have no stored variable cell; the
    no-arg enumeration (all_exported_variables) must inject them subject to
    the SAME exported filter it uses for stored vars, so the default case
    still omits them (like bash) while an explicit `export SHELLOPTS`
    surfaces the `declare -rx` row.
    """

    def test_default_export_p_omits_specials(self, captured_shell):
        """Not exported by default -> export -p must not list them (bash)."""
        result = captured_shell.run_command('export -p')
        assert result == 0
        out = captured_shell.get_stdout()
        assert 'SHELLOPTS' not in out
        assert 'BASHOPTS' not in out

    def test_export_shellopts_then_listed(self, captured_shell):
        """`export SHELLOPTS; export -p` lists `declare -rx SHELLOPTS=...`."""
        captured_shell.run_command('export SHELLOPTS')
        captured_shell.clear_output()
        result = captured_shell.run_command('export -p')
        assert result == 0
        out = captured_shell.get_stdout()
        assert 'declare -rx SHELLOPTS=' in out

    def test_export_bashopts_then_listed(self, captured_shell):
        """Symmetric: exported BASHOPTS shows a `declare -rx BASHOPTS=` row."""
        captured_shell.run_command('export BASHOPTS')
        captured_shell.clear_output()
        result = captured_shell.run_command('export -p')
        assert result == 0
        out = captured_shell.get_stdout()
        assert 'declare -rx BASHOPTS=' in out
