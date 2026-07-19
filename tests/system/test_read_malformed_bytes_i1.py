"""Byte-level behavioral pins for the source-lifetime byte cursor (campaign I1,
closes #20 H16).

The `read`/`mapfile` character path used to decode with ``errors='replace'``
(U+FFFD) and, worse, mis-read the byte after a malformed lead as a continuation,
eating record delimiters and cascading every following record into replacement
characters. It now decodes through one incremental UTF-8 ``surrogateescape``
decoder: a valid multibyte char is one char, a MALFORMED byte round-trips as a
lone surrogate.

Text-layer probes cannot see fd-level bugs (banked v0.662 lesson), so every case
feeds RAW BYTES on a pipe and compares RAW stdout bytes.

Oracle: psh's clean byte model equals **C-locale bash** (byte-per-char) for
every malformed case, so each row is asserted against ``LC_ALL=C bash`` — a
stable, portable oracle. Ambient UTF-8-locale bash additionally exhibits libc
``mbrtowc`` quirks (an incomplete lead swallows the following delimiter; ``read
-N`` over-reads on a trailing incomplete lead); those are documented deliberate
divergences (DECISION 1) and are recorded in the per-row comments, not matched.

Run RED-ON-BASE by pointing PSH_ROOT at a pre-I1 tree:
    PSH_ROOT=/path/to/base python -m pytest tests/system/test_read_malformed_bytes_i1.py
"""
import os
import subprocess
import sys

import pytest
from shell_oracle import resolve_bash

PSH_ROOT = os.environ.get(
    "PSH_ROOT",
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)
BASH = resolve_bash().path


def _psh(script: bytes, stdin: bytes) -> bytes:
    p = subprocess.run(
        [sys.executable, "-m", "psh", "-c", script.decode()],
        input=stdin, capture_output=True, cwd=PSH_ROOT, timeout=15,
        env={**os.environ, "PYTHONPATH": PSH_ROOT, "PSH_STRICT_ERRORS": "1"},
    )
    return p.stdout


def _bash_c_locale(script: bytes, stdin: bytes) -> bytes:
    # The oracle BINARY comes from the sanctioned resolver (E2 ratchet); the
    # run mode stays local because these cases compare RAW stdout bytes and
    # run_shell_case's decoded-text policy would hide the byte-level facts.
    p = subprocess.run(
        [BASH, "-c", script.decode()],
        input=stdin, capture_output=True, timeout=15,
        env={**os.environ, "LC_ALL": "C", "LANG": "C"},
    )
    return p.stdout


# name -> (script, stdin, note about ambient UTF-8-bash quirk if any)
MALFORMED_ROWS = {
    # parity even with UTF-8 bash: \xc3 followed by A is invalid, delimiter respected
    "read_then_read": (
        b"read x; read y; printf 'x=<%s> y=<%s>\\n' \"$x\" \"$y\"",
        b"\xc3A\nB\n", None),
    # bare invalid bytes round-trip, then the newline delimiter stops the record
    "bare_invalid": (
        b"read x; printf 'x=<%s>\\n' \"$x\"", b"\xff\xfe\nB\n", None),
    "mapfile_lines": (
        b"mapfile -t a; printf '<%s>' \"${a[@]}\"; echo", b"\xc3A\nB\n", None),
    "mapfile_read_all": (
        b"mapfile a; printf '<%s>' \"${a[@]}\"; echo", b"\xc3A\nB\n", None),
    # DOCUMENTED DIVERGENCE from ambient UTF-8 bash: a malformed lead before the
    # newline. UTF-8 bash SWALLOWS the delimiter (x=<A\xc3\nB>); psh respects it
    # (x=<A\xc3>), matching C-locale bash.
    "lead_before_newline": (
        b"read x; printf 'x=<%s>\\n' \"$x\"", b"A\xc3\nB\n", "utf8 bash swallows \\n"),
    # DOCUMENTED DIVERGENCE from ambient UTF-8 bash: read -N on a trailing
    # incomplete lead. UTF-8 bash over-reads to 6 bytes (x=<\xc3A\xc3B\n>);
    # psh counts one surrogate per malformed byte (x=<\xc3A\xc3>), matching C bash.
    "read_N_malformed": (
        b"read -N 3 x; printf 'x=<%s>\\n' \"$x\"", b"\xc3A\xc3B\n", "utf8 bash over-reads"),
}


@pytest.mark.parametrize("name", sorted(MALFORMED_ROWS))
def test_read_malformed_matches_c_locale_bash(name):
    script, stdin, _quirk = MALFORMED_ROWS[name]
    psh_out = _psh(script, stdin)
    bash_out = _bash_c_locale(script, stdin)
    assert psh_out == bash_out, (
        f"{name}: psh {psh_out!r} != C-locale bash {bash_out!r}")


def test_malformed_does_not_cascade_through_delimiters():
    """The #20 H16 headline: a malformed lead must not eat the record delimiter.

    On base psh this printed five U+FFFD chars for x and an EMPTY y; now x holds
    the two raw bytes and y holds B.
    """
    out = _psh(b"read x; read y; printf 'x=<%s> y=<%s>\\n' \"$x\" \"$y\"",
               b"\xc3A\nB\n")
    assert out == b"x=<\xc3A> y=<B>\n"


def test_valid_multibyte_is_one_char_per_codepoint():
    # A valid multibyte char decodes whole and counts as ONE character. psh
    # decodes read/mapfile input as UTF-8 surrogateescape regardless of
    # LC_CTYPE (locale-blind — pre-existing behavior, not changed by I1), so
    # `read -N 2` on two 2-byte chars yields both chars. This matches a
    # UTF-8-locale bash; a C-locale bash would count 2 BYTES instead (one
    # char) — a documented locale divergence psh does not track.
    out = _psh(b"read -N 2 x; printf 'x=<%s>\\n' \"$x\"", b"\xc3\xa9\xc3\xa8\n")
    assert out == b"x=<\xc3\xa9\xc3\xa8>\n"  # e-acute e-grave, both preserved


# ---- never-over-read: a record read leaves the rest for an external child ----

@pytest.mark.parametrize("tail_cmd,expected", [
    (b"cat", b"b\nc\n"),
    (b"head -1", b"b\n"),
])
def test_read_then_external_never_over_reads(tail_cmd, expected):
    out = _psh(b"read x; " + tail_cmd, b"a\nb\nc\n")
    assert out == expected


def test_mapfile_n1_then_cat_never_over_reads():
    out = _psh(b"mapfile -n1 a; printf 'arr=<%s>' \"${a[@]}\"; cat", b"a\nb\nc\n")
    assert out == b"arr=<a\n>b\nc\n"


# ---- same-fd count-boundary carryover (persistent cursor) ----

def test_same_fd_malformed_count_carryover():
    """`read -N1 x; read -N1 y` on \\xc3A: the byte read to classify the
    malformed lead survives to the next read on the same description
    (matches C-locale bash x=\\xc3 y=A). On base the surplus was lost."""
    out = _psh(b"read -N 1 x; read -N 1 y; printf 'x=<%s> y=<%s>\\n' \"$x\" \"$y\"",
               b"\xc3A\n")
    assert out == b"x=<\xc3> y=<A>\n"
