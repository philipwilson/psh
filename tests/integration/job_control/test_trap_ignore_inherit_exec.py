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
