"""Signal-disposition leases under the process coordinator (campaign F2).

Continuation finding B, bullet 1 (red on base 909a79b9 — probe B4 in
tmp/boundary-ledgers/F2-probes/base-battery.txt): two live shells could
lease the SAME signal and restore out of order, leaking a closed shell's
handler into the host.  The coordinator makes the overlap unrepresentable:
a second shell activating while the first still HOLDS its SIGNALS lease is
rejected BEFORE any mutation; once the first shell closes (restoring the
host disposition), the second proceeds.  Sequential shells therefore always
net out to the host's original disposition, in either close order — there
is only ever one lease to restore.

Serial: process-global signal dispositions.  Every test force-restores USR1
and closes its shells in ``finally`` (symmetric entry/exit, so the tests
are order-independent under seeded shuffling).
"""

import signal

import pytest

from psh.core.process_lease import LeaseError
from psh.shell import Shell

pytestmark = pytest.mark.serial

USR1 = signal.SIGUSR1


def test_second_shell_rejected_while_first_holds_signal_lease():
    prior = signal.getsignal(USR1)
    s1 = Shell(norc=True)
    s2 = Shell(norc=True)
    try:
        s1.run_command('trap ": one" USR1')
        installed = signal.getsignal(USR1)
        assert installed != prior
        # Competing owner: rejected BEFORE mutation — the disposition and
        # the first shell's trap survive untouched.
        with pytest.raises(LeaseError):
            s2.run_command('trap ": two" USR1')
        assert signal.getsignal(USR1) == installed
    finally:
        s1.close()
        s2.close()
        signal.signal(USR1, prior)
    assert signal.getsignal(USR1) == prior


def test_second_shell_runs_after_first_closes():
    prior = signal.getsignal(USR1)
    s1 = Shell(norc=True)
    s1.run_command('trap ": one" USR1')
    s1.close()
    assert signal.getsignal(USR1) == prior       # lease restored at close
    s2 = Shell(norc=True)
    try:
        assert s2.run_command('trap ": two" USR1') == 0
        assert signal.getsignal(USR1) != prior
    finally:
        s2.close()
        signal.signal(USR1, prior)
    assert signal.getsignal(USR1) == prior


def test_sequential_shells_never_leak_a_dead_handler():
    """The out-of-order-restore leak (base: final disposition was shell1's
    dead handler) is gone: with one lease at a time, any close order of any
    number of sequential shells restores the HOST disposition."""
    prior = signal.getsignal(USR1)
    try:
        for _ in range(3):
            shell = Shell(norc=True)
            shell.run_command('trap ": n" USR1')
            shell.close()
        assert signal.getsignal(USR1) == prior
    finally:
        signal.signal(USR1, prior)


def test_shell_without_unmanaged_trap_never_blocks_a_second_shell():
    """Managed-signal traps (INT/TERM/EXIT) take no process lease, so the
    common two-shell test pattern keeps working unchanged."""
    s1 = Shell(norc=True)
    s2 = Shell(norc=True)
    try:
        assert s1.run_command('trap ": t" TERM; trap ": e" EXIT') == 0
        assert s2.run_command('echo fine >/dev/null') == 0
        assert s1.run_command('echo back >/dev/null') == 0   # and back again
    finally:
        s1.close()
        s2.close()


def test_dropped_shell_without_close_is_recovered_when_handler_free():
    """GC-safety: a shell dropped WITHOUT close that holds only leases whose
    restore data doesn't pin it (here: none) releases ownership to the next
    shell.  (A dropped shell with a live USR1 handler is pinned by the
    signal registry itself; close() is the contract there — see the F2
    ledger.)"""
    s1 = Shell(norc=True)
    s1.run_command('echo owned >/dev/null')
    del s1
    s2 = Shell(norc=True)
    try:
        assert s2.run_command('echo takeover >/dev/null') == 0
    finally:
        s2.close()
