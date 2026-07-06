"""POSIX special-builtin semantics are mode-aware (executor F9).

Two consequences of the special-builtin registry are decided by `set -o
posix`:

  - Prefix-assignment persistence: `VAR=v <special>` leaves VAR set ONLY in
    POSIX mode. In default (bash) mode the prefix is temporary, like any
    builtin. psh previously persisted it in BOTH modes.
  - Lookup precedence: default mode lets a function shadow a special builtin;
    POSIX mode gives special builtins precedence over functions.

Also: `.` and `times` are now in the complete special-builtin registry (so a
POSIX-mode `X=v . file` persists X).
"""

import subprocess
import sys

import pytest


def _run(script: str):
    result = subprocess.run(
        [sys.executable, "-m", "psh", "-c", script],
        capture_output=True, text=True, timeout=15,
    )
    return result.stdout, result.stderr, result.returncode


# --- Prefix persistence is mode-aware -----------------------------------

@pytest.mark.parametrize("special", [":", "eval ':'", ". /dev/null"])
def test_default_mode_prefix_is_temporary(special):
    out, _, _ = _run(f"unset X; X=new {special}; printf '<%s>\\n' \"${{X-unset}}\"")
    assert out == "<unset>\n"


@pytest.mark.parametrize("special", [":", "eval ':'", ". /dev/null"])
def test_posix_mode_prefix_persists(special):
    out, _, _ = _run(
        f"set -o posix; unset X; X=new {special}; printf '<%s>\\n' \"${{X-unset}}\"")
    assert out == "<new>\n"


def test_regular_builtin_prefix_temporary_in_both_modes():
    out, _, _ = _run("unset X; X=new true; printf '<%s>' \"${X-unset}\"")
    assert out == "<unset>"
    out, _, _ = _run(
        "set -o posix; unset X; X=new true; printf '<%s>' \"${X-unset}\"")
    assert out == "<unset>"


# --- Lookup precedence is mode-aware ------------------------------------

def test_default_mode_function_shadows_special_builtin():
    out, _, _ = _run(
        "export() { echo FUNC; }; unset Q; export Q=1; echo \"Q=<${Q-unset}>\"")
    assert out == "FUNC\nQ=<unset>\n"


def test_posix_mode_special_builtin_takes_precedence():
    # Function defined in default mode, then posix enabled: `export` resolves
    # to the special builtin (Q exported), not the function.
    out, _, _ = _run(
        "export() { echo FUNC; }; set -o posix; unset Q; export Q=1; "
        "echo \"Q=<${Q-unset}>\"")
    assert out == "Q=<1>\n"


# --- Registry completeness ----------------------------------------------

@pytest.mark.parametrize("name", [".", "times", ":", "eval", "export"])
def test_special_builtins_exist(name):
    out, _, rc = _run(f"type {name} >/dev/null 2>&1 && echo yes || echo no")
    assert out == "yes\n"


def test_toggling_posix_mid_session_reresolves():
    # persistence flips as posix is toggled on then off within one session.
    out, _, _ = _run(
        "unset X; X=a :; printf '<%s>' \"${X-unset}\"; "        # default: temp
        "set -o posix; unset X; X=b :; printf '<%s>' \"${X-unset}\"; "  # posix: persist
        "set +o posix; unset X; X=c :; printf '<%s>\\n' \"${X-unset}\"")  # default again
    assert out == "<unset><b><unset>\n"
