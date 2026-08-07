#!/usr/bin/env python3
"""i6 — the A5 rider matrix, v2 with a SHELL-NEUTRAL producer (Phase A item 3).

WHY v2 EXISTS (recorded, not hidden): i5_rider_matrix.py produced the byte
stream with the SHELL UNDER TEST (``printf 'a\\303'`` inside the pipeline). bash
and psh render octal escapes differently, so the multibyte cells compared two
different INPUTS and the divergence they showed was a producer artifact, not a
``read`` behaviour. See tmp/w4b2/i5_rider_matrix_base.txt for that run and
tmp/w4b2/INSTRUMENT-DEFECT-i5.md for the write-up. This version:

  * produces bytes from a NON-SHELL process (this harness) through a FIFO, on a
    scripted timeline, so both shells consume the IDENTICAL byte stream;
  * compares the assigned value as RAW BYTES (``od -An -tx1``, an external
    program) rather than ``printf %q``, so a %q rendering difference cannot be
    mistaken for a read difference;
  * can hold the FIFO open past the deadline (``hold=True``), which is the only
    way to reproduce the TRUE hang — with a producer that exits, psh's ``-N``
    terminates at EOF and the hang is invisible.

Hygiene: PATH bash /opt/homebrew/bin/bash 5.2.26 with explicit argv, never
/bin/bash; every shell runs in its own session under a bounded process-GROUP
kill (8x the 1.0s deadline); explicit env with LC_ALL pinned; FIFOs live in a
per-run scratch dir under this worktree's tmp/ and are removed at the end.
"""
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

BASH = '/opt/homebrew/bin/bash'
KILL_AFTER = 8.0
LC = 'en_US.UTF-8'
ENV = {
    'PATH': '/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',
    'HOME': os.environ.get('HOME', '/tmp'),
    'LC_ALL': LC, 'LANG': LC, 'TERM': 'dumb',
}

# The producer runs as a separate python process so the shell under test never
# generates the bytes. steps = [(delay_seconds, bytes), ...]; hold keeps the
# write end OPEN (no EOF) for hold_seconds after the last step.
PRODUCER = r'''
import os, sys, time
fifo, hold = sys.argv[1], float(sys.argv[2])
steps = eval(sys.argv[3])
fd = os.open(fifo, os.O_WRONLY)
try:
    for delay, data in steps:
        time.sleep(delay)
        os.write(fd, data)
    if hold:
        time.sleep(hold)
finally:
    os.close(fd)
'''

# Script template: run `read`, then report rc and the RAW BYTES of the value.
SCRIPT = (r'''read {opts} x < {fifo}; rc=$?; '''
          r'''printf 'rc=%s bytes=' "$rc"; '''
          r'''printf '%s' "$x" | od -An -tx1 | tr -d ' \n'; printf '\n' ''')

