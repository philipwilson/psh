"""Dispatch probes — slot 4B.4 (InputCursor contract) at base e3924ed3.

Leg A — TEMP-FRAME ISOLATION: strand timeout-partial chars on fd 0's cursor
(psh holds them per D-4B.2-s1), then `read x < FILE` inside the same shell.
If the temp-redirected fd 0 reuses the stdin cursor, the stranded chars leak
into x. bash: x = the file's line only.
Leg B — DUP SHARING: strand surplus on fd 0's cursor, `exec 3<&0`, read fd 3.
The fd-3 cursor is fresh; the surplus chars (already consumed from the shared
kernel offset) are lost to fd 3. bash: kernel offset is the only state.
Leg C — P1 _pushback producer census at this base (grep).
"""
import os
import subprocess
import sys
import tempfile

REPO = '/Users/pwilson/src/psh'
sys.path.insert(0, REPO)
import psh  # noqa: E402
assert psh.__file__ == REPO + '/psh/__init__.py', psh.__file__
print("DISCRIMINATOR:", psh.__file__)
BASH = ['/opt/homebrew/bin/bash']
PSH = [sys.executable, '-m', 'psh']


def run(argv, script, feed, cwd=REPO):
    env = {'HOME': os.environ['HOME'], 'PATH': os.environ['PATH'],
           'PYTHONPATH': cwd, 'TERM': 'dumb'}
    r, w = os.pipe()
    p = subprocess.Popen(argv + ['-c', script], stdin=r,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         cwd=cwd, env=env)
    os.close(r)
    os.write(w, feed)          # partial data; pipe stays open past timeout
    try:
        out, _ = p.communicate(timeout=8)
        return out.decode(errors='replace').strip()
    except subprocess.TimeoutExpired:
        p.kill()
        p.communicate()
        return 'HUNG'
    finally:
        try:
            os.close(w)
        except OSError:
            pass


with tempfile.TemporaryDirectory(dir=REPO + '/tmp') as d:
    f = os.path.join(d, 'file')
    with open(f, 'w') as fh:
        fh.write('FILELINE\n')
    # Leg A: -t 1 -N 3 with only 'ab' fed -> timeout; psh strands 'ab' on
    # fd 0's cursor (D-4B.2-s1: bash assigns, psh holds). Then a
    # temp-redirected read from FILE.
    scriptA = f'read -t 1 -N 3 v; read x < {f}; echo "v=<$v> x=<$x>"'
    print("A temp-frame bash:", run(BASH, scriptA, b'ab'))
    print("A temp-frame psh :", run(PSH, scriptA, b'ab'))
    # Leg B: strand 'ab', then dup fd0->3 and read fd 3; kernel pipe holds
    # 'CD\n' beyond the stranded bytes.
    scriptB = 'read -t 1 -N 6 v; exec 3<&0; read -u 3 y; echo "v=<$v> y=<$y>"'
    print("B dup-share bash:", run(BASH, scriptB, b'ab\nCD\n'))
    print("B dup-share psh :", run(PSH, scriptB, b'ab\nCD\n'))

print("C _pushback references outside input_reader.py (expect none):")
os.system("grep -rn '_pushback' --include='*.py' psh/ | grep -v input_reader | wc -l")
print("C _pushback references inside input_reader.py:")
os.system("grep -c '_pushback' psh/builtins/input_reader.py")
