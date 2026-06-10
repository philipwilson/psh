"""Regression tests for the kill-then-wait signal race (v0.282.0).

`sleep 5 & kill %1 && wait %1` intermittently reported rc=0 instead of
143 under load. Root cause: the forked child inherits the shell's
Python-level SIGTERM trap-check handler until apply_child_signal_policy()
resets it; a SIGTERM delivered in the fork->exec window was consumed by
Python's C-level handler and then LOST across exec(), so `sleep` ran to
completion and exited 0. ProcessLauncher now blocks termination signals
across fork() and the child unblocks them only after resetting handlers
to SIG_DFL, so a window signal stays kernel-pending and terminates the
child with the correct status.

These run psh in subprocesses (signals + process lifecycle), and the
job_control path is auto-marked serial by conftest.
"""

import subprocess
import sys


def run_psh(cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, '-m', 'psh', '-c', cmd],
                          capture_output=True, text=True, timeout=30)


class TestKillWaitRace:
    """wait on a killed job must report the signal status, every time."""

    def test_wait_after_kill_reports_143(self):
        """Repeated runs: kill %1 then wait %1 always yields 128+SIGTERM."""
        cmd = 'sleep 5 & kill %1 && wait %1 2>/dev/null; echo rc=$?'
        for _ in range(10):
            result = run_psh(cmd)
            assert result.stdout.strip() == 'rc=143', (
                f"expected rc=143, got {result.stdout!r} "
                f"(stderr: {result.stderr!r})")

    def test_wait_reports_background_exit_code(self):
        """wait $! must report the background job's real exit code."""
        result = run_psh('(sleep 0.05; exit 5) & wait $!; echo rc=$?')
        assert result.stdout.strip() == 'rc=5'

    def test_kill_during_fork_window_not_lost(self):
        """An immediate kill (no sleep before it) must still terminate the
        job — the tightest version of the fork-window race."""
        cmd = 'sleep 5 & kill -TERM %1; wait %1 2>/dev/null; echo rc=$?'
        for _ in range(10):
            result = run_psh(cmd)
            assert result.stdout.strip() == 'rc=143', (
                f"expected rc=143, got {result.stdout!r} "
                f"(stderr: {result.stderr!r})")
