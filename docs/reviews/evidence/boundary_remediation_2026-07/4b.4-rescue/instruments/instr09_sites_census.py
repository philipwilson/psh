"""INSTR09 — R2 invariant 1: dup-site + frame-kind census, red-on-base.

Every dup SPELLING and every redirect FRAME KIND gets its own cell, so no
site is closed by accident and none is left silently open (rule 7: a face
living in one probe is one probe away from silence).

Oracle = C-locale bash (malformed model, I1 DECISION 1). The stimulus is the
deterministic malformed-lead surplus, so no timing is involved.
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import BASH, PSH, REPO, discriminate, env  # noqa: E402

discriminate()
print()
ROWS = []


def cell(name, script, stdin_bytes):
    def one(argv, e):
        r = subprocess.run(argv + ['-c', script], input=stdin_bytes, cwd=REPO,
                           env=e, capture_output=True, timeout=30)
        return r.stdout, r.returncode, r.stderr
    psh, prc, perr = one(PSH, env())
    bc, brc, berr = one(BASH, env({'LC_ALL': 'C', 'LANG': 'C'}))
    v = 'MATCH' if psh == bc else 'DIVERGE'
    ROWS.append((name, v))
    print(f"[{v:7}] {name}")
    print(f"          psh   : {psh!r} rc={prc}" + (f" err={perr[:70]!r}" if perr else ""))
    print(f"          bash-C: {bc!r} rc={brc}" + (f" err={berr[:70]!r}" if berr else ""))
    print()


with tempfile.TemporaryDirectory(dir=REPO + '/tmp') as d:
    F = os.path.join(d, 'f.txt'); open(F, 'wb').write(b'F1\nF2\n')
    G = os.path.join(d, 'g.txt'); open(G, 'wb').write(b'\xc3AGGG\nG2\n')

    print("=" * 72); print("DUP SPELLINGS"); print("=" * 72)
    cell("dup: exec 3<&0 (permanent)",
         "exec 3<&0; read -N 1 a; read -N 1 -u 3 b; printf 'a=<%s> b=<%s>\\n' \"$a\" \"$b\"",
         b"\xc3A\n")
    cell("dup: {v}<&0 (named fd)",
         "exec {v}<&0; read -N 1 a; read -N 1 -u $v b; printf 'a=<%s> b=<%s>\\n' \"$a\" \"$b\"",
         b"\xc3A\n")
    cell("dup: per-command 3<&0 on a builtin (temp)",
         "read -N 1 a; read -N 1 -u 3 b 3<&0; printf 'a=<%s> b=<%s>\\n' \"$a\" \"$b\"",
         b"\xc3A\n")

    print("=" * 72); print("FRAME KINDS — forward leak (stdin surplus INTO frame)"); print("=" * 72)
    cell("frame: builtin redirect  read b < F",
         f"read -N 1 a; read b < {F}; read -N 1 c; printf 'a=<%s> b=<%s> c=<%s>\\n' \"$a\" \"$b\" \"$c\"",
         b"\xc3A\nS2\n")
    cell("frame: brace group  { read b; } < F",
         f"read -N 1 a; {{ read b; }} < {F}; read -N 1 c; printf 'a=<%s> b=<%s> c=<%s>\\n' \"$a\" \"$b\" \"$c\"",
         b"\xc3A\nS2\n")
    cell("frame: while loop  while read b; do break; done < F",
         f"read -N 1 a; while read b; do break; done < {F}; read -N 1 c; "
         "printf 'a=<%s> b=<%s> c=<%s>\\n' \"$a\" \"$b\" \"$c\"",
         b"\xc3A\nS2\n")
    cell("frame: function with redirect",
         f"f() {{ read b; printf 'b=<%s>\\n' \"$b\"; }}; read -N 1 a; f < {F}; "
         "read -N 1 c; printf 'a=<%s> c=<%s>\\n' \"$a\" \"$c\"",
         b"\xc3A\nS2\n")

    print("=" * 72); print("FRAME KINDS — REVERSE leak (frame surplus OUT into stdin)"); print("=" * 72)
    cell("reverse: builtin redirect  read -N 1 a < G",
         f"read -N 1 a < {G}; read b; printf 'a=<%s> b=<%s>\\n' \"$a\" \"$b\"",
         b"STDIN1\nSTDIN2\n")
    cell("reverse: brace group  { read -N 1 a; } < G",
         f"{{ read -N 1 a; }} < {G}; read b; printf 'a=<%s> b=<%s>\\n' \"$a\" \"$b\"",
         b"STDIN1\nSTDIN2\n")

    print("=" * 72); print("MUST-HOLDS (must stay MATCH after the fix)"); print("=" * 72)
    cell("must-hold: same-fd persistence",
         "read -N 1 x; read -N 1 y; printf 'x=<%s> y=<%s>\\n' \"$x\" \"$y\"", b"\xc3A\n")
    cell("must-hold: exec rebind drops",
         f"read -N 1 a; exec 0<{F}; read b; printf 'a=<%s> b=<%s>\\n' \"$a\" \"$b\"",
         b"\xc3A\nS2\n")
    cell("must-hold: never-over-read to external",
         "read x; cat", b"a\nb\nc\n")

print("=" * 72)
for n, v in ROWS:
    print(f"{v:7}  {n}")
print(f"\nDIVERGE={sum(1 for _, v in ROWS if v=='DIVERGE')}  MATCH={sum(1 for _, v in ROWS if v=='MATCH')}")
