#!/usr/bin/env python3
"""QR item 2 — TIMEFORMAT %P absurd values: reproduce at tip (ae871a16).

Charter: rate over <=60 `time true` runs; confirm the mechanism note
(10 ms accounting tick / tiny elapsed); this probe also runs a small bash
oracle batch for the sane-value contrast.

Run with cwd INSIDE the worktree. `python -m psh` prepends CWD to sys.path,
so cwd discipline selects the worktree tree; the discriminator subprocess
asserts the resolved psh.__file__ and version before any measurement.

Absurd threshold: %P > 200.0 (bash's value for `time true` is a genuine
CPU percentage; multi-thousand values are the defect face — LEDGER records
P=11934.31 vs bash 2.02).
"""
import os
import re
import subprocess
import sys

WT = "/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/qr/wt"
BASH = "/opt/homebrew/bin/bash"
CMD = "TIMEFORMAT='R=%R U=%U S=%S P=%P'; time true"
N_PSH = 60
N_BASH = 10

assert os.path.realpath(os.getcwd()) == os.path.realpath(WT), "cwd must be the worktree"

# Discriminator: the psh that `python -m psh` will resolve from this cwd.
disc = subprocess.run(
    [sys.executable, "-c",
     "import psh, psh.version; print(psh.__file__); print(psh.version.__version__)"],
    cwd=WT, capture_output=True, text=True)
lines = disc.stdout.strip().splitlines()
assert len(lines) == 2 and lines[0].startswith(WT) and lines[1] == "0.773.0", disc.stdout
print(f"DISCRIMINATOR-OK {lines[0]} version={lines[1]}")

pat = re.compile(r"R=([\d.]+) U=([\d.]+) S=([\d.]+) P=([\d.]+)")


def batch(label, argv, n):
    values = []
    absurd = []
    for i in range(n):
        p = subprocess.run(argv, cwd=WT, capture_output=True, text=True, timeout=30)
        m = pat.search(p.stderr)
        if not m:
            print(f"  [{label} {i}] UNPARSEABLE stderr={p.stderr!r}")
            continue
        r, u, s, pct = (float(m.group(k)) for k in (1, 2, 3, 4))
        values.append((r, u, s, pct))
        if pct > 200.0:
            absurd.append((i, r, u, s, pct))
    pcts = sorted(v[3] for v in values)
    print(f"{label}: n={len(values)} absurd(P>200)={len(absurd)} "
          f"P min={pcts[0]:.2f} median={pcts[len(pcts)//2]:.2f} max={pcts[-1]:.2f}")
    for i, r, u, s, pct in absurd[:6]:
        # Mechanism check: pct should equal (u+s)/r*100 within rounding —
        # i.e. a 10ms-granular U (or S) divided by a sub-millisecond R.
        implied = (u + s) / r * 100 if r > 0 else float("nan")
        print(f"    iter {i}: R={r} U={u} S={s} P={pct}  (U+S)/R*100={implied:.2f} "
              f"tick10ms={'YES' if abs(u*100 - round(u*100)) < 1e-9 and u > 0 else 'no'}")
    return values, absurd


print(f"cmd: {CMD!r}")
psh_vals, psh_absurd = batch("psh-tip", [sys.executable, "-m", "psh", "-c", CMD], N_PSH)
bash_vals, bash_absurd = batch("bash-5.2.26", [BASH, "-c", CMD], N_BASH)
print(f"RESULT psh absurd rate: {len(psh_absurd)}/{len(psh_vals)}; "
      f"bash absurd rate: {len(bash_absurd)}/{len(bash_vals)}")
