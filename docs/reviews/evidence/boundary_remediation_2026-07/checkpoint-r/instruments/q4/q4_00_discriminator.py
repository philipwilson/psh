#!/usr/bin/env python3
"""Q4 discriminator: assert psh resolves under the Q4 worktree at v0.773.0.

Run with cwd = worktree root. `python -m psh -c` prepends CWD to sys.path,
so cwd discipline is the mechanism; this probe asserts the resolved fact.
"""
import os
import sys

WT = "/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q4/wt"

assert os.getcwd() == WT, f"cwd is {os.getcwd()}, expected {WT}"

import psh  # noqa: E402
import psh.version  # noqa: E402

resolved = os.path.realpath(psh.__file__)
wt_real = os.path.realpath(WT)
print(f"psh.__file__ = {resolved}")
print(f"psh.version.__version__ = {psh.version.__version__}")
assert resolved.startswith(wt_real + os.sep), (
    f"psh resolved OUTSIDE worktree: {resolved}"
)
assert psh.version.__version__ == "0.773.0", (
    f"version is {psh.version.__version__}, expected 0.773.0"
)
print("DISCRIMINATOR-OK")
