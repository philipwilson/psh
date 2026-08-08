"""The completed InputCursor ownership contract: dup aliasing + frame scoping.

Slot 4B.4 (integrator ruling ROW 4). Campaign I1 keyed the byte cursor to an
owned open-file-description identity but consumed that identity only for
SAME-fd persistence, deferring two cases as "purely additive" fidelity that
"exceeds the oracle". This slot measured that argument false and closed both.

**What was actually wrong.** The cursor can hold userspace state the kernel
offset does not carry — a decoder part-way through a multibyte character after
a ``-t`` timeout, or the one byte read ahead to classify a malformed lead. With
the registry keyed by bare fd, that state met the wrong stream:

* **temp frames, FORWARD** — a surplus held on fd 0 was prepended to a
  ``read x < FILE``, so one source's bytes appeared in another source's read;
* **temp frames, REVERSE** (found here, never previously pinned) — a surplus
  stranded while fd 0 *was* the temp file was prepended to the next read of
  real stdin;
* **dups** — ``exec 3<&0`` gave fd 3 a FRESH cursor, so a byte already consumed
  through fd 0 (and therefore already gone from the shared kernel offset) was
  readable through neither fd. It reached no consumer at all.

Every cell below was RED at base e3924ed3 and is pinned in AGREEMENT FORM
(psh == bash) so it survives a change of spelling, with the value asserted too
so a cell where both shells moved together cannot pass silently.

**Oracle per cell.** Malformed-input cells use **C-locale** bash: campaign I1
DECISION 1 established that psh's hybrid model matches C-locale bash for
malformed bytes, while ambient UTF-8 bash has ``mbrtowc`` quirks of its own.
The timeout cells feed WELL-FORMED input (``\\xc3`` is a valid ``é`` lead that
merely had not arrived yet), so their oracle is ambient bash.

**One divergence remains BY DESIGN** and is not a gap: at a ``-t`` timeout bash
assigns the stranded partial to the read that timed out, while psh holds it and
resumes it on the next read of the same description (successor row D-4B.2-s1,
ruled a permanent psh contract in 4B.4). The cells below therefore assert what
that divergence must NOT be: never corruption, never loss. See
``docs/user_guide/17_differences_from_bash.md``.

`exec` rewrites process fds, so every case runs psh in a subprocess.
"""
import os
import subprocess
import sys
import threading
import time

import pytest
from shell_oracle import is_comparable, run_bash, run_psh

PSH_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _psh(script: bytes, stdin: bytes) -> bytes:
    r = run_psh(["-c", script.decode()], stdin_data=stdin, stdin_mode="pipe",
                cwd=PSH_ROOT, timeout=15, env={"PSH_STRICT_ERRORS": "1"})
    assert is_comparable(r), r
    return r.stdout.encode("utf-8", "surrogateescape")


def _bash_c(script: bytes, stdin: bytes) -> bytes:
    r = run_bash(["-c", script.decode()], stdin_data=stdin, stdin_mode="pipe",
                 timeout=15, env={"LC_ALL": "C", "LANG": "C"})
    assert is_comparable(r), r
    return r.stdout.encode("utf-8", "surrogateescape")


# A malformed lead followed by one more byte: psh must read the second byte to
# classify the first as a lone surrogate, which is what strands a surplus.
STRAND_IN = b"\xc3A\n"


class TestDupAliasesTheDescription:
    """Each dup SPELLING aliases the cursor. One cell per spelling: a site that
    is never exercised is a site that silently stops aliasing."""

    @pytest.mark.parametrize("script,stdin,name", [
        (b"exec 3<&0; read -N 1 a; read -N 1 -u 3 b; "
         b"printf 'a=<%s> b=<%s>\\n' \"$a\" \"$b\"", STRAND_IN, "exec-permanent"),
        (b"exec {v}<&0; read -N 1 a; read -N 1 -u $v b; "
         b"printf 'a=<%s> b=<%s>\\n' \"$a\" \"$b\"", STRAND_IN, "named-fd"),
        (b"read -N 1 a; read -N 1 -u 3 b 3<&0; "
         b"printf 'a=<%s> b=<%s>\\n' \"$a\" \"$b\"", STRAND_IN, "per-command"),
    ], ids=["exec-permanent", "named-fd", "per-command"])
    def test_dup_spelling_shares_the_surplus(self, script, stdin, name):
        psh, bash_c = _psh(script, stdin), _bash_c(script, stdin)
        assert psh == bash_c, f"{name}: dup did not alias the cursor"
        assert psh == b"a=<\xc3> b=<A>\n"

    def test_valid_dup_alias_is_unaffected(self):
        # Control: the common no-surplus case was ALREADY parity via the kernel
        # offset. If aliasing broke it, the fix would be trading one bug for
        # another, and this cell is what would say so.
        script = (b"exec 3<&0; read -u 0 a; read -u 3 b; read -u 0 c; "
                  b"printf '%s|%s|%s\\n' \"$a\" \"$b\" \"$c\"")
        stdin = b"one\ntwo\nthree\n"
        assert _psh(script, stdin) == _bash_c(script, stdin) == b"one|two|three\n"


