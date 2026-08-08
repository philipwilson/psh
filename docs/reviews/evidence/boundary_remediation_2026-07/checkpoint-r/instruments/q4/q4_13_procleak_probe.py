#!/usr/bin/env python3
"""Q4 axis-5: OS-level process-leak probes at ae871a16, psh vs bash oracle.

Cells (each run for BOTH shells; axis = DIVERGENCE tip-vs-bash, plus the
absolute zombie/orphan discipline):
  P1 procsub-zombie: run `cat <(echo a) <(echo b); cat <(echo c); sleep 1.6`;
     mid-sleep, count Z-state children of the shell pid. Expect 0.
  P2 procsub-writer: run `head -1 <(yes q4markerA)`; after shell exit, count
     surviving `yes q4markerA` processes. Expect 0 (writer dies on SIGPIPE).
  P3 bg-reap: run `sleep 0.2 & sleep 1.4; :`; mid-second-sleep, count Z-state
     children. Expect 0 (job reaped while shell alive).
  P4 bg-on-shutdown: run `sleep 6.47 &`; after shell exit, is the sleep
     alive? bash leaves it running (normal POSIX orphan) — record both,
     compare, then KILL any survivor (cleanup of our own markers).

pgrep snapshots for the marker patterns are taken before and after the whole
batch. Timing margins are generous; each mid-run check polls until the shell
child is observed or a deadline passes.
"""
import os
import subprocess
import sys
import time

WT = ("/private/tmp/claude-501/-Users-pwilson-src-psh/"
      "05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q4/wt")
BASH = "/opt/homebrew/bin/bash"
assert os.getcwd() == WT, f"cwd {os.getcwd()} != worktree"
ENV = dict(os.environ, PYTHONPATH=WT)

PSH = [sys.executable, "-m", "psh", "-c"]
ORACLE = [BASH, "-c"]


def ps_children(pid):
    out = subprocess.run(["ps", "-axo", "pid,ppid,stat,command"],
                         capture_output=True, text=True).stdout
    rows = []
    for line in out.splitlines()[1:]:
        parts = line.split(None, 3)
        if len(parts) >= 3 and parts[1] == str(pid):
            rows.append(parts)
    return rows


def zombies_of(pid):
    return [r for r in ps_children(pid) if r[2].startswith("Z")]


def pgrep(pattern):
    out = subprocess.run(["pgrep", "-fl", pattern],
                         capture_output=True, text=True).stdout
    me = str(os.getpid())
    return [ln for ln in out.splitlines() if ln.split()[0] != me]


def midrun_zombie_cell(label, argv, script, check_at, total):
    proc = subprocess.Popen(argv + [script], cwd=WT, env=ENV,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    time.sleep(check_at)
    z = zombies_of(proc.pid)
    kids = ps_children(proc.pid)
    proc.wait(timeout=total)
    print(f"  {label}: zombies-at-check={len(z)} "
          f"(children seen: {len(kids)}) rc={proc.returncode}")
    for r in z:
        print(f"    Z: {r}")
    return len(z)


def after_exit_survivors(label, argv, script, pattern, settle=0.8):
    proc = subprocess.run(argv + [script], cwd=WT, env=ENV,
                          capture_output=True, text=True, timeout=30)
    time.sleep(settle)
    surv = pgrep(pattern)
    print(f"  {label}: rc={proc.returncode} survivors[{pattern}]={len(surv)}")
    for ln in surv:
        print(f"    {ln}")
    return surv


print("=== pgrep snapshot BEFORE batch ===")
for pat in ["q4markerA", "sleep 6.47", "sleep 6.48"]:
    print(f"  [{pat}]: {pgrep(pat)}")

print("\n=== P1 procsub-zombie (mid-run Z census) ===")
s1 = "cat <(echo a) <(echo b); cat <(echo c); sleep 1.6"
p1_psh = midrun_zombie_cell("psh ", PSH, s1, check_at=1.0, total=25)
p1_bash = midrun_zombie_cell("bash", ORACLE, s1, check_at=1.0, total=25)

print("\n=== P2 procsub-writer survivors after exit ===")
s2 = "head -1 <(yes q4markerA)"
p2_psh = after_exit_survivors("psh ", PSH, s2, "q4markerA")
subprocess.run(["pkill", "-f", "q4markerA"])
p2_bash = after_exit_survivors("bash", ORACLE, s2, "q4markerA")
subprocess.run(["pkill", "-f", "q4markerA"])

print("\n=== P3 bg-reap (mid-run Z census) ===")
s3 = "sleep 0.2 & sleep 1.4; :"
p3_psh = midrun_zombie_cell("psh ", PSH, s3, check_at=0.9, total=25)
p3_bash = midrun_zombie_cell("bash", ORACLE, s3, check_at=0.9, total=25)

print("\n=== P4 bg job survives shell exit? (both shells; then cleaned) ===")
p4_psh = after_exit_survivors("psh ", PSH, "sleep 6.47 &", "sleep 6.47")
p4_bash = after_exit_survivors("bash", ORACLE, "sleep 6.48 &", "sleep 6.48")
subprocess.run(["pkill", "-f", "sleep 6.47"])
subprocess.run(["pkill", "-f", "sleep 6.48"])
time.sleep(0.5)

print("\n=== pgrep snapshot AFTER batch (post-cleanup) ===")
leftover = []
for pat in ["q4markerA", "sleep 6.47", "sleep 6.48"]:
    got = pgrep(pat)
    leftover.extend(got)
    print(f"  [{pat}]: {got}")

print("\n=== verdict lines ===")
print(f"P1 zombies psh={p1_psh} bash={p1_bash} (expect 0/0)")
print(f"P2 writer-survivors psh={len(p2_psh)} bash={len(p2_bash)} (expect 0/0)")
print(f"P3 zombies psh={p3_psh} bash={p3_bash} (expect 0/0)")
print(f"P4 bg-survives psh={len(p4_psh)} bash={len(p4_bash)} "
      f"(bash norm: 1 — divergence only if psh differs)")
print(f"post-batch leftovers: {len(leftover)}")
