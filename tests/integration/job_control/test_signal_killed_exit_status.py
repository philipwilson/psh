"""Exit status of a foreground external command killed by a signal.

POSIX: a command terminated by signal N reports status 128+N. Pinned to
bash 5.2:

    SIGINT  (2)  -> 130
    SIGTERM (15) -> 143
    SIGKILL (9)  -> 137
    SIGPIPE (13) -> 141 (visible via pipefail / PIPESTATUS)

Determinism over realism: rather than racing a real signal at psh
in-process, each case drives psh in a subprocess running a child that
sends the signal to *itself* (`sh -c 'kill -N $$'`), and asserts the
``$?`` psh computes. No timing, no flake.

The ``job_control`` path is auto-marked ``serial`` (these spawn/kill/wait
on processes — xdist-unsafe).
"""

import subprocess
import sys

import pytest


def run_psh(cmd, timeout=15):
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True, timeout=timeout)


def run_bash(cmd, timeout=15):
    return subprocess.run(['bash', '-c', cmd],
                          capture_output=True, text=True, timeout=timeout)


class TestSignalKilledExitStatus:
    """A self-killing child yields 128+signum, matching bash."""

    @pytest.mark.parametrize('signame,expected', [
        ('INT', 130),    # 128 + 2
        ('TERM', 143),   # 128 + 15
        ('KILL', 137),   # 128 + 9
    ])
    def test_self_kill_exit_status(self, signame, expected):
        # The child sends the signal to its own pid ($$). stderr is
        # discarded so the OS "Terminated"/"Killed" notice doesn't pollute
        # the comparison.
        cmd = (
            f'sh -c "kill -{signame} \\$\\$" 2>/dev/null; '
            'echo rc=$?'
        )
        psh = run_psh(cmd)
        assert psh.stdout == f'rc={expected}\n', psh.stderr
        # Cross-check against bash so the expectation is bash-pinned.
        bash = run_bash(cmd)
        assert bash.stdout == psh.stdout


class TestSigpipeFromPipeline:
    """A pipeline producer killed by SIGPIPE (reader closed early)."""

    def test_pipefail_reports_sigpipe(self):
        """`cat /dev/zero | head -c1` — the writer dies of SIGPIPE; with
        pipefail the pipeline status is 141 (128+13), like bash."""
        cmd = ('set -o pipefail; cat /dev/zero 2>/dev/null | head -c1 '
               '>/dev/null; echo rc=$?')
        psh = run_psh(cmd)
        bash = run_bash(cmd)
        assert psh.stdout == 'rc=141\n', psh.stderr
        assert psh.stdout == bash.stdout

    def test_without_pipefail_status_is_last_command(self):
        """Without pipefail the status is the last (reader) command's: the
        SIGPIPE death of the producer is masked, like bash."""
        cmd = ('cat /dev/zero 2>/dev/null | head -c1 >/dev/null; echo rc=$?')
        psh = run_psh(cmd)
        bash = run_bash(cmd)
        assert psh.stdout == 'rc=0\n', psh.stderr
        assert psh.stdout == bash.stdout

    def test_pipestatus_records_sigpipe(self):
        """PIPESTATUS[0] for the SIGPIPE'd producer is 141, like bash."""
        cmd = ('cat /dev/zero 2>/dev/null | head -c1 >/dev/null; '
               'echo "${PIPESTATUS[0]}"')
        psh = run_psh(cmd)
        bash = run_bash(cmd)
        assert psh.stdout == '141\n', psh.stderr
        assert psh.stdout == bash.stdout
