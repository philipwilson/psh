"""Tests for psh -i flag and $- special variable."""
import subprocess
import sys


def run_psh(*args, stdin_input=None):
    """Run psh with given arguments and return (stdout, stderr, returncode)."""
    cmd = [sys.executable, '-m', 'psh'] + list(args)
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=10,
        input=stdin_input
    )
    return result.stdout, result.stderr, result.returncode


class TestDollarDash:
    """Tests for $- special variable expansion."""

    def test_dollar_dash_default_flags(self):
        """In -c mode $- is 'hBc' (bash): braceexpand + command-mode, but
        NOT 's' (not stdin mode) and NOT 'H' (histexpand is interactive-only)."""
        stdout, stderr, rc = run_psh('-c', 'echo $-')
        assert rc == 0
        flags = stdout.strip()
        assert flags == 'hBc', f"Expected 'hBc' (bash -c) but got: {flags}"

    def test_dollar_dash_with_interactive_flag(self):
        """psh -i -c should include 'i' in $-."""
        stdout, stderr, rc = run_psh('-i', '-c', 'echo $-')
        assert rc == 0
        flags = stdout.strip()
        assert 'i' in flags, f"Expected 'i' in $- with -i flag but got: {flags}"

    def test_dollar_dash_after_set_e(self):
        """set -e should add 'e' to $-."""
        stdout, stderr, rc = run_psh('-c', 'set -e; echo $-')
        assert rc == 0
        flags = stdout.strip()
        assert 'e' in flags, f"Expected 'e' in $- after set -e but got: {flags}"

    def test_dollar_dash_after_set_eux(self):
        """set -eux should add 'e', 'u', 'x' to $-."""
        stdout, stderr, rc = run_psh('-c', 'set -eux; echo $-')
        assert rc == 0
        flags = stdout.strip()
        assert 'e' in flags, f"Expected 'e' in $- but got: {flags}"
        assert 'u' in flags, f"Expected 'u' in $- but got: {flags}"
        assert 'x' in flags, f"Expected 'x' in $- but got: {flags}"

    def test_dollar_dash_interactive_with_set_x(self):
        """psh -i -c 'set -x; echo $-' should include both 'i' and 'x'."""
        stdout, stderr, rc = run_psh('-i', '-c', 'set -x; echo $-')
        assert rc == 0
        flags = stdout.strip()
        assert 'i' in flags, f"Expected 'i' in $- but got: {flags}"
        assert 'x' in flags, f"Expected 'x' in $- but got: {flags}"

    def test_dollar_dash_piped_with_interactive(self):
        """echo 'echo $-' | psh -i should include 'i' and 's'."""
        stdout, stderr, rc = run_psh('-i', stdin_input='echo $-\n')
        assert rc == 0
        flags = stdout.strip()
        assert 'i' in flags, f"Expected 'i' in $- but got: {flags}"
        assert 's' in flags, f"Expected 's' in $- but got: {flags}"

    def test_dollar_dash_command_mode_no_s_no_h(self):
        """bash -c 'echo $-' has 'c' (command mode), not 's', and no 'H'."""
        stdout, stderr, rc = run_psh('-c', 'echo $-')
        assert rc == 0
        flags = stdout.strip()
        assert 'c' in flags, f"Expected 'c' (command mode) but got: {flags}"
        assert 's' not in flags, f"Did not expect 's' in -c mode but got: {flags}"
        assert 'H' not in flags, f"Did not expect 'H' in -c mode but got: {flags}"

    def test_dollar_dash_in_braces(self):
        """${-} should work the same as $-."""
        stdout, stderr, rc = run_psh('-c', 'echo ${-}')
        assert rc == 0
        flags = stdout.strip()
        assert 'B' in flags, f"Expected 'B' in ${{-}} but got: {flags}"

    def test_dollar_dash_in_double_quotes(self):
        """"$-" should expand inside double quotes."""
        stdout, stderr, rc = run_psh('-c', 'echo "$-"')
        assert rc == 0
        flags = stdout.strip()
        assert 'B' in flags, f"Expected 'B' in quoted $- but got: {flags}"

    def test_dollar_dash_heredoc(self):
        """$- should expand in heredocs (the -c shell's flags: 'c', not 's')."""
        stdout, stderr, rc = run_psh('-c', 'cat <<EOF\n$-\nEOF')
        assert rc == 0
        flags = stdout.strip()
        assert 'c' in flags, f"Expected 'c' in heredoc $- but got: {flags}"


class TestDashIFlag:
    """Tests for psh -i flag behavior."""

    def test_dash_i_c_runs_and_exits(self):
        """psh -i -c 'echo ok' should print ok and exit (no hang)."""
        stdout, stderr, rc = run_psh('-i', '-c', 'echo ok')
        assert rc == 0
        assert stdout.strip() == 'ok'

    def test_dash_i_c_exit_code(self):
        """psh -i -c 'false' should exit with code 1."""
        stdout, stderr, rc = run_psh('-i', '-c', 'false')
        assert rc == 1

    def test_force_interactive_long_flag(self):
        """--force-interactive should work same as -i."""
        stdout, stderr, rc = run_psh('--force-interactive', '-c', 'echo $-')
        assert rc == 0
        flags = stdout.strip()
        assert 'i' in flags, f"Expected 'i' with --force-interactive but got: {flags}"

    def test_dash_i_with_piped_input(self):
        """psh -i with piped stdin should execute and exit."""
        stdout, stderr, rc = run_psh('-i', stdin_input='echo hello\n')
        assert rc == 0
        assert 'hello' in stdout

    def test_dash_i_help_text(self):
        """Help text should mention -i flag."""
        stdout, stderr, rc = run_psh('--help')
        assert rc == 0
        assert '-i' in stdout
