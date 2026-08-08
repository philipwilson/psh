#!/usr/bin/env python3
"""Q4 axis-5 follow-up.

(A) P3 zombie provenance: the mid-foreground-wait zombie of a finished
    background job — is it NEW at tip, or present at v0.750.0 / v0.749.0?
    Same cell run against all three trees (cwd + PYTHONPATH per tree).
(B) P3b boundary-reap: does the zombie persist PAST a command boundary?
    script: `sleep 0.2 & sleep 0.9; :; sleep 0.9` checked at t=1.4 (after
    the `:` boundary). bash oracle for divergence.
(C) P4 fixed (v1 errata: capture_output pipes made subprocess.run wait for
    the background child's death, so the cell could not distinguish
    anything): Popen with DEVNULL streams; wait shell; check survivor at
    +0.8s; then kill it.
"""
import os
import subprocess
import sys
import time

Q4 = ("/private/tmp/claude-501/-Users-pwilson-src-psh/"
      "05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q4")
TREES = {
    "tip-0.773": f"{Q4}/wt",
    "base-0.750": f"{Q4}/base0215",
    "base-0.749": f"{Q4}/base0749",
}
BASH = "/opt/homebrew/bin/bash"


def ps_children(pid):
    out = subprocess.run(["ps", "-axo", "pid,ppid,stat,command"],
                         capture_output=True, text=True).stdout
    return [line.split(None, 3) for line in out.splitlines()[1:]
            if line.split(None, 3)[1:2] == [str(pid)]]


def zombies_of(pid):
    return [r for r in ps_children(pid) if r[2].startswith("Z")]


def cell(label, argv, script, cwd, env, check_at, total):
    proc = subprocess.Popen(argv + [script], cwd=cwd, env=env,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    time.sleep(check_at)
    z = zombies_of(proc.pid)
    proc.wait(timeout=total)
    print(f"  {label}: zombies-at-t={check_at}: {len(z)} rc={proc.returncode}")
    return len(z)


print("=== (A) P3 provenance across trees: sleep 0.2 & sleep 1.4; : ===")
s3 = "sleep 0.2 & sleep 1.4; :"
for name, tree in TREES.items():
    env = dict(os.environ, PYTHONPATH=tree)
    # verify per-tree discriminator: resolved psh package path
    chk = subprocess.run(
        [sys.executable, "-c",
         "import psh,os;print(os.path.realpath(psh.__file__))"],
        cwd=tree, env=env, capture_output=True, text=True)
    print(f"  [{name}] psh -> {chk.stdout.strip()}")
    cell(name, [sys.executable, "-m", "psh", "-c"], s3, tree, env,
         check_at=0.9, total=25)
cell("bash-oracle", [BASH, "-c"], s3, TREES["tip-0.773"], dict(os.environ),
     check_at=0.9, total=25)

print("\n=== (B) P3b past-a-command-boundary: sleep 0.2 & sleep 0.9; :; sleep 0.9 ===")
s3b = "sleep 0.2 & sleep 0.9; :; sleep 0.9"
tip = TREES["tip-0.773"]
env_tip = dict(os.environ, PYTHONPATH=tip)
cell("psh-tip", [sys.executable, "-m", "psh", "-c"], s3b, tip, env_tip,
     check_at=1.4, total=25)
cell("bash-oracle", [BASH, "-c"], s3b, tip, dict(os.environ),
     check_at=1.4, total=25)

print("\n=== (C) P4 fixed: bg job survives shell exit? ===")
for label, argv, env, marker in [
        ("psh-tip", [sys.executable, "-m", "psh", "-c"], env_tip, "6.47"),
        ("bash", [BASH, "-c"], dict(os.environ), "6.48")]:
    script = f"sleep {marker} &"
    proc = subprocess.Popen(argv + [script], cwd=tip, env=env,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    rc = proc.wait(timeout=30)
    time.sleep(0.8)
    surv = subprocess.run(["pgrep", "-f", f"sleep {marker}"],
                          capture_output=True, text=True).stdout.split()
    print(f"  {label}: rc={rc} survivor-count={len(surv)}")
    subprocess.run(["pkill", "-f", f"sleep {marker}"])
time.sleep(0.3)
left = subprocess.run(["pgrep", "-fl", "sleep 6.4"],
                      capture_output=True, text=True).stdout.strip()
print(f"post-cleanup leftovers: {left!r}")
