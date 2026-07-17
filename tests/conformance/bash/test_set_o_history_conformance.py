"""Conformance tests for `set -o history` / `set +o history` (bash).

Pins the L6 fix (reappraisal #7): bash accepts `history` as a `set -o`
option name (it toggles command-history recording). Previously psh rejected
it with "invalid option name" (rc 2). Both the toggle (rc 0) and the
`set -o` listing of its state are matched against bash 5.2 (non-interactive,
where the default is `history off`... but psh defaults it on; we therefore
pin the ACCEPTANCE and round-trip behavior, which is shell-state-independent).
"""

import sys

from shell_oracle import resolve_bash

BASH = resolve_bash().path


class TestSetOHistory:
    """`set -o history` and `set +o history` are accepted (rc 0)."""

    def _run(self, shell_cmd, script):
        import subprocess
        return subprocess.run(shell_cmd + ['-c', script],
                              capture_output=True, text=True)

    def test_disable_accepted(self):
        psh = self._run([sys.executable, '-m', 'psh'],
                        'set +o history; echo rc=$?')
        bash = self._run([BASH], 'set +o history; echo rc=$?')
        assert psh.stdout == bash.stdout == 'rc=0\n'

    def test_enable_accepted(self):
        psh = self._run([sys.executable, '-m', 'psh'],
                        'set -o history; echo rc=$?')
        bash = self._run([BASH], 'set -o history; echo rc=$?')
        assert psh.stdout == bash.stdout == 'rc=0\n'

    def test_round_trips_in_listing(self):
        """`set +o history` then `set -o` lists `history off`."""
        psh = self._run([sys.executable, '-m', 'psh'],
                        'set +o history; set -o')
        assert 'history' in psh.stdout
        # The toggled-off state is reflected.
        line = [ln for ln in psh.stdout.splitlines() if ln.startswith('history')]
        assert line and line[0].split()[-1] == 'off'

    def test_enable_then_listing_shows_on(self):
        psh = self._run([sys.executable, '-m', 'psh'],
                        'set -o history; set -o')
        line = [ln for ln in psh.stdout.splitlines() if ln.startswith('history')]
        assert line and line[0].split()[-1] == 'on'
