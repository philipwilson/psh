#!/usr/bin/env python3
"""atk-c p00: import discriminator. Run with cwd = worktree and PYTHONPATH = worktree.

Asserts psh.__file__ resolves under the worktree AND __version__ == 0.773.0.
Also records the bash oracle version.
"""
import os
import subprocess
import sys

WT = "/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/atk-c/wt"
BASH = "/opt/homebrew/bin/bash"

assert os.getcwd() == WT, f"cwd must be worktree, got {os.getcwd()}"

import psh  # noqa: E402
import psh.version  # noqa: E402

print(f"psh.__file__ = {psh.__file__}")
print(f"psh.version.__version__ = {psh.version.__version__}")
assert psh.__file__.startswith(WT + os.sep), "DISCRIMINATOR FAIL: psh imported from outside the worktree"
assert psh.version.__version__ == "0.773.0", "DISCRIMINATOR FAIL: wrong version"

r = subprocess.run([BASH, "--version"], capture_output=True, text=True)
print("bash oracle:", r.stdout.splitlines()[0])
assert "5.2.26" in r.stdout.splitlines()[0], "ORACLE FAIL: not bash 5.2.26"

# git HEAD of the worktree
r2 = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=WT)
print("worktree HEAD:", r2.stdout.strip())
assert r2.stdout.strip().startswith("ae871a16"), "WORKTREE FAIL: wrong HEAD"

print("DISCRIMINATOR OK")
