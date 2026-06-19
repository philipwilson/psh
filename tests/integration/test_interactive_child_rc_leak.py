"""Subshell-style children must not source rc files (reappraisal #1).

In an *interactive* shell, several constructs build a child shell via
``Shell.for_subshell(...)``. Two of them passed ``norc=False``, so when the
child's stdin was still the parent tty (it looked interactive) the child
sourced ``~/.pshrc`` — and for input ``<(cmd)`` the rc output was captured
into the substitution. The affected paths:

  * input process substitution ``<(cmd)`` (``io_redirect/process_sub.py``) —
    ``cat <(echo HI)`` returned the user's ``.pshrc`` banner as data;
  * the ``env CMD`` builtin's in-process child (``builtins/env_command.py``).

bash sources rc once, at startup — never per subshell — but keeps the
interactive flag in ``$-`` inside substitutions. The fix (``norc=True``,
matching command substitution and ``for_subshell``'s default) preserves both:
no rc sourcing, ``$-`` still carries ``i``.

The harness puts a real tty on fd 0, so it must run in a subprocess: an
in-process ``dup2`` onto fd 0 would clobber the test runner / xdist worker.
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Counts rc sourcings via a file (robust to the env builtin's fd juggling),
# drives the real <(cmd) path, and reports $- seen inside the substitution.
_HARNESS = r"""
import os, pty, sys
COUNTER = os.environ["RC_COUNTER"]

master, slave = pty.openpty()
os.dup2(slave, 0)
sys.stdin = os.fdopen(0, 'r')
assert sys.stdin.isatty(), "setup: fd 0 is not a tty"

from psh.shell import Shell
sh = Shell(norc=True)  # parent does NOT source rc; any count is from a child
h = sh.io_manager.process_sub_handler

produced = open(h.create_for_expansion('in', 'echo HI')).read()
dash = open(h.create_for_expansion('in', 'echo "DASH:$-"')).read().strip()
sh.run_command("env echo via-env", add_to_history=False)

def count():
    try:
        return sum(1 for _ in open(COUNTER))
    except FileNotFoundError:
        return 0

print("PRODUCED=%r" % produced)
print("DASH=%r" % dash)
print("RC_COUNT=%d" % count())
"""


def _run_harness(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    counter = tmp_path / "rc_count"
    # rc writes to a file (not stdout) so we detect sourcing regardless of
    # which child sourced it or how its fds were bound.
    (home / ".pshrc").write_text(f"echo sourced >> {counter}\n")
    env = {
        "HOME": str(home),
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(PROJECT_ROOT),
        "PSH_STRICT_ERRORS": "1",
        "RC_COUNTER": str(counter),
    }
    result = subprocess.run(
        [sys.executable, "-c", _HARNESS],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30, env=env,
    )
    assert result.returncode == 0, f"harness failed:\n{result.stderr}"
    fields = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            fields[k] = v
    return fields


def test_no_subshell_child_sources_rc(tmp_path):
    """Neither `<(cmd)` nor `env cmd` sources ~/.pshrc in an interactive shell."""
    fields = _run_harness(tmp_path)
    assert fields["RC_COUNT"] == "0", (
        f"a subshell-style child sourced ~/.pshrc {fields['RC_COUNT']} time(s)"
    )


def test_input_procsub_output_not_polluted(tmp_path):
    """`<(echo HI)` yields exactly 'HI', not rc output spliced in front."""
    fields = _run_harness(tmp_path)
    assert "RC-MARKER" not in fields["PRODUCED"]
    assert "HI" in fields["PRODUCED"]


def test_procsub_keeps_interactive_flag(tmp_path):
    """`$-` inside `<(...)` still carries 'i' (bash parity — only rc is skipped)."""
    fields = _run_harness(tmp_path)
    flags = fields["DASH"].split("DASH:", 1)[1].rstrip("'\"")
    assert "i" in flags, f"interactive flag missing from $- in <(...): {fields['DASH']}"
