"""Dispatch probes v2 — slot 4B.4, mid-multibyte strand variants.

Strand = feed a lone \xc3 (first byte of é) into `read -t 1 -N 2`: per
D-4B.2-s1 bash ASSIGNS the partial (v = lone surrogate, len 1); psh HOLDS it
on fd 0's cursor for the next read (v empty). THEN:

Leg A (temp-frame): `read x < FILE`. If the temp-redirected fd 0 reuses the
stdin cursor, psh's pending \xc3 meets the FILE's bytes.
Leg B (dup, two-phase): after the strand, phase-2 writes b'\xa9Z\n' (the
continuation byte + tail); `exec 3<&0; read -t 1 -u 3 y` then a final
`read -t 1 -N 1 w` on fd 0. Where does the é land — nowhere (psh: lead on
fd0's cursor, continuation to fd3's fresh cursor) vs bash's single kernel
offset?
"""
import os
import subprocess
import sys
import tempfile
import threading

REPO = '/Users/pwilson/src/psh'
sys.path.insert(0, REPO)
import psh  # noqa: E402
assert psh.__file__ == REPO + '/psh/__init__.py', psh.__file__
print("DISCRIMINATOR:", psh.__file__)
BASH = ['/opt/homebrew/bin/bash']
PSH = [sys.executable, '-m', 'psh']


def run(argv, script, phase1, phase2=None, phase2_delay=2.0):
    env = {'HOME': os.environ['HOME'], 'PATH': os.environ['PATH'],
           'PYTHONPATH': REPO, 'TERM': 'dumb'}
    r, w = os.pipe()
    p = subprocess.Popen(argv + ['-c', script], stdin=r,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         cwd=REPO, env=env)
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
            t.join()
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
    print("A temp-frame bash:", run(BASH, scriptA, b'\xc3'))
    print("A temp-frame psh :", run(PSH, scriptA, b'\xc3'))
    scriptB = ('read -t 1 -N 2 v; exec 3<&0; read -t 1 -u 3 y; '
               'read -t 1 -N 1 w; '
               'printf "v=%s|y=%s|w=%s\\n" "$v" "$y" "$w" | od -c | head -2')
    print("B dup two-phase bash:", run(BASH, scriptB, b'\xc3', b'\xa9Z\n'))
    print("B dup two-phase psh :", run(PSH, scriptB, b'\xc3', b'\xa9Z\n'))
