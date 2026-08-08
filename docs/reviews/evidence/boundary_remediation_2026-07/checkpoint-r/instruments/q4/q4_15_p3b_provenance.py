#!/usr/bin/env python3
"""Q4 axis-5: P3b (zombie persists past a command boundary) provenance —
same cell at base v0.750.0 and v0.749.0."""
import os
import subprocess
import sys
import time

Q4 = ("/private/tmp/claude-501/-Users-pwilson-src-psh/"
      "05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q4")


def zombies_of(pid):
    out = subprocess.run(["ps", "-axo", "pid,ppid,stat"],
                         capture_output=True, text=True).stdout
    return [ln for ln in out.splitlines()[1:]
            if ln.split()[1:2] == [str(pid)] and ln.split()[2].startswith("Z")]


s3b = "sleep 0.2 & sleep 0.9; :; sleep 0.9"
for name, tree in [("base-0.750", f"{Q4}/base0215"),
                   ("base-0.749", f"{Q4}/base0749")]:
    env = dict(os.environ, PYTHONPATH=tree)
    chk = subprocess.run(
        [sys.executable, "-c",
         "import psh,os;print(os.path.realpath(psh.__file__))"],
        cwd=tree, env=env, capture_output=True, text=True)
    print(f"[{name}] psh -> {chk.stdout.strip()}")
    proc = subprocess.Popen([sys.executable, "-m", "psh", "-c", s3b],
                            cwd=tree, env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    time.sleep(1.4)
    z = zombies_of(proc.pid)
    proc.wait(timeout=25)
    print(f"  {name}: zombies-at-t=1.4: {len(z)} rc={proc.returncode}")
