"""``--posix`` flag and POSIXLY_CORRECT startup-environment support (task #31).

These need a real process: the ``--posix`` flag varies invocation argv, and
the startup import reads the actual environment before any command runs — both
outside what an in-process Shell or the ``shell -c`` conformance harness can
drive. Each behavior is pinned against live bash on the same host.

Cross-release check (v0.673): the ``--posix`` flag and POSIXLY_CORRECT must
reach the SAME posix option the special-builtin exit-on-error policy reads, so
a special-builtin usage error exits a non-interactive shell under either.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from shell_oracle import try_resolve_bash

REPO_ROOT = Path(__file__).resolve().parents[2]

# A clean-ish environment: full env for PATH/python, PYTHONPATH to import the
# worktree's psh, DISPLAY/XAUTHORITY stripped (they can auto-start XQuartz on
# macOS), and POSIXLY_CORRECT removed so a test controls it explicitly.
_BASE_ENV = {k: v for k, v in os.environ.items()
             if k not in ('DISPLAY', 'XAUTHORITY', 'POSIXLY_CORRECT')}
_BASE_ENV['PYTHONPATH'] = str(REPO_ROOT)

_ORACLE = try_resolve_bash()
BASH = _ORACLE.path if _ORACLE else 'bash-oracle-unavailable'


def _psh(*args, env_extra=None, cwd=None):
    env = dict(_BASE_ENV)
    if env_extra:
        env.update(env_extra)
    return subprocess.run([sys.executable, '-m', 'psh', *args],
                          capture_output=True, text=True, timeout=15,
                          cwd=cwd, env=env)


def _bash(*args, env_extra=None, cwd=None):
    env = dict(_BASE_ENV)
    env.pop('PYTHONPATH', None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run([BASH, *args],
                          capture_output=True, text=True, timeout=15,
                          cwd=cwd, env=env)


@pytest.mark.skipif(_ORACLE is None, reason="bash not available")
class TestPosixFlag:
    """``--posix`` enables posix mode at startup, matching bash."""

    def test_flag_enables_posix_and_binds_variable(self):
        cmd = 'set -o | grep posix; echo "var=[${POSIXLY_CORRECT-U}]"'
        p = _psh('--posix', '-c', cmd)
        b = _bash('--posix', '-c', cmd)
        assert p.stdout == b.stdout
        assert p.returncode == b.returncode
        # concretely: posix on, POSIXLY_CORRECT bound to y (bash).
        assert 'posix' in p.stdout and 'on' in p.stdout
        assert 'var=[y]' in p.stdout

    def test_no_flag_posix_off(self):
        p = _psh('-c', 'set -o | grep posix')
        assert 'off' in p.stdout

    def test_flag_help_lists_posix(self):
        p = _psh('--help')
        assert '--posix' in p.stdout


@pytest.mark.skipif(_ORACLE is None, reason="bash not available")
class TestPosixlyCorrectStartupEnv:
    """POSIXLY_CORRECT in the startup environment enables posix mode."""

    def test_env_present_enables_posix(self):
        cmd = 'set -o | grep posix; echo "var=[$POSIXLY_CORRECT]"'
        p = _psh('-c', cmd, env_extra={'POSIXLY_CORRECT': '1'})
        b = _bash('-c', cmd, env_extra={'POSIXLY_CORRECT': '1'})
        assert p.stdout == b.stdout
        assert 'on' in p.stdout

    def test_env_empty_enables_posix(self):
        cmd = 'set -o | grep posix'
        p = _psh('-c', cmd, env_extra={'POSIXLY_CORRECT': ''})
        b = _bash('-c', cmd, env_extra={'POSIXLY_CORRECT': ''})
        assert p.stdout == b.stdout
        assert 'on' in p.stdout

    def test_env_absent_posix_off(self):
        p = _psh('-c', 'set -o | grep posix')
        assert 'off' in p.stdout


@pytest.mark.skipif(_ORACLE is None, reason="bash not available")
class TestPosixScriptFile:
    """``--posix`` governs a script file, not just -c."""

    def test_flag_on_script(self, tmp_path):
        script = tmp_path / 's.sh'
        script.write_text('set -o | grep posix\n')
        p = _psh('--posix', str(script))
        b = _bash('--posix', str(script))
        assert p.stdout == b.stdout
        assert 'on' in p.stdout


@pytest.mark.skipif(_ORACLE is None, reason="bash not available")
class TestSpecialBuiltinExitCrossRelease:
    """v0.673: --posix / POSIXLY_CORRECT reach the special-builtin exit policy.

    A special-builtin usage error (``export -q``) exits a non-interactive
    posix-mode shell with the builtin's status and does NOT run the following
    command; without posix it reports the error and runs on.
    """

    SCRIPT = 'export -q 2>/dev/null\necho AFTER\n'

    def test_flag_special_builtin_exits(self, tmp_path):
        script = tmp_path / 'sb.sh'
        script.write_text(self.SCRIPT)
        p = _psh('--posix', str(script))
        b = _bash('--posix', str(script))
        # --posix must be ACCEPTED (not rejected as an unknown flag) and only
        # THEN exit on the special-builtin usage error, before `echo AFTER`.
        # Asserting rc==2 + no-AFTER alone is vacuously true on a shell that
        # rejects --posix ("invalid option", rc 2, empty stdout), so pin that
        # the flag was honoured: no "invalid option" diagnostic. The non-posix
        # control proves the script itself reaches `echo AFTER` — so its
        # absence here is the posix exit, not an unrelated failure.
        control = _psh(str(script))
        assert 'AFTER' in control.stdout
        assert 'invalid option' not in p.stderr
        assert p.returncode == b.returncode == 2
        assert 'AFTER' not in p.stdout
        assert 'AFTER' not in b.stdout

    def test_env_special_builtin_exits(self, tmp_path):
        script = tmp_path / 'sb.sh'
        script.write_text(self.SCRIPT)
        p = _psh(str(script), env_extra={'POSIXLY_CORRECT': '1'})
        b = _bash(str(script), env_extra={'POSIXLY_CORRECT': '1'})
        assert p.returncode == b.returncode == 2
        assert 'AFTER' not in p.stdout
        assert 'AFTER' not in b.stdout

    def test_no_posix_special_builtin_runs_on(self, tmp_path):
        script = tmp_path / 'sb.sh'
        script.write_text(self.SCRIPT)
        p = _psh(str(script))
        b = _bash(str(script))
        assert p.returncode == b.returncode == 0
        assert 'AFTER' in p.stdout
        assert 'AFTER' in b.stdout
