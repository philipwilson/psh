"""Conformance pins for bug M1 (reappraisal #7): an in-process builtin that
has its OWN output fd closed (`echo hi 1>&-`) must NOT leak output to the
real stdout.

The close (`1>&-`/bare `>&-`/`2>&-`) is a per-command fd-level redirect, but a
builtin writes through the Python stream object (`sys.stdout`/`shell.stdout`),
which `os.close(1)` does not reach. Before the fix psh closed fd 1 yet still
wrote `hi` to the real stdout while ALSO reporting the write error — bash
produces empty stdout, exit 1, and `NAME: write error: Bad file descriptor`.

Covered:
- echo / printf / pwd (and any builtin via the central guard) report the
  bash-shape write error and exit 1 with NO leaked output.
- bare `>&-` defaults to closing fd 1, same as `1>&-`.
- `2>&-` closes only stderr: a stdout write still succeeds, exit 0.
- the in-process COMPOUND paths leak the same way without the fix: a brace
  group `{ ...; } 1>&-` and a function `f 1>&-` (each builtin inside must
  fail, no leak).
- restore after the command is clean: `... 1>&-; echo back` prints `back`,
  and `cmd 1>&- 2>FILE` leaves fd 1 usable for the next command (the
  freed-fd-reuse corruption pin).
- `<&-` (input close) and a normal write are unaffected.

The bash MESSAGE prefix differs (`bash: line 1:` vs the builtin name) — that
is the shell-name/location prefix, not behavior — so these assert the
write-error body, the absence of any leak, and the exit codes rather than
byte-identical stderr.

All driven through subprocesses so psh and bash are directly comparable and so
closing fd 1 happens in a real process (never the test runner's own fds).
"""

import shutil
import subprocess
import sys

import pytest

pytestmark = pytest.mark.serial  # spawns subprocesses; closes fds

BASH = shutil.which("bash")


def _psh(cmd):
    return subprocess.run(
        [sys.executable, "-m", "psh", "-c", cmd],
        capture_output=True, text=True, timeout=30,
    )


def _bash(cmd):
    return subprocess.run(
        [BASH, "-c", cmd], capture_output=True, text=True, timeout=30,
    )


# --------------------------------------------------------------------------
# Closing the builtin's own output fd: no leak, write error, exit 1
# --------------------------------------------------------------------------

# (command, builtin name that fails)
_CLOSE_OUTPUT_CASES = [
    ("echo hi 1>&-", "echo"),
    ("echo hi >&-", "echo"),       # bare >&- defaults to fd 1
    ('printf "x\\n" 1>&-', "printf"),
    ("pwd 1>&-", "pwd"),
    ("type echo 1>&-", "type"),
]


@pytest.mark.skipif(BASH is None, reason="bash not available")
@pytest.mark.parametrize("cmd,name", _CLOSE_OUTPUT_CASES)
def test_close_output_fd_no_leak(cmd, name):
    p = _psh(cmd)
    b = _bash(cmd)
    # Same exit code as bash (1).
    assert p.returncode == b.returncode == 1, (
        f"exit differs for {cmd!r}: psh={p.returncode} bash={b.returncode}")
    # The whole point of M1: nothing leaks to the real stdout.
    assert p.stdout == "" == b.stdout, (
        f"output leaked for {cmd!r}: psh stdout={p.stdout!r}")
    # bash-shape write-error message on stderr.
    assert f"{name}: write error: Bad file descriptor" in p.stderr, p.stderr
    assert "[Errno" not in p.stderr, p.stderr


# --------------------------------------------------------------------------
# Compound in-process paths: brace group + function
# --------------------------------------------------------------------------

@pytest.mark.skipif(BASH is None, reason="bash not available")
@pytest.mark.parametrize("cmd", [
    "{ echo a; echo b; } 1>&-",
    "f(){ echo hi;}; f 1>&-",
    "{ pwd; echo x; } 1>&-",
])
def test_compound_close_output_no_leak(cmd):
    p = _psh(cmd)
    b = _bash(cmd)
    assert p.returncode == b.returncode == 1, (
        f"exit differs for {cmd!r}: psh={p.returncode} bash={b.returncode}")
    assert p.stdout == "" == b.stdout, (
        f"output leaked for {cmd!r}: psh stdout={p.stdout!r}")
    assert "write error: Bad file descriptor" in p.stderr, p.stderr


# --------------------------------------------------------------------------
# Restore after the command is clean (no leaked closed-stream state)
# --------------------------------------------------------------------------

@pytest.mark.skipif(BASH is None, reason="bash not available")
def test_restore_after_close_output_fd():
    cmd = "echo hi 1>&-; echo back"
    p = _psh(cmd)
    b = _bash(cmd)
    assert p.stdout == "back\n" == b.stdout, p.stdout
    assert p.returncode == b.returncode == 0


@pytest.mark.skipif(BASH is None, reason="bash not available")
def test_close_output_fd_plus_other_redirect_no_fd_reuse():
    """`cmd 1>&- 2>FILE` must not let the freed fd 1 be reused by the 2>FILE
    open and then closed on restore (which would corrupt the shell's stdout).
    The error goes to FILE, fd 1 stays usable for the next command.
    """
    cmd = "echo a 1>&- 2>/dev/null; echo back"
    p = _psh(cmd)
    b = _bash(cmd)
    assert p.stdout == "back\n" == b.stdout, p.stdout
    assert p.returncode == b.returncode == 0


@pytest.mark.skipif(BASH is None, reason="bash not available")
def test_declare_close_output_fd_combo():
    """declare -p output goes through the central builtin write-error guard."""
    cmd = "declare -p PATH 1>&- 2>/dev/null; echo rc=$?"
    p = _psh(cmd)
    b = _bash(cmd)
    assert p.stdout == "rc=1\n" == b.stdout, p.stdout
    assert p.returncode == b.returncode == 0


# --------------------------------------------------------------------------
# Unaffected paths: 2>&- (stderr only), <&- (input), normal write
# --------------------------------------------------------------------------

@pytest.mark.skipif(BASH is None, reason="bash not available")
@pytest.mark.parametrize("cmd,expect_out", [
    ("echo hi 2>&-", "hi\n"),               # stdout still works
    ("echo hi 2>&-; echo back2", "hi\nback2\n"),
    ("echo hi", "hi\n"),                     # plain, no close
    ("pwd 2>&-", None),                      # pwd succeeds (cwd-dependent)
])
def test_close_stderr_or_normal_unaffected(cmd, expect_out):
    p = _psh(cmd)
    b = _bash(cmd)
    assert p.returncode == b.returncode == 0, (
        f"{cmd!r}: psh={p.returncode} bash={b.returncode} err={p.stderr!r}")
    if expect_out is not None:
        assert p.stdout == expect_out == b.stdout, p.stdout
    assert p.stderr == "", p.stderr


@pytest.mark.skipif(BASH is None, reason="bash not available")
def test_input_close_unaffected():
    """`<&-` closes stdin; a builtin that does not read stdin is unaffected."""
    cmd = "echo hi 0<&-"
    p = _psh(cmd)
    b = _bash(cmd)
    assert p.stdout == "hi\n" == b.stdout
    assert p.returncode == b.returncode == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
