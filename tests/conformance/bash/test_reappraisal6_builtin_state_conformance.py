"""Conformance pins for four small bash-divergence fixes from reappraisal #6.

Covers:
- M5: ``unset -f NONEXISTENT`` is a silent no-op returning 0 (like ``unset -v``).
- M6: ``test``/``[`` support ``<`` / ``>`` string comparison (ASCII/byte order).
- L7: ``trap -p`` prints SIG-prefixed names for real signals, bare names for
      pseudo-signals (EXIT/ERR/DEBUG/RETURN).
- L8: ``$-`` matches bash's flag order and does not include ``s`` for ``-c``.

All driven through subprocesses so psh and bash are directly comparable.
"""

import shutil
import subprocess
import sys

import pytest

pytestmark = pytest.mark.serial  # spawns subprocesses

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


def _both_identical(cmd):
    p = _psh(cmd)
    b = _bash(cmd)
    assert p.stdout == b.stdout, f"stdout differ for {cmd!r}: psh={p.stdout!r} bash={b.stdout!r}"
    assert p.returncode == b.returncode, f"rc differ for {cmd!r}: psh={p.returncode} bash={b.returncode}"


# --------------------------------------------------------------------------
# M5: unset -f on a missing function is a silent no-op (exit 0)
# --------------------------------------------------------------------------

@pytest.mark.skipif(BASH is None, reason="bash not available")
@pytest.mark.parametrize("cmd", [
    "unset -f nope; echo $?",
    "unset nope; echo $?",
    "unset -v nope; echo $?",
    "f(){ :;}; unset -f f; declare -F f; echo rc=$?",
])
def test_unset_missing_is_silent_zero(cmd):
    _both_identical(cmd)


def test_unset_f_missing_no_stderr():
    p = _psh("unset -f nope")
    assert p.returncode == 0
    assert p.stderr == ""


# --------------------------------------------------------------------------
# M6: test/[ string comparison with < and > (ASCII order)
# --------------------------------------------------------------------------

@pytest.mark.skipif(BASH is None, reason="bash not available")
@pytest.mark.parametrize("cmd", [
    r"[ a \< b ]; echo $?",
    r"[ b \< a ]; echo $?",
    r"[ a \< a ]; echo $?",
    r"[ abc \> ab ]; echo $?",
    r"[ b \> a ]; echo $?",
    # test/[ compares by ASCII byte order, NOT locale: A(65) sorts before a(97)
    r"[ A \< a ]; echo $?",
    r"test a \< b; echo $?",
])
def test_bracket_string_comparison(cmd):
    _both_identical(cmd)


# --------------------------------------------------------------------------
# L7: trap -p prints SIG-prefixed names for real signals, bare for pseudo
# --------------------------------------------------------------------------

@pytest.mark.skipif(BASH is None, reason="bash not available")
@pytest.mark.parametrize("sig", ["TERM", "INT", "HUP", "ERR"])
def test_trap_p_signal_name_canonicalization(sig):
    # Compare just the `trap --` line (these traps don't fire on their own).
    cmd = f"trap 'echo x' {sig}; trap -p {sig} | grep trap"
    _both_identical(cmd)


@pytest.mark.skipif(BASH is None, reason="bash not available")
@pytest.mark.parametrize("sig", ["EXIT", "DEBUG"])
def test_trap_p_pseudo_name_matches_bash(sig):
    # EXIT/DEBUG fire (possibly a differing number of times across shells),
    # so pin only the `trap --` definition line, not the action output.
    def line(out):
        for ln in out.splitlines():
            if ln.startswith("trap -- "):
                return ln
        return None
    cmd = f"trap 'echo x' {sig}; trap -p {sig}"
    assert line(_psh(cmd).stdout) == line(_bash(cmd).stdout)


def test_trap_p_real_signal_gets_sig_prefix():
    p = _psh("trap '' TERM; trap -p TERM")
    assert p.stdout == "trap -- '' SIGTERM\n"


def test_trap_p_pseudo_signal_no_sig_prefix():
    # EXIT fires on shell exit; pin only the definition line.
    out = _psh("trap 'echo x' EXIT; trap -p EXIT").stdout
    assert "trap -- 'echo x' EXIT" in out.splitlines()


def test_trap_p_numeric_signal_canonicalized():
    p = _psh("trap 'echo x' 15; trap -p | grep trap")
    assert p.stdout == "trap -- 'echo x' SIGTERM\n"


def test_trap_p_lowercase_input_normalized():
    p = _psh("trap '' term; trap -p TERM")
    assert p.stdout == "trap -- '' SIGTERM\n"


# --------------------------------------------------------------------------
# L8: $- flag order and no 's' for -c mode
# --------------------------------------------------------------------------

def test_dash_var_command_mode_no_s():
    # bash -c 'echo $-' -> hBc  (command mode 'c', no stdin 's', no 'H')
    p = _psh("echo $-")
    assert p.stdout == "hBc\n"


def test_dash_var_order_with_options():
    p = _psh("set -aefuvx; echo $-")
    assert p.stdout == "aefhuvxBc\n"


def test_dash_var_errexit_order():
    p = _psh("set -e; echo $-")
    assert p.stdout == "ehBc\n"


@pytest.mark.skipif(BASH is None, reason="bash not available")
@pytest.mark.parametrize("cmd", [
    "echo $-",
    "set -e; echo $-",
    "set -aefuvx; echo $-",
    "set -x; echo $-",
    "set -u; echo $-",
])
def test_dash_var_matches_bash(cmd):
    _both_identical(cmd)


def test_dash_var_stdin_mode_has_s():
    # Piped stdin: bash -> hBs. The 'c' becomes 's', still no 'H'.
    p = subprocess.run(
        [sys.executable, "-m", "psh"],
        input="echo $-\n", capture_output=True, text=True, timeout=30,
    )
    assert p.stdout == "hBs\n"


def test_dash_var_script_file_no_s(tmp_path):
    # A script run by path is neither stdin nor command mode: bash -> hB.
    script = tmp_path / "s.sh"
    script.write_text("echo $-\n")
    p = subprocess.run(
        [sys.executable, "-m", "psh", str(script)],
        capture_output=True, text=True, timeout=30,
    )
    assert p.stdout == "hB\n"
