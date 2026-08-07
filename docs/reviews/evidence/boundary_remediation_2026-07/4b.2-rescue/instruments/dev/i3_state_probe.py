#!/usr/bin/env python3
"""i3 — DYNAMIC seam census for InputCursor (slot 4B.2 Phase A).

Drives each public entry point over a real ``os.pipe()`` and records the
observable cursor-state quadruple after every call, so the seam-route table is
MEASURED rather than read off the source.

Each cell is independently runnable (``python i3_state_probe.py <cell>``) so a
red/green derivation can isolate one interpreter per cell; ``all`` runs every
cell in one process for the exploratory table (labelled as such in the output).

Every fd opened here is closed in a finally block: no fd may leak.
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

import psh.builtins.input_reader as ir  # noqa: E402
from psh.builtins.input_reader import InputCursor, Outcome  # noqa: E402

E_ACUTE = 'é'.encode('utf-8')      # C3 A9        (2 bytes)
EURO = '€'.encode('utf-8')         # E2 82 AC     (3 bytes)
SMILE = '🙂'.encode('utf-8')       # F0 9F 99 82  (4 bytes)


def discriminator() -> None:
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(['git', 'status', '--porcelain', 'psh/'], cwd=ROOT,
                           capture_output=True, text=True).stdout
    print("== DISCRIMINATOR ==")
    print(f"module under test: {ir.__file__}")
    print(f"repo root:         {ROOT}")
    print(f"HEAD:              {head}")
    print(f"psh/ dirty lines:  {len(dirty.splitlines())}")
    print(f"python:            {sys.version.split()[0]}")
    print()


def state(c: InputCursor) -> str:
    """The observable cursor-lifetime state quadruple."""
    dec = c._decoder
    pending = dec.getstate()[0] if dec is not None else b''
    return (f"decoder={'LIVE' if dec is not None else 'None'} "
            f"pending={pending!r} "
            f"decoded={''.join(c._decoded)!r} "
            f"pushback={bytes(c._pushback)!r}")


def show(label: str, cur: InputCursor, extra: str = '') -> None:
    print(f"    [{label}] {extra}{' | ' if extra else ''}{state(cur)}")


# --------------------------------------------------------------------------
# cells
# --------------------------------------------------------------------------

def cell_timeout_then_read_all() -> None:
    """R1: timed read TIMES OUT mid-multibyte -> read_all drains the rest."""
    print("-- R1: TIMEOUT mid-sequence, then read_all --")
    r, w = os.pipe()
    try:
        os.write(w, E_ACUTE[:1])            # C3 only: char is incomplete
        cur = InputCursor(fd=r)
        res = cur.read_record(delimiter='\n', include_delimiter=True,
                              deadline=time.monotonic() + 0.25)
        show("after timed read", cur, f"outcome={res.outcome.name} data={res.data!r}")
        os.write(w, E_ACUTE[1:] + b'\n')    # A9 \n: completes the char
        os.close(w)
        w = -1
        out = cur.read_all()
        show("after read_all", cur, f"out={out!r}")
        print(f"    CHAR-IDENTITY: got {out!r} want {'é\n'!r} -> "
              f"{'PASS' if out == 'é\n' else 'FAIL'}")
        rt = out.encode('utf-8', 'surrogateescape')
        print(f"    ROUND-TRIP:    got {rt!r} want {E_ACUTE + b'\n'!r} -> "
              f"{'PASS' if rt == E_ACUTE + b'\n' else 'FAIL'}")
    finally:
        os.close(r)
        if w != -1:
            os.close(w)


def cell_timeout_then_read_record() -> None:
    """R2: does the NEXT timed read RESUME the split char correctly?"""
    print("-- R2: TIMEOUT mid-sequence, then another read_record (resume) --")
    r, w = os.pipe()
    try:
        os.write(w, EURO[:2])               # E2 82: incomplete 3-byte char
        cur = InputCursor(fd=r)
        res = cur.read_record(delimiter='\n', include_delimiter=True,
                              deadline=time.monotonic() + 0.25)
        show("after timed read", cur, f"outcome={res.outcome.name} data={res.data!r}")
        os.write(w, EURO[2:] + b'\n')
        res2 = cur.read_record(delimiter='\n', include_delimiter=True,
                               deadline=time.monotonic() + 2.0)
        show("after resume read", cur,
             f"outcome={res2.outcome.name} data={res2.data!r}")
        print(f"    CHAR-IDENTITY: got {res2.data!r} want {'€\n'!r} -> "
              f"{'PASS' if res2.data == '€\n' else 'FAIL'}")
    finally:
        os.close(r)
        os.close(w)


def cell_timeout_then_read_limited() -> None:
    """R3: TIMEOUT mid-sequence, then a -N style count read."""
    print("-- R3: TIMEOUT mid-sequence, then read_limited (-N shape) --")
    r, w = os.pipe()
    try:
        os.write(w, SMILE[:3])              # F0 9F 99: incomplete 4-byte char
        cur = InputCursor(fd=r)
        res = cur.read_record(delimiter='\n', include_delimiter=True,
                              deadline=time.monotonic() + 0.25)
        show("after timed read", cur, f"outcome={res.outcome.name} data={res.data!r}")
        os.write(w, SMILE[3:])
        res2 = cur.read_limited(delimiter=None, max_chars=1,
                                deadline=time.monotonic() + 2.0)
        show("after read_limited", cur,
             f"outcome={res2.outcome.name} data={res2.data!r}")
        print(f"    CHAR-IDENTITY: got {res2.data!r} want {'🙂'!r} -> "
              f"{'PASS' if res2.data == '🙂' else 'FAIL'}")
    finally:
        os.close(r)
        os.close(w)


def cell_eof_mid_sequence() -> None:
    """R4: EOF mid-multibyte — does it leave decoder state behind?"""
    print("-- R4: EOF mid-sequence (truncated char at EOF) --")
    r, w = os.pipe()
    try:
        os.write(w, EURO[:2])
        os.close(w)
        cur = InputCursor(fd=r)
        res = cur.read_record(delimiter='\n', include_delimiter=True)
        show("after read_record to EOF", cur,
             f"outcome={res.outcome.name} data={res.data!r}")
        rt = res.data.encode('utf-8', 'surrogateescape')
        print(f"    ROUND-TRIP:    got {rt!r} want {EURO[:2]!r} -> "
              f"{'PASS' if rt == EURO[:2] else 'FAIL'}")
        out = cur.read_all()
        show("after read_all", cur, f"out={out!r}")
    finally:
        os.close(r)


def cell_surplus_decoded() -> None:
    """R5: malformed lead + ASCII leaves a SURPLUS char in _decoded."""
    print("-- R5: surplus in _decoded (malformed lead disambiguated) --")
    r, w = os.pipe()
    try:
        os.write(w, b'\xc3A' + EURO + b'\n')   # C3 is a lead with no continuation
        cur = InputCursor(fd=r)
        res = cur.read_limited(delimiter=None, max_chars=1)
        show("after read_limited(1)", cur,
             f"outcome={res.outcome.name} data={res.data!r}")
        os.close(w)
        w = -1
        out = cur.read_all()
        show("after read_all", cur, f"out={out!r}")
        whole = res.data + out
        rt = whole.encode('utf-8', 'surrogateescape')
        want = b'\xc3A' + EURO + b'\n'
        print(f"    ROUND-TRIP:    got {rt!r} want {want!r} -> "
              f"{'PASS' if rt == want else 'FAIL'}")
    finally:
        os.close(r)
        if w != -1:
            os.close(w)


def cell_can_count_split_a_char() -> None:
    """R6: can a COUNT boundary alone leave pending decoder state?

    The claim under test is that only TIMEOUT/ERROR can strand a partial
    sequence (EOF flushes, and the char loop never returns mid-character).
    """
    print("-- R6: can a -N count boundary strand a partial sequence? --")
    r, w = os.pipe()
    try:
        os.write(w, b'a' + EURO + b'b')
        cur = InputCursor(fd=r)
        for n in (1, 2, 3):
            res = cur.read_limited(delimiter=None, max_chars=1)
            show(f"after read_limited(1) #{n}", cur,
                 f"outcome={res.outcome.name} data={res.data!r}")
        os.close(w)
        w = -1
        out = cur.read_all()
        show("after read_all", cur, f"out={out!r}")
    finally:
        os.close(r)
        if w != -1:
            os.close(w)


def cell_pushback_producers() -> None:
    """R7: is _pushback EVER populated by any public call sequence? (P1)"""
    print("-- R7: _pushback population census (dynamic) --")
    NL = ord('\n')
    seqs = [
        ("read_record_bytes x2 over 2 records", b'one\ntwo\n'),
        ("read_record_bytes, partial final record", b'one\ntwo'),
        ("read_record_bytes over multibyte record", EURO + b'\n' + E_ACUTE),
        ("read_record_bytes empty record", b'\n\n'),
    ]
    for label, payload in seqs:
        r, w = os.pipe()
        try:
            os.write(w, payload)
            os.close(w)
            w = -1
            cur = InputCursor(fd=r)
            n = 0
            while True:
                rec = cur.read_record_bytes(delimiter_byte=NL)
                n += 1
                show(f"{label} rec#{n}", cur, f"rec={rec!r}")
                if rec is None or n > 5:
                    break
        finally:
            os.close(r)
            if w != -1:
                os.close(w)
    print("    (a non-empty pushback= above would REFUTE P1)")


def cell_stream_duality() -> None:
    """R8: the stream source has no decoder seam at all."""
    print("-- R8: stream (non-fd) source duality --")
    import io as _io
    cur = InputCursor(stream=_io.StringIO("é€\nrest"))
    res = cur.read_record(delimiter='\n', include_delimiter=True)
    show("after read_record", cur, f"outcome={res.outcome.name} data={res.data!r}")
    out = cur.read_all()
    show("after read_all", cur, f"out={out!r}")


def cell_decoder_equivalence() -> None:
    """R9: is decoder.decode(raw, final=True) == raw.decode(surrogateescape)?

    The proposed fix feeds the tail through the EXISTING decoder; when the
    decoder is CLEAN that must be indistinguishable from the fresh one-shot
    decode the current code does, or the fix would change untouched behavior.
    """
    print("-- R9: incremental-final vs one-shot decode equivalence (clean decoder) --")
    import codecs
    payloads = [b'', b'abc\n', EURO + b'\n', SMILE, b'\xc3A', b'\xa9',
                b'a\xffb', EURO[:2], SMILE[:1], b'\x80\x80']
    bad = 0
    for p in payloads:
        one = p.decode('utf-8', errors='surrogateescape')
        dec = codecs.getincrementaldecoder('utf-8')('surrogateescape')
        inc = dec.decode(p, final=True)
        ok = one == inc
        bad += 0 if ok else 1
        print(f"    {p!r:>16} one-shot={one!r} incremental-final={inc!r} "
              f"-> {'SAME' if ok else 'DIFFER'}")
    print(f"    DIFFERING PAYLOADS: {bad} (0 = the fix's clean-decoder path is "
          f"behaviour-preserving)")


CELLS = {
    'r1_timeout_read_all': cell_timeout_then_read_all,
    'r2_timeout_resume': cell_timeout_then_read_record,
    'r3_timeout_read_limited': cell_timeout_then_read_limited,
    'r4_eof_mid_sequence': cell_eof_mid_sequence,
    'r5_surplus_decoded': cell_surplus_decoded,
    'r6_count_boundary': cell_can_count_split_a_char,
    'r7_pushback_census': cell_pushback_producers,
    'r8_stream_duality': cell_stream_duality,
    'r9_decoder_equivalence': cell_decoder_equivalence,
}


def main() -> int:
    discriminator()
    which = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if which == 'all':
        print("MODE: all cells in ONE interpreter (EXPLORATORY census; a "
              "red/green derivation runs one cell per interpreter)\n")
        for name, fn in CELLS.items():
            print(f"### {name}")
            fn()
            print()
        return 0
    if which not in CELLS:
        print(f"unknown cell {which!r}; known: {', '.join(CELLS)}",
              file=sys.stderr)
        return 2
    print(f"MODE: single cell {which!r} (isolated interpreter)\n")
    CELLS[which]()
    return 0


if __name__ == '__main__':
    sys.exit(main())
