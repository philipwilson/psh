"""INSTR01 — reproduce the dispatch v2 corruption faces AT THIS WORKTREE.

Port of tmp/w4b4-dispatch-probes/probe_cursor_contract_v2.py (MAIN) with:
  * REPO retargeted to /Users/pwilson/src/psh-r4b-4 (the tree under test);
  * a SUBPROCESS-level discriminator (4B.2 lesson 4: the search path is a
    request, the resolved __file__ is the fact) — the parent's `import psh`
    proves nothing about what `python -m psh` in the child resolved;
  * VALIDITY CONTROLS (4B.2 lesson 1) proving each stimulus actually
    arrived: A-ctl feeds a COMPLETE char so no strand exists (both shells
    must agree, x=FILELINE clean); B-ctl proves the phase-2 write lands
    inside the child's read window (else leg B's "never delivered" would be
    indistinguishable from "phase 2 arrived too late").

Two-phase feed hygiene: writer is a threading.Timer with a bounded join;
deadlines >= 1s; hang detection at 12s (>= 4x).

Run:  python tmp/w4b4/instr01_reproduce_v2.py
"""
import os
import subprocess
import sys
import tempfile
import threading

REPO = '/Users/pwilson/src/psh-r4b-4'
sys.path.insert(0, REPO)
import psh  # noqa: E402

assert psh.__file__ == REPO + '/psh/__init__.py', psh.__file__
print("PARENT DISCRIMINATOR:", psh.__file__)
BASH = ['/opt/homebrew/bin/bash']
PSH = [sys.executable, '-m', 'psh']


def child_env():
    return {'HOME': os.environ['HOME'], 'PATH': os.environ['PATH'],
            'PYTHONPATH': REPO, 'TERM': 'dumb'}


# SUBPROCESS discriminator: what does a child with THIS env/cwd resolve?
_d = subprocess.run([sys.executable, '-c', 'import psh; print(psh.__file__)'],
                    cwd=REPO, env=child_env(), capture_output=True, text=True)
_resolved = _d.stdout.strip()
assert _resolved == REPO + '/psh/__init__.py', f"CHILD RESOLVED {_resolved!r}"
print("CHILD  DISCRIMINATOR:", _resolved)
print("ORACLE:", subprocess.run(BASH + ['--version'], capture_output=True,
                                text=True).stdout.splitlines()[0])
print()


def run(argv, script, phase1, phase2=None, phase2_delay=2.0):
    r, w = os.pipe()
    p = subprocess.Popen(argv + ['-c', script], stdin=r,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         cwd=REPO, env=child_env())
    os.close(r)
    os.write(w, phase1)
    t = None
    if phase2 is not None:
        def later():
            try:
                os.write(w, phase2)
            except OSError:
                pass
        t = threading.Timer(phase2_delay, later)
        t.start()
    try:
        out, _ = p.communicate(timeout=12)
        return out.decode('utf-8', errors='backslashreplace').strip()
    except subprocess.TimeoutExpired:
        p.kill()
        p.communicate()
        return 'HUNG'
    finally:
        if t:
            t.join(5)
        try:
            os.close(w)
        except OSError:
            pass


with tempfile.TemporaryDirectory(dir=REPO + '/tmp') as d:
    f = os.path.join(d, 'file')
    with open(f, 'w') as fh:
        fh.write('FILELINE\n')

    scriptA = (f'read -t 1 -N 2 v; read x < {f}; '
               'printf "v=%s|x=%s\\n" "$v" "$x" | od -c | head -2')
    print("== LEG A  temp-frame contamination (strand = lone \\xc3) ==")
    print("A bash:", run(BASH, scriptA, b'\xc3'))
    print("A psh :", run(PSH, scriptA, b'\xc3'))

    # VALIDITY CONTROL A: feed a COMPLETE 2-char stimulus so -N 2 is
    # satisfied and NOTHING is stranded. Both shells must show a clean
    # x=FILELINE. If this cell diverges, leg A's divergence is not about
    # stranding at all.
    print("A-ctl bash:", run(BASH, scriptA, b'AB'))
    print("A-ctl psh :", run(PSH, scriptA, b'AB'))
    print()

    scriptB = ('read -t 1 -N 2 v; exec 3<&0; read -t 1 -u 3 y; '
               'read -t 1 -N 1 w; '
               'printf "v=%s|y=%s|w=%s\\n" "$v" "$y" "$w" | od -c | head -2')
    print("== LEG B  dup loss (two-phase: \\xc3 then \\xa9Z\\n) ==")
    print("B bash:", run(BASH, scriptB, b'\xc3', b'\xa9Z\n'))
    print("B psh :", run(PSH, scriptB, b'\xc3', b'\xa9Z\n'))

    # VALIDITY CONTROL B: identical shape/timing, but phase 2 is pure ASCII
    # 'QZ\n'. This proves the phase-2 bytes DO arrive inside the child's
    # read window (y must be non-empty in both shells). Without it, "psh
    # never delivered \xc3" is confounded with "phase 2 arrived too late".
    print("B-ctl bash:", run(BASH, scriptB, b'\xc3', b'QZ\n'))
    print("B-ctl psh :", run(PSH, scriptB, b'\xc3', b'QZ\n'))
