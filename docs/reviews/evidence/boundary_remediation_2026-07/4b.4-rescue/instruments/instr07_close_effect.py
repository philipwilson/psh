"""INSTR07 — does the CLOSE design remove the faces? Measured, not predicted.

Same three-way shape as INSTR06, but the third arm is psh+CLOSE (temp-frame
push/pop + dup aliasing, injected via sitecustomize — no production edit).
VALIDITY CONTROL first: a no-surplus control must stay MATCHED (the
emulation must not "fix" things by breaking the common path).
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import BASH, PSH, REPO, discriminate, env  # noqa: E402

discriminate()
CLOSESITE = os.path.join(REPO, 'tmp/w4b4/closesite')
print(f"CLOSE emulation: {CLOSESITE}/sitecustomize.py\n")


def env_close():
    e = env()
    e['PYTHONPATH'] = CLOSESITE + os.pathsep + e['PYTHONPATH']
    return e


def run3(name, script, stdin_bytes, oracle='C'):
    def one(argv, e):
        return subprocess.run(argv + ['-c', script], input=stdin_bytes,
                              cwd=REPO, env=e, capture_output=True,
                              timeout=30).stdout
    psh = one(PSH, env())
    pshc = one(PSH, env_close())
    orc = one(BASH, env({'LC_ALL': 'C', 'LANG': 'C'}) if oracle == 'C' else env())
    vb = 'MATCH' if psh == orc else 'DIVERGE'
    vc = 'MATCH' if pshc == orc else 'DIVERGE'
    print(f"### {name}   (oracle = bash {oracle})")
    print(f"    psh      : {psh!r}   [{vb}]")
    print(f"    psh+CLOSE: {pshc!r}   [{vc}]")
    print(f"    bash-{oracle:<4}: {orc!r}")
    print(f"    -> CLOSE {'FIXES' if vb=='DIVERGE' and vc=='MATCH' else ('holds' if vb==vc=='MATCH' else 'does NOT fix')}")
    print()


with tempfile.TemporaryDirectory(dir=REPO + '/tmp') as d:
    F = os.path.join(d, 'f.txt')
    open(F, 'wb').write(b'F1\nF2\n')
    G = os.path.join(d, 'g.txt')
    open(G, 'wb').write(b'\xc3AGGG\nG2\n')

    print("=" * 72); print("CONTROLS — the common path must NOT move"); print("=" * 72)
    run3("CTL temp-frame, no surplus",
         f"read a; read b < {F}; read c; printf '%s|%s|%s\\n' \"$a\" \"$b\" \"$c\"",
         b"S1\nS2\nS3\n", oracle='utf8')
    run3("CTL dup alias, no surplus",
         "exec 3<&0; read -u 0 a; read -u 3 b; read -u 0 c; "
         "printf '%s|%s|%s\\n' \"$a\" \"$b\" \"$c\"",
         b"one\ntwo\nthree\n", oracle='utf8')
    run3("CTL same-fd carryover (I1 MUST-HOLD — must stay MATCH)",
         "read -N 1 x; read -N 1 y; printf 'x=<%s> y=<%s>\\n' \"$x\" \"$y\"",
         b"\xc3A\n")

    print("=" * 72); print("THE FACES"); print("=" * 72)
    run3("R-MALFORMED x S-TEMPFRAME forward (I1 (c'))",
         f"read -N 1 a; read b < {F}; read -N 1 c; "
         "printf 'a=<%s> b=<%s> c=<%s>\\n' \"$a\" \"$b\" \"$c\"",
         b"\xc3A\nS2\n")
    run3("R-MALFORMED x S-TEMPFRAME REVERSE (new face)",
         f"read -N 1 a < {G}; read b; printf 'a=<%s> b=<%s>\\n' \"$a\" \"$b\"",
         b"STDIN1\nSTDIN2\n")
    run3("R-MALFORMED x S-DUP (I1 (b))",
         "exec 3<&0; read -N 1 -u 0 a; read -N 1 -u 3 b; "
         "printf 'a=<%s> b=<%s>\\n' \"$a\" \"$b\"",
         b"\xc3A\n")
