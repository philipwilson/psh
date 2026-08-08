"""INSTR12 — three-column comparator: BASE psh | TIP psh | bash.

Supersedes INSTR11's summary column, which was the WRONG AXIS and hid a real
finding. INSTR11 scored each row MATCH/DIVERGE on psh-vs-bash only. On the
move-form row (`true 3<&0-`) bash diverges from psh at BOTH ends for an
unrelated reason (bash's move closes the source, so its `b` is empty), so a
psh-vs-bash column reads DIVERGE at base and DIVERGE at tip and the
base->tip REGRESSION inside it (b=<A> -> b=<B>, the held byte destroyed)
is invisible. The verifier classified that row correctly and my instrument
did not. Two axes are needed, always:

    REGRESSION  = base psh != tip psh          (did MY branch change it?)
    DIVERGENCE  = tip psh  != bash             (do we match the oracle?)

A row can be either, both, or neither, and the two questions have different
owners: a REGRESSION is mine to fix now; a pre-existing DIVERGENCE is a
scope/declaration question.

Run:  python tmp/w4b4/instr12_three_way.py
"""
import os
import subprocess
import sys
import tempfile

TIP = "/Users/pwilson/src/psh-r4b-4"
BASE = "/Users/pwilson/src/psh-4b4-base"
BASH = ["/opt/homebrew/bin/bash"]


def _env(tree, extra=None):
    e = {"HOME": os.environ["HOME"], "PATH": os.environ["PATH"],
         "PYTHONPATH": tree, "TERM": "dumb"}
    if extra:
        e.update(extra)
    return e


def _discriminate(tree):
    r = subprocess.run([sys.executable, "-c", "import psh; print(psh.__file__)"],
                       cwd=tree, env=_env(tree), capture_output=True, text=True)
    got = r.stdout.strip()
    assert got == tree + "/psh/__init__.py", f"{tree}: child resolved {got!r}"
    return got


for t in (TIP, BASE):
    print("DISCRIMINATOR:", _discriminate(t))
print("ORACLE:", subprocess.run(BASH + ["--version"], capture_output=True,
                                text=True).stdout.splitlines()[0])
print()

ROWS = []


def cell(label, script, stdin_bytes, oracle="C"):
    def psh(tree):
        return subprocess.run(
            [sys.executable, "-m", "psh", "-c", script], input=stdin_bytes,
            cwd=tree, env=_env(tree), capture_output=True, timeout=30).stdout
    base, tip = psh(BASE), psh(TIP)
    oe = _env(TIP, {"LC_ALL": "C", "LANG": "C"}) if oracle == "C" else _env(TIP)
    bash = subprocess.run(BASH + ["-c", script], input=stdin_bytes, cwd=TIP,
                          env=oe, capture_output=True, timeout=30).stdout
    regressed = base != tip
    diverges = tip != bash
    ROWS.append((label, regressed, diverges, base == bash))
    flag = ("REGRESSED" if regressed else "         ") + \
           ("  DIVERGES" if diverges else "  matches ")
    print(f"[{flag}] {label}")
    print(f"            base: {base!r}")
    print(f"            tip : {tip!r}")
    print(f"            bash: {bash!r}")
    print()


STRAND = b"\xc3ABZ\n"

print("=" * 76)
print("BL-1 / BL-6 — reference-blind drops (claimed REGRESSIONS)")
print("=" * 76)
cell("BL1-R1  true 3<&0 between reads",
     'read -N 1 a; true 3<&0; read -N 1 b; printf "a=<%s> b=<%s>\\n" "$a" "$b"',
     b"\xc3ABC\n")
cell("BL1-R2  ':' instead of 'true'",
     'read -N 1 a; : 3<&0; read -N 1 b; printf "a=<%s> b=<%s>\\n" "$a" "$b"',
     b"\xc3ABC\n")
cell("BL1-N4  move form true 3<&0-",
     'read -N 1 a; true 3<&0-; read -N 1 b; printf "a=<%s> b=<%s>\\n" "$a" "$b"',
     b"\xc3ABC\n")