class TestTempFrameScopesTheCursor:
    """Both leak directions, across every frame kind that can host a read."""

    @pytest.mark.parametrize("wrap,name", [
        (b"read b < %s", "builtin-redirect"),
        (b"{ read b; } < %s", "brace-group"),
        (b"while read b; do break; done < %s", "while-loop"),
    ], ids=["builtin-redirect", "brace-group", "while-loop"])
    def test_surplus_does_not_leak_into_the_frame(self, tmp_path, wrap, name):
        f = tmp_path / "f.txt"
        f.write_bytes(b"F1\nF2\n")
        script = (b"read -N 1 a; " + (wrap % str(f).encode())
                  + b"; read -N 1 c; "
                  b"printf 'a=<%s> b=<%s> c=<%s>\\n' \"$a\" \"$b\" \"$c\"")
        psh, bash_c = _psh(script, STRAND_IN + b"S2\n"), _bash_c(script, STRAND_IN + b"S2\n")
        assert psh == bash_c, f"{name}: outer surplus leaked into the frame"
        # c proves the surplus was SET ASIDE, not destroyed: closing the leak by
        # dropping the byte would give c=<\n> and still pass a b-only assertion.
        assert psh == b"a=<\xc3> b=<F1> c=<A>\n"

    @pytest.mark.parametrize("wrap,name", [
        (b"read -N 1 a < %s", "builtin-redirect"),
        (b"{ read -N 1 a; } < %s", "brace-group"),
    ], ids=["builtin-redirect", "brace-group"])
    def test_frame_surplus_does_not_escape_into_stdin(self, tmp_path, wrap, name):
        g = tmp_path / "g.txt"
        g.write_bytes(b"\xc3AGGG\nG2\n")
        script = ((wrap % str(g).encode())
                  + b"; read b; printf 'a=<%s> b=<%s>\\n' \"$a\" \"$b\"")
        stdin = b"STDIN1\nSTDIN2\n"
        psh, bash_c = _psh(script, stdin), _bash_c(script, stdin)
        assert psh == bash_c, f"{name}: frame surplus escaped into stdin"
        assert psh == b"a=<\xc3> b=<STDIN1>\n"

    def test_nested_frames_restore_innermost_first(self, tmp_path):
        # Composition: frames nest, so the scoping must too. The inner frame's
        # surplus must not reach the outer frame's source, nor stdin.
        f = tmp_path / "f.txt"
        f.write_bytes(b"\xc3AOUTER\nO2\n")
        g = tmp_path / "g.txt"
        g.write_bytes(b"\xc3AINNER\nI2\n")
        script = (b"{ read -N 1 a; { read -N 1 b; } < " + str(g).encode()
                  + b"; read -N 1 c; } < " + str(f).encode()
                  + b"; read d; printf 'a=<%s> b=<%s> c=<%s> d=<%s>\\n' "
                  b"\"$a\" \"$b\" \"$c\" \"$d\"")
        stdin = b"STDIN1\n"
        psh, bash_c = _psh(script, stdin), _bash_c(script, stdin)
        assert psh == bash_c


class TestMustHold:
    """The I1 guarantees the close must not have traded away."""

    def test_same_fd_persistence(self):
        script = b"read -N 1 x; read -N 1 y; printf 'x=<%s> y=<%s>\\n' \"$x\" \"$y\""
        assert _psh(script, STRAND_IN) == _bash_c(script, STRAND_IN) == b"x=<\xc3> y=<A>\n"

    def test_exec_rebind_still_drops_the_stale_cursor(self, tmp_path):
        # An OPEN gives the fd a NEW description, so the surplus must NOT carry.
        # This is the cell that fails if bind_dup were applied to every redirect
        # instead of only to dups.
        f = tmp_path / "f.txt"
        f.write_bytes(b"F1\nF2\n")
        script = (b"read -N 1 a; exec 0<" + str(f).encode()
                  + b"; read b; printf 'a=<%s> b=<%s>\\n' \"$a\" \"$b\"")
        psh = _psh(script, STRAND_IN + b"S2\n")
        assert psh == _bash_c(script, STRAND_IN + b"S2\n") == b"a=<\xc3> b=<F1>\n"

    def test_fork_child_gets_a_fresh_registry(self):
        """A child inherits no userspace buffer — only the kernel offset.

        This is a MECHANISM must-hold, NOT a parity cell, and the difference
        matters: the mechanism holding is exactly WHY the observable diverges.
        The parent read one byte ahead to classify the malformed lead, so that
        byte is already gone from the shared kernel offset; the child, starting
        with an empty registry as it must, cannot see it and reads the next one.

        That is I1 deliberate-loss row (d) — the stranded lookahead byte is
        invisible to a child — which slot 4B.4 did NOT close and did not claim
        to: closing it needs a replaying fd view for the child, which campaign
        I1 considered and ruled out. Dup aliasing and frame scoping are
        in-process description bookkeeping and cannot reach across a fork.

        Pinned in both-sides form so the divergence stays VISIBLE: if psh ever
        converges here, this cell fails and the I1 (d) row gets re-examined
        rather than quietly going stale.
        """
        script = (b"read -N 1 a; ( read -N 1 b; printf 'child=<%s>\\n' \"$b\" ); "
                  b"printf 'a=<%s>\\n' \"$a\"")
        psh, bash_c = _psh(script, b"\xc3ABC\n"), _bash_c(script, b"\xc3ABC\n")
        assert psh == b"child=<B>\na=<\xc3>\n"     # child missed the eaten 'A'
        assert bash_c == b"child=<A>\na=<\xc3>\n"  # bash-C never read ahead
        assert psh != bash_c, "I1 (d) — re-examine the row, do not just update it"

    def test_never_over_read_to_external(self):
        assert _psh(b"read x; cat", b"a\nb\nc\n") == b"b\nc\n"


