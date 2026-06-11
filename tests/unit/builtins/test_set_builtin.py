"""
Tests for the `set` builtin's option parsing.

Regression guards (verified against bash 5.2):
- `set -o errexit -o pipefail` used to stop after the first -o, silently
  dropping pipefail.
- `set -o vi` printed "Edit mode set to vi" to stdout (bash is silent).
- Bare `set` printed a non-bash `edit_mode=...` line.
- `set -euo pipefail` (trailing 'o' in a cluster) was rejected.
"""


class TestSetLongOptions:
    def test_multiple_o_options_all_applied(self, captured_shell):
        """Regression: processing must not stop after the first -o."""
        result = captured_shell.run_command('set -o errexit -o pipefail')
        assert result == 0
        assert captured_shell.state.options['errexit'] is True
        assert captured_shell.state.options['pipefail'] is True

    def test_o_then_short_flags(self, captured_shell):
        result = captured_shell.run_command('set -o pipefail -x')
        assert result == 0
        assert captured_shell.state.options['pipefail'] is True
        assert captured_shell.state.options['xtrace'] is True

    def test_plus_o_disables(self, captured_shell):
        captured_shell.run_command('set -o errexit')
        result = captured_shell.run_command('set +o errexit')
        assert result == 0
        assert captured_shell.state.options['errexit'] is False

    def test_invalid_option_name_exit_2(self, captured_shell):
        result = captured_shell.run_command('set -o no_such_option_zz')
        assert result == 2
        assert 'invalid option name' in captured_shell.get_stderr()

    def test_set_o_vi_is_silent(self, captured_shell):
        """bash prints nothing when changing the edit mode."""
        result = captured_shell.run_command('set -o vi')
        assert result == 0
        assert captured_shell.get_stdout() == ""

    def test_set_o_emacs_is_silent(self, captured_shell):
        result = captured_shell.run_command('set -o emacs')
        assert result == 0
        assert captured_shell.get_stdout() == ""


class TestSetShortClusters:
    def test_euo_pipefail_cluster(self, captured_shell):
        """The canonical strict-mode idiom must work as one argument."""
        result = captured_shell.run_command('set -euo pipefail')
        assert result == 0
        assert captured_shell.state.options['errexit'] is True
        assert captured_shell.state.options['nounset'] is True
        assert captured_shell.state.options['pipefail'] is True

    def test_plus_cluster_disables(self, captured_shell):
        captured_shell.run_command('set -eu')
        result = captured_shell.run_command('set +eu')
        assert result == 0
        assert captured_shell.state.options['errexit'] is False
        assert captured_shell.state.options['nounset'] is False

    def test_invalid_short_flag_exit_2(self, captured_shell):
        result = captured_shell.run_command('set -q')
        assert result == 2

    def test_options_then_positional_params(self, captured_shell):
        result = captured_shell.run_command('set -e foo bar; echo $1 $2')
        assert result == 0
        assert captured_shell.get_stdout() == "foo bar\n"
        assert captured_shell.state.options['errexit'] is True

    def test_double_dash_starts_positionals(self, captured_shell):
        result = captured_shell.run_command(
            'set -- -e notanoption; printf "%s %s\\n" "$1" "$2"')
        assert result == 0
        assert captured_shell.get_stdout() == "-e notanoption\n"
        # And -e was NOT applied as an option
        assert captured_shell.state.options['errexit'] is False


class TestRemovedParserOptions:
    """The four dead parser options (validate-context, validate-semantics,
    analyze-semantics, enhanced-error-recovery) had zero consumers and were
    removed. Like bash with any unknown -o name, they must now be rejected
    with rc 2 (verified: `bash -c 'set -o validate-context'` → rc 2,
    "invalid option name").
    """

    DEAD_OPTIONS = ['validate-context', 'validate-semantics',
                    'analyze-semantics', 'enhanced-error-recovery']

    def test_dead_options_rejected_rc2(self, captured_shell):
        for opt in self.DEAD_OPTIONS:
            result = captured_shell.run_command(f'set -o {opt}')
            assert result == 2, opt
            assert 'invalid option name' in captured_shell.get_stderr()
            captured_shell.clear_output()

    def test_dead_options_plus_o_rejected_rc2(self, captured_shell):
        for opt in self.DEAD_OPTIONS:
            result = captured_shell.run_command(f'set +o {opt}')
            assert result == 2, opt
            captured_shell.clear_output()

    def test_dead_options_not_listed(self, captured_shell):
        for listing in ('set -o', 'set +o'):
            result = captured_shell.run_command(listing)
            assert result == 0
            out = captured_shell.get_stdout()
            for opt in self.DEAD_OPTIONS:
                assert opt not in out, (listing, opt)
            captured_shell.clear_output()

    def test_dead_options_not_in_help(self, captured_shell):
        result = captured_shell.run_command('help set')
        assert result == 0
        out = captured_shell.get_stdout()
        for opt in self.DEAD_OPTIONS:
            assert opt not in out, opt


class TestSetDisplay:
    def test_bare_set_has_no_edit_mode_line(self, captured_shell):
        """Regression: bare `set` printed a non-bash edit_mode= line."""
        result = captured_shell.run_command('set')
        assert result == 0
        assert 'edit_mode=' not in captured_shell.get_stdout()

    def test_set_o_lists_options(self, captured_shell):
        result = captured_shell.run_command('set -o')
        assert result == 0
        out = captured_shell.get_stdout()
        assert 'errexit' in out
        assert 'pipefail' in out

    def test_set_plus_o_reenterable_format(self, captured_shell):
        result = captured_shell.run_command('set +o')
        assert result == 0
        out = captured_shell.get_stdout()
        assert 'set +o errexit' in out or 'set -o errexit' in out
