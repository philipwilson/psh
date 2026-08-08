#!/usr/bin/env python3
"""atk-a discriminator: assert measurement subject before ANY measurement.

Runs a child python with cwd = worktree and PYTHONPATH = worktree, asserts
psh.__file__ resolves UNDER the worktree and __version__ == 0.773.0.
Records worktree HEAD and bash oracle version.
"""
import os
import subprocess
import sys

WT = "/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/atk-a/wt"
BASH = "/opt/homebrew/bin/bash"

env = dict(os.environ)
env["PYTHONPATH"] = WT

child = (
    "import psh, psh.version, sys;"
    "print('psh.__file__=' + psh.__file__);"
    "print('__version__=' + psh.version.__version__)"
)
r = subprocess.run([sys.executable, "-c", child], cwd=WT, env=env,
                   capture_output=True, text=True, timeout=60)
print(r.stdout, end="")
assert r.returncode == 0, r.stderr
lines = dict(l.split("=", 1) for l in r.stdout.strip().splitlines())
assert lines["psh.__file__"].startswith(WT + "/"), "psh resolved OUTSIDE worktree"
assert lines["__version__"] == "0.773.0", "wrong version"

head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=WT,
                      capture_output=True, text=True).stdout.strip()
print("worktree_HEAD=" + head)
assert head.startswith("ae871a16")

bv = subprocess.run([BASH, "--version"], capture_output=True, text=True).stdout.splitlines()[0]
print("bash_oracle=" + bv)
assert "5.2.26" in bv
print("DISCRIMINATOR-OK")
