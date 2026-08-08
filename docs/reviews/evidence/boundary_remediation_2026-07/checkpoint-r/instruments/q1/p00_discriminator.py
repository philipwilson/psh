# Q1 checkpoint-R probe 00: import discriminator (rule B71).
# Run with cwd = the detached worktree. Asserts psh resolves UNDER the
# worktree and __version__ == 0.773.0 BEFORE any measurement.
import os
import sys

WT = ('/private/tmp/claude-501/-Users-pwilson-src-psh/'
      '05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q1/wt')
assert os.getcwd() == WT, f"cwd is {os.getcwd()}, not the worktree"
sys.path.insert(0, WT)
import psh
import psh.version
print("psh.__file__ =", psh.__file__)
print("psh.version.__version__ =", psh.version.__version__)
assert psh.__file__.startswith(WT), psh.__file__
assert psh.version.__version__ == "0.773.0", psh.version.__version__
print("DISCRIMINATOR OK: worktree import, version 0.773.0")
