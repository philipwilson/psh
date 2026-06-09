"""
Script-mode tests for errexit/readonly fatality.

These run psh via subprocess (`psh -c`), the mode where the sys.exit paths
live — the interactive-mode `shell` fixture never reaches them, which is how
the original errexit divergences survived. Expected behavior verified
against bash 5.2.
"""

import subprocess
import sys


def run_psh(cmd):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True)


class TestErrexitScriptMode:
    def test_plain_failure_aborts(self):
        result = run_psh('set -e; false; echo no')
        assert result.returncode == 1
        assert result.stdout == ''

    def test_if_condition_does_not_abort(self):
        result = run_psh('set -e; if false; then :; fi; echo after')
        assert result.returncode == 0
        assert result.stdout == 'after\n'

    def test_nonfinal_and_member_does_not_abort(self):
        result = run_psh('set -e; false && true; echo after')
        assert result.returncode == 0
        assert result.stdout == 'after\n'

    def test_negation_does_not_abort(self):
        result = run_psh('set -e; ! true; echo after')
        assert result.returncode == 0
        assert result.stdout == 'after\n'

    def test_subshell_inherits_errexit_and_aborts(self):
        result = run_psh('set -e; (false; echo notreached); echo after')
        assert result.returncode == 1
        assert result.stdout == ''

    def test_strict_mode_idiom_end_to_end(self):
        """The canonical set -euo pipefail preamble works as in bash."""
        result = run_psh(
            'set -euo pipefail\n'
            'ok() { return 0; }\n'
            'if ! ok; then echo bad; fi\n'
            'v=$(false) || v=default\n'
            'echo "v=$v"\n'
            'false | true && echo unreached || echo pipefail-works\n')
        assert result.returncode == 0
        assert result.stdout == 'v=default\npipefail-works\n'


class TestReadonlyFatality:
    def test_pure_assignment_aborts_script(self):
        result = run_psh('readonly c=1; c=2; echo after')
        assert result.returncode == 1
        assert 'after' not in result.stdout
        assert 'readonly variable' in result.stderr

    def test_command_prefix_assignment_does_not_abort(self):
        """bash: RO=v cmd fails (rc 1) but the script continues."""
        result = run_psh('readonly c=1; c=2 true; echo after')
        assert result.returncode == 0
        assert result.stdout == 'after\n'
        assert 'readonly variable' in result.stderr