# ---- The well-formed-input faces: a `-t` timeout strands a VALID character
# mid-sequence. These are what made the gap urgent — no malformed input is
# involved, just a character that had not finished arriving. ----

TIMEOUT = 1.0        # >= 1s per the slot's timing-hygiene floor
LATE = 2.0           # 2x the deadline: when the completing bytes arrive
KILL_AFTER = 8.0     # 8x the deadline: hang detection


def _feed_late(argv, script, phase1, phase2=None):
    """Run `argv -c script`, feeding phase2 only AFTER the deadline expired.

    Nothing can race the deadline: phase 2 is written at 2x it. The writer is a
    thread with a bounded join and the child has an 8x watchdog.
    """
    r, w = os.pipe()
    p = subprocess.Popen(list(argv) + ['-c', script.decode()], stdin=r,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         cwd=PSH_ROOT)
    os.close(r)
    os.write(w, phase1)
    t = None
    if phase2 is not None:
        def later():
            time.sleep(LATE)
            try:
                os.write(w, phase2)
            except OSError:
                pass
        t = threading.Thread(target=later, daemon=True)
        t.start()
    try:
        out, _ = p.communicate(timeout=KILL_AFTER + LATE)
    except subprocess.TimeoutExpired:
        p.kill()
        p.communicate()
        raise AssertionError("shell hung on the timeout cell") from None
    finally:
        if t is not None:
            t.join(KILL_AFTER)
        try:
            os.close(w)
        except OSError:
            pass
    return out


@pytest.mark.serial  # real deadlines: a starved clock would flake
class TestTimeoutStrandIsContainedNotLeaked:
    PSH = (sys.executable, '-m', 'psh')
    BASH = ('/opt/homebrew/bin/bash',)

    def test_stranded_partial_does_not_contaminate_a_temp_frame(self, tmp_path):
        """LEG A. A `-t` timeout mid-`é` used to prepend the held lead byte to a
        read from a DIFFERENT FILE."""
        f = tmp_path / "f.txt"
        f.write_bytes(b"FILELINE\n")
        script = (f"read -t {TIMEOUT} -N 2 v; read x < {f}; "
                  'printf "v=%s|x=%s\\n" "$v" "$x"').encode()
        out = _feed_late(self.PSH, script, b"\xc3")
        # ANTI-VACUITY: v empty proves the read timed out MID-CHARACTER and psh
        # held the partial. If v held the byte, nothing was stranded and the
        # cell would pass without ever reaching its subject.
        assert out.startswith(b"v=|"), f"cell stranded nothing: {out!r}"
        # The file read is clean — no byte from stdin in it.
        assert out == b"v=|x=FILELINE\n"

    def test_stranded_partial_is_not_lost_across_a_dup(self, tmp_path):
        """LEG B. `exec 3<&0` used to give fd 3 a fresh cursor, so the held lead
        byte reached NEITHER fd. Every fed byte must reach some reader."""
        script = (f"read -t {TIMEOUT} -N 2 v; exec 3<&0; "
                  f"read -t {TIMEOUT} -u 3 y; read -t {TIMEOUT} -N 1 w; "
                  'printf "v=%s|y=%s|w=%s\\n" "$v" "$y" "$w"').encode()
        out = _feed_late(self.PSH, script, b"\xc3", b"\xa9Z\n")
        assert out.startswith(b"v=|"), f"cell stranded nothing: {out!r}"
        # The é is delivered whole through the SHARED cursor. Before the fix
        # y was b'\xa9Z' and the \xc3 appeared nowhere at all.
        assert out == b"v=|y=\xc3\xa9Z|w=\n", out
        # Byte-conservation, stated as its own property: everything fed came
        # back out. This is the assertion the loss actually violated, and it
        # holds independently of WHERE the shells split the character.
        assert out.count(b"\xc3") == 1 and out.count(b"\xa9") == 1
