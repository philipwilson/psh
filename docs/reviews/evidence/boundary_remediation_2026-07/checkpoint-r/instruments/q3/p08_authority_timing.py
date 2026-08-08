"""Q3 fresh probe: authority-timing cells (slots 3.4 / declared D-3.4-s4).

  A. seed-at-COMMIT determinism: `RANDOM=42; echo $RANDOM...` matches bash
     value-for-value (the persistent assignment takes the seed route).
  B. prefix staging does NOT seed: `RANDOM=42 true; echo $RANDOM` must NOT
     produce the seeded sequence's first value (in psh or bash).
  C. DECLARED deviation D-3.4-s4 behaves as declared:
     `RANDOM=1 eval 'echo $RANDOM'` -> bash prints the literal 1, psh
     generates (masked-special LAYER/SEED route). NOT a finding either way
     as long as it behaves AS DECLARED.
  D. refuse-before-evaluate on readonly prefixes:
     D1 `readonly RX; f(){ echo "RX=[${RX-UNSET}]"; }; RX=1 f` — bash parity
        (the 3.4 RO1 red-on-base cell: readonly-and-UNSET refused on the
        function/scope route).
     D2 side-effect visibility: does the RHS command substitution run when
        the target is readonly? psh vs bash, marker-file instrumented.
Run with cwd = worktree.
"""
import os
import subprocess
import sys
import tempfile

WT = "/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q3/wt"
assert os.getcwd() == WT
BASH = ["/opt/homebrew/bin/bash"]
ENV = {"HOME": os.environ["HOME"], "PATH": os.environ["PATH"],
       "PYTHONPATH": WT, "TERM": "dumb", "LC_ALL": "C", "LANG": "C"}

r = subprocess.run([sys.executable, "-c", "import psh; print(psh.__file__)"],
                   cwd=WT, env=ENV, capture_output=True, text=True)
assert r.stdout.strip() == WT + "/psh/__init__.py", r.stdout
failures = []


def psh_out(script):
    r = subprocess.run([sys.executable, "-m", "psh", "-c", script], cwd=WT,
                       env=ENV, capture_output=True, text=True, timeout=30)
    return r.stdout, r.stderr, r.returncode


def bash_out(script):
    r = subprocess.run(BASH + ["-c", script], cwd=WT, env=ENV,
                       capture_output=True, text=True, timeout=30)
    return r.stdout, r.stderr, r.returncode


# A. seeded sequence parity (deterministic; 5 draws)
seq_script = 'RANDOM=42; echo $RANDOM $RANDOM $RANDOM $RANDOM $RANDOM'
pa, _, _ = psh_out(seq_script)
ba, _, _ = bash_out(seq_script)
print(f"A  seeded sequence psh={pa.strip()!r} bash={ba.strip()!r}")
if pa != ba:
    failures.append(("A seed determinism", pa, ba))
seed42_first = ba.split()[0]

# B. prefix on an external-free builtin does NOT commit the seed
pb, _, _ = psh_out('RANDOM=42 true; echo $RANDOM')
bb, _, _ = bash_out('RANDOM=42 true; echo $RANDOM')
print(f"B  after 'RANDOM=42 true': psh={pb.strip()!r} bash={bb.strip()!r} "
      f"(seeded-first would be {seed42_first!r})")
if pb.strip() == seed42_first:
    failures.append(("B psh prefix leaked the seed", pb.strip(), "!= " + seed42_first))
if bb.strip() == seed42_first:
    print("   NOTE: bash itself matched the seeded first draw (chance 1/32768?)")

# C. declared deviation cell behaves AS DECLARED
pc, _, _ = psh_out("RANDOM=1 eval 'echo $RANDOM'")
bc, _, _ = bash_out("RANDOM=1 eval 'echo $RANDOM'")
print(f"C  RANDOM=1 eval: psh={pc.strip()!r} bash={bc.strip()!r}")
if bc.strip() != "1":
    failures.append(("C bash side of D-3.4-s4 moved", bc.strip(), "1"))
if pc.strip() == "1":
    failures.append(("C psh no longer generates (D-3.4-s4 flipped)", pc.strip(), "!= 1"))

# D1. RO1 cell — readonly-and-UNSET refused on the function route (bash parity)
d1 = 'readonly RX; f(){ echo "RX=[${RX-UNSET}]"; }; RX=1 f'
p1o, p1e, p1c = psh_out(d1)
b1o, b1e, b1c = bash_out(d1)
print(f"D1 psh: out={p1o.strip()!r} err={p1e.strip()!r} rc={p1c}")
print(f"D1 bash: out={b1o.strip()!r} err={b1e.strip()!r} rc={b1c}")
if p1o != b1o:
    failures.append(("D1 stdout parity", p1o, b1o))
if ("readonly" in b1e) != ("readonly" in p1e):
    failures.append(("D1 diagnostic presence parity", p1e, b1e))

# D2. side-effect visibility of the refused assignment's RHS
with tempfile.TemporaryDirectory(dir=WT + "/tmp") as d:
    for shellname, runner in (("psh", psh_out), ("bash", bash_out)):
        marker = os.path.join(d, f"marker_{shellname}")
        s = (f'readonly RX; g(){{ :; }}; RX=$(echo hit > {marker}; echo v) g; '
             f'test -f {marker} && echo CREATED || echo ABSENT')
        out, err, rc = runner(s)
        print(f"D2 {shellname}: {out.strip()!r} err={err.strip()!r} rc={rc}")
        if shellname == "psh":
            psh_d2 = out.strip()
        else:
            bash_d2 = out.strip()
if psh_d2 != bash_d2:
    failures.append(("D2 RHS-evaluation parity", psh_d2, bash_d2))

print("P08-RESULT:", "HOLDS" if not failures else f"HOLE: {failures}")
sys.exit(0 if not failures else 1)
