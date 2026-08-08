"""Q3 fresh probe: dup + temp-frame input-cursor cells at TIP vs bash (slots 4B.2/4B.4).

Cell scripts and stdin bytes are copied VERBATIM from the committed
`4b.4-rescue/instruments/instr12_three_way.py` (a copy sits alongside this
probe as instr12_three_way.COPY.py). That instrument's BASE/TIP trees are
retired, so this fresh equivalent measures the DIVERGENCE axis only
(tip psh vs /opt/homebrew/bin/bash); the REGRESSION axis base facts live in
the committed 4b.4 transcripts.

DECLARED deviations expected to read DIVERGES (NOT findings):
  - BL1-N4 move form `3<&0-`: bash closes the source, psh does not (D-4B.4-s2).
Everything else must MATCH bash for the lifecycle rule ("a description
outlives any ONE of the fds naming it") to hold at ae871a16.

Run with cwd = worktree.
"""
import os
import subprocess
import sys
import tempfile

WT = "/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/atk-b/wt"
assert os.getcwd() == WT
BASH = ["/opt/homebrew/bin/bash"]

ENV = {"HOME": os.environ["HOME"], "PATH": os.environ["PATH"],
       "PYTHONPATH": WT, "TERM": "dumb"}

r = subprocess.run([sys.executable, "-c", "import psh; print(psh.__file__)"],
                   cwd=WT, env=ENV, capture_output=True, text=True)
got = r.stdout.strip()
assert got == WT + "/psh/__init__.py", f"child resolved {got!r}"
print("DISCRIMINATOR:", got)
print("ORACLE:", subprocess.run(BASH + ["--version"], capture_output=True,
                                text=True).stdout.splitlines()[0])
print()

DECLARED_DIVERGE = {"BL1-N4"}
ROWS = []


def cell(label, script, stdin_bytes):
    tip = subprocess.run([sys.executable, "-m", "psh", "-c", script],
                         input=stdin_bytes, cwd=WT, env=ENV,
                         capture_output=True, timeout=30).stdout
    oe = dict(ENV, LC_ALL="C", LANG="C")
    bash = subprocess.run(BASH + ["-c", script], input=stdin_bytes, cwd=WT,
                          env=oe, capture_output=True, timeout=30).stdout
    diverges = tip != bash
    key = label.split()[0]
    declared = key in DECLARED_DIVERGE
    ROWS.append((label, diverges, declared))
    flag = "DIVERGES" if diverges else "matches "
    note = " [DECLARED D-4B.4-s2]" if declared else ""
    print(f"[{flag}] {label}{note}")
    print(f"          tip : {tip!r}")
    print(f"          bash: {bash!r}")
    print()


STRAND = b"\xc3ABZ\n"

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
cell("BL2-P1  read -N 1 b {v}<&0",
     'read -N 1 a; read -N 1 b {v}<&0; read -N 1 c; '
     'printf "a=<%s> b=<%s> c=<%s>\\n" "$a" "$b" "$c"', b"\xc3ABCD\n")
cell("BL7-X8  { read -N 1 -u 3 b; } 3<&0",
     'read -N 1 a; { read -N 1 -u 3 b; } 3<&0; read -N 1 c; '
     'printf "a=<%s> b=<%s> c=<%s>\\n" "$a" "$b" "$c"', b"\xc3ABZ\n")
cell("BL5     exec 3<&0; exec 4<&3; read -u 4",
     'read -N 1 a; exec 3<&0; exec 4<&3; read -N 1 -u 4 b; '
     'printf "a=<%s> b=<%s>\\n" "$a" "$b"', b"\xc3ABC\n")
cell("CTL-1   same-fd persistence",
     'read -N 1 x; read -N 1 y; printf "x=<%s> y=<%s>\\n" "$x" "$y"', b"\xc3A\n")
cell("CTL-2   plain dup share (leg B face)",
     'exec 3<&0; read -N 1 a; read -N 1 -u 3 b; '
     'printf "a=<%s> b=<%s>\\n" "$a" "$b"', b"\xc3A\n")
with tempfile.TemporaryDirectory(dir=WT + "/tmp") as d:
    f = os.path.join(d, "f.txt")
    open(f, "wb").write(b"F1\nF2\n")
    g = os.path.join(d, "g.txt")
    open(g, "wb").write(b"\xc3AGGG\nG2\n")
    cell("CTL-3   temp-frame forward isolation",
         f'read -N 1 a; read b < {f}; read -N 1 c; '
         'printf "a=<%s> b=<%s> c=<%s>\\n" "$a" "$b" "$c"', b"\xc3A\nS2\n")
    cell("CTL-4   temp-frame reverse isolation",
         f'read -N 1 a < {g}; read b; printf "a=<%s> b=<%s>\\n" "$a" "$b"',
         b"STDIN1\nSTDIN2\n")

print("=" * 68)
undeclared = [(lbl, d) for lbl, d, dec in ROWS if d and not dec]
declared_ok = [(lbl,) for lbl, d, dec in ROWS if dec and d]
declared_gone = [(lbl,) for lbl, d, dec in ROWS if dec and not d]
print(f"cells: {len(ROWS)}  undeclared divergences: {len(undeclared)}  "
      f"declared-deviation cells diverging as declared: {len(declared_ok)}")
if declared_gone:
    print("NOTE: declared-deviation cell now MATCHES bash (record drift?):",
          declared_gone)
print("P05-RESULT:", "HOLDS" if not undeclared else f"HOLE: {undeclared}")
sys.exit(0 if not undeclared else 1)
