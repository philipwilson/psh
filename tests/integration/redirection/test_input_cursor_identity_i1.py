"""Open-file-description identity and cursor lifetime (campaign I1, SCOPED).

The InputCursor is keyed to an owned open-file-description identity and persists
across read invocations (same-fd carryover). A permanent rebind (`exec 0<file`)
assigns the fd a NEW description, dropping the old cursor. Cross-fd dup sharing
and temp-redirect-frame isolation are the DEFERRED FULL fidelity; the two
documented deliberate-loss rows below pin psh's current behavior AND assert it
diverges from C-locale bash so the divergence is visible, not silent.

`exec` permanent redirects rewrite fds, so every case runs psh in a subprocess.
"""
import os
import subprocess
import sys

import pytest

PSH_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ENV = {**os.environ, "PYTHONPATH": PSH_ROOT, "PSH_STRICT_ERRORS": "1"}


def _psh(script: bytes, stdin: bytes) -> bytes:
    return subprocess.run(
        [sys.executable, "-m", "psh", "-c", script.decode()],
        input=stdin, capture_output=True, cwd=PSH_ROOT, timeout=15, env=ENV,
    ).stdout


def _bash_c(script: bytes, stdin: bytes) -> bytes:
    return subprocess.run(
        ["bash", "-c", script.decode()], input=stdin, capture_output=True,
        timeout=15, env={**os.environ, "LC_ALL": "C", "LANG": "C"},
    ).stdout


class TestSameFdPersistence:
    def test_same_fd_carryover_matches_c_bash(self):
        # read -N1 twice: the byte read to classify the malformed lead survives.
        script = b"read -N 1 x; read -N 1 y; printf 'x=<%s> y=<%s>\\n' \"$x\" \"$y\""
        assert _psh(script, b"\xc3A\n") == _bash_c(script, b"\xc3A\n") == b"x=<\xc3> y=<A>\n"

    def test_plain_reads_across_invocations(self):
        # No surplus on plain reads: a while-read loop is unchanged.
        out = _psh(b"while read line; do echo got:$line; done", b"a\nb\nc\n")
        assert out == b"got:a\ngot:b\ngot:c\n"


class TestRebindBoundary:
    def test_exec_rebind_drops_stale_cursor(self, tmp_path):
        # exec 0<file gives fd0 a NEW description; the next read comes from the
        # file, never a stale stdin buffer.
        f = tmp_path / "f.txt"
        f.write_bytes(b"FILE1\nFILE2\n")
        script = (b"read a; exec 0<" + str(f).encode()
                  + b"; read b; printf 'a=%s b=%s\\n' \"$a\" \"$b\"")
        assert _psh(script, b"STDIN\nUNUSED\n") == b"a=STDIN b=FILE1\n"


class TestTempRedirectComposition:
    def test_common_composition_matches_bash(self, tmp_path):
        # DOCUMENTED + PINNED current behavior: a temp `read b < file` between
        # two stdin reads composes exactly like bash in the common (no-surplus)
        # case — the persistent fd-0 cursor reads whatever fd 0 currently is.
        f = tmp_path / "f.txt"
        f.write_bytes(b"F1\nF2\n")
        script = (b"read a; read b < " + str(f).encode()
                  + b"; read c; printf '%s|%s|%s\\n' \"$a\" \"$b\" \"$c\"")
        out = _psh(script, b"S1\nS2\nS3\n")
        bash = subprocess.run(["bash", "-c", script.decode()], input=b"S1\nS2\nS3\n",
                              capture_output=True, timeout=15).stdout
        assert out == bash == b"S1|F1|S2\n"


# ---- Documented deliberate-loss rows (SCOPED): pin psh CURRENT + prove the
# divergence from C-locale bash is real (not accidental parity). FULL fidelity
# would close these; the divergence is the ultra-rare malformed-multibyte -N
# count boundary crossing a dup alias / temp-redirect frame. ----

class TestDeliberateLossDupAlias:
    def test_valid_dup_alias_is_parity(self):
        # The COMMON dup-alias case matches bash via the shared kernel offset.
        script = (b"exec 3<&0; read -u 0 a; read -u 3 b; read -u 0 c; "
                  b"printf '%s|%s|%s\\n' \"$a\" \"$b\" \"$c\"")
        out = _psh(script, b"one\ntwo\nthree\n")
        bash = subprocess.run(["bash", "-c", script.decode()],
                              input=b"one\ntwo\nthree\n",
                              capture_output=True, timeout=15).stdout
        assert out == bash == b"one|two|three\n"

    def test_malformed_dup_alias_documented_divergence(self):
        # DELIBERATE LOSS (b): psh reads one byte ahead to classify the malformed
        # lead; that byte is stranded in fd0's cursor, invisible to the fd3 alias
        # (FULL cursor-sharing would carry it). Pin psh CURRENT; prove it differs
        # from C-locale bash (which is byte-per-char and never looks ahead).
        script = (b"exec 3<&0; read -N 1 -u 0 a; read -N 1 -u 3 b; "
                  b"printf 'a=<%s> b=<%s>\\n' \"$a\" \"$b\"")
        psh = _psh(script, b"\xc3A\n")
        bash_c = _bash_c(script, b"\xc3A\n")
        assert psh == b"a=<\xc3> b=<\n>\n"       # psh: A stranded in fd0's cursor
        assert bash_c == b"a=<\xc3> b=<A>\n"     # C bash: A read via kernel offset
        assert psh != bash_c                     # the divergence is real


class TestDeliberateLossTempFrame:
    def test_malformed_surplus_leaks_across_temp_frame(self, tmp_path):
        # DELIBERATE LOSS (c'): a malformed -N surplus in the persistent fd-0
        # cursor leaks into a temp `read b < file`. The SAME persistence that
        # fixes same-fd carryover causes this; hooking the temp frame = FULL.
        f = tmp_path / "f.txt"
        f.write_bytes(b"F1\nF2\n")
        script = (b"read -N 1 a; read b < " + str(f).encode()
                  + b"; read -N 1 c; printf 'a=<%s> b=%s c=<%s>\\n' \"$a\" \"$b\" \"$c\"")
        psh = _psh(script, b"\xc3A\nS2\n")
        # psh leaks the stranded 'A' into b (AF1); bash-C keeps b=F1.
        assert psh == b"a=<\xc3> b=AF1 c=<\n>\n"
        bash_c = _bash_c(script, b"\xc3A\nS2\n")
        assert bash_c == b"a=<\xc3> b=F1 c=<A>\n"
        assert psh != bash_c


@pytest.mark.parametrize("script,stdin,expected", [
    (b"read x; cat", b"a\nb\nc\n", b"b\nc\n"),
    (b"mapfile -n1 a; printf 'arr=<%s>' \"${a[@]}\"; cat", b"a\nb\nc\n", b"arr=<a\n>b\nc\n"),
])
def test_never_over_read_to_external(script, stdin, expected):
    assert _psh(script, stdin) == expected
