#!/usr/bin/env python3
"""atk-b a00: import discriminator. Run with cwd = worktree root and
PYTHONPATH = worktree root. Asserts BOTH facts before any measurement:
  1. psh.__file__ resolves under the worktree path
  2. psh.version.__version__ == "0.773.0"
Exits nonzero loudly on either failure.
"""
import os
import sys

WT = "/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/atk-b/wt"

import psh  # noqa: E402
import psh.version  # noqa: E402

resolved = os.path.realpath(psh.__file__)
wt_real = os.path.realpath(WT)
print(f"cwd            : {os.getcwd()}")
print(f"psh.__file__   : {resolved}")
print(f"psh.version    : {psh.version.__version__}")
assert resolved.startswith(wt_real + os.sep), f"DISCRIMINATOR FAIL: {resolved} not under {wt_real}"
assert psh.version.__version__ == "0.773.0", f"DISCRIMINATOR FAIL: version {psh.version.__version__}"
print("DISCRIMINATOR OK: worktree import + 0.773.0")
