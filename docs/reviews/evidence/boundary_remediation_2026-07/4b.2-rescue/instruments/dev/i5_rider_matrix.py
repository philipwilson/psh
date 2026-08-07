#!/usr/bin/env python3
"""i5 — the A5 rider matrix: OPTION COMPOSITION x TIME OUTCOME (Phase A item 3).

Bash-probes the full ``-N`` x ``-t`` matrix (with the lowercase ``-n``
counterpart of every cell as the must-hold reference) BEFORE any design, and
runs the identical script under psh so each cell is an A/B row.

Hygiene (binding for this slot):
  * bash oracle is PATH bash /opt/homebrew/bin/bash 5.2.26, EXPLICIT argv,
    never /bin/bash; the version is recorded in the transcript.
  * every invocation runs in its OWN session (``start_new_session=True``) under
    a BOUNDED KILL: on timeout the whole process GROUP is killed, so a hung psh
    cannot leave orphan producers behind. The base psh HANGS on the headline
    cell, so this shape is mandatory from the outset.
  * deadlines are 1.0s; the kill bound is 8s (8x the deadline).
  * the environment is explicit (LC_ALL pinned) so ``-N``'s char-vs-byte
    counting is not at the mercy of an inherited locale.
"""
import os
import shutil
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

BASH = '/opt/homebrew/bin/bash'
KILL_AFTER = 8.0          # 8x the 1.0s deadline used by every cell
LC = 'en_US.UTF-8'

ENV = {
    'PATH': '/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',
    'HOME': os.environ.get('HOME', '/tmp'),
    'LC_ALL': LC,
    'LANG': LC,
    'TERM': 'dumb',
}

# Each cell: (id, description, script). The script prints ONE line:
#   rc=<status> v=<printf %q of the variable>
CELLS = [
    # ---- the headline family: -N x -t -------------------------------------
    ('N_none',
     '-N 3 -t 1, NO input ever arrives',
     r'''sleep 2 | { read -t 1 -N 3 x; printf 'rc=%s v=%q\n' "$?" "$x"; }'''),
    ('N_partial',
     '-N 3 -t 1, 2 of 3 chars arrive early then silence',
     r'''{ printf ab; sleep 2; } | { read -t 1 -N 3 x; printf 'rc=%s v=%q\n' "$?" "$x"; }'''),
    ('N_full',
     '-N 3 -t 1, all 3 chars arrive early (satisfied) [CONTROL]',
     r'''{ printf abc; sleep 2; } | { read -t 1 -N 3 x; printf 'rc=%s v=%q\n' "$?" "$x"; }'''),
    ('N_late',
     '-N 3 -t 1, input arrives AFTER the deadline',
     r'''{ sleep 2; printf abc; } | { read -t 1 -N 3 x; printf 'rc=%s v=%q\n' "$?" "$x"; }'''),
    ('N_eof_short_no_t',
     '-N 3, EOF before the count, NO -t [CONTROL]',
     r'''printf ab | { read -N 3 x; printf 'rc=%s v=%q\n' "$?" "$x"; }'''),
    ('N_eof_short_with_t',
     '-N 3 -t 1, EOF before the count (EOF vs timeout rc)',
     r'''printf ab | { read -t 1 -N 3 x; printf 'rc=%s v=%q\n' "$?" "$x"; }'''),
    ('N_zero_with_t',
     '-N 0 -t 1, count zero',
     r'''sleep 2 | { read -t 1 -N 0 x; printf 'rc=%s v=%q\n' "$?" "$x"; }'''),
    ('N_t0_ready',
     '-N 3 -t 0, data READY (poll)',
     r'''printf abc | { read -t 0 -N 3 x; printf 'rc=%s v=%q\n' "$?" "$x"; }'''),
    ('N_t0_notready',
     '-N 3 -t 0, data NOT ready (poll)',
     r'''sleep 2 | { read -t 0 -N 3 x; printf 'rc=%s v=%q\n' "$?" "$x"; }'''),
    ('N_delim_ignored',
     '-N 3 -t 1 -d :, does the delimiter matter for -N?',
     r'''{ printf 'a:bc'; sleep 2; } | { read -t 1 -d : -N 3 x; printf 'rc=%s v=%q\n' "$?" "$x"; }'''),
    ('N_backslash',
     '-N 3 -t 1 over a backslash (escape processing under -N)',
     r'''{ printf 'a\\b'; sleep 2; } | { read -t 1 -N 3 x; printf 'rc=%s v=%q\n' "$?" "$x"; }'''),
    ('N_backslash_raw',
     '-N 3 -t 1 -r over a backslash [CONTROL]',
     r'''{ printf 'a\\b'; sleep 2; } | { read -t 1 -r -N 3 x; printf 'rc=%s v=%q\n' "$?" "$x"; }'''),
    # ---- rider x multibyte: the count is in CHARS -------------------------
    ('N_mb_split',
     '-N 2 -t 1, a multibyte char SPLIT by the deadline (a + lead byte only)',
     r'''{ printf 'a\303'; sleep 2; } | { read -t 1 -N 2 x; printf 'rc=%s v=%q\n' "$?" "$x"; }'''),
    ('N_mb_complete',
     '-N 2 -t 1, the multibyte char completes before the deadline [CONTROL]',
     r'''{ printf 'a\303'; sleep 0.3; printf '\251'; sleep 2; } | { read -t 1 -N 2 x; printf 'rc=%s v=%q\n' "$?" "$x"; }'''),
    ('N_mb_late',
     '-N 2 -t 1, the completing continuation byte arrives AFTER the deadline',
     r'''{ printf 'a\303'; sleep 2; printf '\251'; } | { read -t 1 -N 2 x; printf 'rc=%s v=%q\n' "$?" "$x"; }'''),
    # ---- the lowercase -n counterparts: MUST-HOLD reference ---------------
    ('n_none',
     '-n 3 -t 1, NO input ever [REFERENCE]',
     r'''sleep 2 | { read -t 1 -n 3 x; printf 'rc=%s v=%q\n' "$?" "$x"; }'''),
    ('n_partial',
     '-n 3 -t 1, 2 of 3 chars early then silence [REFERENCE]',
     r'''{ printf ab; sleep 2; } | { read -t 1 -n 3 x; printf 'rc=%s v=%q\n' "$?" "$x"; }'''),
    ('n_full',
     '-n 3 -t 1, all 3 chars early [REFERENCE]',
     r'''{ printf abc; sleep 2; } | { read -t 1 -n 3 x; printf 'rc=%s v=%q\n' "$?" "$x"; }'''),
    ('n_late',
     '-n 3 -t 1, input arrives AFTER the deadline [REFERENCE]',
     r'''{ sleep 2; printf abc; } | { read -t 1 -n 3 x; printf 'rc=%s v=%q\n' "$?" "$x"; }'''),
    ('n_eof_short_with_t',
     '-n 3 -t 1, EOF before the count [REFERENCE]',
     r'''printf ab | { read -t 1 -n 3 x; printf 'rc=%s v=%q\n' "$?" "$x"; }'''),
    ('n_zero_with_t',
     '-n 0 -t 1, count zero [REFERENCE]',
     r'''sleep 2 | { read -t 1 -n 0 x; printf 'rc=%s v=%q\n' "$?" "$x"; }'''),
    ('n_t0_ready',
     '-n 3 -t 0, data READY [REFERENCE]',
     r'''printf abc | { read -t 0 -n 3 x; printf 'rc=%s v=%q\n' "$?" "$x"; }'''),
    ('n_t0_notready',
     '-n 3 -t 0, data NOT ready [REFERENCE]',
     r'''sleep 2 | { read -t 0 -n 3 x; printf 'rc=%s v=%q\n' "$?" "$x"; }'''),
    ('n_mb_split',
     '-n 2 -t 1, multibyte split by the deadline [REFERENCE]',
     r'''{ printf 'a\303'; sleep 2; } | { read -t 1 -n 2 x; printf 'rc=%s v=%q\n' "$?" "$x"; }'''),
    # ---- plain -t (no count): the settled shape ----------------------------
    ('t_plain_none',
     '-t 1 plain, no input [REFERENCE]',
     r'''sleep 2 | { read -t 1 x; printf 'rc=%s v=%q\n' "$?" "$x"; }'''),
    ('t_plain_partial',
     '-t 1 plain, partial line then silence [REFERENCE]',
     r'''{ printf ab; sleep 2; } | { read -t 1 x; printf 'rc=%s v=%q\n' "$?" "$x"; }'''),
]


