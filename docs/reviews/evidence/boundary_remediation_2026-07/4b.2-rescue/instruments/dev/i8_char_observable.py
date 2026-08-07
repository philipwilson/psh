#!/usr/bin/env python3
"""i8 — is MEDIUM-2 SHELL-OBSERVABLE, and through which observable?

The byte round-trip survives the seam corruption by design, so a byte-level
comparison (i7) CANNOT see MEDIUM-2: `'\\udcc3\\udca9'` re-encodes to exactly
`c3 a9`. This probe finds the observable that CAN see it — CHARACTER count and
character slicing — and measures bash's answer for the same byte stream.

Same shell-neutral FIFO producer and bounded process-group kill as i6/i7.
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

CELLS = [
    ('char_len_after_seam',
     'CHAR LENGTH across the seam: ${#x} and ${#arr[0]} (é split by the deadline)',
     r'''exec 3< {fifo}; read -t 1 -u 3 x; rc=$?; mapfile -u 3 arr; '''
     r'''printf 'rc=%s xlen=%s a0len=%s nelem=%s\n' '''
     r'''"$rc" "${{#x}}" "${{#arr[0]}}" "${{#arr[@]}}" ''',
     [(0.1, b'a\xc3'), (1.5, b'\xa9\n')], 0.5),
    ('char_len_after_seam_3byte',
     'CHAR LENGTH across the seam, 3-byte char split at byte 2',
     r'''exec 3< {fifo}; read -t 1 -u 3 x; rc=$?; mapfile -u 3 arr; '''
     r'''printf 'rc=%s xlen=%s a0len=%s nelem=%s\n' '''
     r'''"$rc" "${{#x}}" "${{#arr[0]}}" "${{#arr[@]}}" ''',
     [(0.1, b'a\xe2\x82'), (1.5, b'\xac\n')], 0.5),
    ('char_len_after_seam_4byte',
     'CHAR LENGTH across the seam, 4-byte char split at byte 3',
     r'''exec 3< {fifo}; read -t 1 -u 3 x; rc=$?; mapfile -u 3 arr; '''
     r'''printf 'rc=%s xlen=%s a0len=%s nelem=%s\n' '''
     r'''"$rc" "${{#x}}" "${{#arr[0]}}" "${{#arr[@]}}" ''',
     [(0.1, b'a\xf0\x9f\x99'), (1.5, b'\x82\n')], 0.5),
    ('char_slice_after_seam',
     'CHAR SLICING across the seam: ${arr[0]:0:1} byte-dumped',
     r'''exec 3< {fifo}; read -t 1 -u 3 x; mapfile -u 3 arr; '''
     r'''printf 'first='; printf '%s' "${{arr[0]:0:1}}" | od -An -tx1 '''
     r'''| tr -d ' \n'; printf ' len=%s\n' "${{#arr[0]}}" ''',
     [(0.1, b'a\xc3'), (1.5, b'\xa9\n')], 0.5),
    ('char_len_no_timeout',
     'CONTROL: no timeout — mapfile alone, the char never crosses a seam',
     r'''exec 3< {fifo}; mapfile -u 3 arr; '''
     r'''printf 'a0len=%s nelem=%s\n' "${{#arr[0]}}" "${{#arr[@]}}" ''',
     [(0.1, b'a\xc3'), (0.3, b'\xa9\n')], 0.2),
    ('char_len_malformed_control',
     'CONTROL: a GENUINELY malformed byte across the seam stays one char each',
     r'''exec 3< {fifo}; read -t 1 -u 3 x; mapfile -u 3 arr; '''
     r'''printf 'xlen=%s a0len=%s\n' "${{#x}}" "${{#arr[0]}}" ''',
     [(0.1, b'a\xc3'), (1.5, b'Zb\n')], 0.5),
]


def run_shell(argv, script, steps, hold, scratch, tag):
    fifo = os.path.join(scratch, f"fifo.{tag}")
    os.mkfifo(fifo)
    prod = subprocess.Popen(
        [sys.executable, '-c', PRODUCER, fifo, str(hold), repr(steps)],
        cwd=ROOT, env=ENV, stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE, text=True, start_new_session=True)
    t0 = time.monotonic()
    proc = subprocess.Popen(argv + [script.format(fifo=fifo)], cwd=ROOT,
                            env=ENV, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True,
                            start_new_session=True)
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
    try:
        os.killpg(os.getpgid(prod.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        prod.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    os.unlink(fifo)
    body = (out or '').strip().splitlines()
    body = body[-1] if body else ''
    if timed_out:
        body = f"HUNG(>{KILL_AFTER:.0f}s)"
    return {'body': body, 'dt': dt, 'stderr': (err or '').strip()}


def main() -> int:
    bash_ver = subprocess.run([BASH, '--version'], capture_output=True,
                              text=True).stdout.splitlines()[0]
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()
    print("== DISCRIMINATOR ==")
    print(f"bash oracle:    {BASH} -> {bash_ver}")
    print(f"HEAD:           {head}")
    print(f"LC_ALL:         {LC}")
    print()
    scratch = tempfile.mkdtemp(prefix='w4b2-char-', dir=os.path.join(ROOT, 'tmp'))
    rows = []
    try:
        for cid, desc, script, steps, hold in CELLS:
            b = run_shell([BASH, '-c'], script, steps, hold, scratch, f"b.{cid}")
            p = run_shell([sys.executable, '-m', 'psh', '-c'], script, steps,
                          hold, scratch, f"p.{cid}")
            match = 'SAME' if b['body'] == p['body'] else 'DIFFER'
            rows.append((cid, match))
            print(f"### {cid} — {desc}  [{match}]")
            print(f"    bash: {b['body']}   (dt={b['dt']:.2f}s)")
            if b['stderr']:
                print(f"    bash stderr: {b['stderr']}")
            print(f"    psh : {p['body']}   (dt={p['dt']:.2f}s)")
            if p['stderr']:
                print(f"    psh stderr: {p['stderr']}")
            print()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    same = sum(1 for r in rows if r[1] == 'SAME')
    print("== MEASURED SPLIT ==")
    print(f"  cells: {len(rows)}   SAME: {same}   DIFFER: {len(rows) - same}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
