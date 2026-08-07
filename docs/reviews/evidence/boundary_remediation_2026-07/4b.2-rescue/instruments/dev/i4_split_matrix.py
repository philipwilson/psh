#!/usr/bin/env python3
"""i4 — the SPLIT POINT x SEAM ROUTE matrix (slot 4B.2 Phase A item 2).

Every internal split point of a 2-, 3- and 4-byte UTF-8 character, crossed with
every seam route the i3 census found can strand a partial sequence, asserting
BOTH halves of the exit criterion per cell:

  * CHAR IDENTITY   — the drained text equals the original character sequence
  * BYTE ROUND-TRIP — text.encode('utf-8','surrogateescape') equals the bytes

Cells that are already GREEN at base are labelled CONTROL: they are must-hold
rows, not defect evidence. The summary reports the red/green split PER CLASS as
a measured number (never "all X except Y").

Run: python i4_split_matrix.py            # whole matrix, one interpreter
     python i4_split_matrix.py <cell-id>  # one cell, isolated interpreter
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

CHARS = [('e_acute', 'é'), ('euro', '€'), ('smile', '🙂')]
SUFFIX = 'Z\n'          # trailing context, so a merge-ORDER error is visible


def discriminator() -> None:
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(['git', 'status', '--porcelain', 'psh/'], cwd=ROOT,
                           capture_output=True, text=True).stdout
    print("== DISCRIMINATOR ==")
    print(f"module under test: {ir.__file__}")
    print(f"HEAD:              {head}")
    print(f"psh/ dirty lines:  {len(dirty.splitlines())}")
    print(f"python:            {sys.version.split()[0]}")
    print()


class Cell:
    """One matrix cell: a payload split at a byte offset, drained by a route."""

    def __init__(self, cid, route, klass, payload, split, want_text,
                 tail_after_timeout=True, expect_green_at_base=None):
        self.cid = cid
        self.route = route
        self.klass = klass
        self.payload = payload
        self.split = split
        self.want_text = want_text
        self.tail_after_timeout = tail_after_timeout
        self.expect_green_at_base = expect_green_at_base

    def run(self):
        """Return (identity_pass, roundtrip_pass, observed_text)."""
        r, w = os.pipe()
        wopen = True
        try:
            os.write(w, self.payload[:self.split])
            cur = InputCursor(fd=r)
            res = cur.read_record(delimiter='\n', include_delimiter=True,
                                  deadline=time.monotonic() + 0.25)
            assert res.outcome is Outcome.TIMEOUT, (
                f"{self.cid}: setup did not TIME OUT (got {res.outcome})")
            prefix = res.data
            if self.tail_after_timeout:
                os.write(w, self.payload[self.split:])
            os.close(w)
            wopen = False
            if self.route == 'read_all':
                got = prefix + cur.read_all()
            elif self.route == 'read_record':
                out = []
                while True:
                    rr = cur.read_record(delimiter='\n', include_delimiter=True,
                                         deadline=time.monotonic() + 2.0)
                    out.append(rr.data)
                    if rr.outcome is not Outcome.DATA:
                        break
                got = prefix + ''.join(out)
            elif self.route == 'read_limited':
                out = []
                while True:
                    rr = cur.read_limited(delimiter=None, max_chars=1,
                                          deadline=time.monotonic() + 2.0)
                    out.append(rr.data)
                    if rr.outcome is not Outcome.DATA:
                        break
                got = prefix + ''.join(out)
            else:
                raise AssertionError(f"unknown route {self.route}")
        finally:
            os.close(r)
            if wopen:
                os.close(w)
        identity = got == self.want_text
        want_bytes = (self.payload if self.tail_after_timeout
                      else self.payload[:self.split])
        roundtrip = got.encode('utf-8', 'surrogateescape') == want_bytes
        return identity, roundtrip, got


def build_matrix():
    cells = []
    # ---- class SPLIT: a VALID multibyte char split at every internal point,
    #      tail arrives after the timeout, drained by each route.
    for name, ch in CHARS:
        raw = ch.encode('utf-8')
        text = ch + SUFFIX
        payload = raw + SUFFIX.encode('utf-8')
        for split in range(1, len(raw)):
            for route in ('read_all', 'read_record', 'read_limited'):
                cells.append(Cell(
                    cid=f"split.{name}.{split}.{route}",
                    route=route, klass=f"SPLIT/{route}",
                    payload=payload, split=split, want_text=text))
    # ---- class NOTAIL: the completing bytes NEVER arrive (EOF right after the
    #      timeout). Both current and fixed code must surrogate-escape the
    #      stranded lead; this is a MUST-HOLD control for the fix.
    for name, ch in CHARS:
        raw = ch.encode('utf-8')
        for split in range(1, len(raw)):
            want = raw[:split].decode('utf-8', 'surrogateescape')
            cells.append(Cell(
                cid=f"notail.{name}.{split}.read_all",
                route='read_all', klass="NOTAIL/read_all",
                payload=raw, split=split, want_text=want,
                tail_after_timeout=False))
    # ---- class NONCONT: after the timeout the next byte is NOT a continuation
    #      (so the pending lead is genuinely malformed). MUST-HOLD control: the
    #      fix must not change this, and it discriminates "fed through the
    #      existing decoder" from "silently swallowed".
    for name, ch in CHARS:
        raw = ch.encode('utf-8')
        for split in range(1, len(raw)):
            payload = raw[:split] + SUFFIX.encode('utf-8')
            want = payload.decode('utf-8', 'surrogateescape')
            cells.append(Cell(
                cid=f"noncont.{name}.{split}.read_all",
                route='read_all', klass="NONCONT/read_all",
                payload=payload, split=split, want_text=want))
    # ---- class MALFORMED: genuinely malformed byte sequences across the seam.
    #      surrogateescape POLICY is settled; these are MUST-HOLD.
    malformed = [
        ('lone_lead_then_ascii', b'\xc3' + b'A' + SUFFIX.encode('utf-8'), 1),
        ('orphan_continuation', b'\xa9' + SUFFIX.encode('utf-8'), 1),
        ('two_leads', b'\xc3\xc3' + SUFFIX.encode('utf-8'), 1),
        ('overlong_lead', b'\xf0\x9f' + b'\x41' + SUFFIX.encode('utf-8'), 2),
        ('bare_ff', b'\xff' + SUFFIX.encode('utf-8'), 1),
        ('c0_80', b'\xc0\x80' + SUFFIX.encode('utf-8'), 1),
    ]
    for name, payload, split in malformed:
        want = payload.decode('utf-8', 'surrogateescape')
        cells.append(Cell(
            cid=f"malformed.{name}.read_all",
            route='read_all', klass="MALFORMED/read_all",
            payload=payload, split=split, want_text=want))
    return cells


def main() -> int:
    discriminator()
    cells = build_matrix()
    only = sys.argv[1] if len(sys.argv) > 1 else None
    if only:
        cells = [c for c in cells if c.cid == only]
        if not cells:
            print(f"unknown cell id {only!r}", file=sys.stderr)
            return 2
        print(f"MODE: single cell {only!r} (isolated interpreter)\n")
    else:
        print("MODE: whole matrix in ONE interpreter (exploratory table; the "
              "red-on-base COUNT is derived per-cell from the pytest pins)\n")

    per_class = {}
    print(f"{'CELL':<44} {'IDENT':<6} {'RTRIP':<6} OBSERVED")
    print("-" * 100)
    for c in cells:
        ident, rtrip, got = c.run()
        cell_ok = ident and rtrip
        stats = per_class.setdefault(c.klass, {'pass': 0, 'fail': 0,
                                               'ident_fail': 0, 'rt_fail': 0})
        stats['pass' if cell_ok else 'fail'] += 1
        if not ident:
            stats['ident_fail'] += 1
        if not rtrip:
            stats['rt_fail'] += 1
        print(f"{c.cid:<44} {'PASS' if ident else 'FAIL':<6} "
              f"{'PASS' if rtrip else 'FAIL':<6} {got!r}")

    print()
    print("== PER-CLASS MEASURED SPLIT (never 'all X except Y') ==")
    tot_p = tot_f = 0
    for klass in sorted(per_class):
        s = per_class[klass]
        n = s['pass'] + s['fail']
        tot_p += s['pass']
        tot_f += s['fail']
        label = ("CONTROL (must-hold)" if s['fail'] == 0
                 else "DEFECT EVIDENCE (red-on-base)")
        print(f"  {klass:<22} {n:>3} cells: {s['pass']:>3} pass / "
              f"{s['fail']:>3} fail  "
              f"(identity-fail {s['ident_fail']}, round-trip-fail {s['rt_fail']})"
              f"  -> {label}")
    print(f"  {'TOTAL':<22} {tot_p + tot_f:>3} cells: {tot_p:>3} pass / "
          f"{tot_f:>3} fail")
    return 0


if __name__ == '__main__':
    sys.exit(main())
