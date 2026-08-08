#!/usr/bin/env python3
"""QR item 5 (no-defer audit) spot-check — the 2.3-carry PRIORITY row:
CLI-reachable lexer no-progress RuntimeError crash, spelling from
2.3-rescue/slot-ledger.md R1-8: a["x`echo "]"`"]=v

Verifies the row is still an accurate description of tip (ae871a16):
a raw RuntimeError ('lexer made no progress at position N') from a
CLI-reachable input. Bash oracle keys `x]` fine (recorded, not asserted).

Byte-exact script files (od -c printed for the record). cwd = worktree.
"""
import os
import subprocess
import sys

WT = "/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/qr/wt"
BASH = "/opt/homebrew/bin/bash"

assert os.path.realpath(os.getcwd()) == os.path.realpath(WT), "cwd must be the worktree"

disc = subprocess.run(
    [sys.executable, "-c",
     "import psh, psh.version; print(psh.__file__); print(psh.version.__version__)"],
    cwd=WT, capture_output=True, text=True)
lines = disc.stdout.strip().splitlines()
assert len(lines) == 2 and lines[0].startswith(WT) and lines[1] == "0.773.0", disc.stdout
print(f"DISCRIMINATOR-OK {lines[0]} version={lines[1]}")

# The R1-8 spelling, bare and declare-prefixed (assoc read-back for bash).
CASES = {
    "bare": 'a["x`echo "]"`"]=v\n',
    "declared": 'declare -A a; a["x`echo "]"`"]=v; declare -p a\n',
}

scratch = os.path.join(WT, "tmp", "qr_p03")
os.makedirs(scratch, exist_ok=True)

for name, body in CASES.items():
    path = os.path.join(scratch, f"{name}.sh")
    with open(path, "wb") as f:
        f.write(body.encode())
    od = subprocess.run(["od", "-c", path], capture_output=True, text=True)
    print(f"--- case {name}: od -c ---")
    print(od.stdout.rstrip())
    p = subprocess.run([sys.executable, "-m", "psh", path], cwd=WT,
                       capture_output=True, text=True, timeout=30)
    tb = "Traceback" in p.stderr
    noprog = "no progress" in p.stderr
    print(f"psh : rc={p.returncode} traceback={tb} no-progress={noprog}")
    print(f"      stdout={p.stdout!r}")
    tail = p.stderr.strip().splitlines()[-3:]
    for ln in tail:
        print(f"      stderr| {ln}")
    b = subprocess.run([BASH, path], cwd=WT, capture_output=True, text=True, timeout=30)
    print(f"bash: rc={b.returncode} stdout={b.stdout!r} stderr={b.stderr.strip()!r}")