cell("BL1-N5  mapfile after the frame",
     'read -N 1 a; true 3<&0; mapfile -t -n 1 L; printf "L=<%s>\\n" "${L[0]}"',
     b"\xc3ABC\nX\n")
cell("BL6-X3  output dup to a read fd: true >&0",
     'read -N 1 a; true >&0; read -N 1 b; printf "a=<%s> b=<%s>\\n" "$a" "$b"',
     STRAND)
cell("BL6-X4  save/close idiom exec 3<&0; exec 3<&-",
     'read -N 1 a; exec 3<&0; exec 3<&-; read -N 1 b; '
     'printf "a=<%s> b=<%s>\\n" "$a" "$b"', STRAND)
cell("BL1-N9  aliasing across an intervening frame",
     'exec 3<&0; read -N 1 a; true 4<&3; read -N 1 -u 3 b; '
     'printf "a=<%s> b=<%s>\\n" "$a" "$b"', b"\xc3ABC\n")

print("=" * 76)
print("BL-2 — named-fd redirect on a builtin frame (claimed REGRESSION)")
print("=" * 76)
cell("BL2-P1  read -N 1 b {v}<&0",
     'read -N 1 a; read -N 1 b {v}<&0; read -N 1 c; '
     'printf "a=<%s> b=<%s> c=<%s>\\n" "$a" "$b" "$c"', b"\xc3ABCD\n")

print("=" * 76)
print("BL-7 — compound dup (claimed PRE-EXISTING, undeclared under CLOSE)")
print("=" * 76)
cell("BL7-X8  { read -N 1 -u 3 b; } 3<&0",
     'read -N 1 a; { read -N 1 -u 3 b; } 3<&0; read -N 1 c; '
     'printf "a=<%s> b=<%s> c=<%s>\\n" "$a" "$b" "$c"', b"\xc3ABZ\n")

print("=" * 76)
print("BL-5 — chained dup (claimed already correct at tip)")
print("=" * 76)
cell("BL5     exec 3<&0; exec 4<&3; read -u 4",
     'read -N 1 a; exec 3<&0; exec 4<&3; read -N 1 -u 4 b; '
     'printf "a=<%s> b=<%s>\\n" "$a" "$b"', b"\xc3ABC\n")

print("=" * 76)
print("MUST-HOLD — the slot's own closed faces and I1 guarantees")
print("=" * 76)
cell("CTL     same-fd persistence",
     'read -N 1 x; read -N 1 y; printf "x=<%s> y=<%s>\\n" "$x" "$y"', b"\xc3A\n")
cell("CTL     plain dup share (leg B face)",
     'exec 3<&0; read -N 1 a; read -N 1 -u 3 b; '
     'printf "a=<%s> b=<%s>\\n" "$a" "$b"', b"\xc3A\n")
with tempfile.TemporaryDirectory(dir=TIP + "/tmp") as d:
    f = os.path.join(d, "f.txt")
    open(f, "wb").write(b"F1\nF2\n")
    g = os.path.join(d, "g.txt")
    open(g, "wb").write(b"\xc3AGGG\nG2\n")
    cell("CTL     temp-frame forward isolation",
         f'read -N 1 a; read b < {f}; read -N 1 c; '
         'printf "a=<%s> b=<%s> c=<%s>\\n" "$a" "$b" "$c"', b"\xc3A\nS2\n")
    cell("CTL     temp-frame reverse isolation",
         f'read -N 1 a < {g}; read b; printf "a=<%s> b=<%s>\\n" "$a" "$b"',
         b"STDIN1\nSTDIN2\n")

print("=" * 76)
print(f"{'ROW':<44} {'REGRESSED':<10} {'vs bash'}")
print("=" * 76)
for label, reg, div, base_ok in ROWS:
    print(f"{label:<44} {'YES' if reg else '-':<10} "
          f"{'DIVERGES' if div else 'matches'}")
print()
print(f"REGRESSIONS (base!=tip): {sum(1 for _, r, _, _ in ROWS if r)}")
print(f"DIVERGENCES at tip     : {sum(1 for _, _, d, _ in ROWS if d)}")
