"""Core-state Phase 1: in-process shells restore process-global signal state (H2).

For an unmanaged signal (USR1/USR2/ALRM/...), ``TrapManager`` installs a
Python process-global handler. ``Shell.close()`` closed the self-pipes but did
NOT restore that handler, so a transient in-process shell (tests, an embedded
shell, the env builtins extension) left its handler installed in the hosting
process.

The fix is a SignalDispositionLease: snapshot the prior disposition before
installing, restore it on ``close()``. This is for IN-PROCESS shells — forked
children reset dispositions via the child signal policy and are unaffected.

Serial: touches process-global signal dispositions. The test force-restores
USR1 in a finally so a failure cannot pollute the runner.
"""

import signal

import pytest

from psh.shell import Shell

USR1 = signal.SIGUSR1


@pytest.mark.serial
@pytest.mark.xfail(strict=True, reason="H2: Shell.close() does not restore the "
                   "process-global signal disposition an in-process trap "
                   "installed. Fixed by SignalDispositionLease (Commit 5).")
def test_close_restores_installed_disposition():
    prior = signal.getsignal(USR1)
    try:
        sh = Shell(norc=True)
        sh.run_command('trap ":" USR1')
        # The handler is installed while the shell is live.
        assert signal.getsignal(USR1) != prior
        sh.close()
        # close() must restore the prior disposition for an in-process shell.
        assert signal.getsignal(USR1) == prior, (
            "Shell.close() leaked the USR1 handler into the host process")
    finally:
        signal.signal(USR1, prior)


@pytest.mark.serial
class TestLeaseRegression:
    def test_close_is_idempotent(self):
        # Double close must not raise (restoration itself is the Commit-5
        # xfail above; here we only guard idempotency).
        prior = signal.getsignal(USR1)
        try:
            sh = Shell(norc=True)
            sh.run_command('trap ":" USR1')
            sh.close()
            sh.close()
        finally:
            signal.signal(USR1, prior)

    def test_shell_without_trap_leaves_disposition(self):
        prior = signal.getsignal(USR1)
        try:
            sh = Shell(norc=True)
            sh.run_command("echo hi")
            sh.close()
            assert signal.getsignal(USR1) == prior
        finally:
            signal.signal(USR1, prior)
