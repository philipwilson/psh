"""Core-state Phase 1: the ``env`` builtin must isolate process state (C1/P0).

psh ran ``env CMD`` in an in-process child Shell, so ``env`` could NOT isolate
cwd, umask, resource limits, signal dispositions, or process replacement, and
its in-process child leaked Python-owned mutations (arrays, functions, traps)
into the parent. bash's ``env`` is an EXTERNAL command: it builds the child
environment and execs the argv; it does not resolve shell builtins at all.

These run psh in a SUBPROCESS (process-state and signal behaviour need a real
process). Fixed by making standard ``env`` external argv execution (v0.656):
exit/exec/cd/umask no longer touch the parent, and — because the command runs
externally rather than in an in-process child — the USR1 trap is never
installed in the parent, so the parent dies on USR1 like bash. (The
signal-disposition lease still matters for OTHER in-process shells; see
tests/unit/core/test_signal_disposition_lease_p1.py.)
"""

import subprocess
import sys

import pytest
from shell_oracle import resolve_bash

PSH = [sys.executable, "-m", "psh", "--norc", "-c"]
BASH = [resolve_bash().path, "--noprofile", "--norc", "-c"]


def _run(argv, cmd):
    return subprocess.run(argv + [cmd], capture_output=True, text=True,
                          timeout=20, stdin=subprocess.DEVNULL)


def _psh(cmd):
    return _run(PSH, cmd)


# --------------------------------------------------------------------------
# env does not terminate / replace / mutate the parent process.
# --------------------------------------------------------------------------

def test_env_exit_does_not_kill_shell():
    r = _psh("env exit 7; echo AFTER")
    assert "AFTER" in r.stdout, "env exit terminated the parent shell"


def test_env_exec_does_not_replace_shell():
    r = _psh("env exec /bin/echo inner; echo AFTER")
    assert "AFTER" in r.stdout, "env exec replaced the parent process"


def test_env_cd_does_not_change_cwd():
    # Compare the REAL getcwd (via /bin/pwd) before/after — env cd running
    # in-process calls os.chdir, changing the whole process's cwd even though
    # the parent's $PWD variable stays old.
    r = _psh('s=$(/bin/pwd); env cd /; e=$(/bin/pwd); '
             '[ "$s" = "$e" ] && echo CWD_OK || echo "CWD_CHANGED:$e"')
    assert "CWD_OK" in r.stdout, f"env cd changed the parent cwd: {r.stdout!r}"


def test_env_umask_does_not_change_umask():
    r = _psh('before=$(umask); env umask 077; after=$(umask); '
             'test "$before" = "$after" && echo UMASK_OK')
    assert "UMASK_OK" in r.stdout, "env umask changed the parent umask"


def test_env_ulimit_does_not_change_limits():
    # `env ulimit` (external → not found) must not touch the parent's limits;
    # an in-process child running the ulimit builtin could make an
    # irreversible hard-limit reduction.
    r = _psh('before=$(ulimit -n); env ulimit -n 64; after=$(ulimit -n); '
             'test "$before" = "$after" && echo ULIMIT_OK')
    assert "ULIMIT_OK" in r.stdout, "env ulimit changed the parent limits"


# --------------------------------------------------------------------------
# env's (former) in-process child leaked Python-owned mutations.
# --------------------------------------------------------------------------

# NOTE: the array/function leaks below were SHARED-IDENTITY leaks — the env
# in-process child shared the parent's array value and Function object. Commit
# 2's clone_for_child deep-clones both, so these are isolated even while env is
# still in-process; Commit 3 (external env) is what fixes the process-state
# leaks (exit/exec/cd/umask) above.
def test_env_unset_array_no_leak():
    r = _psh('a=(x y); env unset "a[0]"; printf "<%s>\\n" "${a[*]}"')
    assert "<x y>" in r.stdout, "env unset leaked into the parent array"


def test_env_readonly_f_no_leak():
    r = _psh('f(){ :; }; env readonly -f f; f(){ echo REDEFINED; }; f')
    assert "REDEFINED" in r.stdout, "env readonly -f leaked into the parent"


# --------------------------------------------------------------------------
# Signal-disposition leak: env's in-process child installed a process-global
# USR1 handler that swallowed the signal in the parent (H2).
# --------------------------------------------------------------------------

@pytest.mark.serial
def test_env_trap_usr1_no_disposition_leak():
    # A process with the default USR1 disposition terminates on delivery.
    # If the child's trap leaked, psh survives and prints SURVIVED.
    r = _psh('env trap ":" USR1; kill -USR1 $$; sleep 0.3; echo SURVIVED')
    assert "SURVIVED" not in r.stdout, "USR1 disposition leaked into the parent"
    assert r.returncode != 0, "parent should have died on USR1"


# --------------------------------------------------------------------------
# Regressions: forms that already behave correctly must stay byte-identical
# to bash (bare env dump keyset, NAME=VALUE overlay printing).
# --------------------------------------------------------------------------

@pytest.mark.serial
class TestEnvOutputParityRegression:
    def test_env_assignment_overlay_prints(self):
        # `env FOO=bar printenv FOO` prints the overlaid value (both shells).
        cmd = "env FOO=bar printenv FOO"
        assert _psh(cmd).stdout == _run(BASH, cmd).stdout == "bar\n"

    def test_env_unset_removes_from_child_env(self):
        cmd = "export FOO=parent; env -u FOO sh -c 'echo ${FOO-gone}'"
        assert _psh(cmd).stdout == _run(BASH, cmd).stdout

    def test_env_i_clears_environment(self):
        cmd = "export FOO=x; env -i sh -c 'echo ${FOO-empty}'"
        assert _psh(cmd).stdout == _run(BASH, cmd).stdout == "empty\n"
