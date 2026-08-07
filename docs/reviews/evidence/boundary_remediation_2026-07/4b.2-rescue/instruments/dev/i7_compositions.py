#!/usr/bin/env python3
"""i7 — end-to-end legs + composition cells (Phase A items 1, 4).

Three questions, all with the shell-neutral FIFO producer from i6:

  E2E  — is the MEDIUM-2 seam reachable at SHELL level? (a timed `read` that
         times out mid-multibyte, then `mapfile` with no count on the same fd —
         `mapfile`'s no-count path is the only production caller of read_all.)
  COMP — what happens to the stranded partial multibyte on the NEXT read?
         (bash consumed and assigned it; psh holds it in the cursor decoder.)
  ERR  — does the ERROR outcome strand decoder state the way TIMEOUT does?
         (in-process only: no bash analogue, stated as such.)
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
sys.path.insert(0, ROOT)

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

# id, description, script-template ({fifo}), producer steps, hold
CELLS = [
    ('e2e_seam_mapfile',
     'E2E: read -t times out mid-multibyte, then mapfile (no count) drains',
     r'''exec 3< {fifo}; read -t 1 -u 3 x; rc=$?; mapfile -u 3 arr; '''
     r'''printf 'rc=%s x=' "$rc"; printf '%s' "$x" | od -An -tx1 | tr -d ' \n'; '''
     r'''printf ' n=%s all=' "${{#arr[@]}}"; '''
     r'''printf '%s' "${{arr[*]}}" | od -An -tx1 | tr -d ' \n'; printf '\n' ''',
     [(0.1, b'a\xc3'), (1.5, b'\xa9\n')], 0.5),
    ('e2e_seam_mapfile_3byte',
     'E2E: same, 3-byte char split at byte 2',
     r'''exec 3< {fifo}; read -t 1 -u 3 x; rc=$?; mapfile -u 3 arr; '''
     r'''printf 'rc=%s x=' "$rc"; printf '%s' "$x" | od -An -tx1 | tr -d ' \n'; '''
     r'''printf ' n=%s all=' "${{#arr[@]}}"; '''
     r'''printf '%s' "${{arr[*]}}" | od -An -tx1 | tr -d ' \n'; printf '\n' ''',
     [(0.1, b'a\xe2\x82'), (1.5, b'\xac\n')], 0.5),
    ('comp_timeout_then_read',
     'COMP: read -t times out mid-multibyte, then a SECOND read on the same fd',
     r'''exec 3< {fifo}; read -t 1 -u 3 x; rc1=$?; read -u 3 y; rc2=$?; '''
     r'''printf 'rc1=%s x=' "$rc1"; printf '%s' "$x" | od -An -tx1 | tr -d ' \n'; '''
     r'''printf ' rc2=%s y=' "$rc2"; '''
     r'''printf '%s' "$y" | od -An -tx1 | tr -d ' \n'; printf '\n' ''',
     [(0.1, b'a\xc3'), (1.5, b'\xa9b\n')], 0.5),
    ('comp_timeout_then_cat',
     'COMP: read -t times out mid-multibyte, then cat drains the fd (byte view)',
     r'''exec 3< {fifo}; read -t 1 -u 3 x; rc=$?; '''
     r'''printf 'rc=%s x=' "$rc"; printf '%s' "$x" | od -An -tx1 | tr -d ' \n'; '''
     r'''printf ' rest='; cat <&3 | od -An -tx1 | tr -d ' \n'; printf '\n' ''',
     [(0.1, b'a\xc3'), (1.5, b'\xa9b\n')], 0.5),
    ('e2e_seam_no_timeout',
     'CONTROL: no timeout at all — mapfile alone over a multibyte stream',
     r'''exec 3< {fifo}; mapfile -u 3 arr; printf 'n=%s all=' "${{#arr[@]}}"; '''
     r'''printf '%s' "${{arr[*]}}" | od -An -tx1 | tr -d ' \n'; printf '\n' ''',
     [(0.1, b'a\xc3'), (0.3, b'\xa9\n')], 0.2),
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


def error_route_census() -> None:
    """ERR: does an ERROR outcome strand decoder state? (no bash analogue)"""
    from psh.builtins.input_reader import InputCursor, Outcome
    print("\n== ERR: does Outcome.ERROR strand pending decoder bytes? ==")
    print("   (in-process census; there is NO bash analogue for this cell — an")
    print("    fd error mid-character is not a shell-observable bash behaviour)")
    r, w = os.pipe()
    try:
        os.write(w, b'a\xc3')
        cur = InputCursor(fd=r)
        res = cur.read_limited(delimiter=None, max_chars=1)
        print(f"   after read_limited(1): outcome={res.outcome.name} "
              f"data={res.data!r} decoder="
              f"{'LIVE' if cur._decoder is not None else 'None'}")
        # Feed the lead byte into the decoder, then force an ERROR by closing
        # the read end under the cursor.
        res = cur.read_limited(delimiter=None, max_chars=1,
                               deadline=time.monotonic() + 0.25)
        pend = cur._decoder.getstate()[0] if cur._decoder is not None else b''
        print(f"   after timed read:      outcome={res.outcome.name} "
              f"data={res.data!r} pending={pend!r}")
        os.close(r)
        res = cur.read_limited(delimiter=None, max_chars=1)
        pend = cur._decoder.getstate()[0] if cur._decoder is not None else b''
        print(f"   after fd CLOSED:       outcome={res.outcome.name} "
              f"data={res.data!r} pending={pend!r}")
        print(f"   => ERROR strands pending bytes: "
              f"{'YES' if pend else 'NO'}")
        out = cur.read_all()
        print(f"   read_all after ERROR:  {out!r} (read_all swallows OSError "
              f"by design, input_reader.py:203-205)")
    finally:
        try:
            os.close(w)
        except OSError:
            pass


def main() -> int:
    bash_ver = subprocess.run([BASH, '--version'], capture_output=True,
                              text=True).stdout.splitlines()[0]
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()
    print("== DISCRIMINATOR ==")
    print(f"bash oracle:    {BASH} -> {bash_ver}")
    print(f"HEAD:           {head}")
    print(f"psh under test: {os.path.join(ROOT, 'psh')}")
    print("producer:       separate python process over a FIFO")
    print()

    scratch = tempfile.mkdtemp(prefix='w4b2-comp-', dir=os.path.join(ROOT, 'tmp'))
    rows = []
    try:
        for cid, desc, script, steps, hold in CELLS:
            b = run_shell([BASH, '-c'], script, steps, hold, scratch, f"b.{cid}")
            p = run_shell([sys.executable, '-m', 'psh', '-c'], script, steps,
                          hold, scratch, f"p.{cid}")
            match = 'SAME' if b['body'] == p['body'] else 'DIFFER'
            rows.append((cid, desc, b, p, match))
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

    error_route_census()

    same = sum(1 for r in rows if r[4] == 'SAME')
    print()
    print("== MEASURED SPLIT (shell-level cells) ==")
    print(f"  cells: {len(rows)}   SAME: {same}   DIFFER: {len(rows) - same}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