# id, description, read-options, producer steps, hold-seconds
CELLS = [
    # ---- headline: -N x -t, with a producer that HOLDS the fifo open (no EOF)
    ('N_none_hold', '-N 3 -t 1, no input and NO EOF (the true hang repro)',
     '-t 1 -N 3', [], 4.0),
    ('N_partial_hold', '-N 3 -t 1, 2 of 3 chars then silence, NO EOF',
     '-t 1 -N 3', [(0.1, b'ab')], 4.0),
    ('N_full_hold', '-N 3 -t 1, all 3 chars early, NO EOF [CONTROL]',
     '-t 1 -N 3', [(0.1, b'abc')], 4.0),
    ('N_late_hold', '-N 3 -t 1, input arrives AFTER the deadline, NO EOF',
     '-t 1 -N 3', [(2.0, b'abc')], 2.0),
    # ---- EOF-vs-timeout discrimination (producer exits => EOF)
    ('N_eof_short_no_t', '-N 3, EOF before the count, no -t [CONTROL]',
     '-N 3', [(0.0, b'ab')], 0.0),
    ('N_eof_short_with_t', '-N 3 -t 1, EOF before the count (EOF vs timeout)',
     '-t 1 -N 3', [(0.0, b'ab')], 0.0),
    ('N_eof_after_deadline', '-N 3 -t 1, partial then EOF AFTER the deadline',
     '-t 1 -N 3', [(0.1, b'ab')], 2.0),
    # ---- degenerate counts and the poll
    ('N_zero_with_t', '-N 0 -t 1, count zero, NO EOF',
     '-t 1 -N 0', [], 3.0),
    ('N_t0_ready', '-N 3 -t 0, data READY (poll)',
     '-t 0 -N 3', [(0.0, b'abc')], 1.0),
    ('N_t0_notready', '-N 3 -t 0, data NOT ready (poll)',
     '-t 0 -N 3', [], 1.5),
    # ---- delimiter / escape composition
    ('N_delim_ignored', '-N 3 -t 1 -d :, is the delimiter ignored for -N?',
     '-t 1 -d : -N 3', [(0.1, b'a:bc')], 3.0),
    ('N_backslash_no_t', '-N 3 over a\\b, no -t, EOF (escape-vs-count, ISOLATED)',
     '-N 3', [(0.0, b'a\\b')], 0.0),
    ('N_backslash4_no_t', '-N 3 over a\\bc, no -t, EOF (escape-vs-count)',
     '-N 3', [(0.0, b'a\\bc')], 0.0),
    ('N_backslash_raw_no_t', '-N 3 -r over a\\b, no -t, EOF [CONTROL]',
     '-r -N 3', [(0.0, b'a\\b')], 0.0),
    ('N_backslash_hold', '-N 3 -t 1 over a\\b, NO EOF',
     '-t 1 -N 3', [(0.1, b'a\\b')], 3.0),
    # ---- rider x multibyte: the count is in CHARS
    ('N_mb_split_hold', '-N 2 -t 1, multibyte SPLIT by the deadline, NO EOF',
     '-t 1 -N 2', [(0.1, b'a\xc3')], 3.0),
    ('N_mb_complete_hold', '-N 2 -t 1, multibyte completes before deadline [CONTROL]',
     '-t 1 -N 2', [(0.1, b'a\xc3'), (0.2, b'\xa9')], 3.0),
    ('N_mb_late_hold', '-N 2 -t 1, continuation byte arrives AFTER the deadline',
     '-t 1 -N 2', [(0.1, b'a\xc3'), (1.9, b'\xa9')], 2.0),
    ('N_mb_eof', '-N 2, multibyte truncated at EOF, no -t [CONTROL]',
     '-N 2', [(0.0, b'a\xc3')], 0.0),
    ('N_mb_3byte_split_hold', '-N 2 -t 1, 3-byte char split at byte 2, NO EOF',
     '-t 1 -N 2', [(0.1, b'a\xe2\x82')], 3.0),
    # ---- the lowercase -n counterparts: MUST-HOLD reference
    ('n_none_hold', '-n 3 -t 1, no input, NO EOF [REFERENCE]',
     '-t 1 -n 3', [], 4.0),
    ('n_partial_hold', '-n 3 -t 1, 2 of 3 chars then silence, NO EOF [REFERENCE]',
     '-t 1 -n 3', [(0.1, b'ab')], 4.0),
    ('n_full_hold', '-n 3 -t 1, all 3 chars early, NO EOF [REFERENCE]',
     '-t 1 -n 3', [(0.1, b'abc')], 4.0),
    ('n_late_hold', '-n 3 -t 1, input after the deadline, NO EOF [REFERENCE]',
     '-t 1 -n 3', [(2.0, b'abc')], 2.0),
    ('n_eof_short_with_t', '-n 3 -t 1, EOF before the count [REFERENCE]',
     '-t 1 -n 3', [(0.0, b'ab')], 0.0),
    ('n_zero_with_t', '-n 0 -t 1, count zero, NO EOF [REFERENCE]',
     '-t 1 -n 0', [], 3.0),
    ('n_t0_ready', '-n 3 -t 0, data READY [REFERENCE]',
     '-t 0 -n 3', [(0.0, b'abc')], 1.0),
    ('n_t0_notready', '-n 3 -t 0, data NOT ready [REFERENCE]',
     '-t 0 -n 3', [], 1.5),
    ('n_mb_split_hold', '-n 2 -t 1, multibyte split by the deadline [REFERENCE]',
     '-t 1 -n 2', [(0.1, b'a\xc3')], 3.0),
    ('n_mb_late_hold', '-n 2 -t 1, continuation AFTER the deadline [REFERENCE]',
     '-t 1 -n 2', [(0.1, b'a\xc3'), (1.9, b'\xa9')], 2.0),
    # ---- plain -t (no count): the settled shape
    ('t_plain_none_hold', '-t 1 plain, no input, NO EOF [REFERENCE]',
     '-t 1', [], 3.0),
    ('t_plain_partial_hold', '-t 1 plain, partial line then silence [REFERENCE]',
     '-t 1', [(0.1, b'ab')], 3.0),
    ('t_plain_mb_split_hold', '-t 1 plain, multibyte split by the deadline [REFERENCE]',
     '-t 1', [(0.1, b'a\xc3')], 3.0),
]


