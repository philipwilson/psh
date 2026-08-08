"""INSTR11 — reproduce every verify-round blocker row MYSELF before fixing.

Round 1 bounced with 7 blockers. Two are regressions my branch introduced.
I do not fix on another agent's transcript: each row below is re-derived
here, at THIS tree, with the two-level discriminator, against live bash.

Rows (verifier's labels kept so the mapping is checkable):
  BL-1/BL-6  reference-blind drops: a frame pop or a rebind destroys a
             description that ANOTHER fd still names.
  BL-2       cursor_scope_fds derives fd 0 for a named-fd redirect, whose
             real fd is only allocated at apply time.
  BL-7       compound-command dups (`{ ...; } 3<&0`) get frame scoping but
             no aliasing — pre-existing, but undeclared under CLOSE.
  N9         dup aliasing does not survive an intervening frame.

Oracle: C-locale bash for the malformed-lead rows (I1 DECISION 1).

Run:  python tmp/w4b4/instr11_bounce_repro.py
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


def cell(label, script, stdin_bytes, oracle="C"):
    e = env({"LC_ALL": "C", "LANG": "C"}) if oracle == "C" else env()
    psh = subprocess.run(PSH + ["-c", script], input=stdin_bytes, cwd=REPO,
                         env=env(), capture_output=True, timeout=30).stdout
    bash = subprocess.run(BASH + ["-c", script], input=stdin_bytes, cwd=REPO,
                          env=e, capture_output=True, timeout=30).stdout
    ok = psh == bash
    ROWS.append((label, ok))
    print(f"[{'MATCH  ' if ok else 'DIVERGE'}] {label}")
    print(f"          psh   : {psh!r}")
    print(f"          bash-{oracle}: {bash!r}")
    print()
    return ok


STRAND = b"\xc3ABZ\n"

print("=" * 74)
print("BL-1 / BL-6 — a frame pop or rebind destroys a STILL-REFERENCED cursor")
print("=" * 74)

cell("BL1-R1  true 3<&0 between reads",
     'read -N 1 a; true 3<&0; read -N 1 b; printf "a=<%s> b=<%s>\\n" "$a" "$b"',
     b"\xc3ABC\n")

cell("BL1-R2  ':' instead of 'true'",
     'read -N 1 a; : 3<&0; read -N 1 b; printf "a=<%s> b=<%s>\\n" "$a" "$b"',
     b"\xc3ABC\n")

cell("BL1-N4  move form  true 3<&0-",
     'read -N 1 a; true 3<&0-; read -N 1 b; printf "a=<%s> b=<%s>\\n" "$a" "$b"',
     b"\xc3ABC\n")

cell("BL1-N5  mapfile after the frame",
     'read -N 1 a; true 3<&0; mapfile -t -n 1 L; printf "L=<%s>\\n" "${L[0]}"',
     b"\xc3ABC\nX\n")

cell("BL6-X3  output dup to a read fd:  true >&0",
     'read -N 1 a; true >&0; read -N 1 b; printf "a=<%s> b=<%s>\\n" "$a" "$b"',
     STRAND)

cell("BL6-X4  save/close idiom:  exec 3<&0; exec 3<&-",
     'read -N 1 a; exec 3<&0; exec 3<&-; read -N 1 b; '
     'printf "a=<%s> b=<%s>\\n" "$a" "$b"',
     STRAND)

cell("BL1-N9  dup aliasing across an intervening frame",
     'exec 3<&0; read -N 1 a; true 4<&3; read -N 1 -u 3 b; '
     'printf "a=<%s> b=<%s>\\n" "$a" "$b"',
     b"\xc3ABC\n")

print("=" * 74)
print("BL-2 — named-fd redirect on a BUILTIN frame (fd known only at apply)")
print("=" * 74)

cell("BL2-P1  read -N 1 b {v}<&0",
     'read -N 1 a; read -N 1 b {v}<&0; read -N 1 c; '
     'printf "a=<%s> b=<%s> c=<%s>\\n" "$a" "$b" "$c"',
     b"\xc3ABCD\n")

print("=" * 74)
print("BL-7 — compound-command dup (guarded_redirections path, no aliasing)")
print("=" * 74)

cell("BL7-X8  { read -N 1 -u 3 b; } 3<&0",
     'read -N 1 a; { read -N 1 -u 3 b; } 3<&0; read -N 1 c; '
     'printf "a=<%s> b=<%s> c=<%s>\\n" "$a" "$b" "$c"',
     b"\xc3ABZ\n")

print("=" * 74)
print("BL-5 / RN-17 — chained dup (verifier says already correct; confirm)")
print("=" * 74)

cell("BL5     exec 3<&0; exec 4<&3; read -u 4",
     'read -N 1 a; exec 3<&0; exec 4<&3; read -N 1 -u 4 b; '
     'printf "a=<%s> b=<%s>\\n" "$a" "$b"',
     b"\xc3ABC\n")

print("=" * 74)
print("MUST-HOLD controls — these were green and must STAY green")
print("=" * 74)

cell("CTL     same-fd persistence",
     'read -N 1 x; read -N 1 y; printf "x=<%s> y=<%s>\\n" "$x" "$y"',
     b"\xc3A\n")

cell("CTL     plain dup share (the slot's leg-B face)",
     'exec 3<&0; read -N 1 a; read -N 1 -u 3 b; '
     'printf "a=<%s> b=<%s>\\n" "$a" "$b"',
     b"\xc3A\n")

with tempfile.TemporaryDirectory(dir=REPO + "/tmp") as d:
    f = os.path.join(d, "f.txt")
    open(f, "wb").write(b"F1\nF2\n")
    cell("CTL     temp-frame forward isolation",
         f'read -N 1 a; read b < {f}; read -N 1 c; '
         'printf "a=<%s> b=<%s> c=<%s>\\n" "$a" "$b" "$c"',
         b"\xc3A\nS2\n")
    cell("CTL     non-dup frame between reads (true 2>/dev/null)",
         'read -N 1 a; true 2>/dev/null; read -N 1 b; '
         'printf "a=<%s> b=<%s>\\n" "$a" "$b"',
         b"\xc3ABC\n")

print("=" * 74)
bad = [n for n, ok in ROWS if not ok]
for n, ok in ROWS:
    print(f"{'MATCH  ' if ok else 'DIVERGE'}  {n}")
print(f"\nDIVERGE={len(bad)}  MATCH={len(ROWS)-len(bad)}")
