"""Q3 discriminator: assert psh resolves under the Q3 worktree and version == 0.773.0.

Run with cwd = worktree root. Exits nonzero loudly on any mismatch.
"""
import os
import sys

WT = "/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q3/wt"

assert os.getcwd() == WT, f"cwd is {os.getcwd()}, expected {WT}"
sys.path.insert(0, WT)

import psh  # noqa: E402
import psh.version  # noqa: E402

resolved = os.path.realpath(psh.__file__)
wt_real = os.path.realpath(WT)
assert resolved.startswith(wt_real + os.sep), f"psh.__file__ = {resolved} NOT under worktree {wt_real}"
assert psh.version.__version__ == "0.773.0", f"version = {psh.version.__version__}, expected 0.773.0"

print("DISCRIMINATOR-OK")
print("psh.__file__ =", resolved)
print("__version__ =", psh.version.__version__)