def run_cell(argv, opts, steps, hold, scratch, tag):
    fifo = os.path.join(scratch, f"fifo.{tag}")
    if os.path.exists(fifo):
        os.unlink(fifo)
    os.mkfifo(fifo)
    prod = subprocess.Popen(
        [sys.executable, '-c', PRODUCER, fifo, str(hold), repr(steps)],
        cwd=ROOT, env=ENV, stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE, text=True, start_new_session=True)
    script = SCRIPT.format(opts=opts, fifo=fifo)
    t0 = time.monotonic()
    proc = subprocess.Popen(argv + [script], cwd=ROOT, env=ENV,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, start_new_session=True)
    timed_out = False
    try:
        out, err = proc.communicate(timeout=KILL_AFTER)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        out, err = proc.communicate()
    dt = time.monotonic() - t0
    # Always sweep the producer group, so no orphan can outlive the cell.
    try:
        os.killpg(os.getpgid(prod.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        prod.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    os.unlink(fifo)
    lines = [ln for ln in (out or '').splitlines() if ln.startswith('rc=')]
    body = lines[-1] if lines else (out or '').strip()
    if timed_out:
        body = f"HUNG(>{KILL_AFTER:.0f}s, pgroup SIGKILLed)"
    return {'body': body, 'dt': dt, 'stderr': (err or '').strip(),
            'timed_out': timed_out}


def main() -> int:
    bash_ver = subprocess.run([BASH, '--version'], capture_output=True,
                              text=True).stdout.splitlines()[0]
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(['git', 'status', '--porcelain', 'psh/'], cwd=ROOT,
                           capture_output=True, text=True).stdout
    psh_file = subprocess.run(
        [sys.executable, '-c', 'import psh; print(psh.__file__)'],
        cwd=ROOT, env=ENV, capture_output=True, text=True).stdout.strip()
    print("== DISCRIMINATOR ==")
    print(f"bash oracle:    {BASH} -> {bash_ver}")
    print(f"resolved bash:  {shutil.which('bash', path=ENV['PATH'])}")
    print(f"psh under test: {psh_file}")
    print(f"HEAD:           {head}")
    print(f"psh/ dirty:     {len(dirty.splitlines())} lines")
    print(f"LC_ALL:         {LC}   kill bound: {KILL_AFTER}s")
    print("producer:       separate python process over a FIFO "
          "(NOT the shell under test)")
    print("value compared: raw bytes via external od -An -tx1 (NOT printf %q)")
    print()

    only = sys.argv[1] if len(sys.argv) > 1 else None
    cells = [c for c in CELLS if only is None or c[0] == only]
    if not cells:
        print(f"unknown cell {only!r}", file=sys.stderr)
        return 2

    scratch = tempfile.mkdtemp(prefix='w4b2-rider-', dir=os.path.join(ROOT, 'tmp'))
    rows = []
    try:
        print(f"{'CELL':<24} {'BASH':<30} {'dt':<6} {'PSH':<30} {'dt':<6} MATCH")
        print("-" * 112)
        for cid, desc, opts, steps, hold in cells:
            b = run_cell([BASH, '-c'], opts, steps, hold, scratch, f"b.{cid}")
            p = run_cell([sys.executable, '-m', 'psh', '-c'], opts, steps,
                         hold, scratch, f"p.{cid}")
            match = 'SAME' if b['body'] == p['body'] else 'DIFFER'
            rows.append((cid, desc, opts, steps, hold, b, p, match))
            print(f"{cid:<24} {b['body']:<30} {b['dt']:<6.2f} "
                  f"{p['body']:<30} {p['dt']:<6.2f} {match}")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    print()
    print("== PER-CELL DETAIL ==")
    for cid, desc, opts, steps, hold, b, p, match in rows:
        print(f"\n### {cid} — {desc}  [{match}]")
        print(f"    read opts: {opts!r}   producer steps: {steps!r}   "
              f"hold: {hold}s")
        print(f"    bash: {b['body']}  (dt={b['dt']:.2f}s)")
        if b['stderr']:
            print(f"    bash stderr: {b['stderr']}")
        print(f"    psh : {p['body']}  (dt={p['dt']:.2f}s)")
        if p['stderr']:
            print(f"    psh stderr: {p['stderr']}")

    same = sum(1 for r in rows if r[7] == 'SAME')
    print()
    print("== MEASURED SPLIT ==")
    print(f"  cells: {len(rows)}   SAME: {same}   DIFFER: {len(rows) - same}   "
          f"psh HUNG: {sum(1 for r in rows if r[6]['timed_out'])}   "
          f"bash HUNG: {sum(1 for r in rows if r[5]['timed_out'])}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
