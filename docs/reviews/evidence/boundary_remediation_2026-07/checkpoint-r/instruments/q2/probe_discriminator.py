#!/usr/bin/env python3
"""Q2 discriminator: assert psh resolves under the worktree and is v0.773.0.

Run with cwd = the Q2 worktree root. Exits nonzero on any mismatch.
"""
import os
import sys

WT = "/private/tmp/claude-501/-Users-pwilson-src-psh/05736dde-f3cd-4b98-98df-9708e107bca4/scratchpad/ckr/q2/wt"

assert os.path.realpath(os.getcwd()) == os.path.realpath(WT), (
    f"cwd is {os.getcwd()}, expected {WT}")

import psh  # noqa: E402
import psh.version  # noqa: E402

resolved = os.path.realpath(psh.__file__)
assert resolved.startswith(os.path.realpath(WT) + os.sep), (
    f"psh.__file__ = {resolved} NOT under worktree {WT}")
assert psh.version.__version__ == "0.773.0", (
    f"version is {psh.version.__version__}, expected 0.773.0")

print(f"DISCRIMINATOR-OK psh.__file__={resolved}")
print(f"DISCRIMINATOR-OK __version__={psh.version.__version__}")
print(f"DISCRIMINATOR-OK python={sys.version.split()[0]}")
