"""ignoreeof / IGNOREEOF policy (reappraisal #17 M2).

bash 5.2 semantics, PTY-probed (tmp/probes-r17t2-interactive/):
IGNOREEOF=N ignores N consecutive EOFs then exits on the N+1st;
empty/non-numeric values mean 10; `set -o ignoreeof` binds IGNOREEOF=10
and `set +o` unbinds it (set_ignoreeof); the option flag tracks the
variable's existence in both directions (sv_ignoreeof).

The counter itself lives in the REPL loop and is exercised by the PTY
tier (tests/system/interactive/test_pty_smoke.py TestExitPolicy).
"""

from psh.interactive.eof_policy import ignoreeof_limit


class TestIgnoreeofLimit:
    """The limit computation (bash: variable is authoritative)."""

    def test_off_by_default(self, captured_shell):
        assert ignoreeof_limit(captured_shell.state) is None

    def test_numeric_variable(self, captured_shell):
        captured_shell.run_command("IGNOREEOF=2")
        assert ignoreeof_limit(captured_shell.state) == 2

    def test_zero_means_exit_on_first_eof(self, captured_shell):
        captured_shell.run_command("IGNOREEOF=0")
        assert ignoreeof_limit(captured_shell.state) == 0

    def test_empty_value_means_ten(self, captured_shell):
        captured_shell.run_command("IGNOREEOF=")
        assert ignoreeof_limit(captured_shell.state) == 10

    def test_non_numeric_means_ten(self, captured_shell):
        captured_shell.run_command("IGNOREEOF=abc")
        assert ignoreeof_limit(captured_shell.state) == 10

    def test_negative_not_all_digits_means_ten(self, captured_shell):
        captured_shell.run_command("IGNOREEOF=-5")
        assert ignoreeof_limit(captured_shell.state) == 10

    def test_unset_disables(self, captured_shell):
        captured_shell.run_command("IGNOREEOF=2")
        captured_shell.run_command("unset IGNOREEOF")
        assert ignoreeof_limit(captured_shell.state) is None

    def test_bare_option_fallback_is_ten(self, captured_shell):
        # Embedder/test path: option set without the variable.
        captured_shell.state.options['ignoreeof'] = True
        assert ignoreeof_limit(captured_shell.state) == 10


class TestOptionVariableCoupling:
    """set -o ignoreeof <-> IGNOREEOF (bash set_ignoreeof/sv_ignoreeof)."""

    def test_set_o_binds_ignoreeof_10(self, captured_shell):
        assert captured_shell.run_command("set -o ignoreeof") == 0
        assert captured_shell.state.get_variable('IGNOREEOF') == '10'
        assert captured_shell.state.options['ignoreeof'] is True
        assert ignoreeof_limit(captured_shell.state) == 10

    def test_set_plus_o_unbinds(self, captured_shell):
        captured_shell.run_command("set -o ignoreeof")
        assert captured_shell.run_command("set +o ignoreeof") == 0
        assert captured_shell.state.scope_manager.get_variable('IGNOREEOF') is None
        assert captured_shell.state.options['ignoreeof'] is False
        assert ignoreeof_limit(captured_shell.state) is None

    def test_assigning_variable_turns_option_on(self, captured_shell):
        captured_shell.run_command("IGNOREEOF=5")
        assert captured_shell.state.options['ignoreeof'] is True

    def test_unset_variable_turns_option_off(self, captured_shell):
        captured_shell.run_command("set -o ignoreeof")
        captured_shell.run_command("unset IGNOREEOF")
        assert captured_shell.state.options['ignoreeof'] is False
        assert ignoreeof_limit(captured_shell.state) is None

    def test_set_o_display_tracks_variable(self, captured_shell):
        captured_shell.run_command("IGNOREEOF=5")
        captured_shell.run_command("set -o")
        out = captured_shell.get_stdout()
        assert any('ignoreeof' in line and 'on' in line
                   for line in out.splitlines())