def run_cell(argv, script, label):
    """Run one script under one shell with a bounded process-GROUP kill."""
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
    rc = proc.returncode
    line = (out or '').strip().splitlines()
    body = line[-1] if line else ''
    if timed_out:
        body = f"HUNG(>{KILL_AFTER:.0f}s, process group SIGKILLed)"
    return {
        'label': label, 'body': body, 'dt': dt, 'shell_rc': rc,
        'stderr': (err or '').strip(), 'timed_out': timed_out,
    }


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
    print(f"bash oracle:   {BASH} -> {bash_ver}")
    print(f"which bash:    {shutil.which('bash', path=ENV['PATH'])}")
    print(f"psh under test:{psh_file}")
    print(f"repo root:     {ROOT}")
    print(f"HEAD:          {head}")
    print(f"psh/ dirty:    {len(dirty.splitlines())} lines")
    print(f"LC_ALL:        {LC}")
    print(f"kill bound:    {KILL_AFTER}s (8x the 1.0s deadline)")
    print()

    bash_argv = [BASH, '-c']
    psh_argv = [sys.executable, '-m', 'psh', '-c']

    print(f"{'CELL':<20} {'BASH':<34} {'dt':<6} {'PSH':<34} {'dt':<6} MATCH")
    print("-" * 118)
    rows = []
    for cid, desc, script in CELLS:
        b = run_cell(bash_argv, script, 'bash')
        p = run_cell(psh_argv, script, 'psh')
        match = 'SAME' if b['body'] == p['body'] else 'DIFFER'
        rows.append((cid, desc, script, b, p, match))
        print(f"{cid:<20} {b['body']:<34} {b['dt']:<6.2f} "
              f"{p['body']:<34} {p['dt']:<6.2f} {match}")

    print()
    print("== PER-CELL DETAIL (description, script, stderr) ==")
    for cid, desc, script, b, p, match in rows:
        print(f"\n### {cid} — {desc}  [{match}]")
        print(f"    script: {script}")
        print(f"    bash: {b['body']}  (dt={b['dt']:.2f}s, shell rc={b['shell_rc']})")
        if b['stderr']:
            print(f"    bash stderr: {b['stderr']}")
        print(f"    psh : {p['body']}  (dt={p['dt']:.2f}s, shell rc={p['shell_rc']})")
        if p['stderr']:
            print(f"    psh stderr: {p['stderr']}")

    same = sum(1 for r in rows if r[5] == 'SAME')
    differ = len(rows) - same
    hung = sum(1 for r in rows if r[4]['timed_out'])
    print()
    print("== MEASURED SPLIT ==")
    print(f"  cells: {len(rows)}   SAME: {same}   DIFFER: {differ}   "
          f"psh HUNG: {hung}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
