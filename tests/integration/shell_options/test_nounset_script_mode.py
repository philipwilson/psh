"""
Tests for set -u (nounset) script-mode semantics.

Regression guards (verified against bash 5.2):
- The error used to print with a doubled prefix ("psh: psh: $x: unbound
  variable") because the expansion code wrapped the message in a "psh: "
  prefix that the printing handler added again.
- A non-interactive shell kept executing after the violation with rc 0;
  bash aborts with status 127.
- Out-of-range positional parameters ($5) skipped the nounset check.
"""

import subprocess
import sys


def run_psh(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True)


class TestNounsetScriptMode:
    def test_single_prefix_in_message(self):
        result = run_psh('set -u; echo $undef')
        assert 'psh: psh:' not in result.stderr
        assert 'undef: unbound variable' in result.stderr

    def test_message_format_matches_bash(self):
        """bash: `x: unbound variable` (no dollar sign for plain names)."""
        result = run_psh('set -u; echo $undef')
        assert result.stderr == 'psh: undef: unbound variable\n'

    def test_aborts_script_with_127(self):
        result = run_psh('set -u; echo $undef; echo after')
        assert result.returncode == 127
        assert 'after' not in result.stdout

    def test_braced_form_aborts_too(self):
        result = run_psh('set -u; echo ${undef}; echo after')
        assert result.returncode == 127
        assert 'after' not in result.stdout

    def test_out_of_range_positional_aborts(self):
        """bash keeps the $ for positionals: `$5: unbound variable`."""
        result = run_psh('set -u; echo $5; echo after')
        assert result.returncode == 127
        assert '$5: unbound variable' in result.stderr
        assert 'after' not in result.stdout

    def test_set_positional_ok(self):
        result = run_psh('set -u; set -- a b; echo $2')
        assert result.returncode == 0
        assert result.stdout == 'b\n'

    def test_default_operator_suppresses_error(self):
        result = run_psh('set -u; echo ${undef:-fallback}')
        assert result.returncode == 0
        assert result.stdout == 'fallback\n'

    def test_without_nounset_no_error(self):
        result = run_psh('echo "[$undef]"')
        assert result.returncode == 0
        assert result.stdout == '[]\n'
