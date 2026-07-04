"""Reappraisal #16 Tier-2: `trap '' SIG` (ignore) inherited across exec.

POSIX: exec preserves a SIG_IGN disposition. bash keeps a signal *ignored*
(the empty-action trap) ignored in an exec'd external child, while a signal
trapped WITH an action resets to default (the handler can't cross exec).
psh's child-signal policy reset every signal to SIG_DFL, clobbering the
inherited ignore — an external child saw the signal defaulted.

Run in a subprocess (an external `bash` child is forked+exec'd; capturing its
fd-level output needs a real process, not the in-process capture fixture).
"""

import subprocess
import sys

import pytest

PSH = [sys.executable, "-m", "psh", "-c"]


def _run(cmd):
    return subprocess.run(
        PSH + [cmd], capture_output=True, text=True, timeout=15)


def _bash(cmd):
    return subprocess.run(
        ["bash", "-c", cmd], capture_output=True, text=True, timeout=15)


@pytest.mark.serial
class TestTrapIgnoreInheritedAcrossExec:
    def test_ignored_int_inherited(self):
        cmd = 'trap "" INT; bash -c "trap -p INT"'
        psh = _run(cmd)
        assert psh.returncode == 0
        assert psh.stdout == "trap -- '' SIGINT\n"
        assert psh.stdout == _bash(cmd).stdout

    def test_ignored_term_inherited(self):
        cmd = 'trap "" TERM; bash -c "trap -p TERM"'
        psh = _run(cmd)
        assert psh.returncode == 0
        assert psh.stdout == "trap -- '' SIGTERM\n"
        assert psh.stdout == _bash(cmd).stdout

    def test_action_trap_resets_across_exec(self):
        # A signal trapped WITH an action resets to default in the child.
        cmd = 'trap "echo hi" INT; bash -c "trap -p INT"'
        psh = _run(cmd)
        assert psh.returncode == 0
        assert psh.stdout == ""
        assert psh.stdout == _bash(cmd).stdout

    def test_no_trap_stays_default(self):
        cmd = 'bash -c "trap -p INT"'
        psh = _run(cmd)
        assert psh.stdout == ""
        assert psh.stdout == _bash(cmd).stdout

    def test_ignore_then_reset_is_default(self):
        cmd = 'trap "" INT; trap - INT; bash -c "trap -p INT"'
        psh = _run(cmd)
        assert psh.stdout == ""
        assert psh.stdout == _bash(cmd).stdout


@pytest.mark.serial
class TestTrapIgnoreInheritedAcrossDirectExec:
    """`trap '' SIG` must also survive the DIRECT `exec` builtin.

    Reappraisal #17 core MED: the v0.593 reconciliation lived only in the
    forked-child policy (reset_child_signals); `trap "" INT; exec cmd`
    still lost the ignore for MANAGED signals (INT/TERM/HUP/QUIT), whose
    traps are Python-level handlers the kernel resets to SIG_DFL on exec.
    The exec builtin now applies the same keep-SIG_IGN-for-''/default-
    otherwise reconciliation (prepare_signals_for_exec) before execvpe.
    """

    def test_ignored_managed_signals_inherited(self):
        for sig in ('INT', 'TERM', 'HUP', 'QUIT'):
            cmd = f'trap "" {sig}; exec bash -c "trap -p {sig}"'
            psh = _run(cmd)
            assert psh.returncode == 0, (sig, psh.stderr)
            assert psh.stdout == f"trap -- '' SIG{sig}\n", (sig, psh.stdout)
            assert psh.stdout == _bash(cmd).stdout

    def test_ignored_unmanaged_signal_inherited(self):
        cmd = 'trap "" USR1; exec bash -c "trap -p USR1"'
        psh = _run(cmd)
        assert psh.stdout == "trap -- '' SIGUSR1\n"
        assert psh.stdout == _bash(cmd).stdout

    def test_action_trap_resets_across_direct_exec(self):
        cmd = 'trap "echo hit" INT; exec bash -c "trap -p INT"'
        psh = _run(cmd)
        assert psh.returncode == 0
        assert psh.stdout == ""
        assert psh.stdout == _bash(cmd).stdout

    def test_no_trap_stays_default(self):
        cmd = 'exec bash -c "trap -p INT"'
        psh = _run(cmd)
        assert psh.stdout == ""
        assert psh.stdout == _bash(cmd).stdout

    def test_no_shell_internal_ignores_leak(self):
        """psh's own SIG_IGNs (SIGTTOU/SIGTTIN in script mode) and
        CPython's startup SIGXFSZ ignore must not leak into the image:
        bash-under-bash inherits NO ignored signals, so `trap -p` in the
        exec'd child prints nothing."""
        cmd = 'exec bash -c "trap -p"'
        psh = _run(cmd)
        assert psh.stdout == ""
        assert psh.stdout == _bash(cmd).stdout

    def test_forked_child_does_not_leak_sigxfsz(self):
        """The forked path shares the disposition list: CPython ignores
        SIGXFSZ at startup, and reset_child_signals must reset it."""
        cmd = 'bash -c "trap -p"'
        psh = _run(cmd)
        assert psh.stdout == ""
        assert psh.stdout == _bash(cmd).stdout
