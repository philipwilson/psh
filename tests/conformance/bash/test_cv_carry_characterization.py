"""Both-sides characterization pins for closing-verification carry register
(dev-cv, v0.750.0). These are DOCUMENTED DIVERGENCES — psh's behavior is pinned
alongside bash's so a future accidental change to EITHER is caught. They are
carried (carry register #18, #19 in docs/reviews/boundary_campaign_close_2026-07),
not fixed, per the closing-verification dispositions.
"""
import subprocess
import sys

from shell_oracle import resolve_bash

BASH = resolve_bash().path
PSH = [sys.executable, "-m", "psh"]


def _run(argv, cmd):
    return subprocess.run(argv + ["-c", cmd], capture_output=True, text=True,
                          timeout=20)


class TestPosixSpecialBuiltinRedirectFatality:
    """Carry #18 (R3): in POSIX mode a redirection error on a POSIX SPECIAL
    builtin is FATAL in bash (the shell exits, the rest of the line never runs);
    psh reports the error and CONTINUES. Both shells agree in default (non-posix)
    mode (continue). Divergence probed vs bash 5.2."""

    _CMD = "{mode}: > /no/such/dir/f 2>/dev/null; echo AFTER=$?"

    def test_posix_mode_bash_exits_psh_continues(self):
        cmd = "set -o posix; : > /no/such/dir/f 2>/dev/null; echo AFTER=$?"
        bash = _run([BASH], cmd)
        psh = _run(PSH, cmd)
        # bash: the special-builtin redirect error aborts — AFTER never prints.
        assert "AFTER=" not in bash.stdout, bash.stdout
        assert bash.returncode != 0
        # psh: continues past the error (documented divergence).
        assert psh.stdout.strip() == "AFTER=1", psh.stdout

    def test_default_mode_both_continue(self):
        cmd = ": > /no/such/dir/f 2>/dev/null; echo AFTER=$?"
        bash = _run([BASH], cmd)
        psh = _run(PSH, cmd)
        assert bash.stdout.strip() == "AFTER=1"
        assert psh.stdout.strip() == "AFTER=1"


class TestAnsiCHighEscapeByteModel:
    """Carry #19: an ANSI-C `$'\\xNN'` escape with NN >= 0x80 — bash emits the
    RAW byte 0xNN; psh emits the UTF-8 ENCODING of codepoint U+00NN. Probed vs
    bash 5.2 (a documented pre-existing byte-model divergence)."""

    def test_xff_bash_raw_byte_psh_utf8(self):
        cmd = r"printf '%s' $'\xff'"
        bash = subprocess.run([BASH, "-c", cmd], capture_output=True, timeout=20)
        psh = subprocess.run(PSH + ["-c", cmd], capture_output=True, timeout=20)
        assert bash.stdout == b"\xff", bash.stdout            # raw byte
        assert psh.stdout == b"\xc3\xbf", psh.stdout          # UTF-8 of U+00FF

    def test_x80_boundary(self):
        cmd = r"printf '%s' $'\x80'"
        bash = subprocess.run([BASH, "-c", cmd], capture_output=True, timeout=20)
        psh = subprocess.run(PSH + ["-c", cmd], capture_output=True, timeout=20)
        assert bash.stdout == b"\x80"
        assert psh.stdout == b"\xc2\x80"                      # UTF-8 of U+0080
