#!/usr/bin/env python3
"""Q5 discriminator: assert psh resolves under the Q5 worktree and is v0.773.0.

Run with cwd = the Q5 detached worktree so sys.path[0]/cwd resolution points
at the worktree tree. Aborts loudly on any mismatch.
"""
import os
import sys

WT = "/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q5/wt"

sys.path.insert(0, WT)
import psh  # noqa: E402
import psh.version  # noqa: E402

resolved = os.path.realpath(psh.__file__)
wt_real = os.path.realpath(WT)
print("cwd:", os.getcwd())
print("psh.__file__:", resolved)
print("psh.version.__version__:", psh.version.__version__)
assert resolved.startswith(wt_real + os.sep), f"psh resolved OUTSIDE worktree: {resolved}"
assert psh.version.__version__ == "0.773.0", f"wrong version: {psh.version.__version__}"
print("DISCRIMINATOR-OK")
