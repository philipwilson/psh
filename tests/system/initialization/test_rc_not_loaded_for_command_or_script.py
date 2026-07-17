"""rc is sourced only for an interactive shell, never for -c or a script.

bash sources ~/.bashrc only for an interactive non-login shell; `bash -c '...'`
and `bash script.sh` never source it — even when stdin is a terminal. psh
decided this in ``_init_interactive`` at construction time, but ``is_script_mode``
/ ``command_mode`` were set by ``__main__`` AFTER construction, so under a tty
(the normal case at a prompt) EVERY ``psh -c '...'`` and ``psh script.sh``
sourced ``~/.pshrc`` first (appraisal 2026-06-21, finding H8).

The existing ``test_rc_file_not_loaded_in_script_mode`` constructs
``Shell(script_name=...)`` directly — a path that sets the flag early, which the
real entry points never take — so it stayed green while the real flow was broken.
This test drives the REAL ``python -m psh`` entry point with a real tty on fd 0.

The harness needs a tty on fd 0, so it runs psh in a subprocess (an in-process
``dup2`` onto fd 0 would clobber the test runner / xdist worker).
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Spawns `python -m psh` with the given args under a fresh pty (so isatty() is
# True), optionally feeding stdin, and reports how many times ~/.pshrc sourced
# (the rc appends to RC_COUNTER). Prints "RC_COUNT=<n>" and "OUT=<stdout>".
_HARNESS = r"""
import os, pty, sys

rc = sys.argv[1]
feed = sys.argv[2]            # text to send to the child's stdin ('' for none)
psh_args = sys.argv[3:]
counter = os.environ["RC_COUNTER"]

master, slave = pty.openpty()
if feed:
    os.write(master, feed.encode())

proc = __import__("subprocess").run(
    [sys.executable, "-m", "psh", "--rcfile", rc] + psh_args,
    stdin=slave, stdout=master if False else __import__("subprocess").PIPE,
    stderr=__import__("subprocess").STDOUT, text=True, timeout=20,
)

def count():
    try:
        return sum(1 for _ in open(counter))
    except FileNotFoundError:
        return 0

print("RC_COUNT=%d" % count())
print("OUT=%r" % proc.stdout)
"""


def _run(tmp_path, *, feed: str, psh_args: list):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    counter = tmp_path / "rc_count"
    if counter.exists():
        counter.unlink()
    (home / ".pshrc").write_text(f"echo sourced >> {counter}\n")
    env = {
        "HOME": str(home),
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(PROJECT_ROOT),
        "RC_COUNTER": str(counter),
    }
    result = subprocess.run(
        [sys.executable, "-c", _HARNESS, str(home / ".pshrc"), feed, *psh_args],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30, env=env,
    )
    assert result.returncode == 0, f"harness failed:\n{result.stdout}\n{result.stderr}"
    fields = {}
    for line in result.stdout.splitlines():
        k, _, v = line.partition("=")
        fields[k] = v
    return fields


def test_rc_not_sourced_for_dash_c(tmp_path):
    fields = _run(tmp_path, feed="", psh_args=["-c", "echo HELLO"])
    assert fields["RC_COUNT"] == "0", "psh -c sourced ~/.pshrc under a tty"
    assert "HELLO" in fields["OUT"]


def test_rc_not_sourced_for_script_file(tmp_path):
    script = tmp_path / "s.sh"
    script.write_text("echo SCRIPT_BODY\n")
    fields = _run(tmp_path, feed="", psh_args=[str(script)])
    assert fields["RC_COUNT"] == "0", "psh script.sh sourced ~/.pshrc under a tty"
    assert "SCRIPT_BODY" in fields["OUT"]


# A live interactive shell (tty stdin, no -c, no script) MUST still source rc.
# Constructing Shell() and running the explicit startup step is exactly what
# the REPL entry path does (campaign F1: __main__ calls
# run_invocation_startup, and run_interactive_loop re-runs it idempotently for
# embedders); this exercises the decision directly (the flaky part of a full
# REPL subprocess is the pty/job-control loop, not the rc decision).
# CONSTRUCTION alone must NOT source it — that purity is asserted here too.
_INTERACTIVE_HARNESS = r"""
import os, pty, sys
counter = os.environ["RC_COUNTER"]
master, slave = pty.openpty()
os.dup2(slave, 0)
sys.stdin = os.fdopen(0, 'r')
assert sys.stdin.isatty()

from psh.shell import Shell
shell = Shell(rcfile=os.environ["PSH_RCFILE"])  # no script_name, no command_mode

def count():
    try:
        return sum(1 for _ in open(counter))
    except FileNotFoundError:
        return 0

print("RC_AT_CONSTRUCTION=%d" % count())
shell.run_invocation_startup()   # the REPL entry's explicit startup step
shell.run_invocation_startup()   # idempotent: a second call must not re-run rc
print("RC_COUNT=%d" % count())
"""


def test_rc_sourced_for_interactive_shell(tmp_path):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    counter = tmp_path / "rc_count"
    rc = home / ".pshrc"
    rc.write_text(f"echo sourced >> {counter}\n")
    env = {
        "HOME": str(home), "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(PROJECT_ROOT), "RC_COUNTER": str(counter),
        "PSH_RCFILE": str(rc),
    }
    result = subprocess.run(
        [sys.executable, "-c", _INTERACTIVE_HARNESS],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30, env=env,
    )
    assert result.returncode == 0, f"harness failed:\n{result.stderr}"
    lines = result.stdout.splitlines()
    construction = [ln for ln in lines if ln.startswith("RC_AT_CONSTRUCTION=")]
    counts = [ln for ln in lines if ln.startswith("RC_COUNT=")]
    assert construction == ["RC_AT_CONSTRUCTION=0"], (
        f"Shell construction itself sourced the rc (F1 purity): {result.stdout!r}"
    )
    assert counts == ["RC_COUNT=1"], (
        f"interactive startup did not source ~/.pshrc exactly once: {result.stdout!r}"
    )
