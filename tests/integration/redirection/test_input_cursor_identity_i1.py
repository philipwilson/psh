"""Open-file-description identity and cursor lifetime (campaign I1, SCOPED).

The InputCursor is keyed to an owned open-file-description identity and persists
across read invocations (same-fd carryover). A permanent rebind (`exec 0<file`)
assigns the fd a NEW description, dropping the old cursor. Slot 4B.4 completed
the model: a dup ALIASES the description (both fds share one cursor) and a
temporary redirect SCOPES it to the frame (in both directions), so the two rows
below — previously documented deliberate losses — now hold C-locale-bash parity.

`exec` permanent redirects rewrite fds, so every case runs psh in a subprocess.
"""
import os

import pytest
from shell_oracle import is_comparable, run_bash, run_psh

PSH_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _psh(script: bytes, stdin: bytes) -> bytes:
    # raw-bytes comparison: recover the exact stdout bytes from the runner's
    # lossless surrogateescape capture.
    r = run_psh(["-c", script.decode()], stdin_data=stdin, stdin_mode="pipe",
                cwd=PSH_ROOT, timeout=15, env={"PSH_STRICT_ERRORS": "1"})
    assert is_comparable(r), r
    return r.stdout.encode("utf-8", "surrogateescape")


def _bash_c(script: bytes, stdin: bytes) -> bytes:
    r = run_bash(["-c", script.decode()], stdin_data=stdin, stdin_mode="pipe",
                 timeout=15, env={"LC_ALL": "C", "LANG": "C"})
    assert is_comparable(r), r
    return r.stdout.encode("utf-8", "surrogateescape")


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
        b = run_bash(["-c", script.decode()], stdin_data=b"S1\nS2\nS3\n",
                     stdin_mode="pipe", timeout=15)
        assert is_comparable(b), b
        bash = b.stdout.encode("utf-8", "surrogateescape")
        assert out == bash == b"S1|F1|S2\n"


# ---- The two former deliberate-loss rows, CLOSED in slot 4B.4.
# Until 4B.4 these pinned psh's LOSS and asserted it DIFFERED from C-locale bash:
# a dup got a fresh cursor (so a byte already consumed on fd 0 was readable
# through NEITHER fd), and a temp frame reused fd 0's cursor (so a surplus
# crossed into a different source's read). Both now hold exact C-locale-bash
# parity. Each cell asserts psh == bash-C FIRST — agreement form, so the pin
# survives a change of spelling — and then the value, so a cell where BOTH
# shells moved together cannot pass silently. ----

class TestDupAliasSharesTheCursor:
    def test_valid_dup_alias_is_parity(self):
        # The COMMON dup-alias case matches bash via the shared kernel offset.
        script = (b"exec 3<&0; read -u 0 a; read -u 3 b; read -u 0 c; "
                  b"printf '%s|%s|%s\\n' \"$a\" \"$b\" \"$c\"")
        out = _psh(script, b"one\ntwo\nthree\n")
        b = run_bash(["-c", script.decode()], stdin_data=b"one\ntwo\nthree\n",
                     stdin_mode="pipe", timeout=15)
        assert is_comparable(b), b
        bash = b.stdout.encode("utf-8", "surrogateescape")
        assert out == bash == b"one|two|three\n"

    def test_malformed_dup_alias_shares_the_lookahead_byte(self):
        # CLOSED (former deliberate loss (b)). psh reads one byte ahead to
        # classify a malformed lead. That byte is ALREADY GONE from the shared
        # kernel offset, so unless the dup ALIASES the cursor it is readable
        # through neither fd — it reaches no consumer at all. `exec 3<&0` now
        # aliases the OpenDescription instance, so fd 3 finds it.
        script = (b"exec 3<&0; read -N 1 -u 0 a; read -N 1 -u 3 b; "
                  b"printf 'a=<%s> b=<%s>\\n' \"$a\" \"$b\"")
        psh = _psh(script, b"\xc3A\n")
        bash_c = _bash_c(script, b"\xc3A\n")
        assert psh == bash_c
        assert psh == b"a=<\xc3> b=<A>\n"


class TestTempFrameIsolatesTheCursor:
    def test_malformed_surplus_does_not_cross_into_a_temp_frame(self, tmp_path):
        # CLOSED (former deliberate loss (c')). A malformed -N surplus held on
        # fd 0's cursor used to be prepended to a temp `read b < file` — one
        # source's bytes appearing in another source's read. The frame now
        # scopes fd 0's binding, so the file read is clean AND the surplus is
        # still waiting for the next read on the original description (c).
        f = tmp_path / "f.txt"
        f.write_bytes(b"F1\nF2\n")
        script = (b"read -N 1 a; read b < " + str(f).encode()
                  + b"; read -N 1 c; printf 'a=<%s> b=%s c=<%s>\\n' \"$a\" \"$b\" \"$c\"")
        psh = _psh(script, b"\xc3A\nS2\n")
        bash_c = _bash_c(script, b"\xc3A\nS2\n")
        assert psh == bash_c
        assert psh == b"a=<\xc3> b=F1 c=<A>\n"

    def test_temp_frame_surplus_does_not_escape_into_stdin(self, tmp_path):
        # The MIRROR direction, found in slot 4B.4 and never previously pinned:
        # a surplus stranded while fd 0 IS the temp file used to be prepended to
        # the next read of REAL stdin — a file's bytes surfacing in a stdin read.
        # Scoping the frame closes BOTH directions, so this cell fails if only
        # the forward one is fixed.
        g = tmp_path / "g.txt"
        g.write_bytes(b"\xc3AGGG\nG2\n")
        script = (b"read -N 1 a < " + str(g).encode()
                  + b"; read b; printf 'a=<%s> b=<%s>\\n' \"$a\" \"$b\"")
        psh = _psh(script, b"STDIN1\nSTDIN2\n")
        bash_c = _bash_c(script, b"STDIN1\nSTDIN2\n")
        assert psh == bash_c
        assert psh == b"a=<\xc3> b=<STDIN1>\n"


@pytest.mark.parametrize("script,stdin,expected", [
    (b"read x; cat", b"a\nb\nc\n", b"b\nc\n"),
    (b"mapfile -n1 a; printf 'arr=<%s>' \"${a[@]}\"; cat", b"a\nb\nc\n", b"arr=<a\n>b\nc\n"),
])
def test_never_over_read_to_external(script, stdin, expected):
    assert _psh(script, stdin) == expected
