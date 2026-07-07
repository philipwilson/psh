"""read / mapfile streaming behavior, pinned to bash 5.2.

Covers the input-service campaign fixes (builtins appraisal findings 4 + 7):

* ``read`` decodes multibyte UTF-8 across read boundaries (``-N``/``-n`` count
  by character, a whole ``é`` never splits into replacement bytes, and the
  leftover stream is byte-correct for the next consumer).
* ``mapfile -n``/``-s`` consume only the records they keep and leave the rest of
  the stream readable — the historical drain bug where ``mapfile -n1`` slurped
  the whole descriptor into a userspace buffer.
* ``mapfile -u BADFD`` errors (status 1) instead of silently succeeding, and
  negative/invalid counts and origins are rejected with bash's messages.

All cases feed explicit stdin bytes (never the session stdin) with a kill-on-
expiry timeout. Subprocess is required: the drain/leftover cases need a real
descriptor shared between two consumers.
"""

import os
import signal
import subprocess
import sys

import pytest

PSH = [sys.executable, "-m", "psh"]
BASH = "bash"


def _run(argv, script, stdin_bytes, timeout=10):
    """Run ``argv -c script`` feeding stdin_bytes; kill the group on expiry."""
    p = subprocess.Popen(
        argv + ["-c", script],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=True)
    try:
        out, err = p.communicate(input=stdin_bytes, timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(p.pid), signal.SIGKILL)
        p.communicate()
        raise
    return p.returncode, out, err


def _psh(script, stdin_bytes, timeout=10):
    return _run(PSH, script, stdin_bytes, timeout)


def _both_match(script, stdin_bytes):
    """Assert psh and bash agree on (returncode, stdout)."""
    pr, po, _ = _run(PSH, script, stdin_bytes)
    br, bo, _ = _run([BASH], script, stdin_bytes)
    assert (pr, po) == (br, bo), (
        f"script={script!r} stdin={stdin_bytes!r}\n"
        f"  psh : rc={pr} out={po!r}\n  bash: rc={br} out={bo!r}")


class TestReadUtf8:
    def test_line_roundtrips_multibyte(self):
        rc, out, _ = _psh('read x; printf "%s" "$x"',
                          "héllo wörld\n".encode("utf-8"))
        assert rc == 0
        assert out == "héllo wörld".encode("utf-8")

    def test_N1_reads_one_multibyte_char(self):
        rc, out, _ = _psh('read -N1 x; printf "%s" "$x"', "éxy\n".encode("utf-8"))
        assert rc == 0
        assert out == "é".encode("utf-8")

    def test_n1_reads_one_multibyte_char(self):
        rc, out, _ = _psh('read -n1 x; printf "%s" "$x"', "éxy\n".encode("utf-8"))
        assert rc == 0
        assert out == "é".encode("utf-8")

    def test_emoji_N1(self):
        rc, out, _ = _psh('read -N1 x; printf "%s" "$x"', "😀y\n".encode("utf-8"))
        assert rc == 0
        assert out == "😀".encode("utf-8")

    def test_N1_leaves_byte_correct_leftover(self):
        # The orphaned continuation byte of é must not leak to the next reader.
        rc, out, _ = _psh('read -N1 x; cat', "éb\n".encode("utf-8"))
        assert rc == 0
        assert out == b"b\n"

    def test_matches_bash(self):
        # A full line read is byte-transparent in every locale, so psh and bash
        # agree regardless of LC_*. (Character *counting* — read -N1/-n1 on a
        # multibyte char — matches bash only in a UTF-8 locale: psh is
        # Unicode-native while bash counts bytes in the C locale. That
        # byte-vs-character model difference is documented in the user guide, so
        # it is pinned above as psh behavior rather than compared here.)
        _both_match('read x; printf "%s" "$x"', "wörld\n".encode("utf-8"))
        _both_match('read a b; echo "[$a][$b]"', b"one two three\n")


class TestReadLeftover:
    def test_read_then_cat_leaves_rest(self):
        rc, out, _ = _psh("read x; echo \"got=$x\"; cat", b"a\nb\nc\n")
        assert rc == 0
        assert out == b"got=a\nb\nc\n"

    def test_two_reads(self):
        rc, out, _ = _psh('read x; read y; echo "[$x][$y]"',
                          b"first\nsecond\nthird\n")
        assert out == b"[first][second]\n"


class TestMapfileDrainFix:
    def test_n1_leaves_rest_readable(self):
        # Historical bug: mapfile -n1 drained the whole pipe; cat saw nothing.
        rc, out, _ = _psh('mapfile -n1 v; printf "v=%s" "${v[0]}"; cat',
                          b"a\nb\nc\n")
        assert rc == 0
        assert out == b"v=a\nb\nc\n"

    def test_n2_leaves_rest_readable(self):
        rc, out, _ = _psh('mapfile -n2 v; echo "n=${#v[@]}"; cat', b"a\nb\nc\nd\n")
        assert out == b"n=2\nc\nd\n"

    def test_skip_and_count_leave_rest(self):
        rc, out, _ = _psh('mapfile -s1 -n1 v; printf "v=%s" "${v[0]}"; cat',
                          b"a\nb\nc\nd\n")
        assert out == b"v=b\nc\nd\n"

    def test_no_count_still_reads_all(self):
        rc, out, _ = _psh('mapfile v; echo "n=${#v[@]}"; cat', b"a\nb\nc\n")
        assert out == b"n=3\n"

    def test_matches_bash(self):
        _both_match('mapfile -n1 v; printf "v=%s" "${v[0]}"; cat', b"a\nb\nc\n")
        _both_match('mapfile -s1 -n1 v; printf "v=%s" "${v[0]}"; cat',
                    b"a\nb\nc\nd\n")


class TestMapfileValidation:
    def test_bad_fd_errors(self):
        rc, out, err = _psh("mapfile -u99 a; echo rc=$?", b"data\n")
        assert out == b"rc=1\n"
        assert b"invalid file descriptor" in err

    def test_negative_count_rejected(self):
        rc, out, err = _psh("mapfile -n-1 a; echo rc=$?", b"one\ntwo\n")
        assert out == b"rc=1\n"
        assert b"invalid line count" in err

    def test_negative_skip_rejected(self):
        rc, out, err = _psh("mapfile -s-1 a; echo rc=$?", b"one\ntwo\n")
        assert out == b"rc=1\n"
        assert b"invalid line count" in err

    def test_negative_origin_rejected(self):
        rc, out, err = _psh("mapfile -O-1 a; echo rc=$?", b"one\n")
        assert out == b"rc=1\n"
        assert b"invalid array origin" in err

    def test_nonnumeric_count_rejected(self):
        rc, out, err = _psh("mapfile -nabc a; echo rc=$?", b"one\n")
        assert out == b"rc=1\n"
        assert b"invalid line count" in err

    @pytest.mark.parametrize("spec,needle", [
        ("-n-5", b"invalid line count"),
        ("-Oabc", b"invalid array origin"),
        ("-uxyz", b"invalid file descriptor specification"),
    ])
    def test_matches_bash_validation(self, spec, needle):
        _both_match(f"mapfile {spec} a; echo rc=$?", b"one\ntwo\n")
        _, _, err = _psh(f"mapfile {spec} a", b"one\ntwo\n")
        assert needle in err
